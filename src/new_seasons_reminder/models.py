"""Domain models for season detection.

This module defines typed dataclasses representing the core domain entities
for season completion detection across multiple media sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SeasonKey:
    """Unique identifier for a season across all sources."""

    source: str  # e.g., "sonarr"
    series_id: str  # Source-native series ID
    season_number: int  # Season number (1-indexed, 0 = specials)

    def __str__(self) -> str:
        return f"{self.source}:{self.series_id}:S{self.season_number}"


@dataclass(frozen=True, slots=True)
class SeasonRef:
    """Reference to a season from a media source."""

    season_key: SeasonKey
    series_name: str  # Show title
    season_title: str  # Season display name (e.g., "Season 1")
    season_id: str  # Unique season identifier (e.g., "1_S1")

    def __str__(self) -> str:
        return f"{self.series_name} S{self.season_key.season_number}"


@dataclass(frozen=True, slots=True)
class CandidateSeason:
    """A season candidate for completion detection."""

    season_ref: SeasonRef
    completed_at: datetime  # Time when last episode was added (max episodeFile.dateAdded)
    in_library_episode_count: int  # Episodes currently in library
    is_complete_in_source: bool | None  # Source confirms completeness

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for webhook payloads."""
        return {
            "show": self.season_ref.series_name,
            "season": self.season_ref.season_key.season_number,
            "season_title": self.season_ref.season_title,
            "added_at": self.completed_at.isoformat(),
            "episode_count": self.in_library_episode_count,
            "rating_key": self.season_ref.season_id,
            "reason": f"Complete: {self.in_library_episode_count} episodes in library",
            "expected_count": self.in_library_episode_count,
        }
