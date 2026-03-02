"""Tests for SonarrMediaSource adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from new_seasons_reminder.models import SeasonRef
from new_seasons_reminder.sources.sonarr import SonarrMediaSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _recent_ts(days_ago: int = 1) -> str:
    """Return an ISO timestamp from N days ago."""
    return (_now() - timedelta(days=days_ago)).isoformat()


def _make_http(return_value=None, side_effect=None):
    mock = MagicMock()
    if side_effect:
        mock.get_json.side_effect = side_effect
        mock.post_json.side_effect = side_effect
    else:
        mock.get_json.return_value = return_value
        mock.post_json.return_value = return_value
    return mock


def _sonarr_series_item(
    series_id=1,
    title="Test Show",
    tvdb_id=12345,
    tmdb_id=54321,
    added_date=None,
    seasons=None,
):
    """Create a mock Sonarr series item."""
    if added_date is None:
        added_date = (_now() - timedelta(days=100)).isoformat()
    if seasons is None:
        seasons = []
    return {
        "id": series_id,
        "title": title,
        "tvdbId": tvdb_id,
        "tmdbId": tmdb_id,
        "imdbId": "tt1234567",
        "added": added_date,
        "seasons": seasons,
    }


def _sonarr_season_stats(
    season_number=1,
    episode_file_count=10,
    episode_count=10,
    total_episode_count=10,
):
    """Create a mock Sonarr season with statistics."""
    return {
        "seasonNumber": season_number,
        "monitored": True,
        "statistics": {
            "episodeFileCount": episode_file_count,
            "episodeCount": episode_count,
            "totalEpisodeCount": total_episode_count,
            "percentOfEpisodes": (episode_file_count / episode_count * 100)
            if episode_count > 0
            else 0,
        },
    }


def _sonarr_episode(
    episode_id=1,
    series_id=1,
    season_number=1,
    episode_number=1,
    has_file=True,
    date_added=None,
):
    """Create a mock Sonarr episode."""
    if date_added is None:
        date_added = _recent_ts(1)
    ep = {
        "id": episode_id,
        "seriesId": series_id,
        "seasonNumber": season_number,
        "episodeNumber": episode_number,
        "title": f"Episode {episode_number}",
        "hasFile": has_file,
    }
    if has_file:
        ep["episodeFile"] = {
            "id": episode_id * 1000,
            "dateAdded": date_added,
        }
    return ep


# ---------------------------------------------------------------------------
# SonarrMediaSource
# ---------------------------------------------------------------------------


class TestSonarrGetCandidateSeasons:
    def _source(self, http_mock):
        return SonarrMediaSource(
            sonarr_url="http://sonarr:8989",
            sonarr_apikey="test-key",
            http_client=http_mock,
        )

    def test_returns_empty_when_no_series(self):
        since = _now() - timedelta(days=7)
        http = _make_http(return_value=[])
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))
        assert candidates == []

    def test_returns_empty_when_http_error(self):
        since = _now() - timedelta(days=7)
        http = _make_http(side_effect=HTTPError("http://x", 500, "Err", Message(), None))
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))
        assert candidates == []

    def test_returns_candidate_for_complete_season(self):
        since = _now() - timedelta(days=7)
        recent_ts = _recent_ts(1)

        series = [
            _sonarr_series_item(
                series_id=1,
                title="Breaking Bad",
                seasons=[
                    _sonarr_season_stats(
                        season_number=1,
                        episode_file_count=10,
                        episode_count=10,
                    )
                ],
            )
        ]
        episodes = [_sonarr_episode(episode_id=i, date_added=recent_ts) for i in range(1, 11)]

        # First call gets series, second call gets episodes
        http = _make_http(side_effect=[series, episodes])
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))

        assert len(candidates) == 1
        assert candidates[0].season_ref.series_name == "Breaking Bad"
        assert candidates[0].season_ref.season_key.season_number == 1
        assert candidates[0].in_library_episode_count == 10
        assert candidates[0].is_complete_in_source is True

    def test_skips_incomplete_season(self):
        since = _now() - timedelta(days=7)

        series = [
            _sonarr_series_item(
                series_id=1,
                title="Incomplete Show",
                seasons=[
                    _sonarr_season_stats(
                        season_number=1,
                        episode_file_count=5,  # Only 5 of 10
                        episode_count=10,
                    )
                ],
            )
        ]

        http = _make_http(return_value=series)
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))
        assert candidates == []

    def test_skips_season_older_than_since(self):
        since = _now() - timedelta(days=1)  # Only 1 day lookback

        series = [
            _sonarr_series_item(
                series_id=1,
                title="Old Show",
                seasons=[
                    _sonarr_season_stats(
                        season_number=1,
                        episode_file_count=10,
                        episode_count=10,
                    )
                ],
            )
        ]
        # Episode completed 10 days ago
        episodes = [_sonarr_episode(episode_id=i, date_added=_recent_ts(10)) for i in range(1, 11)]

        http = _make_http(side_effect=[series, episodes])
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))
        assert candidates == []

    def test_skips_season_with_no_statistics(self):
        since = _now() - timedelta(days=7)

        series = [
            {
                "id": 1,
                "title": "No Stats Show",
                "added": _recent_ts(100),
                "seasons": [
                    {
                        "seasonNumber": 1,
                        "monitored": True,
                        # No statistics field
                    }
                ],
            }
        ]

        http = _make_http(return_value=series)
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))
        assert candidates == []

    def test_skips_season_with_zero_episodes(self):
        since = _now() - timedelta(days=7)

        series = [
            _sonarr_series_item(
                series_id=1,
                title="Empty Show",
                seasons=[
                    _sonarr_season_stats(
                        season_number=1,
                        episode_file_count=0,
                        episode_count=0,
                    )
                ],
            )
        ]

        http = _make_http(return_value=series)
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))
        assert candidates == []

    def test_handles_multiple_series_and_seasons(self):
        since = _now() - timedelta(days=7)
        recent_ts = _recent_ts(1)

        series = [
            _sonarr_series_item(
                series_id=1,
                title="Show A",
                seasons=[
                    _sonarr_season_stats(1, 10, 10),  # Complete
                    _sonarr_season_stats(2, 5, 10),  # Incomplete
                ],
            ),
            _sonarr_series_item(
                series_id=2,
                title="Show B",
                seasons=[
                    _sonarr_season_stats(1, 8, 8),  # Complete
                ],
            ),
        ]

        # Episodes for both series (Show A and Show B)
        show_a_eps = [
            _sonarr_episode(episode_id=i, series_id=1, date_added=recent_ts) for i in range(1, 11)
        ]
        show_b_eps = [
            _sonarr_episode(episode_id=i, series_id=2, date_added=recent_ts) for i in range(1, 9)
        ]

        http = _make_http(side_effect=[series, show_a_eps, show_b_eps])
        source = self._source(http)

        candidates = list(source.get_candidate_seasons(since))

        # Should only get 2 complete seasons (Show A S1, Show B S1)
        assert len(candidates) == 2
        show_names = {c.season_ref.series_name for c in candidates}
        assert show_names == {"Show A", "Show B"}


class TestSonarrGetShowAddedAt:
    def _source(self, http_mock):
        return SonarrMediaSource(
            sonarr_url="http://sonarr:8989",
            sonarr_apikey="test-key",
            http_client=http_mock,
        )

    def test_returns_datetime_from_iso_string(self):
        date_str = "2025-01-01T12:00:00Z"
        http = _make_http(return_value={"added": date_str})
        source = self._source(http)

        result = source.get_show_added_at("1")
        assert isinstance(result, datetime)

    def test_returns_none_when_no_series(self):
        http = _make_http(return_value=None)
        source = self._source(http)

        result = source.get_show_added_at("999")
        assert result is None

    def test_returns_none_when_no_added_field(self):
        http = _make_http(return_value={"title": "Show"})
        source = self._source(http)

        result = source.get_show_added_at("1")
        assert result is None

    def test_returns_none_on_http_error(self):
        http = _make_http(side_effect=HTTPError("http://x", 404, "Not Found", Message(), None))
        source = self._source(http)

        result = source.get_show_added_at("1")
        assert result is None


class TestSonarrListSeasons:
    def _source(self, http_mock):
        return SonarrMediaSource(
            sonarr_url="http://sonarr:8989",
            sonarr_apikey="test-key",
            http_client=http_mock,
        )

    def test_returns_season_refs(self):
        series = [
            _sonarr_series_item(
                series_id=1,
                title="Show A",
                seasons=[
                    _sonarr_season_stats(1, 10, 10),
                    _sonarr_season_stats(2, 8, 8),
                ],
            )
        ]

        http = _make_http(return_value=series)
        source = self._source(http)

        seasons = list(source.list_seasons())
        assert len(seasons) == 2
        assert all(isinstance(s, SeasonRef) for s in seasons)
        assert seasons[0].series_name == "Show A"

    def test_returns_empty_on_http_error(self):
        http = _make_http(side_effect=HTTPError("http://x", 500, "Err", Message(), None))
        source = self._source(http)

        seasons = list(source.list_seasons())
        assert seasons == []

    def test_skips_season_zero(self):
        """Season 0 (specials) should be skipped."""
        series = [
            _sonarr_series_item(
                series_id=1,
                title="Show A",
                seasons=[
                    _sonarr_season_stats(0, 5, 5),  # Specials
                    _sonarr_season_stats(1, 10, 10),
                ],
            )
        ]

        http = _make_http(return_value=series)
        source = self._source(http)

        seasons = list(source.list_seasons())
        assert len(seasons) == 1
        assert seasons[0].season_key.season_number == 1
