"""Sonarr media source adapter."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError

from new_seasons_reminder.http import HTTPClient
from new_seasons_reminder.models import CandidateSeason, SeasonKey, SeasonRef
from new_seasons_reminder.sources.base import MediaSource

logger = logging.getLogger(__name__)


class SonarrMediaSource(MediaSource):
    """Sonarr media source adapter.

    Sonarr provides all the data we need for season completion detection:
    - Season statistics (episodeFileCount, episodeCount)
    - Series added timestamp
    - Episode file DateAdded for completion time

    Uses Sonarr API v3.
    """

    def __init__(
        self,
        sonarr_url: str,
        sonarr_apikey: str,
        http_client: HTTPClient | None = None,
    ):
        """Initialize Sonarr media source.

        Args:
            sonarr_url: URL to the Sonarr instance
            sonarr_apikey: Sonarr API key
            http_client: Optional HTTP client (for testing)
        """
        self.sonarr_url = sonarr_url.rstrip("/")
        self.sonarr_apikey = sonarr_apikey
        self._http_client = http_client or HTTPClient()
        self._headers = {"X-Api-Key": sonarr_apikey}

    def get_candidate_seasons(
        self,
        since: datetime,
    ) -> Sequence[CandidateSeason]:
        """Get seasons that became candidates since the given timestamp.

        A season is a candidate when:
        1. episodeFileCount >= episodeCount (all aired episodes downloaded)
        2. episodeCount > 0 (season has started airing)
        3. The last episode file was added >= since timestamp

        Args:
            since: Only return seasons with completed_at >= this timestamp.
                   If naive, assumed to be UTC.

        Returns:
            Sequence of candidate seasons
        """
        # Normalize since to UTC if naive to avoid TypeError in comparisons
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
            logger.debug("Normalized naive since to UTC: %s", since)

        logger.debug("Getting candidate seasons since %s", since)

        # Fetch all series with season statistics
        series_list = self._get_all_series()
        if not series_list:
            logger.warning("No series found in Sonarr")
            return []

        candidates: list[CandidateSeason] = []

        # Batch fetch episodes per series to avoid N+1 API calls
        for series in series_list:
            series_id = series.get("id")
            series_title = series.get("title", "Unknown")
            seasons = series.get("seasons", [])

            # Collect complete seasons for this series
            complete_seasons: list[int] = []
            season_episode_counts: dict[int, int] = {}

            for season in seasons:
                season_number = season.get("seasonNumber", 0)
                statistics = season.get("statistics", {})

                if not statistics:
                    continue

                episode_count = statistics.get("episodeCount", 0)
                episode_file_count = statistics.get("episodeFileCount", 0)

                # Skip specials (season 0)
                if season_number == 0:
                    logger.debug("Skipping special season for %s", series_title)
                    continue

                # Check if season is complete (all aired episodes have files)
                if episode_count == 0:
                    logger.debug(
                        "Season %s S%d has no aired episodes, skipping",
                        series_title,
                        season_number,
                    )
                    continue

                if episode_file_count < episode_count:
                    logger.debug(
                        "Season %s S%d incomplete: %d/%d episodes",
                        series_title,
                        season_number,
                        episode_file_count,
                        episode_count,
                    )
                    continue

                # Season is complete - mark for batch processing
                complete_seasons.append(season_number)
                season_episode_counts[season_number] = episode_file_count

            if not complete_seasons:
                continue

            # Batch fetch all episodes for this series once
            season_completed_times = self._get_series_seasons_completed_at(series_id)

            for season_number in complete_seasons:
                completed_at = season_completed_times.get(season_number)

                if completed_at is None:
                    logger.warning(
                        "Could not determine completion time for %s S%d, skipping",
                        series_title,
                        season_number,
                    )
                    continue

                # Filter by since timestamp
                if completed_at < since:
                    logger.debug(
                        "Season %s S%d completed at %s before since %s, skipping",
                        series_title,
                        season_number,
                        completed_at,
                        since,
                    )
                    continue

                episode_file_count = season_episode_counts[season_number]

                # Create unique season_id per season
                season_key = SeasonKey(
                    source="sonarr",
                    series_id=str(series_id),
                    season_number=season_number,
                )

                season_ref = SeasonRef(
                    season_key=season_key,
                    series_name=series_title,
                    season_title=f"Season {season_number}",
                    season_id=f"{series_id}_S{season_number}",  # Unique per season
                )

                candidate = CandidateSeason(
                    season_ref=season_ref,
                    completed_at=completed_at,
                    in_library_episode_count=episode_file_count,
                    is_complete_in_source=True,  # Sonarr confirms completeness
                )
                candidates.append(candidate)

                logger.info(
                    "Found complete season: %s S%d (%d episodes, completed at %s)",
                    series_title,
                    season_number,
                    episode_file_count,
                    completed_at,
                )

        logger.info("Found %d candidate seasons since %s", len(candidates), since)
        return candidates

    def list_seasons(self) -> Sequence[SeasonRef]:
        """List all seasons available in Sonarr.

        Returns:
            Sequence of all seasons
        """
        logger.debug("Listing all seasons")

        series_list = self._get_all_series()
        if not series_list:
            return []

        season_refs: list[SeasonRef] = []

        for series in series_list:
            series_id = series.get("id")
            series_title = series.get("title", "Unknown")
            seasons = series.get("seasons", [])

            for season in seasons:
                season_number = season.get("seasonNumber", 0)
                if season_number == 0:  # Skip specials
                    continue

                season_key = SeasonKey(
                    source="sonarr",
                    series_id=str(series_id),
                    season_number=season_number,
                )

                season_ref = SeasonRef(
                    season_key=season_key,
                    series_name=series_title,
                    season_title=f"Season {season_number}",
                    season_id=f"{series_id}_S{season_number}",  # Unique per season
                )
                season_refs.append(season_ref)

        logger.debug("Listed %d total seasons", len(season_refs))
        return season_refs

    def get_show_added_at(
        self,
        series_id: str,
    ) -> datetime | None:
        """Get the date when the show was first added to Sonarr.

        Args:
            series_id: Sonarr series ID

        Returns:
            Datetime when show was added, or None if unknown
        """
        logger.debug("Getting show added_at for series_id=%s", series_id)

        series = self._get_series(int(series_id))
        if not series:
            logger.warning("No series found for series_id=%s", series_id)
            return None

        added = series.get("added")
        if not added:
            logger.debug("No added timestamp for series_id=%s", series_id)
            return None

        try:
            # Sonarr returns ISO 8601 format
            if isinstance(added, str):
                return datetime.fromisoformat(added.replace("Z", "+00:00"))
            else:
                logger.warning(
                    "Unexpected added type for series_id=%s: %s",
                    series_id,
                    type(added).__name__,
                )
                return None
        except (ValueError, AttributeError) as e:
            logger.warning(
                "Failed to parse added for series_id=%s: %s - %s",
                series_id,
                added,
                e,
            )
            return None

    def _get_all_series(self) -> list[dict[str, Any]]:
        """Fetch all series from Sonarr.

        Returns:
            List of series dictionaries with seasons and statistics
        """
        url = f"{self.sonarr_url}/api/v3/series"

        try:
            data = self._http_client.get_json(url, headers=self._headers)
            if isinstance(data, list):
                return data
            else:
                logger.warning("Unexpected response from /series: %s", type(data).__name__)
                return []
        except HTTPError as e:
            logger.error("HTTP error fetching series: %s - %s", e.code, e.reason)
            return []
        except URLError as e:
            logger.error("URL error fetching series: %s", e.reason)
            return []
        except (ValueError, KeyError) as e:
            logger.error("Error parsing series response: %s", e)
            return []

    def _get_series(self, series_id: int) -> dict[str, Any] | None:
        """Fetch a single series from Sonarr.

        Args:
            series_id: Sonarr series ID

        Returns:
            Series dictionary or None
        """
        url = f"{self.sonarr_url}/api/v3/series/{series_id}"

        try:
            data = self._http_client.get_json(url, headers=self._headers)
            if isinstance(data, dict):
                return data
            else:
                logger.warning("Unexpected response from /series/%s", series_id)
                return None
        except HTTPError as e:
            logger.error("HTTP error fetching series %s: %s - %s", series_id, e.code, e.reason)
            return None
        except URLError as e:
            logger.error("URL error fetching series %s: %s", series_id, e.reason)
            return None
        except (ValueError, KeyError) as e:
            logger.error("Error parsing series response: %s", e)
            return None

    def _get_series_seasons_completed_at(
        self,
        series_id: int,
    ) -> dict[int, datetime]:
        """Get completion timestamps for all seasons of a series in one API call.

        This batches the episode fetch to avoid N+1 API calls when processing
        multiple seasons of the same series.

        Args:
            series_id: Sonarr series ID

        Returns:
            Dict mapping season_number to max(episodeFile.dateAdded) for that season.
            Seasons with no valid dates are not included.
        """
        url = f"{self.sonarr_url}/api/v3/episode"
        params = {
            "seriesId": series_id,
            "includeEpisodeFile": "true",
        }

        # season_number -> list of completed_at timestamps
        season_times: dict[int, list[datetime]] = defaultdict(list)

        try:
            data = self._http_client.get_json(url, params=params, headers=self._headers)
            if not isinstance(data, list):
                logger.warning(
                    "Unexpected response from /episode for series %s",
                    series_id,
                )
                return {}

            for episode in data:
                episode_file = episode.get("episodeFile", {})
                if not episode_file:
                    continue

                date_added = episode_file.get("dateAdded")
                if not date_added:
                    continue

                season_number = episode.get("seasonNumber", 0)
                if season_number == 0:  # Skip specials
                    continue

                try:
                    if isinstance(date_added, str):
                        parsed_date = datetime.fromisoformat(date_added.replace("Z", "+00:00"))
                        season_times[season_number].append(parsed_date)
                except (ValueError, AttributeError) as e:
                    logger.debug(
                        "Failed to parse dateAdded for episode in series %s: %s - %s",
                        series_id,
                        date_added,
                        e,
                    )
                    continue

            # Compute max date per season
            result: dict[int, datetime] = {}
            for season_number, times in season_times.items():
                if times:
                    result[season_number] = max(times)

            return result

        except HTTPError as e:
            logger.error(
                "HTTP error fetching episodes for series %s: %s - %s",
                series_id,
                e.code,
                e.reason,
            )
            return {}
        except URLError as e:
            logger.error(
                "URL error fetching episodes for series %s: %s",
                series_id,
                e.reason,
            )
            return {}
        except (ValueError, KeyError) as e:
            logger.error("Error parsing episode response: %s", e)
            return {}
