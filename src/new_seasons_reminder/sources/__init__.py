"""Media sources package."""

from __future__ import annotations

from new_seasons_reminder.sources.base import MediaSource
from new_seasons_reminder.sources.sonarr import SonarrMediaSource

__all__ = ["MediaSource", "SonarrMediaSource"]
