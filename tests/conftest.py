"""Pytest configuration and fixtures for new_seasons_reminder tests."""

import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


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
            "cover_url": "http://localhost:32400/library/metadata/12345/thumb/1234567890",
        },
        {
            "show": "The Office",
            "season": 2,
            "season_title": "Season 2",
            "added_at": "2026-01-29T14:20:00",
            "episode_count": 22,
            "rating_key": "67890",
            "cover_url": None,
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
        "message_template": "📺 {season_count} new season(s)",
        "lookback_days": 7,
        "signal_number": "+1234567890",
        "signal_recipients": "+0987654321,+1122334455",
        "signal_text_mode": "styled",
        "signal_include_covers": False,
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
def mock_tautulli_response():
    """Mock Tautulli API response."""
    return {
        "response": {
            "result": "success",
            "data": [
                {
                    "rating_key": "12345",
                    "title": "Season 3",
                    "parent_title": "Breaking Bad",
                    "parent_rating_key": "11111",
                    "media_type": "season",
                    "media_index": 3,
                    "added_at": str(int((datetime.now() - timedelta(days=2)).timestamp())),
                },
                {
                    "rating_key": "67890",
                    "title": "Season 2",
                    "parent_title": "The Office",
                    "parent_rating_key": "22222",
                    "media_type": "season",
                    "media_index": 2,
                    "added_at": str(int((datetime.now() - timedelta(days=1)).timestamp())),
                },
            ],
        }
    }


@pytest.fixture
def mock_show_metadata():
    """Mock show metadata from Tautulli."""
    return {
        "rating_key": "11111",
        "title": "Breaking Bad",
        "added_at": str(int((datetime.now() - timedelta(days=365)).timestamp())),
        "thumb": "/library/metadata/11111/thumb/1234567890",
    }


@pytest.fixture
def mock_seasons_data():
    """Mock seasons children data."""
    return [
        {
            "rating_key": "11111_s1",
            "title": "Season 1",
            "index": 1,
            "added_at": str(int((datetime.now() - timedelta(days=365)).timestamp())),
        },
        {
            "rating_key": "11111_s2",
            "title": "Season 2",
            "index": 2,
            "added_at": str(int((datetime.now() - timedelta(days=200)).timestamp())),
        },
        {
            "rating_key": "12345",
            "title": "Season 3",
            "index": 3,
            "added_at": str(int((datetime.now() - timedelta(days=2)).timestamp())),
        },
    ]


@pytest.fixture
def mock_episodes_data():
    """Mock episodes children data."""
    return [
        {"rating_key": "ep1", "media_type": "episode", "title": "Episode 1"},
        {"rating_key": "ep2", "media_type": "episode", "title": "Episode 2"},
        {"rating_key": "ep3", "media_type": "episode", "title": "Episode 3"},
    ]


@pytest.fixture
def mock_image_data():
    """Mock image data for base64 encoding tests."""
    return b"fake_image_data_for_testing"


# Environment setup fixtures


@pytest.fixture
def set_env_vars():
    """Set required environment variables for tests."""
    env_vars = {
        "TAUTULLI_URL": "http://localhost:8181",
        "TAUTULLI_APIKEY": "test-api-key",
        "WEBHOOK_URL": "http://example.com/webhook",
        "PLEX_URL": "http://localhost:32400",
        "PLEX_TOKEN": "test-plex-token",
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
