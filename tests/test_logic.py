"""Tests for main logic functions - new show detection, season completion, etc."""

from datetime import datetime, timedelta, timezone
from email.message import Message
from unittest.mock import MagicMock, patch

from new_seasons_reminder.config import Config
from new_seasons_reminder.logic import get_new_finished_seasons, is_new_show, is_season_finished
from new_seasons_reminder.main import send_webhook
from new_seasons_reminder.providers import GenericProvider


class TestIsNewShow:
    """Tests for is_new_show function."""

    def test_existing_show_not_new(self):
        """Test that show added long ago is not considered new."""
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=7)

        # Show was added 1 year ago
        mock_get_metadata = MagicMock(
            return_value={
                "rating_key": "11111",
                "title": "Breaking Bad",
                "added_at": str(
                    int((datetime.now(tz=timezone.utc) - timedelta(days=365)).timestamp())
                ),
            }
        )

        result = is_new_show("11111", cutoff_date, mock_get_metadata)

        assert result is False

    def test_recently_added_show_is_new(self):
        """Test that show added recently is considered new."""
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=7)

        # Show was added 2 days ago
        mock_get_metadata = MagicMock(
            return_value={
                "rating_key": "11111",
                "title": "New Show",
                "added_at": str(
                    int((datetime.now(tz=timezone.utc) - timedelta(days=2)).timestamp())
                ),
            }
        )

        result = is_new_show("11111", cutoff_date, mock_get_metadata)

        assert result is True

    def test_show_added_exactly_at_cutoff(self):
        """Test show added exactly at cutoff date."""
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=7)

        # Use a fixed timestamp that's exactly at the cutoff (rounded to seconds)
        cutoff_timestamp = int(cutoff_date.timestamp())
        mock_get_metadata = MagicMock(
            return_value={
                "rating_key": "11111",
                "title": "Show At Cutoff",
                "added_at": str(cutoff_timestamp),
            }
        )

        # Create cutoff from the same timestamp to ensure exact match
        cutoff_from_ts = datetime.fromtimestamp(cutoff_timestamp, tz=timezone.utc)
        result = is_new_show("11111", cutoff_from_ts, mock_get_metadata)

        # Show at exact cutoff should be considered new (>= comparison)
        assert result is True

    def test_metadata_fetch_failure(self):
        """Test handling when metadata fetch fails."""
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=7)
        mock_get_metadata = MagicMock(return_value=None)

        result = is_new_show("11111", cutoff_date, mock_get_metadata)

        assert result is None

    def test_missing_added_at_field(self):
        """Test handling when added_at field is missing."""
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=7)
        mock_get_metadata = MagicMock(
            return_value={
                "rating_key": "11111",
                "title": "Show Without Date",
                # No added_at field
            }
        )

        result = is_new_show("11111", cutoff_date, mock_get_metadata)

        assert result is None

    def test_invalid_added_at_timestamp(self):
        """Test handling when added_at timestamp is invalid."""
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=7)
        mock_get_metadata = MagicMock(
            return_value={
                "rating_key": "11111",
                "title": "Show With Bad Date",
                "added_at": "invalid_timestamp",
            }
        )

        result = is_new_show("11111", cutoff_date, mock_get_metadata)

        assert result is None


class TestIsSeasonFinished:
    """Tests for is_season_finished function."""

    def test_finished_season_with_episodes(self):
        """Test season with episodes is considered finished."""
        mock_get_children = MagicMock(
            return_value=[
                {"rating_key": "ep1", "media_type": "episode", "title": "Episode 1"},
                {"rating_key": "ep2", "media_type": "episode", "title": "Episode 2"},
                {"rating_key": "ep3", "media_type": "episode", "title": "Episode 3"},
            ]
        )

        result = is_season_finished("12345", mock_get_children)

        assert result is True

    def test_finished_season_with_mixed_media_types(self):
        """Test season with episodes and extras is considered finished."""
        mock_get_children = MagicMock(
            return_value=[
                {"rating_key": "ep1", "media_type": "episode", "title": "Episode 1"},
                {"rating_key": "ep2", "media_type": "episode", "title": "Episode 2"},
                {"rating_key": "extra1", "media_type": "extra", "title": "Bonus"},
            ]
        )

        result = is_season_finished("12345", mock_get_children)

        assert result is True

    def test_empty_season_not_finished(self):
        """Test season with no episodes is not finished."""
        mock_get_children = MagicMock(return_value=[])

        result = is_season_finished("12345", mock_get_children)

        assert result is False

    def test_api_failure_not_finished(self):
        """Test that API failure results in not finished."""
        mock_get_children = MagicMock(return_value=[])

        result = is_season_finished("12345", mock_get_children)

        assert result is False


