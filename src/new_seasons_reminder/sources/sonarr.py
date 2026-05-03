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

_IMPORT_HISTORY_EVENTS = {
    "downloadFolderImported",
    "seriesFolderImported",
    2,  # seriesFolderImported in generated Sonarr API enums
    3,  # downloadFolderImported in generated Sonarr API enums
}


class SonarrMediaSource(MediaSource):
    """Sonarr media source adapter.

    Sonarr provides all the data we need for season completion detection:
    - Episode aired timestamps
    - Episode file import timestamps
    - Series added timestamp
    - Optional history data for original import timestamps

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
        1. All known regular episodes have aired
        2. All known regular episodes have files
        3. The season became both finished and available >= since timestamp

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
            if not isinstance(series_id, int):
                continue
            series_title = series.get("title", "Unknown")
            series_added_at = self._parse_datetime(series.get("added"))

            episodes_by_season = self._get_series_episodes_by_season(series_id)
            if not episodes_by_season:
                continue

            first_imported_at_by_episode: dict[int, datetime] | None = None

            for season_number, episodes in episodes_by_season.items():
                season_state = self._get_finished_available_state(
                    series_title=series_title,
                    season_number=season_number,
                    episodes=episodes,
                )
                if season_state is None:
                    continue

                completed_at, episode_count, latest_air_at, latest_file_at = season_state

                if latest_air_at is not None and latest_air_at < since and latest_file_at >= since:
                    if first_imported_at_by_episode is None:
                        first_imported_at_by_episode = self._get_series_episode_first_imported_at(
                            series_id
                        )
                    history_completed_at = self._get_history_based_completed_at(
                        episodes=episodes,
                        latest_air_at=latest_air_at,
                        fallback_completed_at=completed_at,
                        first_imported_at_by_episode=first_imported_at_by_episode,
                    )
                    if history_completed_at is not None:
                        completed_at = history_completed_at

                newly_added_at = (
                    series_added_at
                    if series_added_at is not None and series_added_at >= since
                    else None
                )
                if completed_at < since and newly_added_at is None:
                    logger.debug(
                        "Season %s S%d became complete at %s before since %s, skipping",
                        series_title,
                        season_number,
                        completed_at,
                        since,
                    )
                    continue
                if newly_added_at is not None and completed_at < newly_added_at:
                    completed_at = newly_added_at

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
                    in_library_episode_count=episode_count,
                    is_complete_in_source=True,  # Sonarr confirms completeness
                )
                candidates.append(candidate)

                logger.info(
                    "Found complete season: %s S%d (%d episodes, completed at %s)",
                    series_title,
                    season_number,
                    episode_count,
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

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Parse a Sonarr timestamp into a timezone-aware datetime."""
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _get_series_episodes_by_season(
        self,
        series_id: int,
    ) -> dict[int, list[dict[str, Any]]]:
        """Fetch and group all regular episodes for a series by season."""
        url = f"{self.sonarr_url}/api/v3/episode"
        params = {
            "seriesId": str(series_id),
            "includeEpisodeFile": "true",
        }

        try:
            data = self._http_client.get_json(url, params=params, headers=self._headers)
            if not isinstance(data, list):
                logger.warning(
                    "Unexpected response from /episode for series %s",
                    series_id,
                )
                return {}

            episodes_by_season: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for episode in data:
                if not isinstance(episode, dict):
                    continue
                season_number = episode.get("seasonNumber", 0)
                if not isinstance(season_number, int) or season_number == 0:
                    continue
                episodes_by_season[season_number].append(episode)

            return dict(episodes_by_season)

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

    def _get_finished_available_state(
        self,
        series_title: str,
        season_number: int,
        episodes: list[dict[str, Any]],
    ) -> tuple[datetime, int, datetime | None, datetime] | None:
        """Return completion state when every known episode is aired and available."""
        now = datetime.now(tz=UTC)
        air_dates: list[datetime] = []
        file_dates: list[datetime] = []

        if not episodes:
            return None

        for episode in episodes:
            air_date = self._parse_datetime(episode.get("airDateUtc"))
            if air_date is not None:
                if air_date > now:
                    logger.debug(
                        "Season %s S%d still airing: episode %s airs at %s",
                        series_title,
                        season_number,
                        episode.get("episodeNumber", "?"),
                        air_date,
                    )
                    return None
                air_dates.append(air_date)

            episode_file = episode.get("episodeFile", {})
            if not episode.get("hasFile") or not isinstance(episode_file, dict):
                logger.debug(
                    "Season %s S%d unavailable: episode %s has no file",
                    series_title,
                    season_number,
                    episode.get("episodeNumber", "?"),
                )
                return None

            file_date = self._parse_datetime(episode_file.get("dateAdded"))
            if file_date is None:
                logger.warning(
                    "Could not determine file import time for %s S%d episode %s",
                    series_title,
                    season_number,
                    episode.get("episodeNumber", "?"),
                )
                return None
            file_dates.append(file_date)

        if not file_dates:
            return None

        latest_air_at = max(air_dates) if air_dates else None
        latest_file_at = max(file_dates)
        completed_at = max(latest_air_at, latest_file_at) if latest_air_at else latest_file_at
        return completed_at, len(episodes), latest_air_at, latest_file_at

    def _get_history_based_completed_at(
        self,
        episodes: list[dict[str, Any]],
        latest_air_at: datetime,
        fallback_completed_at: datetime,
        first_imported_at_by_episode: dict[int, datetime],
    ) -> datetime | None:
        """Use first import history so upgrades do not make old seasons look new."""
        first_import_dates: list[datetime] = []
        for episode in episodes:
            episode_id = episode.get("id")
            if isinstance(episode_id, int):
                first_imported_at = first_imported_at_by_episode.get(episode_id)
                if first_imported_at is not None:
                    first_import_dates.append(first_imported_at)
                    continue

            episode_file = episode.get("episodeFile", {})
            if isinstance(episode_file, dict):
                file_date = self._parse_datetime(episode_file.get("dateAdded"))
                if file_date is not None:
                    first_import_dates.append(file_date)

        if len(first_import_dates) != len(episodes):
            return fallback_completed_at

        first_available_at = max(first_import_dates)
        return max(latest_air_at, first_available_at)

    def _get_series_episode_first_imported_at(
        self,
        series_id: int,
    ) -> dict[int, datetime]:
        """Fetch earliest import history for each episode in a series."""
        url = f"{self.sonarr_url}/api/v3/history"
        page = 1
        page_size = 1000
        result: dict[int, datetime] = {}

        while True:
            params = {
                "page": str(page),
                "pageSize": str(page_size),
                "sortKey": "date",
                "sortDirection": "ascending",
                "includeSeries": "false",
                "includeEpisode": "false",
                "seriesIds": str(series_id),
            }

            try:
                data = self._http_client.get_json(url, params=params, headers=self._headers)
            except HTTPError as e:
                logger.warning(
                    "HTTP error fetching history for series %s: %s - %s",
                    series_id,
                    e.code,
                    e.reason,
                )
                return result
            except URLError as e:
                logger.warning(
                    "URL error fetching history for series %s: %s",
                    series_id,
                    e.reason,
                )
                return result
            except (ValueError, KeyError) as e:
                logger.warning("Error parsing history response for series %s: %s", series_id, e)
                return result

            if not isinstance(data, dict):
                logger.warning("Unexpected response from /history for series %s", series_id)
                return result

            records = data.get("records", [])
            if not isinstance(records, list) or not records:
                return result

            for record in records:
                if not isinstance(record, dict):
                    continue
                if record.get("eventType") not in _IMPORT_HISTORY_EVENTS:
                    continue

                imported_at = self._parse_datetime(record.get("date"))
                if imported_at is None:
                    continue

                for episode_id in self._get_history_episode_ids(record):
                    current = result.get(episode_id)
                    if current is None or imported_at < current:
                        result[episode_id] = imported_at

            total_records = data.get("totalRecords")
            if not isinstance(total_records, int) or page * page_size >= total_records:
                return result
            page += 1

    @staticmethod
    def _get_history_episode_ids(record: dict[str, Any]) -> list[int]:
        """Extract episode ids from Sonarr history records across API variants."""
        episode_ids: list[int] = []
        episode_id = record.get("episodeId")
        if isinstance(episode_id, int):
            episode_ids.append(episode_id)

        raw_episode_ids = record.get("episodeIds")
        if isinstance(raw_episode_ids, list):
            episode_ids.extend(i for i in raw_episode_ids if isinstance(i, int))

        episode = record.get("episode")
        if isinstance(episode, dict):
            nested_episode_id = episode.get("id")
            if isinstance(nested_episode_id, int):
                episode_ids.append(nested_episode_id)

        return list(dict.fromkeys(episode_ids))
