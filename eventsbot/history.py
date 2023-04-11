import json
import logging
import pathlib

logger = logging.getLogger(__name__)


def check_history(history_path: str) -> None:
    """Check if history file exists or create it."""

    path = pathlib.Path(history_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        with path.open("w", encoding="utf-8") as history_file:
            json.dump([], history_file)


def load_history(history_path: str) -> list[dict[str, str]]:
    """Load the messages history."""

    history = []

    path = pathlib.Path(history_path)
    try:
        with path.open("r", encoding="utf-8") as history_file:
            history = json.load(history_file)
    except json.decoder.JSONDecodeError:
        logger.warning(
            "Corrupted history file, resetting it. You might have to cleanp manually messages posted by the bot",
        )

    return history


def save_history(history_path: str, history: list[dict[str, str]]) -> None:
    """Write message history to disk."""
    path = pathlib.Path(history_path)
    with path.open("w", encoding="utf-8") as history_file:
        json.dump(history, history_file)
