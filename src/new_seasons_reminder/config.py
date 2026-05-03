"""Configuration management for new_seasons_reminder."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from new_seasons_reminder.http import HTTPClient

if TYPE_CHECKING:
    from new_seasons_reminder.sources.sonarr import SonarrMediaSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    # Sonarr settings
    sonarr_url: str = ""
    sonarr_apikey: str = ""

    # Webhook settings
    webhook_url: str = ""
    webhook_mode: str = "default"
    webhook_message_template: str = "📺 {season_count} new {season_word} completed this week!"
    webhook_on_empty: bool = False
    webhook_payload_template: str = "default"

    # Signal CLI settings
    signal_number: str = ""
    signal_recipients: str = ""
    signal_text_mode: str = "styled"

    # Message templates
    message_templates_file: str = ""

    # Application settings
    lookback_days: int = 7
    debug: bool = False
    include_new_shows: bool = True
    disable_ssl_verify: bool = False

    @classmethod
    def from_env(cls) -> Config:
        """Create configuration from environment variables."""
        sonarr_url = os.environ.get("SONARR_URL", "")
        sonarr_apikey = os.environ.get("SONARR_APIKEY", "")
        webhook_url = os.environ.get("WEBHOOK_URL", "")
        webhook_mode = os.environ.get("WEBHOOK_MODE", "default")
        webhook_message_template = os.environ.get(
            "WEBHOOK_MESSAGE_TEMPLATE",
            "📺 {season_count} new {season_word} completed this week!",
        )
        webhook_on_empty = os.environ.get("WEBHOOK_ON_EMPTY", "false").lower() == "true"
        webhook_payload_template = os.environ.get("WEBHOOK_PAYLOAD_TEMPLATE", "default")
        signal_number = os.environ.get("SIGNAL_NUMBER", "")
        signal_recipients = os.environ.get("SIGNAL_RECIPIENTS", "")
        signal_text_mode = os.environ.get("SIGNAL_TEXT_MODE", "styled")
        message_templates_file = os.environ.get("MESSAGE_TEMPLATES_FILE", "")
        lookback_days = cls._get_lookback_days()
        debug = os.environ.get("DEBUG", "false").lower() == "true"
        include_new_shows = os.environ.get("INCLUDE_NEW_SHOWS", "true").lower() == "true"
        disable_ssl_verify = os.environ.get("DISABLE_SSL_VERIFY", "false").lower() == "true"

        config = cls(
            sonarr_url=sonarr_url,
            sonarr_apikey=sonarr_apikey,
            webhook_url=webhook_url,
            webhook_mode=webhook_mode,
            webhook_message_template=webhook_message_template,
            webhook_on_empty=webhook_on_empty,
            webhook_payload_template=webhook_payload_template,
            signal_number=signal_number,
            signal_recipients=signal_recipients,
            signal_text_mode=signal_text_mode,
            message_templates_file=message_templates_file,
            lookback_days=lookback_days,
            debug=debug,
            include_new_shows=include_new_shows,
            disable_ssl_verify=disable_ssl_verify,
        )

        logger.debug("Loaded config: sonarr_url=%s, webhook_mode=%s", sonarr_url, webhook_mode)
        return config

    @staticmethod
    def _mask_value(value: str, prefix: int = 4) -> str:
        """Mask sensitive values for logging.

        Args:
            value: Value to mask
            prefix: Number of characters to show

        Returns:
            Masked value or empty string
        """
        if not value:
            return ""
        visible = value[:prefix]
        return f"{visible}***"

    @staticmethod
    def _get_lookback_days() -> int:
        """Get and validate LOOKBACK_DAYS from environment."""
        try:
            days = int(os.environ.get("LOOKBACK_DAYS", "7"))
            if days < 1 or days > 365:
                raise ValueError("LOOKBACK_DAYS must be between 1 and 365")
            logger.debug("Parsed LOOKBACK_DAYS=%s", days)
            return days
        except ValueError as e:
            logger.warning("Invalid LOOKBACK_DAYS: %s. Using default of 7.", e)
            return 7

    def create_http_client(self) -> HTTPClient:
        """Create HTTP client for API requests."""
        return HTTPClient(verify_ssl=not self.disable_ssl_verify)

    def get_provider_config(self) -> dict[str, Any]:
        return {
            "webhook_url": self.webhook_url,
            "webhook_on_empty": self.webhook_on_empty,
            "message_template": self.webhook_message_template,
            "webhook_payload_template": self.webhook_payload_template,
            "payload_template": self.webhook_payload_template,
            "lookback_days": self.lookback_days,
            "signal_number": self.signal_number,
            "signal_recipients": self.signal_recipients,
            "signal_text_mode": self.signal_text_mode,
            "message_templates_file": self.message_templates_file,
        }

    def create_media_source(self) -> SonarrMediaSource:
        """Create Sonarr media source instance."""
        from new_seasons_reminder.sources.sonarr import SonarrMediaSource

        if not self.sonarr_url or not self.sonarr_apikey:
            raise ValueError("Sonarr URL and API key are required")

        return SonarrMediaSource(
            sonarr_url=self.sonarr_url,
            sonarr_apikey=self.sonarr_apikey,
            http_client=self.create_http_client(),
        )

    def validate(self) -> None:
        """Validate configuration and raise errors for invalid settings."""
        if not self.sonarr_url:
            raise ValueError("SONARR_URL is required")
        if not self.sonarr_apikey:
            raise ValueError("SONARR_APIKEY is required")
        if not self.webhook_url:
            raise ValueError("WEBHOOK_URL is required")

        logger.info("Configuration validation passed")


def setup_logging(debug: bool = False) -> logging.Logger:
    """Setup application logging with appropriate verbosity.

    Args:
        debug: If True, set logging level to DEBUG. Otherwise, use INFO (default).

    Returns:
        Configured logger instance.
    """
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger(__name__)
    logger.info("Logging initialized at %s level", logging.getLevelName(level))

    if debug:
        logger.debug("Debug mode enabled - verbose logging active")

    logger.debug(
        "Configured log levels: root=%s, %s=%s",
        logging.getLevelName(logging.getLogger().getEffectiveLevel()),
        __name__,
        logging.getLevelName(logger.getEffectiveLevel()),
    )

    return logger
