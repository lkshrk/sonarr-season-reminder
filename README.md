# Tautulli New Seasons Reminder

[![Tests](https://github.com/lkshrk/tautulli-new-seasons-reminder/actions/workflows/test.yml/badge.svg)](https://github.com/lkshrk/tautulli-new-seasons-reminder/actions/workflows/test.yml)
[![Release](https://github.com/lkshrk/tautulli-new-seasons-reminder/actions/workflows/release.yml/badge.svg)](https://github.com/lkshrk/tautulli-new-seasons-reminder/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Sends webhook notifications for newly completed TV show seasons detected via Tautulli. Ignores brand new shows — only notifies about new seasons of existing shows.

## Quick Start

```bash
docker run -e TAUTULLI_URL=http://tautulli:8181 \
           -e TAUTULLI_APIKEY=your-api-key \
           -e WEBHOOK_URL=your-webhook-url \
           ghcr.io/lkshrk/tautulli-new-seasons-reminder:latest
```

### Docker Compose

```yaml
services:
  new-seasons-reminder:
    image: ghcr.io/lkshrk/tautulli-new-seasons-reminder:latest
    environment:
      - TAUTULLI_URL=http://tautulli:8181
      - TAUTULLI_APIKEY=your-api-key
      - WEBHOOK_URL=your-webhook-url
      - LOOKBACK_DAYS=7
    restart: unless-stopped
```

## Configuration

All configuration is done via environment variables.

### Required

| Variable | Description |
|----------|-------------|
| `TAUTULLI_URL` | Tautulli instance URL |
| `TAUTULLI_APIKEY` | Tautulli API key |
| `WEBHOOK_URL` | URL to send notifications to |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `LOOKBACK_DAYS` | Days to look back for new seasons (1-365) | `7` |
| `DEBUG` | Enable verbose debug logging | `false` |
| `INCLUDE_NEW_SHOWS` | Include newly added shows if all seasons have episodes | `false` |
| `PLEX_URL` | Plex server URL (for cover images) | — |
| `PLEX_TOKEN` | Plex token (for cover images) | — |
| `WEBHOOK_MODE` | `default`, `signal-cli`, or `custom` | `default` |
| `WEBHOOK_ON_EMPTY` | Send webhook even with no new seasons | `false` |
| `WEBHOOK_MESSAGE_TEMPLATE` | Custom message template (supports `{season_count}`) | `📺 {season_count} new season(s) completed this week!` |
| `WEBHOOK_PAYLOAD_TEMPLATE` | Custom JSON payload template (see [Custom Payloads](#custom-payload-template)) | `default` |

### Signal CLI Mode

Set `WEBHOOK_MODE=signal-cli` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `SIGNAL_NUMBER` | Signal sender phone number | Required |
| `SIGNAL_RECIPIENTS` | Comma-separated recipient phone numbers | Required |
| `SIGNAL_TEXT_MODE` | `styled`, `normal`, or `extended` | `styled` |
| `SIGNAL_INCLUDE_COVERS` | Attach show covers as base64 | `false` |

## Webhook Payload

Default JSON payload:

```json
{
  "timestamp": "2026-01-30T12:00:00",
  "period_days": 7,
  "season_count": 1,
  "seasons": [
    {
      "show": "Breaking Bad",
      "season": 3,
      "season_title": "Season 3",
      "added_at": "2026-01-28T10:30:00",
      "episode_count": 13,
      "rating_key": "12345",
      "cover_url": "http://plex:32400/library/metadata/12345/thumb/..."
    }
  ],
  "message": "📺 1 new season(s) completed this week!"
}
```

### Custom Payload Template

Set `WEBHOOK_PAYLOAD_TEMPLATE` to a JSON string with template variables:

| Variable | Description |
|----------|-------------|
| `{timestamp}` | ISO 8601 timestamp |
| `{period_days}` | Lookback period in days |
| `{season_count}` | Number of seasons found |
| `{message}` | Formatted message string |
| `{show_list}` | Comma-separated list (e.g. `Breaking Bad S3, Lost S2`) |
| `{seasons}` | Full seasons array as JSON |

## How It Works

1. Queries Tautulli for recently added shows
2. Filters for seasons added within the lookback period
3. Skips new shows (show has only Season 1 and was recently added)
4. Skips seasons with no episodes
5. Sends results to the configured webhook

## License

MIT
