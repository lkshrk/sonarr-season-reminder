"""Main entry point for the new_seasons_reminder application."""

import json
import logging
import sys
import time
from functools import partial
from typing import Any

from .api import (
    get_children_metadata,
    get_metadata,
    get_recently_added,
    get_show_cover,
)
from .config import Config, setup_logging
from .logic import get_new_finished_seasons, is_new_show
from .providers import GenericProvider, SignalCliProvider, WebhookProvider

logger = logging.getLogger(__name__)


def get_webhook_provider(config: Config) -> WebhookProvider:
    """Get the appropriate webhook provider based on configuration.

    Args:
        config: Application configuration.

    Returns:
        Configured webhook provider instance.

    Raises:
        ValueError: If configuration is invalid or mode is unsupported.
    """
    provider_config = config.get_provider_config()
    mode = config.webhook_mode.lower()

    provider: WebhookProvider
    if mode == "signal-cli":
        provider = SignalCliProvider(provider_config)
    elif mode == "default" or mode == "custom":
        provider = GenericProvider(provider_config)
    else:
        raise ValueError(f"Unsupported webhook_mode: {config.webhook_mode}")

    logger.info("Selected webhook provider: %s (mode=%s)", provider.__class__.__name__, mode)

    is_valid = provider.validate_config()
    logger.debug("Provider validation result for %s: %s", mode, is_valid)
    if not is_valid:
        raise ValueError(f"Invalid configuration for {mode} provider")

    return provider


def send_webhook(seasons: list[dict[str, Any]], provider: WebhookProvider, config: Config) -> bool:
    """Send webhook notification with new seasons data.

    Args:
        seasons: List of new finished seasons.
        provider: Configured webhook provider.
        config: Application configuration.

    Returns:
        True if webhook was sent successfully, False otherwise.
    """
    if not seasons and not provider.should_send_on_empty():
        logger.info("No new seasons found, skipping webhook")
        return True

    if not config.webhook_url:
        logger.warning("WEBHOOK_URL not set, skipping webhook send")
        return False

    try:
        payload = provider.build_payload(seasons)
        headers = provider.get_headers()

        import urllib.request

        logger.info(
            "Sending webhook to %s with %d season(s)",
            config.webhook_url,
            len(seasons),
        )
        data = json.dumps(payload).encode("utf-8")
        logger.debug("Webhook payload size: %d bytes", len(data))
        request = urllib.request.Request(
            config.webhook_url, data=data, headers=headers, method="POST"
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status in (200, 201, 202, 204):
                logger.info(
                    "Webhook sent successfully to %s (status=%s)",
                    config.webhook_url,
                    response.status,
                )
                return True
            else:
                logger.info(
                    "Webhook request failed to %s (status=%s)",
                    config.webhook_url,
                    response.status,
                )
                logger.warning("Webhook returned status %s", response.status)
                return False

    except Exception as e:
        logger.error(f"Failed to send webhook: {e}")
        return False


def main() -> int:
    """Main entry point for the application.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    try:
        config = Config.from_env()
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 1

    setup_logging(config.debug)

    def _mask_value(value: str, prefix: int = 4) -> str:
        if not value:
            return ""
        visible = value[:prefix]
        return f"{visible}***"

    logger.debug(
        "Loaded config values: %s",
        {
            "tautulli_url": config.tautulli_url,
            "tautulli_apikey": _mask_value(config.tautulli_apikey),
            "plex_url": config.plex_url,
            "plex_token_set": bool(config.plex_token),
            "webhook_url": config.webhook_url,
            "webhook_mode": config.webhook_mode,
            "webhook_message_template": config.webhook_message_template,
            "webhook_on_empty": config.webhook_on_empty,
            "webhook_payload_template": config.webhook_payload_template,
            "signal_number": config.signal_number,
            "signal_recipients": config.signal_recipients,
            "signal_text_mode": config.signal_text_mode,
            "signal_include_covers": config.signal_include_covers,
            "lookback_days": config.lookback_days,
            "debug": config.debug,
        },
    )

    if not config.tautulli_url or not config.tautulli_apikey:
        logger.error("TAUTULLI_URL and TAUTULLI_APIKEY must be set")
        logger.info("Exiting with code 1 (missing Tautulli configuration)")
        return 1

    try:
        provider = get_webhook_provider(config)
    except ValueError as e:
        logger.error(f"Invalid webhook configuration: {e}")
        logger.info("Exiting with code 1 (invalid webhook configuration)")
        return 1

    try:
        logger.debug("Creating API helper partial functions")
        get_recently_added_func = partial(
            get_recently_added,
            tautulli_url=config.tautulli_url,
            tautulli_apikey=config.tautulli_apikey,
        )

        get_metadata_func = partial(
            get_metadata,
            tautulli_url=config.tautulli_url,
            tautulli_apikey=config.tautulli_apikey,
        )

        get_children_func = partial(
            get_children_metadata,
            tautulli_url=config.tautulli_url,
            tautulli_apikey=config.tautulli_apikey,
        )

        get_show_cover_func = partial(
            get_show_cover,
            plex_url=config.plex_url,
            plex_token=config.plex_token,
            tautulli_url=config.tautulli_url,
            tautulli_apikey=config.tautulli_apikey,
        )

        is_new_show_func = partial(is_new_show, get_metadata_func=get_metadata_func)

        logger.info("Starting season detection...")
        start_time = time.monotonic()
        seasons = get_new_finished_seasons(
            lookback_days=config.lookback_days,
            get_recently_added_func=get_recently_added_func,
            is_new_show_func=is_new_show_func,
            get_show_cover_func=get_show_cover_func,
            get_children_func=get_children_func,
            include_new_shows=config.include_new_shows,
        )
        elapsed = time.monotonic() - start_time
        logger.info(
            "Season detection complete: found %d season(s) in %.2fs",
            len(seasons),
            elapsed,
        )

        logger.info(f"Found {len(seasons)} new finished season(s)")
        for season in seasons:
            logger.info(
                f"  - {season['show']} Season {season['season']} "
                f"({season['episode_count']} episodes)"
            )

        if config.webhook_url:
            success = send_webhook(seasons, provider, config)
            if not success:
                logger.error("Failed to send webhook notification")
                logger.info("Exiting with code 1 (webhook send failed)")
                return 1
        else:
            logger.warning("WEBHOOK_URL not set, skipping webhook send (useful for testing)")
            if seasons:
                print(json.dumps(seasons, indent=2))

        logger.info("Exiting with code 0 (completed successfully)")
        return 0

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if config.debug:
            import traceback

            traceback.print_exc()
        logger.info("Exiting with code 1 (unexpected error)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
