"""Tests for HTTPClient retry logic and request handling."""

from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from new_seasons_reminder.http import HTTPClient, _redact_sensitive_data

# --- _redact_sensitive_data ---


class TestRedactSensitiveData:
    def test_redacts_apikey_param(self):
        assert "apikey=***" in _redact_sensitive_data("http://host?apikey=secret123")

    def test_redacts_bearer_token(self):
        assert "Bearer ***" in _redact_sensitive_data("Bearer abc123token")

    def test_redacts_authorization_header(self):
        result = _redact_sensitive_data("Authorization: mysecret")
        assert "mysecret" not in result
        assert "Authorization: ***" in result

    def test_leaves_safe_text_unchanged(self):
        safe = "http://example.com/api/v3/series"
        assert _redact_sensitive_data(safe) == safe


# --- _is_retryable ---


class TestIsRetryable:
    def test_connection_error_is_retryable(self):
        err = URLError("Connection refused")
        assert HTTPClient._is_retryable(err) is True

    def test_http_500_is_retryable(self):
        err = HTTPError("http://x", 500, "Internal Server Error", {}, None)
        assert HTTPClient._is_retryable(err) is True

    def test_http_502_is_retryable(self):
        err = HTTPError("http://x", 502, "Bad Gateway", {}, None)
        assert HTTPClient._is_retryable(err) is True

    def test_http_503_is_retryable(self):
        err = HTTPError("http://x", 503, "Service Unavailable", {}, None)
        assert HTTPClient._is_retryable(err) is True

    def test_http_400_is_not_retryable(self):
        err = HTTPError("http://x", 400, "Bad Request", {}, None)
        assert HTTPClient._is_retryable(err) is False

    def test_http_404_is_not_retryable(self):
        err = HTTPError("http://x", 404, "Not Found", {}, None)
        assert HTTPClient._is_retryable(err) is False

    def test_http_401_is_not_retryable(self):
        err = HTTPError("http://x", 401, "Unauthorized", {}, None)
        assert HTTPClient._is_retryable(err) is False

    def test_timeout_error_is_retryable(self):
        assert HTTPClient._is_retryable(TimeoutError()) is True

    def test_os_error_is_retryable(self):
        assert HTTPClient._is_retryable(OSError("Network unreachable")) is True

    def test_value_error_is_not_retryable(self):
        assert HTTPClient._is_retryable(ValueError("bad")) is False

    def test_runtime_error_is_not_retryable(self):
        assert HTTPClient._is_retryable(RuntimeError("oops")) is False


# --- _request_with_retry ---


