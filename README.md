# New Seasons Reminder

[![CI](https://github.com/lkshrk/sonarr-season-reminder/actions/workflows/test.yml/badge.svg)](https://github.com/lkshrk/sonarr-season-reminder/actions/workflows/test.yml)
[![Release](https://github.com/lkshrk/sonarr-season-reminder/actions/workflows/release.yml/badge.svg)](https://github.com/lkshrk/sonarr-season-reminder/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Sends webhook notifications when TV show seasons are completed in your Sonarr library.

## Quick Start

```bash
docker run \
  -e SONARR_URL=http://sonarr:8989 \
  -e SONARR_APIKEY=your-api-key \
  -e WEBHOOK_URL=http://your-webhook-url \
  ghcr.io/lkshrk/tautulli-new-seasons-reminder:latest
```

### Docker Compose

```yaml
services:
  new-seasons-reminder:
    image: ghcr.io/lkshrk/tautulli-new-seasons-reminder:latest
    environment:
      - SONARR_URL=http://sonarr:8989
      - SONARR_APIKEY=your-api-key
      - WEBHOOK_URL=http://your-webhook-url
      - LOOKBACK_DAYS=7
    restart: unless-stopped
```

## Configuration

All configuration is via environment variables.

### Sonarr Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SONARR_URL` | URL to your Sonarr instance | Required |
| `SONARR_APIKEY` | Sonarr API key | Required |

### Webhook

| Variable | Description | Default |
|----------|-------------|---------|
| `WEBHOOK_URL` | URL to POST notifications to | Required |
| `WEBHOOK_MODE` | `default`, `signal-cli`, or `custom` | `default` |
| `WEBHOOK_ON_EMPTY` | Send webhook even when no seasons found | `false` |
| `WEBHOOK_MESSAGE_TEMPLATE` | Message template (supports `{season_count}`) | `📺 {season_count} new season(s) completed this week!` |
| `WEBHOOK_PAYLOAD_TEMPLATE` | Custom JSON payload template | `default` |

### Application

| Variable | Description | Default |
|----------|-------------|---------|
| `LOOKBACK_DAYS` | Days to look back for completed seasons (1–365) | `7` |
| `INCLUDE_NEW_SHOWS` | Include shows first added within the lookback window | `true` |
| `DISABLE_SSL_VERIFY` | Disable TLS certificate verification for HTTP calls | `false` |
| `DEBUG` | Verbose logging | `false` |

### Signal CLI Mode

Set `WEBHOOK_MODE=signal-cli` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `SIGNAL_TEXT_MODE` | `styled`, `normal`, or `extended` | `styled` |

### Signal Message Format

When using `WEBHOOK_MODE=signal-cli`, messages are formatted as:

```
**📺 3 new seasons completed in the last 7 days 🎉**

• *Breaking Bad* - 1, 2, 3 (33 episodes)
• *The Office* - 2 (22 episodes)
```

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
      "reason": "Complete: 13 episodes in library",
      "expected_count": 13
    }
  ],
  "message": "📺 1 new season(s) completed this week!"
}
```

### Custom Payload Template

Set `WEBHOOK_PAYLOAD_TEMPLATE` to a JSON string with these placeholders:

| Variable | Description |
|----------|-------------|
| `{timestamp}` | ISO 8601 timestamp |
| `{period_days}` | Lookback period in days |
| `{season_count}` | Number of seasons found |
| `{message}` | Formatted message string |
| `{show_list}` | Comma-separated list (e.g. `Breaking Bad S3, Lost S2`) |
| `{seasons}` | Full seasons array as JSON |


## License

MIT
