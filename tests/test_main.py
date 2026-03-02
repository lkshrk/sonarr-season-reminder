"""Tests for main.py entry point: get_webhook_provider, send_webhook, main."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from new_seasons_reminder.config import Config
from new_seasons_reminder.main import get_webhook_provider, main, send_webhook
from new_seasons_reminder.providers.generic import GenericProvider
from new_seasons_reminder.providers.signal_cli import SignalCliProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sonarr_config(**kwargs) -> Config:
    base = Config(
        sonarr_url="http://sonarr:8989",
        sonarr_apikey="key",
        webhook_url="http://example.com/hook",
        webhook_mode="default",
    )
    for k, v in kwargs.items():
        object.__setattr__(base, k, v)
    return base


def _make_seasons():
    return [
        {
            "show": "Breaking Bad",
            "season": 3,
            "season_title": "Season 3",
            "added_at": "2026-01-28T10:30:00",
            "episode_count": 13,
            "rating_key": "12345",
            "reason": "Complete: 13 episodes",
            "expected_count": 13,
        }
    ]


# ---------------------------------------------------------------------------
# get_webhook_provider
# ---------------------------------------------------------------------------


class TestGetWebhookProvider:
    def test_returns_generic_provider_for_default_mode(self):
        cfg = _sonarr_config(webhook_mode="default")
        provider = get_webhook_provider(cfg)
        assert isinstance(provider, GenericProvider)

    def test_returns_generic_provider_for_custom_mode(self):
        cfg = _sonarr_config(webhook_mode="custom")
        provider = get_webhook_provider(cfg)
        assert isinstance(provider, GenericProvider)

    def test_returns_signal_cli_provider(self):
        cfg = _sonarr_config(
            webhook_mode="signal-cli",
            webhook_url="http://signal-cli:8080/v2/send",
            signal_number="+1234567890",
            signal_recipients="+0987654321",
        )
        provider = get_webhook_provider(cfg)
        assert isinstance(provider, SignalCliProvider)

    def test_unsupported_mode_raises_value_error(self):
        cfg = _sonarr_config(webhook_mode="unsupported")
        with pytest.raises(ValueError, match="Unsupported webhook_mode"):
            get_webhook_provider(cfg)

    def test_empty_webhook_url_does_not_raise_at_get_provider(self):
        # GenericProvider.validate_config() always returns True; empty URL fails at send time.
        # get_webhook_provider itself should succeed (url validated later).
        cfg = _sonarr_config(webhook_mode="default", webhook_url="")
        # Should NOT raise — validation is lazy
        provider = get_webhook_provider(cfg)
        assert isinstance(provider, GenericProvider)


# ---------------------------------------------------------------------------
# send_webhook
# ---------------------------------------------------------------------------


class TestSendWebhook:
    def _make_provider(self, should_send_empty=False):
        provider = MagicMock()
        provider.should_send_on_empty.return_value = should_send_empty
        provider.build_payload.return_value = {"seasons": []}
        provider.get_headers.return_value = {}
        return provider

    def test_returns_true_on_success(self):
        cfg = _sonarr_config()
        provider = self._make_provider()
        seasons = _make_seasons()

        with patch("new_seasons_reminder.main._http_client") as mock_http:
            mock_http.post_json.return_value = {}
            result = send_webhook(seasons, provider, cfg)

        assert result is True

    def test_returns_true_on_no_seasons_when_send_on_empty_false(self):
        cfg = _sonarr_config()
        provider = self._make_provider(should_send_empty=False)

        result = send_webhook([], provider, cfg)
        assert result is True

    def test_sends_webhook_when_send_on_empty_true(self):
        cfg = _sonarr_config()
        provider = self._make_provider(should_send_empty=True)

        with patch("new_seasons_reminder.main._http_client") as mock_http:
            mock_http.post_json.return_value = {}
            result = send_webhook([], provider, cfg)

        assert result is True
        mock_http.post_json.assert_called_once()

    def test_returns_false_when_no_webhook_url(self):
        cfg = _sonarr_config(webhook_url="")
        provider = self._make_provider(should_send_empty=True)

        result = send_webhook([], provider, cfg)
        assert result is False

    def test_returns_false_on_http_error(self):
        cfg = _sonarr_config()
        provider = self._make_provider()
        seasons = _make_seasons()

        with patch("new_seasons_reminder.main._http_client") as mock_http:
            mock_http.post_json.side_effect = HTTPError(
                url="http://example.com", code=500, msg="Server Error", hdrs=None, fp=None
            )
            result = send_webhook(seasons, provider, cfg)

        assert result is False

    def test_returns_false_on_url_error(self):
        cfg = _sonarr_config()
        provider = self._make_provider()
        seasons = _make_seasons()

        with patch("new_seasons_reminder.main._http_client") as mock_http:
            mock_http.post_json.side_effect = URLError("connection refused")
            result = send_webhook(seasons, provider, cfg)

        assert result is False

    def test_returns_false_on_unexpected_error(self):
        cfg = _sonarr_config()
        provider = self._make_provider()
        seasons = _make_seasons()

        with patch("new_seasons_reminder.main._http_client") as mock_http:
            mock_http.post_json.side_effect = RuntimeError("unexpected")
            result = send_webhook(seasons, provider, cfg)

        assert result is False


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def _minimal_env(**overrides):
    base = {
        "SONARR_URL": "http://sonarr:8989",
        "SONARR_APIKEY": "key",
        "WEBHOOK_URL": "http://example.com/hook",
    }
    base.update(overrides)
    return base


class TestMain:
    def test_main_returns_0_on_success_with_no_seasons(self):
        with (
            patch.dict(os.environ, _minimal_env(), clear=True),
            patch("new_seasons_reminder.main.Config.from_env") as mock_cfg,
            patch("new_seasons_reminder.main.get_webhook_provider") as mock_provider,
            patch("new_seasons_reminder.main.get_completed_seasons") as mock_seasons,
        ):
            cfg = Config(
                sonarr_url="http://sonarr:8989",
                sonarr_apikey="key",
                webhook_url="http://example.com/hook",
            )
            mock_cfg.return_value = cfg
            provider = MagicMock()
            provider.should_send_on_empty.return_value = False
            mock_provider.return_value = provider
            mock_seasons.return_value = []
            result = main()

        assert result == 0

    def test_main_returns_1_on_config_error(self):
        with patch("new_seasons_reminder.main.Config.from_env") as mock_cfg:
            mock_cfg.side_effect = Exception("bad config")
            result = main()
        assert result == 1

    def test_main_returns_1_on_invalid_webhook_config(self):
        with patch("new_seasons_reminder.main.Config.from_env") as mock_cfg:
            cfg = Config(
                sonarr_url="http://sonarr:8989",
                sonarr_apikey="key",
                webhook_url="http://example.com/hook",
            )
            mock_cfg.return_value = cfg
            with patch("new_seasons_reminder.main.get_webhook_provider") as mock_provider:
                mock_provider.side_effect = ValueError("bad config")
                result = main()
        assert result == 1

    def test_main_returns_1_on_webhook_send_failure(self):
        with patch("new_seasons_reminder.main.Config.from_env") as mock_cfg:
            cfg = Config(
                sonarr_url="http://sonarr:8989",
                sonarr_apikey="key",
                webhook_url="http://example.com/hook",
            )
            mock_cfg.return_value = cfg
            with patch("new_seasons_reminder.main.get_webhook_provider") as mock_gwp:
                provider = MagicMock()
                mock_gwp.return_value = provider
                with patch("new_seasons_reminder.main.get_completed_seasons") as mock_seasons:
                    mock_seasons.return_value = _make_seasons()
                    with patch("new_seasons_reminder.main.send_webhook") as mock_send:
                        mock_send.return_value = False
                        result = main()

        assert result == 1

    def test_main_returns_1_on_unexpected_exception(self):
        with patch("new_seasons_reminder.main.Config.from_env") as mock_cfg:
            cfg = Config(
                sonarr_url="http://sonarr:8989",
                sonarr_apikey="key",
                webhook_url="http://example.com/hook",
            )
            mock_cfg.return_value = cfg
            with patch("new_seasons_reminder.main.get_webhook_provider") as mock_gwp:
                mock_gwp.return_value = MagicMock()
                with patch("new_seasons_reminder.main.get_completed_seasons") as mock_seasons:
                    mock_seasons.side_effect = RuntimeError("oops")
                    result = main()

        assert result == 1