def _mock_response(body: bytes = b'{"ok": true}', status: int = 200) -> MagicMock:
    """Build a mock HTTP response usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.headers = {"Content-Length": str(len(body))}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestRequestWithRetry:
    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_success_on_first_attempt(self, mock_urlopen, mock_sleep):
        mock_urlopen.return_value = _mock_response(b"hello")
        client = HTTPClient(max_retries=3, retry_backoff=0.1)

        from urllib.request import Request

        result = client._request_with_retry(Request("http://example.com"), timeout=10)

        assert result == b"hello"
        assert mock_urlopen.call_count == 1
        mock_sleep.assert_not_called()

    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_retries_on_500_then_succeeds(self, mock_urlopen, mock_sleep):
        error_500 = HTTPError("http://x", 500, "ISE", {}, None)
        mock_urlopen.side_effect = [error_500, _mock_response(b"recovered")]
        client = HTTPClient(max_retries=3, retry_backoff=0.01)

        from urllib.request import Request

        result = client._request_with_retry(Request("http://example.com"), timeout=10)

        assert result == b"recovered"
        assert mock_urlopen.call_count == 2
        mock_sleep.assert_called_once()

    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_retries_on_connection_error_then_succeeds(self, mock_urlopen, mock_sleep):
        conn_err = URLError("Connection refused")
        mock_urlopen.side_effect = [conn_err, _mock_response(b"ok")]
        client = HTTPClient(max_retries=3, retry_backoff=0.01)

        from urllib.request import Request

        result = client._request_with_retry(Request("http://example.com"), timeout=10)

        assert result == b"ok"
        assert mock_urlopen.call_count == 2

    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_raises_after_max_retries_exhausted(self, mock_urlopen, mock_sleep):
        error_500 = HTTPError("http://x", 500, "ISE", {}, None)
        mock_urlopen.side_effect = [error_500, error_500, error_500]
        client = HTTPClient(max_retries=3, retry_backoff=0.01)

        from urllib.request import Request

        with pytest.raises(HTTPError) as exc_info:
            client._request_with_retry(Request("http://example.com"), timeout=10)

        assert exc_info.value.code == 500
        assert mock_urlopen.call_count == 3
        # Sleep called between attempts 1→2 and 2→3, not after final failure
        assert mock_sleep.call_count == 2

    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_non_retryable_error_raises_immediately(self, mock_urlopen, mock_sleep):
        error_404 = HTTPError("http://x", 404, "Not Found", {}, None)
        mock_urlopen.side_effect = error_404
        client = HTTPClient(max_retries=3, retry_backoff=0.01)

        from urllib.request import Request

        with pytest.raises(HTTPError) as exc_info:
            client._request_with_retry(Request("http://example.com"), timeout=10)

        assert exc_info.value.code == 404
        assert mock_urlopen.call_count == 1
        mock_sleep.assert_not_called()

    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_backoff_doubles_each_attempt(self, mock_urlopen, mock_sleep):
        error_500 = HTTPError("http://x", 500, "ISE", {}, None)
        mock_urlopen.side_effect = [error_500, error_500, error_500]
        client = HTTPClient(max_retries=3, retry_backoff=1.0)

        from urllib.request import Request

        with pytest.raises(HTTPError):
            client._request_with_retry(Request("http://example.com"), timeout=10)

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0]  # 1.0 * 2^0, 1.0 * 2^1


# --- get / post wired to retry ---


class TestGetWithRetry:
    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_get_retries_on_500(self, mock_urlopen, mock_sleep):
        error_500 = HTTPError("http://x", 500, "ISE", {}, None)
        mock_urlopen.side_effect = [error_500, _mock_response(b"ok")]
        client = HTTPClient(max_retries=3, retry_backoff=0.01)

        result = client.get("http://example.com/api")

        assert result == b"ok"
        assert mock_urlopen.call_count == 2

    @patch("new_seasons_reminder.http.urlopen")
    def test_get_raises_non_retryable_http_error(self, mock_urlopen):
        error_400 = HTTPError("http://x", 400, "Bad Request", {}, None)
        mock_urlopen.side_effect = error_400
        client = HTTPClient(max_retries=3)

        with pytest.raises(HTTPError) as exc_info:
            client.get("http://example.com/api")

        assert exc_info.value.code == 400

    @patch("new_seasons_reminder.http.urlopen")
    def test_get_raises_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("DNS failure")
        client = HTTPClient(max_retries=1)

        with pytest.raises(URLError):
            client.get("http://example.com/api")


class TestPostWithRetry:
    @patch("new_seasons_reminder.http.time.sleep")
    @patch("new_seasons_reminder.http.urlopen")
    def test_post_retries_on_502(self, mock_urlopen, mock_sleep):
        error_502 = HTTPError("http://x", 502, "Bad Gateway", {}, None)
        mock_urlopen.side_effect = [error_502, _mock_response(b"ok")]
        client = HTTPClient(max_retries=3, retry_backoff=0.01)

        result = client.post("http://example.com/api", data='{"key": "val"}')

        assert result == b"ok"
        assert mock_urlopen.call_count == 2

    @patch("new_seasons_reminder.http.urlopen")
    def test_post_raises_non_retryable_http_error(self, mock_urlopen):
        error_422 = HTTPError("http://x", 422, "Unprocessable", {}, None)
        mock_urlopen.side_effect = error_422
        client = HTTPClient(max_retries=3)

        with pytest.raises(HTTPError) as exc_info:
            client.post("http://example.com/api", data="body")

        assert exc_info.value.code == 422


# --- safe logging helpers ---


class TestSafeLogHelpers:
    def test_safe_log_url_redacts_apikey(self):
        client = HTTPClient()
        assert "***" in client._safe_log_url("http://host?apikey=secret")

    def test_safe_log_headers_redacts_authorization(self):
        client = HTTPClient()
        result = client._safe_log_headers({"Authorization": "Bearer token123"})
        assert "token123" not in result["Authorization"]

    def test_safe_log_body_none_returns_placeholder(self):
        client = HTTPClient()
        assert client._safe_log_body(None) == "(none)"

    def test_safe_log_body_truncates_long_body(self):
        client = HTTPClient()
        long_body = "x" * 600
        result = client._safe_log_body(long_body)
        assert result.endswith("... (truncated)")
        assert len(result) < 600

    def test_safe_log_body_short_body_unchanged(self):
        client = HTTPClient()
        assert client._safe_log_body("short") == "short"