class TestGetNewFinishedSeasons:
    """Tests for get_new_finished_seasons main function."""

    def test_finds_new_finished_seasons(self):
        """Test successful detection of new finished seasons."""
        now = datetime.now()
        breaking_bad_added_at = str(int((now - timedelta(days=2)).timestamp()))
        office_added_at = str(int((now - timedelta(days=1)).timestamp()))

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 3",
                    "parent_title": "Breaking Bad",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 3,
                    "added_at": breaking_bad_added_at,
                },
                {
                    "rating_key": "67890",
                    "title": "Season 2",
                    "parent_title": "The Office",
                    "parent_rating_key": "22222",
                    "media_type": "season",
                    "media_index": 2,
                    "added_at": office_added_at,
                },
            ]
        )

        mock_is_new_show = MagicMock(return_value=False)  # Not new shows

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "media_type": "season",
                        "rating_key": "12345",
                        "title": "Season 3",
                        "media_index": 3,
                        "added_at": breaking_bad_added_at,
                    }
                ]
            if rating_key == "22222":
                return [
                    {
                        "media_type": "season",
                        "rating_key": "67890",
                        "title": "Season 2",
                        "media_index": 2,
                        "added_at": office_added_at,
                    }
                ]
            if rating_key == "12345":
                return [
                    {"media_type": "episode"},
                    {"media_type": "episode"},
                ]
            if rating_key == "67890":
                return [
                    {"media_type": "episode"},
                    {"media_type": "episode"},
                ]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value="http://example.com/cover.jpg")

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert len(result) == 2
        assert result[0]["show"] == "Breaking Bad"
        assert result[0]["season"] == 3
        assert result[0]["episode_count"] == 2
        assert result[0]["cover_url"] is not None

    def test_no_recently_added_items(self):
        """Test when no recently added items exist."""
        mock_get_recently_added = MagicMock(return_value=[])
        mock_is_new_show = MagicMock(return_value=False)
        mock_get_children = MagicMock(return_value=[])
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert result == []

    def test_skips_non_season_items(self):
        """Test that non-season items are skipped."""
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "movie123",
                    "title": "A Movie",
                    "media_type": "movie",  # Not a season
                    "added_at": str(int((now - timedelta(days=1)).timestamp())),
                },
                {
                    "rating_key": "episode456",
                    "title": "Episode 1",
                    "media_type": "episode",  # Not a season
                    "added_at": str(int((now - timedelta(days=1)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=False)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 3",
                        "media_type": "season",
                        "media_index": 3,
                        "added_at": str(int((now - timedelta(days=30)).timestamp())),
                    }
                ]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert result == []

    def test_skips_items_before_cutoff(self):
        """Test that items before the cutoff date are skipped."""
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 3",
                    "parent_title": "Old Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 3,
                    "added_at": str(int((now - timedelta(days=30)).timestamp())),  # Too old
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=False)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 3",
                        "media_type": "season",
                        "media_index": 3,
                        "added_at": str(int((now - timedelta(days=30)).timestamp())),
                    }
                ]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert result == []

    def test_skips_new_shows(self):
        """Test that new shows (not new seasons) are skipped."""
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 1",  # First season
                    "parent_title": "Brand New Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 1,
                    "added_at": str(int((now - timedelta(days=2)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=True)  # This IS a new show

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 1",
                        "media_type": "season",
                        "media_index": 1,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    }
                ]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert result == []

    def test_skips_unfinished_seasons(self):
        """Test that unfinished seasons are skipped."""
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 3",
                    "parent_title": "Breaking Bad",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 3,
                    "added_at": str(int((now - timedelta(days=2)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=False)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 3",
                        "media_type": "season",
                        "media_index": 3,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    }
                ]
            if rating_key == "12345":
                return []
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert result == []

    def test_handles_missing_added_at(self):
        """Test handling of items without added_at timestamp."""
        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 3",
                    "parent_title": "Test Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 3,
                    # No added_at field
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=False)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 3",
                        "media_type": "season",
                        "media_index": 3,
                    }
                ]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert result == []

    def test_handles_invalid_added_at(self):
        """Test handling of invalid added_at timestamp."""
        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 3",
                    "parent_title": "Test Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 3,
                    "added_at": "invalid_timestamp",
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=False)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 3",
                        "media_type": "season",
                        "media_index": 3,
                        "added_at": "invalid_timestamp",
                    }
                ]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert result == []

    def test_returns_correct_episode_count(self):
        """Test that episode count is calculated correctly."""
        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 3",
                    "parent_title": "Test Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 3,
                    "added_at": str(int((datetime.now() - timedelta(days=2)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=False)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 3",
                        "media_type": "season",
                        "media_index": 3,
                        "added_at": str(int((datetime.now() - timedelta(days=2)).timestamp())),
                    }
                ]
            if rating_key == "12345":
                return [
                    {"media_type": "episode", "title": "Ep 1"},
                    {"media_type": "episode", "title": "Ep 2"},
                    {"media_type": "episode", "title": "Ep 3"},
                    {"media_type": "extra", "title": "Bonus"},  # Not an episode
                ]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
        )

        assert len(result) == 1
        assert result[0]["episode_count"] == 3  # Only 3 episodes counted

    def test_includes_new_show_when_all_seasons_complete(self):
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 1",
                    "parent_title": "Brand New Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 1,
                    "added_at": str(int((now - timedelta(days=2)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=True)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "media_type": "season",
                        "rating_key": "s1",
                        "title": "Season 1",
                        "media_index": 1,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    },
                    {
                        "media_type": "season",
                        "rating_key": "s2",
                        "title": "Season 2",
                        "media_index": 2,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    },
                ]
            if rating_key == "s1":
                return [{"media_type": "episode"}, {"media_type": "episode"}]
            if rating_key == "s2":
                return [{"media_type": "episode"}]
            if rating_key == "12345":
                return [{"media_type": "episode"}, {"media_type": "episode"}]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
            include_new_shows=True,
        )

        assert len(result) == 2
        assert {season["rating_key"] for season in result} == {"s1", "s2"}
        assert {season["season"] for season in result} == {1, 2}
        assert {season["season_title"] for season in result} == {"Season 1", "Season 2"}

    def test_skips_new_show_when_not_all_seasons_complete(self):
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 1",
                    "parent_title": "Incomplete New Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 1,
                    "added_at": str(int((now - timedelta(days=2)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=True)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "media_type": "season",
                        "rating_key": "s1",
                        "title": "Season 1",
                        "media_index": 1,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    },
                    {
                        "media_type": "season",
                        "rating_key": "s2",
                        "title": "Season 2",
                        "media_index": 2,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    },
                ]
            if rating_key == "s1":
                return [{"media_type": "episode"}]
            if rating_key == "s2":
                return []
            return [{"media_type": "episode"}]

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
            include_new_shows=True,
        )

        assert result == []

    def test_skips_new_shows_when_include_disabled(self):
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 1",
                    "parent_title": "Brand New Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 1,
                    "added_at": str(int((now - timedelta(days=2)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=True)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "rating_key": "12345",
                        "title": "Season 1",
                        "media_type": "season",
                        "media_index": 1,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    }
                ]
            return [{"media_type": "episode"}]

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
            include_new_shows=False,
        )

        assert result == []

    def test_new_show_check_cached_across_seasons(self):
        now = datetime.now()

        mock_get_recently_added = MagicMock(
            return_value=[
                {
                    "rating_key": "12345",
                    "title": "Season 1",
                    "parent_title": "Cached Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 1,
                    "added_at": str(int((now - timedelta(days=2)).timestamp())),
                },
                {
                    "rating_key": "67890",
                    "title": "Season 2",
                    "parent_title": "Cached Show",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 2,
                    "added_at": str(int((now - timedelta(days=1)).timestamp())),
                },
            ]
        )
        mock_is_new_show = MagicMock(return_value=True)

        def _get_children_side_effect(rating_key: str) -> list[dict[str, object]]:
            if rating_key == "11111":
                return [
                    {
                        "media_type": "season",
                        "rating_key": "s1",
                        "title": "Season 1",
                        "media_index": 1,
                        "added_at": str(int((now - timedelta(days=2)).timestamp())),
                    },
                    {
                        "media_type": "season",
                        "rating_key": "s2",
                        "title": "Season 2",
                        "media_index": 2,
                        "added_at": str(int((now - timedelta(days=1)).timestamp())),
                    },
                ]
            if rating_key == "s1":
                return [{"media_type": "episode"}]
            if rating_key == "s2":
                return [{"media_type": "episode"}]
            if rating_key in {"12345", "67890"}:
                return [{"media_type": "episode"}]
            return []

        mock_get_children = MagicMock(side_effect=_get_children_side_effect)
        mock_get_cover = MagicMock(return_value=None)

        result = get_new_finished_seasons(
            lookback_days=7,
            get_recently_added_func=mock_get_recently_added,
            is_new_show_func=mock_is_new_show,
            get_show_cover_func=mock_get_cover,
            get_children_func=mock_get_children,
            include_new_shows=True,
        )

        assert len(result) == 2
        assert {season["season"] for season in result} == {1, 2}
        assert {season["rating_key"] for season in result} == {"s1", "s2"}
        show_key_calls = [call_args.args[0] for call_args in mock_get_children.call_args_list]
        assert show_key_calls.count("11111") == 1


