"""Base protocol for media sources."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from new_seasons_reminder.models import CandidateSeason, SeasonRef


@runtime_checkable
class MediaSource(Protocol):
    """Protocol for media sources (Sonarr)."""

    @abstractmethod
    def get_candidate_seasons(
        self,
        since: datetime,
    ) -> Sequence[CandidateSeason]:
        """Get seasons that became candidates since the given timestamp.

        Args:
            since: Only return seasons with completed_at >= this timestamp

        Returns:
            Sequence of candidate seasons
        """

    @abstractmethod
    def list_seasons(self) -> Sequence[SeasonRef]:
        """List all seasons available in the media source.

        Returns:
            Sequence of all seasons
        """

    @abstractmethod
    def get_show_added_at(
        self,
        series_id: str,
    ) -> datetime | None:
        """Get the date when the show was first added to the library.

        Args:
            series_id: Source-native series ID

        Returns:
            Datetime when show was added, or None if unknown
        """
