"""HTTP client wrapper with safe logging and error handling."""

import json
import logging
import re
import ssl
import time
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Patterns to redact from logs
_SENSITIVE_PATTERNS = [
    (r"(apikey|api_key|token|password|secret)=([^&\s\"']*)", r"\1=***"),
    (r"(Bearer\s+)([^\s]+)", r"\1***"),
    (r"(Authorization:\s*)([^\s]+)", r"\1***"),
]


def _redact_sensitive_data(text: str) -> str:
    """Redact sensitive information from text for safe logging.

    Args:
        text: Text to redact.

    Returns:
        Text with sensitive information redacted.
    """
    redacted = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
    return redacted


class HTTPClient:
    """HTTP client wrapper with safe logging and error handling."""

    def __init__(
        self,
        default_timeout: int = 30,
        user_agent: str | None = None,
        verify_ssl: bool = True,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
    ):
        """Initialize HTTP client.

        Args:
            default_timeout: Default timeout in seconds.
            user_agent: Custom user agent string.
            verify_ssl: Whether to verify SSL certificates.
            max_retries: Maximum number of retry attempts for transient failures.
            retry_backoff: Base delay in seconds between retries (doubles each attempt).
        """
        self.default_timeout = default_timeout
        self.user_agent = user_agent or (
            "new-seasons-reminder/1.0 (https://github.com/lkshrk/tautulli-new-seasons-reminder)"
        )
        self.verify_ssl = verify_ssl
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._ssl_context = None if verify_ssl else ssl._create_unverified_context()

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Check if an error is transient and worth retrying."""
        # HTTPError inherits URLError → OSError, so check it first
        if isinstance(error, HTTPError):
            return error.code >= 500  # Only server errors
        return isinstance(error, URLError | TimeoutError | OSError)

    def _request_with_retry(
        self,
        request: Request,
        timeout: int,
    ) -> bytes:
        """Execute a request with retry logic for transient failures."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with urlopen(request, timeout=timeout, context=self._ssl_context) as response:
                    logger.debug(
                        "HTTP response status=%s content_length=%s",
                        response.status,
                        response.headers.get("Content-Length", "unknown"),
                    )
                    return cast(bytes, response.read())
            except Exception as e:
                last_error = e
                if not self._is_retryable(e) or attempt == self.max_retries - 1:
                    raise
                delay = self.retry_backoff * (2**attempt)
                safe_url = self._safe_log_url(request.full_url)
                logger.warning(
                    "Retryable error on %s (attempt %d/%d), retrying in %.1fs: %s",
                    safe_url,
                    attempt + 1,
                    self.max_retries,
                    delay,
                    e,
                )
                time.sleep(delay)
        raise last_error  # pragma: no cover

    def _safe_log_url(self, url: str) -> str:
        """Safely log URL with sensitive data redacted.

        Args:
            url: URL to log.

        Returns:
            URL with sensitive data redacted.
        """
        return _redact_sensitive_data(url)

    def _safe_log_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Safely log headers with sensitive data redacted.

        Args:
            headers: Headers to log.

        Returns:
            Headers with sensitive data redacted.
        """
        safe_headers = {}
        for key, value in headers.items():
            safe_headers[key] = _redact_sensitive_data(value)
        return safe_headers

    def _safe_log_body(self, body: str | None) -> str:
        """Safely log request body with sensitive data redacted.

        Args:
            body: Body to log.

        Returns:
            Body with sensitive data redacted or placeholder.
        """
        if not body:
            return "(none)"
        redacted = _redact_sensitive_data(body)
        # Truncate long bodies to avoid log spam
        if len(redacted) > 500:
            return redacted[:500] + "... (truncated)"
        return redacted

    def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> bytes:
        """Perform HTTP GET request.

        Args:
            url: Base URL.
            params: Query parameters to append to URL.
            headers: Request headers.
            timeout: Request timeout in seconds.

        Returns:
            Response body as bytes.

        Raises:
            HTTPError: If HTTP error occurs.
            URLError: If URL/connection error occurs.
        """
        safe_url = self._safe_log_url(url)
        logger.debug("HTTP GET: %s", safe_url)

        request_url = url
        if params:
            safe_params = {k: _redact_sensitive_data(str(v)) for k, v in params.items()}
            logger.debug("HTTP GET params: %s", safe_params)
            request_url = f"{url.rstrip('/')}/?{urlencode(params)}"

        request_headers = headers or {}
        safe_headers = self._safe_log_headers(request_headers)
        if safe_headers:
            logger.debug("HTTP GET headers: %s", safe_headers)

        timeout = timeout or self.default_timeout
        request = Request(request_url, headers=request_headers, method="GET")
        request.add_header("User-Agent", self.user_agent)

        try:
            return self._request_with_retry(request, timeout)
        except HTTPError as e:
            logger.error(
                "HTTP GET error for %s: status=%s reason=%s",
                safe_url,
                e.code,
                e.reason,
            )
            raise
        except URLError as e:
            logger.error("HTTP GET URL error for %s: %s", safe_url, e.reason)
            raise

    def post(
        self,
        url: str,
        data: str | bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> bytes:
        """Perform HTTP POST request.

        Args:
            url: Request URL.
            data: Request body (string or bytes).
            headers: Request headers.
            timeout: Request timeout in seconds.

        Returns:
            Response body as bytes.

        Raises:
            HTTPError: If HTTP error occurs.
            URLError: If URL/connection error occurs.
        """
        safe_url = self._safe_log_url(url)
        logger.debug("HTTP POST: %s", safe_url)

        request_headers = headers or {}
        safe_headers = self._safe_log_headers(request_headers)
        if safe_headers:
            logger.debug("HTTP POST headers: %s", safe_headers)

        request_data: bytes | None = None
        if data and isinstance(data, str):
            safe_body = self._safe_log_body(data)
            logger.debug("HTTP POST body length: %d", len(data))
            logger.debug("HTTP POST body (redacted): %s", safe_body)
            request_data = data.encode("utf-8")
        elif data and isinstance(data, bytes):
            request_data = data

        timeout = timeout or self.default_timeout
        request = Request(url, data=request_data, headers=request_headers, method="POST")
        request.add_header("User-Agent", self.user_agent)

        try:
            return self._request_with_retry(request, timeout)
        except HTTPError as e:
            logger.error(
                "HTTP POST error for %s: status=%s reason=%s",
                safe_url,
                e.code,
                e.reason,
            )
            raise
        except URLError as e:
            logger.error("HTTP POST URL error for %s: %s", safe_url, e.reason)
            raise

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Perform HTTP GET request and parse JSON response.

        Args:
            url: Base URL.
            params: Query parameters to append to URL.
            headers: Request headers.
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON response.

        Raises:
            HTTPError: If HTTP error occurs.
            URLError: If URL/connection error occurs.
            ValueError: If response is not valid JSON.
        """
        safe_url = self._safe_log_url(url)
        response_data = self.get(url, params=params, headers=headers, timeout=timeout)

        try:
            decoded = response_data.decode("utf-8")
            return cast(dict[str, Any] | list[Any], json.loads(decoded))
        except UnicodeDecodeError as e:
            logger.error("Failed to decode response from %s: %s", safe_url, e)
            raise ValueError(f"Response decoding failed: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from %s: %s", safe_url, e)
            raise ValueError(f"Invalid JSON response: {e}") from e

    def post_json(
        self,
        url: str,
        data: dict[str, Any] | list[Any],
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Perform HTTP POST request with JSON data and parse JSON response.

        Args:
            url: Request URL.
            data: Request body as dict or list (will be JSON encoded).
            headers: Request headers. Content-Type will be set to application/json
                      if not already present.
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON response.

        Raises:
            HTTPError: If HTTP error occurs.
            URLError: If URL/connection error occurs.
            ValueError: If request data is not JSON serializable or response is not valid JSON.
        """
        safe_url = self._safe_log_url(url)

        try:
            body = json.dumps(data)
        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize request data for %s: %s", safe_url, e)
            raise ValueError(f"Request data is not JSON serializable: {e}") from e

        request_headers = headers or {}
        if "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json"

        response_data = self.post(url, data=body, headers=request_headers, timeout=timeout)

        try:
            decoded = response_data.decode("utf-8")
            return cast(dict[str, Any] | list[Any], json.loads(decoded))
        except UnicodeDecodeError as e:
            logger.error("Failed to decode response from %s: %s", safe_url, e)
            raise ValueError(f"Response decoding failed: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from %s: %s", safe_url, e)
            raise ValueError(f"Invalid JSON response: {e}") from e
