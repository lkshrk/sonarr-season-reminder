"""Tests for Config dataclass and setup_logging."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from new_seasons_reminder.config import Config, setup_logging
from new_seasons_reminder.sources.sonarr import SonarrMediaSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env(**overrides: str):
    """Return a minimal valid env dict for Sonarr source."""
    base = {
        "SONARR_URL": "http://sonarr:8989",
        "SONARR_APIKEY": "sonarr-key",
        "WEBHOOK_URL": "http://example.com/hook",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Config.from_env — defaults
# ---------------------------------------------------------------------------


class TestConfigFromEnvDefaults:
    def test_lookback_days_defaults_to_7(self):
        with patch.dict(os.environ, _env(), clear=True):
            cfg = Config.from_env()
        assert cfg.lookback_days == 7

    def test_debug_defaults_to_false(self):
        with patch.dict(os.environ, _env(), clear=True):
            cfg = Config.from_env()
        assert cfg.debug is False

    def test_include_new_shows_defaults_to_false(self):
        with patch.dict(os.environ, _env(), clear=True):
            cfg = Config.from_env()
        assert cfg.include_new_shows is False

    def test_webhook_on_empty_defaults_to_false(self):
        with patch.dict(os.environ, _env(), clear=True):
            cfg = Config.from_env()
        assert cfg.webhook_on_empty is False

    def test_webhook_mode_defaults_to_default(self):
        with patch.dict(os.environ, _env(), clear=True):
            cfg = Config.from_env()
        assert cfg.webhook_mode == "default"

    def test_disable_ssl_verify_defaults_to_false(self):
        with patch.dict(os.environ, _env(), clear=True):
            cfg = Config.from_env()
        assert cfg.disable_ssl_verify is False


# ---------------------------------------------------------------------------
# Config.from_env — explicit values
# ---------------------------------------------------------------------------


class TestConfigFromEnvExplicit:
    def test_reads_sonarr_url(self):
        with patch.dict(os.environ, _env(SONARR_URL="http://custom:9000"), clear=True):
            cfg = Config.from_env()
        assert cfg.sonarr_url == "http://custom:9000"

    def test_reads_sonarr_apikey(self):
        with patch.dict(os.environ, _env(SONARR_APIKEY="secret123"), clear=True):
            cfg = Config.from_env()
        assert cfg.sonarr_apikey == "secret123"

    def test_reads_lookback_days(self):
        with patch.dict(os.environ, _env(LOOKBACK_DAYS="14"), clear=True):
            cfg = Config.from_env()
        assert cfg.lookback_days == 14

    def test_reads_debug_true(self):
        with patch.dict(os.environ, _env(DEBUG="true"), clear=True):
            cfg = Config.from_env()
        assert cfg.debug is True

    def test_reads_include_new_shows_true(self):
        with patch.dict(os.environ, _env(INCLUDE_NEW_SHOWS="true"), clear=True):
            cfg = Config.from_env()
        assert cfg.include_new_shows is True

    def test_reads_webhook_on_empty_true(self):
        with patch.dict(os.environ, _env(WEBHOOK_ON_EMPTY="true"), clear=True):
            cfg = Config.from_env()
        assert cfg.webhook_on_empty is True

    def test_reads_disable_ssl_verify_true(self):
        with patch.dict(os.environ, _env(DISABLE_SSL_VERIFY="true"), clear=True):
            cfg = Config.from_env()
        assert cfg.disable_ssl_verify is True

    def test_reads_webhook_mode(self):
        with patch.dict(os.environ, _env(WEBHOOK_MODE="signal-cli"), clear=True):
            cfg = Config.from_env()
        assert cfg.webhook_mode == "signal-cli"

    def test_reads_webhook_message_template(self):
        with patch.dict(os.environ, _env(WEBHOOK_MESSAGE_TEMPLATE="Custom message"), clear=True):
            cfg = Config.from_env()
        assert cfg.webhook_message_template == "Custom message"


# ---------------------------------------------------------------------------
# Config.from_env — validation / edge cases
# ---------------------------------------------------------------------------


class TestConfigFromEnvEdgeCases:
    def test_lookback_days_too_low_falls_back_to_7(self):
        with patch.dict(os.environ, _env(LOOKBACK_DAYS="0"), clear=True):
            cfg = Config.from_env()
        assert cfg.lookback_days == 7

    def test_lookback_days_too_high_falls_back_to_7(self):
        with patch.dict(os.environ, _env(LOOKBACK_DAYS="400"), clear=True):
            cfg = Config.from_env()
        assert cfg.lookback_days == 7

    def test_lookback_days_not_a_number_falls_back_to_7(self):
        with patch.dict(os.environ, _env(LOOKBACK_DAYS="abc"), clear=True):
            cfg = Config.from_env()
        assert cfg.lookback_days == 7

    def test_webhook_on_empty_case_insensitive(self):
        with patch.dict(os.environ, _env(WEBHOOK_ON_EMPTY="True"), clear=True):
            cfg = Config.from_env()
        assert cfg.webhook_on_empty is True


# ---------------------------------------------------------------------------
# Config.validate
# ---------------------------------------------------------------------------


class TestConfigValidate:
    def test_valid_sonarr_config_passes(self):
        cfg = Config(
            sonarr_url="http://sonarr:8989",
            sonarr_apikey="key",
            webhook_url="http://example.com/hook",
        )
        cfg.validate()  # should not raise

    def test_missing_sonarr_url_raises(self):
        cfg = Config(sonarr_url="", sonarr_apikey="key", webhook_url="http://x.com")
        with pytest.raises(ValueError, match="SONARR_URL"):
            cfg.validate()

    def test_missing_sonarr_apikey_raises(self):
        cfg = Config(sonarr_url="http://sonarr", sonarr_apikey="", webhook_url="http://x.com")
        with pytest.raises(ValueError, match="SONARR_APIKEY"):
            cfg.validate()

    def test_missing_webhook_url_raises(self):
        cfg = Config(
            sonarr_url="http://sonarr",
            sonarr_apikey="key",
            webhook_url="",
        )
        with pytest.raises(ValueError, match="WEBHOOK_URL"):
            cfg.validate()


# ---------------------------------------------------------------------------
# Config.create_media_source
# ---------------------------------------------------------------------------


class TestCreateMediaSource:
    def test_creates_sonarr_source(self):
        cfg = Config(
            sonarr_url="http://sonarr:8989",
            sonarr_apikey="key",
        )
        source = cfg.create_media_source()
        assert isinstance(source, SonarrMediaSource)

    def test_sonarr_missing_url_raises(self):
        cfg = Config(sonarr_url="", sonarr_apikey="key")
        with pytest.raises(ValueError):
            cfg.create_media_source()

    def test_sonarr_missing_apikey_raises(self):
        cfg = Config(sonarr_url="http://sonarr", sonarr_apikey="")
        with pytest.raises(ValueError):
            cfg.create_media_source()

    def test_create_http_client_disables_ssl_verification(self):
        cfg = Config(disable_ssl_verify=True)
        client = cfg.create_http_client()
        assert client.verify_ssl is False

    def test_sonarr_source_uses_ssl_setting_in_http_client(self):
        cfg = Config(
            sonarr_url="http://sonarr:8989",
            sonarr_apikey="key",
            disable_ssl_verify=True,
        )
        source = cfg.create_media_source()
        assert isinstance(source, SonarrMediaSource)
        assert source._http_client.verify_ssl is False


# ---------------------------------------------------------------------------
# Config.get_provider_config
# ---------------------------------------------------------------------------


class TestGetProviderConfig:
    def test_returns_dict_with_webhook_url(self):
        cfg = Config(webhook_url="http://example.com/hook")
        pc = cfg.get_provider_config()
        assert pc["webhook_url"] == "http://example.com/hook"

    def test_returns_dict_with_lookback_days(self):
        cfg = Config(lookback_days=14)
        pc = cfg.get_provider_config()
        assert pc["lookback_days"] == 14

    def test_returns_dict_with_signal_settings(self):
        cfg = Config(signal_number="+1234", signal_recipients="+5678", signal_text_mode="normal")
        pc = cfg.get_provider_config()
        assert pc["signal_number"] == "+1234"
        assert pc["signal_recipients"] == "+5678"
        assert pc["signal_text_mode"] == "normal"


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_returns_logger(self):
        import logging

        result = setup_logging(debug=False)
        assert isinstance(result, logging.Logger)

    def test_debug_mode_returns_logger_without_error(self):
        import logging

        result = setup_logging(debug=True)
        assert isinstance(result, logging.Logger)

    def test_info_mode_returns_logger_without_error(self):
        import logging

        result = setup_logging(debug=False)
        assert isinstance(result, logging.Logger)
