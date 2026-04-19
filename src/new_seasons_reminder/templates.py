"""Message template loading and selection."""

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)


def load_templates(file_path: str) -> list[str]:
    """Load message templates from a JSON file.

    Expected format: a JSON array of template strings, e.g.::

        [
            "📺 {season_count} new season(s) completed this week!",
            "🎉 You've got {season_count} fresh season(s) waiting!"
        ]

    Args:
        file_path: Path to the JSON templates file.

    Returns:
        List of template strings. Empty list if file not found or invalid.
    """
    path = Path(file_path)
    if not path.is_file():
        logger.warning("Templates file not found: %s", file_path)
        return []

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Failed to read templates file %s: %s", file_path, e)
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in templates file %s: %s", file_path, e)
        return []

    if not isinstance(data, list):
        logger.error(
            "Templates file %s must contain a JSON array, got %s",
            file_path,
            type(data).__name__,
        )
        return []

    templates = [str(item) for item in data if isinstance(item, str) and item.strip()]
    if len(templates) < len(data):
        skipped = len(data) - len(templates)
        logger.warning(
            "Skipped %d non-string or empty entries in %s", skipped, file_path
        )

    logger.info("Loaded %d message template(s) from %s", len(templates), file_path)
    return templates


def pick_template(templates: list[str], fallback: str) -> str:
    """Pick a random template from a list, or return the fallback.

    Args:
        templates: List of template strings.
        fallback: Default template to use when list is empty.

    Returns:
        A randomly selected template, or the fallback.
    """
    if not templates:
        return fallback
    chosen = random.choice(templates)  # noqa: S311
    logger.debug("Picked message template: %s", chosen)
    return chosen
