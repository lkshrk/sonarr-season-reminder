"""Tests for Tautulli API integration and data fetching functions."""

import os
import sys

import importlib
import json
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

api = importlib.import_module("new_seasons_reminder.api")
get_cover_url = api.get_cover_url
get_show_cover = api.get_show_cover


class TestMakeTautulliRequest:
    """Tests for the make_tautulli_request function."""

    @patch("new_seasons_reminder.api.urlopen")
    def test_successful_request(self, mock_urlopen):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"response": {"result": "success", "data": [{"test": "data"}]}}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = api.make_tautulli_request(
            "get_recently_added",
            {"count": 10},
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is not None
        assert result[0]["test"] == "data"

    @patch("new_seasons_reminder.api.urlopen")
    def test_api_error_response(self, mock_urlopen):
        """Test handling of API error response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"response": {"result": "error", "message": "Invalid command"}}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = api.make_tautulli_request(
            "invalid_cmd",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None

    def test_missing_config(self):
        """Test handling when Tautulli config is missing."""
        result = api.make_tautulli_request(
            "get_recently_added",
            tautulli_url="",
            tautulli_apikey="",
        )
        assert result is None

    @patch("new_seasons_reminder.api.urlopen")
    def test_http_error(self, mock_urlopen):
        """Test handling of HTTP error."""
        mock_urlopen.side_effect = HTTPError(
            url="http://test.com",
            code=404,
            msg="Not Found",
            hdrs=Message(),
            fp=None,
        )

        result = api.make_tautulli_request(
            "get_recently_added",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None

    @patch("new_seasons_reminder.api.urlopen")
    def test_url_error(self, mock_urlopen):
        """Test handling of URL error (connection failure)."""
        mock_urlopen.side_effect = URLError("Connection refused")

        result = api.make_tautulli_request(
            "get_recently_added",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None

    @patch("new_seasons_reminder.api.urlopen")
    def test_json_decode_error(self, mock_urlopen):
        """Test handling of invalid JSON response."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"invalid json"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = api.make_tautulli_request(
            "get_recently_added",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None

    @patch("new_seasons_reminder.api.urlopen")
    def test_unexpected_exception(self, mock_urlopen):
        """Test handling of unexpected exceptions."""
        mock_urlopen.side_effect = Exception("Unexpected error")

        result = api.make_tautulli_request(
            "get_recently_added",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None


class TestGetRecentlyAdded:
    """Tests for get_recently_added function."""

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_recently_added_success(self, mock_request, mock_tautulli_response):
        """Test successful fetch of recently added items."""
        mock_request.return_value = {"recently_added": mock_tautulli_response["response"]["data"]}

        result = api.get_recently_added(
            media_type="season",
            count=10,
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert len(result) == 2
        assert result[0]["media_type"] == "season"

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_recently_added_list_response(self, mock_request, mock_tautulli_response):
        """Test backwards compatibility for list response."""
        mock_request.return_value = mock_tautulli_response["response"]["data"]

        result = api.get_recently_added(
            media_type="season",
            count=10,
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert len(result) == 2
        assert result[1]["media_type"] == "season"

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_recently_added_empty_response(self, mock_request):
        """Test handling of empty response."""
        mock_request.return_value = []

        result = api.get_recently_added(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result == []

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_recently_added_api_failure(self, mock_request):
        """Test handling when API call fails."""
        mock_request.return_value = None

        result = api.get_recently_added(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result == []

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_recently_added_non_list_response(self, mock_request):
        """Test handling when response is a dict wrapper."""
        mock_request.return_value = {
            "recently_added": [{"rating_key": "123", "title": "Season 1", "media_type": "season"}]
        }

        result = api.get_recently_added(
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert len(result) == 1
        assert result[0]["rating_key"] == "123"


class TestGetMetadata:
    """Tests for get_metadata function."""

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_metadata_success(self, mock_request, mock_show_metadata):
        """Test successful metadata fetch."""
        mock_request.return_value = mock_show_metadata

        result = api.get_metadata(
            "11111",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is not None
        assert result["title"] == "Breaking Bad"
        assert result["thumb"] is not None

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_metadata_failure(self, mock_request):
        """Test handling when metadata fetch fails."""
        mock_request.return_value = None

        result = api.get_metadata(
            "11111",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None


class TestGetChildrenMetadata:
    """Tests for get_children_metadata function."""

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_children_success(self, mock_request, mock_seasons_data):
        """Test successful children metadata fetch."""
        mock_request.return_value = {
            "children_count": len(mock_seasons_data),
            "children_list": mock_seasons_data,
        }

        result = api.get_children_metadata(
            "11111",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert len(result) == 3
        assert all(child.get("rating_key") for child in result)

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_children_list_response(self, mock_request, mock_seasons_data):
        """Test backwards compatibility for list response."""
        mock_request.return_value = mock_seasons_data

        result = api.get_children_metadata(
            "11111",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert len(result) == 3
        assert all(child.get("rating_key") for child in result)

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_children_empty_response(self, mock_request):
        """Test handling of empty children response."""
        mock_request.return_value = []

        result = api.get_children_metadata(
            "11111",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result == []

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_children_filters_missing_rating_key(self, mock_request):
        """Test that children without rating_key are filtered out."""
        mock_request.return_value = {
            "children_count": 3,
            "children_list": [
                {"title": "Season 1", "rating_key": "123"},
                {"title": "Season 2"},  # No rating_key
                {"title": "Season 3", "rating_key": "456"},
            ],
        }

        result = api.get_children_metadata(
            "11111",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert len(result) == 2

    @patch("new_seasons_reminder.api.make_tautulli_request")
    def test_get_children_api_failure(self, mock_request):
        """Test handling when API call fails."""
        mock_request.return_value = None

        result = api.get_children_metadata(
            "11111",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result == []


class TestCoverUrlFunctions:
    """Tests for cover URL building functions."""

    def test_get_cover_url_with_absolute_path(self):
        """Test cover URL building with absolute path."""
        thumb_path = "/library/metadata/123/thumb/1234567890"
        result = get_cover_url(
            thumb_path,
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
        )

        assert result is not None
        assert result.startswith("http://localhost:32400")
        assert "/library/metadata/123/thumb/1234567890" in result
        assert "X-Plex-Token=test-plex-token" in result

    def test_get_cover_url_with_relative_path(self):
        """Test cover URL building with relative path."""
        thumb_path = "library/metadata/123/thumb/1234567890"
        result = get_cover_url(
            thumb_path,
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
        )

        assert result is not None
        assert "/library/metadata/123/thumb/1234567890" in result

    def test_get_cover_url_missing_plex_config(self):
        """Test cover URL returns None when Plex config missing."""
        result = get_cover_url(
            "/path/to/thumb",
            plex_url="",
            plex_token="",
        )
        assert result is None

    def test_get_cover_url_none_path(self):
        """Test cover URL returns None when thumb_path is None."""
        result = get_cover_url(
            None,
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
        )
        assert result is None

    @patch("new_seasons_reminder.api.get_metadata")
    def test_get_show_cover_success(self, mock_get_metadata, mock_show_metadata):
        """Test successful show cover fetch."""
        mock_get_metadata.return_value = mock_show_metadata

        result = get_show_cover(
            "11111",
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is not None
        assert "thumb" in result or "art" in result

    @patch("new_seasons_reminder.api.get_metadata")
    def test_get_show_cover_no_metadata(self, mock_get_metadata):
        """Test show cover when metadata fetch fails."""
        mock_get_metadata.return_value = None

        result = get_show_cover(
            "11111",
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None

    @patch("new_seasons_reminder.api.get_metadata")
    def test_get_show_cover_no_thumb(self, mock_get_metadata):
        """Test show cover when no thumb available."""
        mock_get_metadata.return_value = {
            "title": "Show Name",
            # No thumb, art, or poster_thumb
        }

        result = get_show_cover(
            "11111",
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is None

    @patch("new_seasons_reminder.api.get_metadata")
    def test_get_show_cover_fallback_to_art(self, mock_get_metadata):
        """Test show cover falls back to art when no thumb."""
        mock_get_metadata.return_value = {
            "title": "Show Name",
            "art": "/library/metadata/123/art/1234567890",
        }

        result = get_show_cover(
            "11111",
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is not None
        assert "art" in result

    @patch("new_seasons_reminder.api.get_metadata")
    def test_get_show_cover_fallback_to_poster_thumb(self, mock_get_metadata):
        """Test show cover falls back to poster_thumb when no thumb or art."""
        mock_get_metadata.return_value = {
            "title": "Show Name",
            "poster_thumb": "/library/metadata/123/thumb/1234567890",
        }

        result = get_show_cover(
            "11111",
            plex_url="http://localhost:32400",
            plex_token="test-plex-token",
            tautulli_url="http://localhost:8181",
            tautulli_apikey="test-api-key",
        )

        assert result is not None
