"""Main entry point for the new_seasons_reminder application."""

import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError

# Imported from __init__.py to avoid duplication
from . import get_webhook_provider
from .config import Config, setup_logging
from .http import HTTPClient
from .logic import get_completed_seasons
from .providers import WebhookProvider

logger = logging.getLogger(__name__)


def send_webhook(
    seasons: list[dict[str, Any]],
    provider: WebhookProvider,
    config: Config,
    http_client: HTTPClient,
) -> bool:
    """Send webhook notification with new seasons data.

    Args:
        seasons: List of new finished seasons.
        provider: Configured webhook provider.
        config: Application configuration.
        http_client: HTTP client for sending requests.

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

        logger.info(
            "Sending webhook to %s with %d season(s)",
            config.webhook_url,
            len(seasons),
        )
        logger.debug("Webhook payload: %s", payload)
        http_client.post_json(config.webhook_url, data=payload, headers=headers)
        logger.info(
            "Webhook sent successfully to %s",
            config.webhook_url,
        )
        return True

    except HTTPError as e:
        logger.error(
            "HTTP error sending webhook to %s: %s - %s",
            config.webhook_url,
            e.code,
            e.reason,
        )
        return False
    except URLError as e:
        logger.error("URL error sending webhook to %s: %s", config.webhook_url, e.reason)
        return False
    except Exception as e:
        logger.error("Failed to send webhook: %s", e)
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

    http_client = config.create_http_client()

    logger.debug(
        "Loaded config values: %s",
        {
            "sonarr_url": config.sonarr_url,
            "sonarr_apikey": Config._mask_value(config.sonarr_apikey),
            "webhook_url": config.webhook_url,
            "webhook_mode": config.webhook_mode,
            "webhook_message_template": config.webhook_message_template,
            "webhook_on_empty": config.webhook_on_empty,
            "webhook_payload_template": config.webhook_payload_template,
            "signal_number": config.signal_number,
            "signal_recipients": config.signal_recipients,
            "signal_text_mode": config.signal_text_mode,
            "lookback_days": config.lookback_days,
            "debug": config.debug,
            "disable_ssl_verify": config.disable_ssl_verify,
        },
    )
    try:
        provider = get_webhook_provider(config)
    except ValueError as e:
        logger.error("Invalid webhook configuration: %s", e)
        logger.info("Exiting with code 1 (invalid webhook configuration)")
        return 1

    try:
        logger.info("Starting season detection...")
        start_time = time.monotonic()
        source = config.create_media_source()

        since = datetime.now(tz=UTC) - timedelta(days=config.lookback_days)
        seasons = get_completed_seasons(
            source=source,
            since=since,
            include_new_shows=config.include_new_shows,
        )
        elapsed = time.monotonic() - start_time
        logger.info(
            "Season detection complete: found %d season(s) in %.2fs",
            len(seasons),
            elapsed,
        )
        logger.info("Found %d new finished season(s)", len(seasons))
        for season in seasons:
            logger.info(
                f"  - {season['show']} Season {season['season']} "
                f"({season['episode_count']} episodes)"
            )

        if config.webhook_url:
            success = send_webhook(seasons, provider, config, http_client)
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
        logger.error("Unexpected error: %s", e)
        if config.debug:
            import traceback

            traceback.print_exc()
        logger.info("Exiting with code 1 (unexpected error)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
