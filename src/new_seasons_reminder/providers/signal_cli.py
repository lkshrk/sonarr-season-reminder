"""Signal CLI webhook provider."""

import logging
from collections import defaultdict
from typing import Any

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

    def _group_seasons_by_show(
        self, seasons: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Group seasons by show name."""
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for season in seasons:
            show_name = str(season.get("show", "Unknown"))
            grouped[show_name].append(season)
        return dict(grouped)

    def format_message(self, seasons: list[dict[str, Any]]) -> str:
        """Format message with Signal styling.

        Format:
        **📺 New seasons available 🎉**

        • *Show Name* - 1, 2, 3 (33 episodes)
        • *Another Show* - 2 (22 episodes)
        """
        if not seasons:
            return ""

        grouped = self._group_seasons_by_show(seasons)
        count = len(seasons)
        show_count = len(grouped)

        lines = []

        period = self.config.get("lookback_days", 7)
        season_word = "season" if count == 1 else "seasons"
        lines.append(f"**📺 {count} new {season_word} completed in the last {period} days 🎉**")
        lines.append("")

        # Build show lines sorted alphabetically
        show_lines = []
        for show_name in sorted(grouped.keys(), key=str.casefold):
            show_seasons = grouped[show_name]
            season_nums = sorted([self._to_int(s.get("season"), 0) for s in show_seasons])
            total_eps = sum(self._to_int(s.get("episode_count"), 0) for s in show_seasons)
            season_list = ", ".join(str(n) for n in season_nums)
            episode_word = "episode" if total_eps == 1 else "episodes"

            # Italic show name, season numbers, episode count
            show_lines.append(f"*{show_name}* - {season_list} ({total_eps} {episode_word})")

        # Add show lines with bullet points
        for show_line in show_lines:
            lines.append(f"• {show_line}")

        message = "\n".join(lines)
        logger.debug(
            "Formatted Signal message (seasons=%d, shows=%d, length=%d)",
            count,
            show_count,
            len(message),
        )
        return message

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except TypeError, ValueError:
            return default

    def format_subject(self, seasons: list[dict[str, Any]]) -> str:
        count = len(seasons)
        period = self.config.get("lookback_days", 7)
        season_plural = "s" if count != 1 else ""
        return f"{count} new season{season_plural} completed in the last {period} days"

    def build_payload(self, seasons: list[dict[str, Any]]) -> dict[str, Any]:
        """Build signal-cli-rest-api payload."""
        message = self.format_message(seasons)
        recipients = self._parse_recipients()

        payload = {
            "message": message,
            "number": self.config["signal_number"],
            "recipients": recipients if recipients else [],
            "text_mode": "styled",
        }

        logger.info(
            "Signal payload summary: recipients=%d, message_length=%d",
            len(recipients),
            len(message),
        )

        return payload
