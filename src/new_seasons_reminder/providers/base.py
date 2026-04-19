"""Base webhook provider class."""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from new_seasons_reminder.templates import load_templates, pick_template

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
            "User-Agent": "NewSeasons-Reminder/1.0",
        }
        self.logger.debug("Using webhook headers: %s", headers)
        return headers

    def format_message(self, seasons: list[dict[str, Any]]) -> str:
        """Format message using template variables.

        If a message_templates_file is configured, a random template is picked
        from that file. Otherwise the single message_template is used.
        """
        default_template = self.config.get(
            "message_template", "📺 {season_count} new {season_word} completed this week!"
        )
        templates_file = self.config.get("message_templates_file", "")
        if templates_file:
            templates = load_templates(templates_file)
            template = pick_template(templates, fallback=default_template)
        else:
            template = default_template
        show_list = self.format_show_list(seasons)
        count = len(seasons)
        message = str(
            template.format(
                season_count=count,
                season_word="season" if count == 1 else "seasons",
                period_days=self.config.get("lookback_days", 7),
                timestamp=datetime.now(tz=UTC).isoformat(),
                show_list=show_list,
            )
        )
        self.logger.debug(
            "Formatted message using template '%s' (length=%d)",
            template,
            len(message),
        )
        return message

    @staticmethod
    def format_show_list(seasons: list[dict[str, Any]]) -> str:
        """Format seasons into a grouped show list.

        Groups seasons by show name, sorts alphabetically, and joins
        season numbers within each show.

        Example: "Breaking Bad S1, The Office S2 & S3"
        """
        if not seasons:
            return "None"

        grouped: dict[str, list[int]] = defaultdict(list)
        for s in seasons:
            grouped[str(s.get("show", "Unknown"))].append(int(s.get("season", 0)))

        parts = []
        for show in sorted(grouped, key=str.casefold):
            nums = sorted(grouped[show])
            if len(nums) == 1:
                parts.append(f"{show} S{nums[0]}")
            else:
                joined = ", ".join(f"S{n}" for n in nums[:-1])
                parts.append(f"{show} {joined} & S{nums[-1]}")

        return ", ".join(parts)
