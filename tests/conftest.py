"""Pytest configuration and fixtures for new_seasons_reminder tests."""

import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Sample test data fixtures


@pytest.fixture
def sample_seasons():
    """Sample season data for testing."""
    return [
        {
            "show": "Breaking Bad",
            "season": 3,
            "season_title": "Season 3",
            "added_at": "2026-01-28T10:30:00",
            "episode_count": 13,
            "rating_key": "12345",
        },
        {
            "show": "The Office",
            "season": 2,
            "season_title": "Season 2",
            "added_at": "2026-01-29T14:20:00",
            "episode_count": 22,
            "rating_key": "67890",
        },
    ]


@pytest.fixture
def empty_seasons():
    """Empty seasons list for testing."""
    return []


@pytest.fixture
def signal_config():
    """Configuration for SignalCliProvider."""
    return {
        "webhook_url": "http://signal-cli:8080/v2/send",
        "webhook_on_empty": False,
        "message_template": "📺 {season_count} new {season_word}",
        "lookback_days": 7,
        "signal_number": "+1234567890",
        "signal_recipients": "+0987654321,+1122334455",
        "signal_text_mode": "styled",
    }


@pytest.fixture
def generic_config():
    """Configuration for GenericProvider."""
    return {
        "webhook_url": "http://example.com/webhook",
        "webhook_on_empty": False,
        "message_template": "Found {season_count} new seasons",
        "payload_template": "default",
        "lookback_days": 7,
    }


@pytest.fixture
def custom_config():
    """Configuration for custom payload template."""
    return {
        "webhook_url": "http://example.com/webhook",
        "webhook_on_empty": True,
        "message_template": "🎬 {season_count} new: {show_list}",
        "webhook_payload_template": (
            '{"custom_msg": {message}, "count": {season_count}, "shows": {show_list}}'
        ),
        "lookback_days": 7,
    }


@pytest.fixture
def mock_sonarr_series_response():
    """Mock Sonarr /api/v3/series response."""
    now = datetime.now(tz=None)
    old_ts = (now - timedelta(days=30)).isoformat()

    return [
        {
            "id": 1,
            "title": "Breaking Bad",
            "tvdbId": 81189,
            "tmdbId": 1396,
            "imdbId": "tt0903747",
            "added": old_ts,
            "seasons": [
                {
                    "seasonNumber": 1,
                    "monitored": True,
                    "statistics": {
                        "episodeFileCount": 7,
                        "episodeCount": 7,
                        "totalEpisodeCount": 7,
                        "percentOfEpisodes": 100.0,
                    },
                },
                {
                    "seasonNumber": 2,
                    "monitored": True,
                    "statistics": {
                        "episodeFileCount": 13,
                        "episodeCount": 13,
                        "totalEpisodeCount": 13,
                        "percentOfEpisodes": 100.0,
                    },
                },
            ],
        },
        {
            "id": 2,
            "title": "Incomplete Show",
            "tvdbId": 12345,
            "added": old_ts,
            "seasons": [
                {
                    "seasonNumber": 1,
                    "monitored": True,
                    "statistics": {
                        "episodeFileCount": 5,
                        "episodeCount": 10,  # Not complete
                        "totalEpisodeCount": 10,
                        "percentOfEpisodes": 50.0,
                    },
                },
            ],
        },
    ]


@pytest.fixture
def mock_sonarr_episodes_response():
    """Mock Sonarr /api/v3/episode response."""
    now = datetime.now(tz=None)
    recent_ts = (now - timedelta(days=1)).isoformat()

    return [
        {
            "id": 101,
            "seriesId": 1,
            "seasonNumber": 1,
            "episodeNumber": 1,
            "title": "Pilot",
            "hasFile": True,
            "episodeFile": {
                "id": 1001,
                "dateAdded": recent_ts,
            },
        },
        {
            "id": 102,
            "seriesId": 1,
            "seasonNumber": 1,
            "episodeNumber": 2,
            "title": "Episode 2",
            "hasFile": True,
            "episodeFile": {
                "id": 1002,
                "dateAdded": recent_ts,
            },
        },
    ]


# Environment setup fixtures


@pytest.fixture
def set_env_vars():
    """Set required environment variables for tests."""
    env_vars = {
        "SONARR_URL": "http://localhost:8989",
        "SONARR_APIKEY": "test-api-key",
        "WEBHOOK_URL": "http://example.com/webhook",
    }

    # Store original values
    original_values = {}
    for key, value in env_vars.items():
        original_values[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original values
    for key, value in original_values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# Mock URL open fixture


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen for API calls."""
    with patch("new_seasons_reminder.urlopen") as mock:
        yield mock


@pytest.fixture
def mock_successful_response():
    """Create a mock successful HTTP response."""
    response = MagicMock()
    response.status = 200
    response.read.return_value = json.dumps({"response": {"result": "success", "data": []}}).encode(
        "utf-8"
    )
    return response
