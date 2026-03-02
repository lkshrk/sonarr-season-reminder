"""New Seasons Reminder package exports."""

from collections.abc import Mapping
from typing import Any

from .config import Config
from .logic import get_completed_seasons, is_new_show
from .providers import GenericProvider, SignalCliProvider, WebhookProvider


def get_webhook_provider(config: Config | Mapping[str, Any]) -> WebhookProvider:
    if isinstance(config, Config):
        provider_config = config.get_provider_config()
        mode = config.webhook_mode.lower()
    else:
        provider_config = dict(config)
        mode = str(provider_config.get("webhook_mode", "default")).lower()

    provider: WebhookProvider
    if mode == "signal-cli":
        provider = SignalCliProvider(provider_config)
    elif mode in {"default", "custom"}:
        provider = GenericProvider(provider_config)
    else:
        raise ValueError(f"Unsupported webhook_mode: {mode}")

    if not provider.validate_config():
        raise ValueError(f"Invalid configuration for {mode} provider")

    return provider


def main() -> int:
    from .main import main as run_main

    return run_main()


def send_webhook(
    seasons: list[dict[str, Any]],
    provider: WebhookProvider,
    config: Config,
) -> bool:
    from .main import send_webhook as send

    return send(seasons, provider, config)


__all__ = [
    "main",
    "send_webhook",
    "get_webhook_provider",
    "Config",
    "WebhookProvider",
    "SignalCliProvider",
    "GenericProvider",
    "get_completed_seasons",
    "is_new_show",
]
