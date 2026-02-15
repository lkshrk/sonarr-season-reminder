"""Signal CLI webhook provider."""

import base64
import logging
from datetime import datetime
from typing import Any
from urllib.request import urlopen

from .base import WebhookProvider

logger = logging.getLogger(__name__)


class SignalCliProvider(WebhookProvider):
    """Provider for signal-cli-rest-api webhook format."""

    def validate_config(self) -> bool:
        """Validate signal-cli configuration."""
        required = ["signal_number", "signal_recipients"]
        logger.debug("Validating Signal CLI config fields: %s", required)
        valid = True
        for key in required:
            if not self.config.get(key):
                logger.error("Missing required config: %s", key)
                valid = False
        logger.info("Signal CLI config validation result: %s", valid)
        return valid

    def should_send_on_empty(self) -> bool:
        """Never send Signal messages when there are no new seasons."""
        return False

    def _parse_recipients(self) -> list[str]:
        """Parse comma-separated recipient list."""
        recipients_str = self.config.get("signal_recipients", "")
        if not recipients_str:
            logger.debug("Parsed 0 Signal recipients")
            return []
        recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
        logger.debug("Parsed %d Signal recipients", len(recipients))
        return recipients

    def _get_covers_as_base64(self, seasons: list[dict[str, Any]]) -> list[str]:
        """Download and encode covers as base64."""
        base64_covers = []
        for season in seasons:
            cover_url = season.get("cover_url")
            if not cover_url:
                continue
            try:
                logger.debug(
                    "Downloading cover for %s from %s",
                    season.get("show"),
                    cover_url,
                )
                with urlopen(cover_url, timeout=30) as response:
                    image_data = response.read()
                    base64_covers.append(base64.b64encode(image_data).decode("utf-8"))
            except Exception as e:
                logger.warning("Failed to download cover for %s: %s", season["show"], e)
        logger.info("Downloaded %d cover(s) for Signal payload", len(base64_covers))
        return base64_covers

    def format_message(self, seasons: list[dict[str, Any]]) -> str:
        """Format message with Signal text styling (bold, italic)."""
        count = len(seasons)
        period = self.config.get("lookback_days", 7)

        season_plural = "s" if count > 1 else ""
        lines = [
            f"📺 *{count} new season{season_plural}* completed in the last {period} days!",
            "",
        ]

        for season in seasons:
            show_name = season["show"]
            season_num = season["season"]
            ep_count = season.get("episode_count", 0)
            lines.append(f"• *{show_name}* - Season {season_num} ({ep_count} episodes)")

        lines.append("")
        lines.append(f"_{datetime.now().strftime('%Y-%m-%d %H:%M')}_")

        message = "\n".join(lines)
        logger.debug(
            "Formatted Signal message (length=%d, lines=%d)",
            len(message),
            len(lines),
        )
        return message

    def build_payload(self, seasons: list[dict[str, Any]]) -> dict[str, Any]:
        """Build signal-cli-rest-api payload."""
        message = self.format_message(seasons)
        recipients = self._parse_recipients()

        payload = {
            "message": message,
            "number": self.config["signal_number"],
            "recipients": recipients,
            "text_mode": self.config.get("signal_text_mode", "styled"),
        }

        if self.config.get("signal_include_covers", False) and seasons:
            base64_covers = self._get_covers_as_base64(seasons)
            if base64_covers:
                payload["base64_attachments"] = base64_covers

        logger.info(
            "Signal payload summary: recipients=%d, attachments=%s, message_length=%d",
            len(recipients),
            "base64_attachments" in payload,
            len(message),
        )

        return payload
