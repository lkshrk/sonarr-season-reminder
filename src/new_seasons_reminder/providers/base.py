"""Base webhook provider class."""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class WebhookProvider:
    """Base class for webhook providers. Extend this to add new webhook services."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(
            "Initialized %s with config keys: %s",
            self.__class__.__name__,
            sorted(self.config.keys()),
        )

    def validate_config(self) -> bool:
        """Validate that required configuration is present."""
        return True

    def should_send_on_empty(self) -> bool:
        """Return True if webhook should be sent even when no seasons found."""
        should_send = bool(self.config.get("webhook_on_empty", False))
        self.logger.debug("should_send_on_empty=%s", should_send)
        return should_send

    def build_payload(self, seasons: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the webhook payload. Must be implemented by subclasses."""
        self.logger.debug("Base build_payload called; subclasses should implement this.")
        raise NotImplementedError("Subclasses must implement build_payload()")

    def get_headers(self) -> dict[str, str]:
        """Get HTTP headers for the webhook request."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Tautulli-NewSeasons-Reminder/1.0",
        }
        self.logger.debug("Using webhook headers: %s", headers)
        return headers

    def format_message(self, seasons: list[dict[str, Any]]) -> str:
        """Format message using template variables."""
        template = self.config.get(
            "message_template", "📺 {season_count} new season(s) completed this week!"
        )
        show_list = (
            ", ".join([f"{s['show']} S{s['season']}" for s in seasons]) if seasons else "None"
        )
        message = str(
            template.format(
                season_count=len(seasons),
                period_days=self.config.get("lookback_days", 7),
                timestamp=datetime.now().isoformat(),
                show_list=show_list,
            )
        )
        self.logger.debug(
            "Formatted message using template '%s' (length=%d)",
            template,
            len(message),
        )
        return message