class TestSendWebhook:
    """Tests for send_webhook function."""

    @patch("urllib.request.urlopen")
    def test_successful_webhook_send(self, mock_urlopen, sample_seasons, generic_config):
        """Test successful webhook transmission."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        provider = GenericProvider(generic_config)
        config = Config(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test",
            webhook_url="http://example.com/webhook",
        )
        result = send_webhook(sample_seasons, provider, config)

        assert result is True
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_webhook_with_empty_seasons_and_on_empty_false(self, mock_urlopen, generic_config):
        """Test that webhook is skipped when empty and on_empty is False."""
        generic_config["webhook_on_empty"] = False

        provider = GenericProvider(generic_config)
        config = Config(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test",
            webhook_url="http://example.com/webhook",
        )
        result = send_webhook([], provider, config)

        assert result is True  # Returns True but doesn't send
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_webhook_with_empty_seasons_and_on_empty_true(self, mock_urlopen, generic_config):
        """Test that webhook is sent when empty and on_empty is True."""
        generic_config["webhook_on_empty"] = True
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        provider = GenericProvider(generic_config)
        config = Config(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test",
            webhook_url="http://example.com/webhook",
        )
        result = send_webhook([], provider, config)

        assert result is True
        mock_urlopen.assert_called_once()

    def test_webhook_missing_url(self, sample_seasons, generic_config):
        """Test that webhook fails when URL is missing."""
        provider = GenericProvider(generic_config)
        config = Config(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test",
            webhook_url="",  # Missing URL
        )
        result = send_webhook(sample_seasons, provider, config)

        assert result is False

    @patch("urllib.request.urlopen")
    def test_webhook_http_error(self, mock_urlopen, sample_seasons, generic_config):
        """Test handling of HTTP error response."""
        from urllib.error import HTTPError

        headers = Message()

        mock_urlopen.side_effect = HTTPError(
            url="http://test.com",
            code=500,
            msg="Internal Server Error",
            hdrs=headers,
            fp=None,
        )

        provider = GenericProvider(generic_config)
        config = Config(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test",
            webhook_url="http://example.com/webhook",
        )
        result = send_webhook(sample_seasons, provider, config)

        assert result is False

    @patch("urllib.request.urlopen")
    def test_webhook_url_error(self, mock_urlopen, sample_seasons, generic_config):
        """Test handling of URL/connection error."""
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("Connection refused")

        provider = GenericProvider(generic_config)
        config = Config(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test",
            webhook_url="http://example.com/webhook",
        )
        result = send_webhook(sample_seasons, provider, config)

        assert result is False
