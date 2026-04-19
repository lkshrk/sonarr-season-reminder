import pytest

import new_seasons_reminder as nsr


class TestWebhookProvider:
    def test_get_headers_contains_default_headers(self, generic_config):
        provider = nsr.WebhookProvider(generic_config)
        assert provider.get_headers() == {
            "Content-Type": "application/json",
            "User-Agent": "NewSeasons-Reminder/1.0",
        }

    def test_format_message_uses_message_template(self, generic_config, sample_seasons):
        provider = nsr.WebhookProvider(generic_config)
        assert provider.format_message(sample_seasons) == "Found 2 new seasons"

    def test_format_message_uses_default_when_template_missing(self):
        provider = nsr.WebhookProvider({})
        assert "2 new season(s)" in provider.format_message(
            [{"show": "A", "season": 1}, {"show": "B", "season": 2}]
        )


class TestSignalCliProvider:
    def test_validate_config_success(self, signal_config):
        provider = nsr.SignalCliProvider(signal_config)
        assert provider.validate_config() is True

    def test_validate_config_missing_fields(self):
        assert nsr.SignalCliProvider({"signal_number": "+123"}).validate_config() is False
        assert nsr.SignalCliProvider({"signal_recipients": "+111"}).validate_config() is False

    def test_parse_recipients_private_helper(self, signal_config):
        provider = nsr.SignalCliProvider(signal_config)
        assert provider._parse_recipients() == ["+0987654321", "+1122334455"]

    def test_format_message_has_bold_title(self, signal_config):
        provider = nsr.SignalCliProvider(signal_config)
        seasons = [{"show": "Test Show", "season": 1, "episode_count": 10}]
        message = provider.format_message(seasons)
        assert message.startswith("**📺 1 new season completed in the last 7 days 🎉**")

    def test_format_message_has_no_spoiler(self, signal_config):
        provider = nsr.SignalCliProvider(signal_config)
        seasons = [{"show": "Test Show", "season": 1, "episode_count": 10}]
        message = provider.format_message(seasons)
        # No spoiler wrapper
        assert "||" not in message

    def test_format_message_has_bullet_points(self, signal_config):
        provider = nsr.SignalCliProvider(signal_config)
        seasons = [{"show": "Test Show", "season": 1, "episode_count": 10}]
        message = provider.format_message(seasons)
        # Bullet point format
        assert "• *Test Show*" in message

    def test_format_message_groups_multiple_seasons(self, signal_config):
        provider = nsr.SignalCliProvider(signal_config)
        seasons = [
            {"show": "The Office", "season": 2, "episode_count": 22},
            {"show": "The Office", "season": 3, "episode_count": 23},
            {"show": "Breaking Bad", "season": 1, "episode_count": 7},
        ]
        message = provider.format_message(seasons)
        # Should show "2, 3" for The Office seasons
        assert "2, 3" in message
        # Show names should be italic
        assert "*The Office*" in message
        assert "*Breaking Bad*" in message

    def test_format_message_sorted_alphabetically(self, signal_config):
        provider = nsr.SignalCliProvider(signal_config)
        seasons = [
            {"show": "Zebra Show", "season": 1, "episode_count": 10},
            {"show": "Alpha Show", "season": 1, "episode_count": 10},
        ]
        message = provider.format_message(seasons)
        # Alpha Show should appear before Zebra Show
        alpha_pos = message.find("Alpha Show")
        zebra_pos = message.find("Zebra Show")
        assert alpha_pos < zebra_pos

    def test_build_payload_shape(self, signal_config, sample_seasons):
        provider = nsr.SignalCliProvider(signal_config)
        payload = provider.build_payload(sample_seasons)
        assert sorted(payload.keys()) == [
            "message",
            "number",
            "recipients",
            "text_mode",
        ]
        assert payload["number"] == "+1234567890"
        assert payload["recipients"] == ["+0987654321", "+1122334455"]
        assert payload["message"]
        assert payload["text_mode"] == "styled"

    def test_build_payload_seerr_notification_shape(self, signal_config, sample_seasons):
        cfg = {
            **signal_config,
            "webhook_url": "https://wh.example.lan/v1/plugins/seerr-notification",
        }
        provider = nsr.SignalCliProvider(cfg)
        payload = provider.build_payload(sample_seasons)
        assert sorted(payload.keys()) == [
            "message",
            "number",
            "recipients",
            "text_mode",
        ]
        assert payload["number"] == "+1234567890"
        assert payload["recipients"] == ["+0987654321", "+1122334455"]
        assert payload["message"]
        assert payload["text_mode"] == "styled"


class TestGenericProvider:
    def test_build_payload_default_template(self, generic_config, sample_seasons):
        provider = nsr.GenericProvider(generic_config)
        payload = provider.build_payload(sample_seasons)
        assert payload["season_count"] == 2
        assert payload["period_days"] == 7
        assert payload["seasons"] == sample_seasons
        assert "message" in payload

    def test_build_payload_custom_template(self):
        config = {
            "webhook_payload_template": '{"custom": {season_count}, "message": {message}}',
            "message_template": "Count {season_count}",
        }
        provider = nsr.GenericProvider(config)
        payload = provider.build_payload([{"show": "Show 1", "season": 1}])
        assert payload["custom"] == 1
        assert payload["message"] == "Count 1"


class TestGetWebhookProvider:
    def test_get_signal_cli_provider_from_mapping(self, signal_config):
        provider = nsr.get_webhook_provider({**signal_config, "webhook_mode": "signal-cli"})
        assert isinstance(provider, nsr.SignalCliProvider)

    def test_get_generic_provider_default_from_mapping(self, generic_config):
        provider = nsr.get_webhook_provider(generic_config)
        assert isinstance(provider, nsr.GenericProvider)

    def test_get_generic_provider_from_config(self, set_env_vars):
        config = nsr.Config.from_env()
        provider = nsr.get_webhook_provider(config)
        assert isinstance(provider, nsr.GenericProvider)

    def test_unknown_mode_raises_error(self):
        with pytest.raises(ValueError):
            nsr.get_webhook_provider({"webhook_mode": "unknown"})
