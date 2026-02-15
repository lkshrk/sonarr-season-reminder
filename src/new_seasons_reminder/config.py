"""Configuration management for new_seasons_reminder."""

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Tautulli settings
    tautulli_url: str = ""
    tautulli_apikey: str = ""

    # Plex settings (for cover images)
    plex_url: str = ""
    plex_token: str = ""

    # Webhook settings
    webhook_url: str = ""
    webhook_mode: str = "default"
    webhook_message_template: str = "📺 {season_count} new season(s) completed this week!"
    webhook_on_empty: bool = False
    webhook_payload_template: str = "default"

    # Signal CLI settings
    signal_number: str = ""
    signal_recipients: str = ""
    signal_text_mode: str = "styled"
    signal_include_covers: bool = False

    # Application settings
    lookback_days: int = 7
    debug: bool = False
    include_new_shows: bool = False

    @classmethod
    def from_env(cls) -> Config:
        """Create configuration from environment variables."""
        config = cls()

        def _mask_value(value: str, prefix: int = 4) -> str:
            if not value:
                return ""
            visible = value[:prefix]
            return f"{visible}***"

        # Tautulli
        config.tautulli_url = os.environ.get("TAUTULLI_URL", "")
        logger.debug("Loaded TAUTULLI_URL=%s", config.tautulli_url)
        config.tautulli_apikey = os.environ.get("TAUTULLI_APIKEY", "")
        logger.debug("Loaded TAUTULLI_APIKEY=%s", _mask_value(config.tautulli_apikey))

        # Plex
        config.plex_url = os.environ.get("PLEX_URL", "")
        logger.debug("Loaded PLEX_URL=%s", config.plex_url)
        config.plex_token = os.environ.get("PLEX_TOKEN", "")
        logger.debug("Loaded PLEX_TOKEN=%s", _mask_value(config.plex_token))

        # Webhook
        config.webhook_url = os.environ.get("WEBHOOK_URL", "")
        logger.debug("Loaded WEBHOOK_URL=%s", config.webhook_url)
        config.webhook_mode = os.environ.get("WEBHOOK_MODE", "default")
        logger.debug("Loaded WEBHOOK_MODE=%s", config.webhook_mode)
        config.webhook_message_template = os.environ.get(
            "WEBHOOK_MESSAGE_TEMPLATE", "📺 {season_count} new season(s) completed this week!"
        )
        logger.debug(
            "Loaded WEBHOOK_MESSAGE_TEMPLATE=%s",
            config.webhook_message_template,
        )
        config.webhook_on_empty = os.environ.get("WEBHOOK_ON_EMPTY", "false").lower() == "true"
        logger.debug("Loaded WEBHOOK_ON_EMPTY=%s", config.webhook_on_empty)
        config.webhook_payload_template = os.environ.get("WEBHOOK_PAYLOAD_TEMPLATE", "default")
        logger.debug("Loaded WEBHOOK_PAYLOAD_TEMPLATE=%s", config.webhook_payload_template)

        # Signal CLI
        config.signal_number = os.environ.get("SIGNAL_NUMBER", "")
        logger.debug("Loaded SIGNAL_NUMBER=%s", config.signal_number)
        config.signal_recipients = os.environ.get("SIGNAL_RECIPIENTS", "")
        logger.debug("Loaded SIGNAL_RECIPIENTS=%s", config.signal_recipients)
        config.signal_text_mode = os.environ.get("SIGNAL_TEXT_MODE", "styled")
        logger.debug("Loaded SIGNAL_TEXT_MODE=%s", config.signal_text_mode)
        config.signal_include_covers = (
            os.environ.get("SIGNAL_INCLUDE_COVERS", "false").lower() == "true"
        )
        logger.debug("Loaded SIGNAL_INCLUDE_COVERS=%s", config.signal_include_covers)

        # Application settings
        config.lookback_days = cls._get_lookback_days()
        logger.debug("Loaded LOOKBACK_DAYS=%s", config.lookback_days)
        config.debug = os.environ.get("DEBUG", "false").lower() == "true"
        logger.debug("Loaded DEBUG=%s", config.debug)
        config.include_new_shows = os.environ.get("INCLUDE_NEW_SHOWS", "false").lower() == "true"
        logger.debug("Loaded INCLUDE_NEW_SHOWS=%s", config.include_new_shows)

        return config

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
            logger.warning(f"Invalid LOOKBACK_DAYS: {e}. Using default of 7.")
            return 7

    def get_provider_config(self) -> dict[str, Any]:
        """Get configuration dictionary for webhook providers."""
        return {
            "webhook_url": self.webhook_url,
            "webhook_on_empty": self.webhook_on_empty,
            "message_template": self.webhook_message_template,
            "payload_template": self.webhook_payload_template,
            "lookback_days": self.lookback_days,
            "signal_number": self.signal_number,
            "signal_recipients": self.signal_recipients,
            "signal_text_mode": self.signal_text_mode,
            "signal_include_covers": self.signal_include_covers,
        }


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

    # Log the startup with appropriate level
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized at {logging.getLevelName(level)} level")
    if debug:
        logger.debug("Debug mode enabled - verbose logging active")
    logger.debug(
        "Configured log levels: root=%s, %s=%s",
        logging.getLevelName(logging.getLogger().getEffectiveLevel()),
        __name__,
        logging.getLevelName(logger.getEffectiveLevel()),
    )

    return logger
