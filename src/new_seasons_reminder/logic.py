import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def is_new_show(
    show_rating_key: str,
    cutoff_date: datetime,
    get_metadata_func: Callable[[str], dict | None],
) -> bool:
    logger.debug(f"Checking if show {show_rating_key} is new")
    show_metadata = get_metadata_func(show_rating_key)
    if not show_metadata:
        logger.warning(f"Could not get metadata for show {show_rating_key}")
        return False

    show_added_at = show_metadata.get("added_at")
    if not show_added_at:
        logger.debug(f"Show {show_rating_key} missing added_at timestamp")
        return False

    try:
        show_date = datetime.fromtimestamp(int(show_added_at), tz=timezone.utc)
        logger.debug(
            f"Show {show_rating_key} added at {show_date} compared to cutoff {cutoff_date}"
        )
        if show_date >= cutoff_date:
            logger.debug(f"Show added at {show_date} - this is a NEW SHOW")
            return True
        logger.debug(f"Show added at {show_date} - existing show")
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parsing added_at for show: {e}")

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


def _are_all_seasons_complete(
    show_rating_key: str,
    get_children_func: Callable[[str], list[dict]],
) -> bool:
    logger.debug("Checking if all seasons of show %s are complete", show_rating_key)
    seasons = get_children_func(show_rating_key)
    if not seasons:
        logger.debug("Show %s has no seasons", show_rating_key)
        return False

    season_items = [s for s in seasons if s.get("media_type") == "season"]
    if not season_items:
        logger.debug("Show %s has no season-type children", show_rating_key)
        return False

    for season in season_items:
        season_key = season.get("rating_key")
        if not season_key:
            continue
        episodes = get_children_func(str(season_key))
        episode_count = sum(1 for ep in episodes if ep.get("media_type") == "episode")
        if episode_count == 0:
            logger.debug(
                "Show %s season %s has no episodes — show is NOT complete",
                show_rating_key,
                season.get("title", season_key),
            )
            return False

    logger.debug("Show %s: all %d seasons have episodes", show_rating_key, len(season_items))
    return True


def get_new_finished_seasons(
    lookback_days: int,
    get_recently_added_func: Callable[[str, int], list[dict]],
    is_new_show_func: Callable[[str, datetime], bool],
    get_show_cover_func: Callable[[str], str | None],
    get_children_func: Callable[[str], list[dict]],
    include_new_shows: bool = False,
) -> list[dict[str, Any]]:
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
    logger.info("Looking for seasons added in last %s days since %s", lookback_days, cutoff_date)
    logger.info("Include new shows: %s", include_new_shows)

    recently_added = get_recently_added_func("show", 100)
    logger.debug("Recently added raw items count: %s", len(recently_added))
    for item in recently_added:
        logger.debug(
            "Recently added item: rating_key=%s title=%s media_type=%s added_at=%s",
            item.get("rating_key"),
            item.get("title"),
            item.get("media_type"),
            item.get("added_at"),
        )
    if not recently_added:
        logger.info("No recently added items found")
        return []

    new_seasons = []
    show_complete_cache: dict[str, bool] = {}

    for item in recently_added:
        media_type = item.get("media_type")
        if media_type != "season":
            logger.debug(
                "Skipping item %s (%s) - media_type=%s",
                item.get("title"),
                item.get("rating_key"),
                media_type,
            )
            continue

        rating_key = item.get("rating_key")
        title = item.get("title", "Unknown")
        parent_title = item.get("parent_title", "Unknown")
        show_rating_key = item.get("parent_rating_key")
        season_index = item.get("media_index", 0)
        added_at_timestamp = item.get("added_at")

        if not added_at_timestamp:
            logger.debug(f"Skipping {title} - no added_at timestamp")
            continue

        try:
            added_at = datetime.fromtimestamp(int(added_at_timestamp), tz=timezone.utc)
            logger.debug(
                "Parsed added_at for %s (%s): %s",
                title,
                rating_key,
                added_at,
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing added_at for {title}: {e}")
            continue

        if added_at < cutoff_date:
            logger.debug(f"Skipping {title} - added at {added_at} (before cutoff)")
            continue

        logger.info(f"Processing: {parent_title} - Season {season_index} (added {added_at})")

        if not show_rating_key:
            logger.debug(f"Skipping {title} - no parent_rating_key (show key)")
            continue

        is_new_show_result = is_new_show_func(str(show_rating_key), cutoff_date)
        logger.debug(
            "Show %s new show check result: %s",
            show_rating_key,
            is_new_show_result,
        )
        if is_new_show_result:
            if not include_new_shows:
                logger.info(f"Skipping {parent_title} - this is a NEW SHOW, not a new season")
                continue
            if show_rating_key not in show_complete_cache:
                show_complete_cache[show_rating_key] = _are_all_seasons_complete(
                    str(show_rating_key), get_children_func
                )
            if not show_complete_cache[show_rating_key]:
                logger.info(f"Skipping new show {parent_title} - not all seasons have episodes")
                continue
            logger.info(f"Including new show {parent_title} - all seasons have episodes")

        if not rating_key:
            logger.debug(f"Skipping {title} - no rating_key")
            continue

        episodes = get_children_func(str(rating_key))
        episode_count = len([ep for ep in episodes if ep.get("media_type") == "episode"])

        if episode_count == 0:
            logger.info(f"Skipping {parent_title} Season {season_index} - season not finished")
            continue

        cover_url = get_show_cover_func(str(show_rating_key))
        logger.info(
            "Accepted season: %s Season %s with %s episodes",
            parent_title,
            season_index,
            episode_count,
        )

        new_seasons.append(
            {
                "show": parent_title,
                "season": season_index,
                "season_title": title,
                "added_at": added_at.isoformat(),
                "episode_count": episode_count,
                "rating_key": rating_key,
                "cover_url": cover_url,
            }
        )

    return new_seasons
