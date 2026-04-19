"""Tests for message template loading and selection."""

import json

from new_seasons_reminder.templates import load_templates, pick_template


class TestLoadTemplates:
    def test_loads_array_from_json(self, tmp_path):
        f = tmp_path / "messages.json"
        f.write_text(json.dumps(["Hello {season_count}!", "Goodbye {season_count}!"]))
        result = load_templates(str(f))
        assert result == ["Hello {season_count}!", "Goodbye {season_count}!"]

    def test_skips_non_string_entries(self, tmp_path):
        f = tmp_path / "messages.json"
        f.write_text(json.dumps(["valid", 42, None, "also valid"]))
        result = load_templates(str(f))
        assert result == ["valid", "also valid"]

    def test_skips_empty_strings(self, tmp_path):
        f = tmp_path / "messages.json"
        f.write_text(json.dumps(["valid", "", "  ", "also valid"]))
        result = load_templates(str(f))
        assert result == ["valid", "also valid"]

    def test_returns_empty_for_missing_file(self):
        result = load_templates("/nonexistent/path/messages.json")
        assert result == []

    def test_returns_empty_for_empty_array(self, tmp_path):
        f = tmp_path / "messages.json"
        f.write_text("[]")
        result = load_templates(str(f))
        assert result == []

    def test_returns_empty_for_invalid_json(self, tmp_path):
        f = tmp_path / "messages.json"
        f.write_text("not valid json {{{")
        result = load_templates(str(f))
        assert result == []

    def test_returns_empty_for_non_array_json(self, tmp_path):
        f = tmp_path / "messages.json"
        f.write_text(json.dumps({"key": "value"}))
        result = load_templates(str(f))
        assert result == []


class TestPickTemplate:
    def test_returns_fallback_when_empty(self):
        assert pick_template([], "default") == "default"

    def test_picks_from_single_entry(self):
        assert pick_template(["only one"], "default") == "only one"

    def test_picks_from_list(self):
        templates = ["a", "b", "c"]
        result = pick_template(templates, "default")
        assert result in templates

    def test_never_returns_fallback_when_list_has_entries(self):
        templates = ["x", "y"]
        for _ in range(50):
            assert pick_template(templates, "fallback") in templates


class TestFormatMessageWithTemplatesFile:
    def test_uses_template_from_file(self, tmp_path):
        from new_seasons_reminder.providers.base import WebhookProvider

        f = tmp_path / "messages.json"
        f.write_text(json.dumps(["Custom: {season_count} seasons!"]))

        config = {
            "message_template": "Default template",
            "message_templates_file": str(f),
        }
        provider = WebhookProvider(config)
        message = provider.format_message([{"show": "Test", "season": 1}])
        assert message == "Custom: 1 seasons!"

    def test_falls_back_to_default_when_file_missing(self):
        from new_seasons_reminder.providers.base import WebhookProvider

        config = {
            "message_template": "Fallback: {season_count}",
            "message_templates_file": "/nonexistent/file.json",
        }
        provider = WebhookProvider(config)
        message = provider.format_message([{"show": "Test", "season": 1}])
        assert message == "Fallback: 1"

    def test_uses_default_when_no_file_configured(self):
        from new_seasons_reminder.providers.base import WebhookProvider

        config = {"message_template": "Default: {season_count}"}
        provider = WebhookProvider(config)
        message = provider.format_message([{"show": "Test", "season": 1}])
        assert message == "Default: 1"

    def test_falls_back_when_file_has_empty_array(self, tmp_path):
        from new_seasons_reminder.providers.base import WebhookProvider

        f = tmp_path / "messages.json"
        f.write_text("[]")

        config = {
            "message_template": "Fallback: {season_count}",
            "message_templates_file": str(f),
        }
        provider = WebhookProvider(config)
        message = provider.format_message([{"show": "Test", "season": 1}])
        assert message == "Fallback: 1"

    def test_falls_back_when_file_has_invalid_json(self, tmp_path):
        from new_seasons_reminder.providers.base import WebhookProvider

        f = tmp_path / "messages.json"
        f.write_text("not json")

        config = {
            "message_template": "Fallback: {season_count}",
            "message_templates_file": str(f),
        }
        provider = WebhookProvider(config)
        message = provider.format_message([{"show": "Test", "season": 1}])
        assert message == "Fallback: 1"
