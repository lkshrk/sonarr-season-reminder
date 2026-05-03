"""Tests for the core season completion logic."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from new_seasons_reminder.logic import get_completed_seasons, is_new_show
from new_seasons_reminder.models import CandidateSeason, SeasonKey, SeasonRef

# --- Helpers ---


def _make_candidate(
    series_name: str = "Test Show",
    series_id: str = "1",
    season_number: int = 1,
    episode_count: int = 10,
    completed_at: datetime | None = None,
) -> CandidateSeason:
    """Build a CandidateSeason with sensible defaults."""
    key = SeasonKey(source="sonarr", series_id=series_id, season_number=season_number)
    ref = SeasonRef(
        season_key=key,
        series_name=series_name,
        season_title=f"Season {season_number}",
        season_id=f"{series_id}_S{season_number}",
    )
    return CandidateSeason(
        season_ref=ref,
        completed_at=completed_at or datetime.now(tz=UTC),
        in_library_episode_count=episode_count,
        is_complete_in_source=True,
    )


def _mock_source(
    candidates: list[CandidateSeason] | None = None,
    show_added_at: datetime | None = None,
) -> MagicMock:
    """Build a mock MediaSource."""
    source = MagicMock()
    source.get_candidate_seasons.return_value = candidates or []
    source.get_show_added_at.return_value = show_added_at
    return source


# --- is_new_show ---


class TestIsNewShow:
    def test_new_show_returns_true(self):
        cutoff = datetime(2026, 1, 1, tzinfo=UTC)
        added = datetime(2026, 1, 15, tzinfo=UTC)  # after cutoff
        assert is_new_show("1", added, cutoff) is True

    def test_existing_show_returns_false(self):
        cutoff = datetime(2026, 1, 15, tzinfo=UTC)
        added = datetime(2025, 6, 1, tzinfo=UTC)  # before cutoff
        assert is_new_show("1", added, cutoff) is False

    def test_added_at_equals_cutoff_returns_true(self):
        cutoff = datetime(2026, 1, 1, tzinfo=UTC)
        assert is_new_show("1", cutoff, cutoff) is True

    def test_none_added_at_returns_none(self):
        cutoff = datetime(2026, 1, 1, tzinfo=UTC)
        assert is_new_show("1", None, cutoff) is None


# --- get_completed_seasons ---


class TestGetCompletedSeasons:
    def test_no_candidates_returns_empty(self):
        source = _mock_source(candidates=[])
        since = datetime(2026, 1, 1, tzinfo=UTC)
        result = get_completed_seasons(source, since)
        assert result == []

    def test_returns_completed_seasons_as_dicts(self):
        candidate = _make_candidate(
            series_name="Breaking Bad",
            series_id="42",
            season_number=3,
            episode_count=13,
        )
        # Show added long ago → not a new show
        old_date = datetime(2020, 1, 1, tzinfo=UTC)
        source = _mock_source(candidates=[candidate], show_added_at=old_date)
        since = datetime(2026, 1, 1, tzinfo=UTC)

        result = get_completed_seasons(source, since)

        assert len(result) == 1
        assert result[0]["show"] == "Breaking Bad"
        assert result[0]["season"] == 3
        assert result[0]["episode_count"] == 13

    def test_includes_new_shows_by_default(self):
        since = datetime(2026, 1, 1, tzinfo=UTC)
        candidate = _make_candidate(series_name="New Show", series_id="5")
        new_date = datetime(2026, 1, 10, tzinfo=UTC)
        source = _mock_source(candidates=[candidate], show_added_at=new_date)

        result = get_completed_seasons(source, since)

        assert len(result) == 1
        assert result[0]["show"] == "New Show"

    def test_filters_out_new_shows_when_flag_disabled(self):
        since = datetime(2026, 1, 1, tzinfo=UTC)
        candidate = _make_candidate(series_name="New Show", series_id="5")
        # Show added after since → is_new_show returns True → filtered out
        new_date = datetime(2026, 1, 10, tzinfo=UTC)
        source = _mock_source(candidates=[candidate], show_added_at=new_date)

        result = get_completed_seasons(source, since, include_new_shows=False)

        assert result == []

    def test_includes_new_shows_when_flag_set(self):
        since = datetime(2026, 1, 1, tzinfo=UTC)
        candidate = _make_candidate(series_name="New Show", series_id="5")
        new_date = datetime(2026, 1, 10, tzinfo=UTC)
        source = _mock_source(candidates=[candidate], show_added_at=new_date)

        result = get_completed_seasons(source, since, include_new_shows=True)

        assert len(result) == 1
        assert result[0]["show"] == "New Show"

    def test_keeps_existing_show_when_filtering(self):
        since = datetime(2026, 1, 1, tzinfo=UTC)
        candidate = _make_candidate(series_name="Old Show", series_id="7")
        # Show added before since → existing → kept
        old_date = datetime(2025, 1, 1, tzinfo=UTC)
        source = _mock_source(candidates=[candidate], show_added_at=old_date)

        result = get_completed_seasons(source, since, include_new_shows=False)

        assert len(result) == 1

    def test_multiple_candidates_mixed_filtering(self):
        since = datetime(2026, 1, 1, tzinfo=UTC)
        old_candidate = _make_candidate(series_name="Old Show", series_id="1")
        new_candidate = _make_candidate(series_name="New Show", series_id="2")

        source = MagicMock()
        source.get_candidate_seasons.return_value = [old_candidate, new_candidate]
        # Return different added_at per series_id
        source.get_show_added_at.side_effect = lambda sid: (
            datetime(2025, 1, 1, tzinfo=UTC) if sid == "1" else datetime(2026, 2, 1, tzinfo=UTC)
        )

        result = get_completed_seasons(source, since, include_new_shows=False)

        assert len(result) == 1
        assert result[0]["show"] == "Old Show"

    def test_show_with_none_added_at_is_kept(self):
        """If get_show_added_at returns None, is_new_show returns None (not True), so kept."""
        since = datetime(2026, 1, 1, tzinfo=UTC)
        candidate = _make_candidate(series_name="Unknown Date Show")
        source = _mock_source(candidates=[candidate], show_added_at=None)

        result = get_completed_seasons(source, since, include_new_shows=False)

        assert len(result) == 1
        assert result[0]["show"] == "Unknown Date Show"


# --- CandidateSeason.to_dict ---


class TestCandidateSeasonToDict:
    def test_to_dict_keys(self):
        ts = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
        candidate = _make_candidate(
            series_name="Test",
            series_id="10",
            season_number=2,
            episode_count=8,
            completed_at=ts,
        )
        d = candidate.to_dict()
        assert d == {
            "show": "Test",
            "season": 2,
            "season_title": "Season 2",
            "added_at": ts.isoformat(),
            "episode_count": 8,
            "rating_key": "10_S2",
            "reason": "Complete: 8 episodes in library",
            "expected_count": 8,
        }
