import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def is_new_show(
    show_rating_key: str,
    cutoff_date: datetime,
    get_metadata_func: Callable[[str], dict | None],
) -> bool | None:
    """Check if a show was recently added (i.e. is "new").

    Returns True if new, False if existing, None if metadata lookup failed.
    """
    logger.debug("Checking if show %s is new", show_rating_key)
    show_metadata = get_metadata_func(show_rating_key)
    if not show_metadata:
        logger.warning("Could not get metadata for show %s", show_rating_key)
        return None

    show_added_at = show_metadata.get("added_at")
    if not show_added_at:
        logger.debug("Show %s missing added_at timestamp", show_rating_key)
        return None

    try:
        show_date = datetime.fromtimestamp(int(show_added_at), tz=timezone.utc)
        logger.debug(
            "Show %s added at %s compared to cutoff %s",
            show_rating_key,
            show_date,
            cutoff_date,
        )
        if show_date >= cutoff_date:
            logger.debug("Show added at %s - this is a NEW SHOW", show_date)
            return True
        logger.debug("Show added at %s - existing show", show_date)
    except (ValueError, TypeError) as e:
        logger.warning("Error parsing added_at for show %s: %s", show_rating_key, e)
        return None

    return False


def is_season_finished(
    season_rating_key: str,
    get_children_func: Callable[[str], list[dict]],
) -> bool:
    logger.debug(f"Checking if season {season_rating_key} is finished")
    episodes = get_children_func(season_rating_key)
    logger.debug(f"Season {season_rating_key} children returned: {len(episodes)}")
    if not episodes:
        logger.debug(f"Season {season_rating_key} has no children")
        return False

    total_children = len(episodes)
    episode_children = [ep for ep in episodes if ep.get("media_type") == "episode"]
    available_episodes = sum(1 for ep in episode_children if ep.get("rating_key"))
    non_episode_children = total_children - len(episode_children)

    logger.debug(
        "Season %s children breakdown: %s total, %s episodes, %s non-episodes",
        season_rating_key,
        total_children,
        len(episode_children),
        non_episode_children,
    )
    logger.debug(
        f"Season {season_rating_key}: {available_episodes}/{len(episode_children)} episodes available"
    )
    return available_episodes > 0


def get_new_finished_seasons(
    lookback_days: int,
    get_recently_added_func: Callable[[str, int], list[dict]],
    is_new_show_func: Callable[[str, datetime], bool | None],
    get_show_cover_func: Callable[[str], str | None],
    get_children_func: Callable[[str], list[dict]],
    include_new_shows: bool = False,
) -> list[dict[str, Any]]:
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
    logger.info("Looking for seasons added in last %s days since %s", lookback_days, cutoff_date)
    logger.info("Include new shows: %s", include_new_shows)

    recently_added = get_recently_added_func("show", 100)
    logger.debug("Recently added raw items count: %s", len(recently_added))
    if not recently_added:
        logger.info("No recently added items found")
        return []

    # Phase 1: Discover unique shows with recent activity
    discovered_shows: dict[str, str] = {}
    for item in recently_added:
        mt = item.get("media_type")
        show_key: str | None = None
        show_name = "Unknown"
        if mt == "show":
            show_key = item.get("rating_key")
            show_name = item.get("title", "Unknown")
        elif mt == "season":
            show_key = item.get("parent_rating_key")
            show_name = item.get("parent_title", "Unknown")
        elif mt == "episode":
            show_key = item.get("grandparent_rating_key")
            show_name = item.get("grandparent_title", "Unknown")
        if show_key and show_key not in discovered_shows:
            discovered_shows[show_key] = show_name
            logger.debug("Discovered show: %s (key=%s) from %s item", show_name, show_key, mt)
    logger.info("Discovered %d unique show(s) with recent activity", len(discovered_shows))

    # Phase 2: Enumerate ALL seasons per show, filter and collect
    new_seasons = []
    is_new_cache: dict[str, bool] = {}
    episode_cache: dict[str, int] = {}

    for show_key, show_name in discovered_shows.items():
        logger.debug("Enumerating seasons for show: %s (key=%s)", show_name, show_key)
        all_children = get_children_func(str(show_key))
        season_items = [s for s in all_children if s.get("media_type") == "season"]
        logger.debug("Show %s has %d season(s)", show_name, len(season_items))

        if not season_items:
            continue

        # is_new_show check (once per show)
        if show_key not in is_new_cache:
            is_new = is_new_show_func(str(show_key), cutoff_date)
            if is_new is None:
                logger.warning(
                    "Could not determine if %s (show_key=%s) is new — assuming existing show",
                    show_name,
                    show_key,
                )
                is_new = False
            is_new_cache[show_key] = is_new

        if is_new_cache[show_key]:
            if not include_new_shows:
                logger.info("Skipping %s - this is a NEW SHOW, not a new season", show_name)
                continue

            # Check ALL seasons have episodes before including any
            all_complete = True
            for s in season_items:
                s_key = s.get("rating_key")
                if not s_key:
                    continue
                if s_key not in episode_cache:
                    eps = get_children_func(str(s_key))
                    episode_cache[s_key] = len([e for e in eps if e.get("media_type") == "episode"])
                if episode_cache[s_key] == 0:
                    all_complete = False
                    logger.info(
                        "Skipping new show %s - %s has no episodes",
                        show_name,
                        s.get("title", s_key),
                    )
                    break

            if not all_complete:
                continue
            logger.info(
                "Including new show %s - all %d seasons have episodes", show_name, len(season_items)
            )

        # Process individual seasons
        for season in season_items:
            rating_key = season.get("rating_key")
            title = season.get("title", "Unknown")
            season_index = season.get("media_index", 0)
            added_at_ts = season.get("added_at")

            if not added_at_ts:
                logger.debug("Skipping %s %s - no added_at timestamp", show_name, title)
                continue

            try:
                added_at = datetime.fromtimestamp(int(added_at_ts), tz=timezone.utc)
            except (ValueError, TypeError) as e:
                logger.warning("Error parsing added_at for %s %s: %s", show_name, title, e)
                continue

            if added_at < cutoff_date:
                logger.debug(
                    "Skipping %s %s - added at %s (before cutoff)", show_name, title, added_at
                )
                continue

            logger.info("Processing: %s - %s (added %s)", show_name, title, added_at)

            if not rating_key:
                logger.debug("Skipping %s %s - no rating_key", show_name, title)
                continue

            if rating_key not in episode_cache:
                episodes = get_children_func(str(rating_key))
                episode_cache[rating_key] = len(
                    [ep for ep in episodes if ep.get("media_type") == "episode"]
                )

            episode_count = episode_cache[rating_key]
            if episode_count == 0:
                logger.info("Skipping %s %s - no episodes", show_name, title)
                continue

            cover_url = get_show_cover_func(str(show_key))
            logger.info("Accepted season: %s %s with %d episodes", show_name, title, episode_count)

            new_seasons.append(
                {
                    "show": show_name,
                    "season": season_index,
                    "season_title": title,
                    "added_at": added_at.isoformat(),
                    "episode_count": episode_count,
                    "rating_key": rating_key,
                    "cover_url": cover_url,
                }
            )

    return new_seasons
