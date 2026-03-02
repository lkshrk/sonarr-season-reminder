"""Core logic for season completion detection."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from new_seasons_reminder.sources.base import MediaSource

logger = logging.getLogger(__name__)


def is_new_show(
    series_id: str,
    show_added_at: datetime | None,
    cutoff_date: datetime,
) -> bool | None:
    """Check if a show was recently added (i.e. is "new").

    Args:
        series_id: Source-native series ID
        show_added_at: Datetime when show was first added to library
        cutoff_date: Cutoff date to consider shows as "new"

    Returns:
        True if new, False if existing, None if timestamp unavailable
    """
    if show_added_at is None:
        logger.debug("Show %s missing added_at timestamp", series_id)
        return None

    logger.debug(
        "Show %s added at %s compared to cutoff %s",
        series_id,
        show_added_at,
        cutoff_date,
    )
    try:
        show_date = show_added_at
        logger.debug(
            "Show %s added at %s - this is a %sSHOW",
            series_id,
            show_date,
            "NEW" if show_date >= cutoff_date else "EXISTING",
        )
        return show_date >= cutoff_date
    except (ValueError, TypeError) as e:
        logger.warning(
            "Error parsing added_at for show %s: %s",
            series_id,
            e,
        )
        return None


def get_completed_seasons(
    source: MediaSource,
    since: datetime,
    include_new_shows: bool = False,
) -> list[dict[str, Any]]:
    """Get seasons that are completed.

    This function:
    1. Gets candidate seasons from Sonarr (seasons with all aired episodes downloaded)
    2. Optionally filters out new shows (first added within the since window)

    Args:
        source: Media source adapter (Sonarr)
        since: Only consider seasons completed at or after this datetime
        include_new_shows: If False (default), skip shows first added within the since window

    Returns:
        List of completed seasons with completion details
    """
    logger.debug(
        "Getting completed seasons from %s since %s",
        source.__class__.__name__,
        since,
    )

    # Get candidate seasons from media source
    # Sonarr already filters for complete seasons (episodeFileCount >= episodeCount)
    candidates = source.get_candidate_seasons(since)

    if not candidates:
        logger.info("No candidate seasons found")
        return []

    completed_seasons: list[dict[str, Any]] = []

    for candidate in candidates:
        season_ref = candidate.season_ref
        season_key = season_ref.season_key
        series_id = season_key.series_id
        season_number = season_key.season_number

        logger.debug(
            "Processing %s (S%s) with %d episodes, completed at %s",
            season_ref.series_name,
            season_number,
            candidate.in_library_episode_count,
            candidate.completed_at,
        )

        # Sonarr guarantees completeness via episodeFileCount >= episodeCount
        # No need for external validation

        # Optionally filter out new shows (first added within the since window)
        if not include_new_shows:
            show_added_at = source.get_show_added_at(series_id)
            if is_new_show(series_id, show_added_at, since) is True:
                logger.debug(
                    "Skipping new show: %s (S%s)",
                    season_ref.series_name,
                    season_number,
                )
                continue

        season_dict: dict[str, Any] = {
            "show": season_ref.series_name,
            "season": season_number,
            "season_title": season_ref.season_title,
            "added_at": candidate.completed_at.isoformat(),
            "episode_count": candidate.in_library_episode_count,
            "rating_key": season_ref.season_id,
            "reason": f"Complete: {candidate.in_library_episode_count} episodes in library",
            "expected_count": candidate.in_library_episode_count,
        }
        completed_seasons.append(season_dict)

        logger.info(
            "Completed: %s (S%s) - %s episodes",
            season_ref.series_name,
            season_number,
            candidate.in_library_episode_count,
        )

    logger.info("Found %d completed seasons", len(completed_seasons))
    return completed_seasons
