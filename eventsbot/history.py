"""History management module."""
import json
import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class History(Protocol):
    """History protocol."""

    history: list[dict[str, str]]

    def __len__(self: "History") -> int:
        ...

    def __getitem__(self: "History", key: int) -> Any:
        ...

    def __setitem__(self: "History", key: int, value: Any) -> None:
        ...

    def __delitem__(self: "History", key: int) -> None:
        ...

    def __iter__(self: "History") -> Any:
        ...

    def __contains__(self: "History", item: Any) -> bool:
        ...

    def __add__(self: "History", item: list) -> list:
        ...

    def __iadd__(self: "History", item: list) -> list:
        ...

    def append(self: "History", item: Any) -> None:
        ...

    def remove(self: "History", item: Any) -> None:
        ...

    def load(self: "History") -> None:
        """Load history."""
        ...

    def save(self: "History") -> None:
        """Save history."""
        ...


class FileHistory:
    """History management using local filesystem."""

    def __init__(self: "FileHistory", path: str) -> None:
        """Initialize FileHistory."""
        self.path = pathlib.Path(path).expanduser()
        self.history = []
        self._check()
        self._load()

    def __len__(self: "FileHistory") -> int:
        return len(self.history)

    def __getitem__(self: "FileHistory", key: int) -> Any:
        return self.history[key]

    def __setitem__(self: "FileHistory", key: int, value: Any) -> None:
        self.history[key] = value

    def __delitem__(self: "FileHistory", key: int) -> None:
        del self.history[key]

    def __iter__(self: "FileHistory") -> Any:
        return iter(self.history)

    def __contains__(self: "FileHistory", item: Any) -> bool:
        return item in self.history

    def __add__(self: "FileHistory", item: list) -> list:
        return self.history + item

    def __iadd__(self: "FileHistory", item: list) -> list:
        self.history += item
        return self.history

    def append(self: "FileHistory", item: Any) -> None:
        self.history.append(item)

    def remove(self: "FileHistory", item: Any) -> None:
        self.history.remove(item)

    def _check(self: "FileHistory") -> None:
        """Check if history file exists or create it."""
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            with self.path.open("w", encoding="utf-8") as history_file:
                json.dump([], history_file)

    def _load(self: "FileHistory") -> None:
        """Load the messages history."""
        try:
            with self.path.open("r", encoding="utf-8") as history_file:
                self.history = json.load(history_file)
        except json.decoder.JSONDecodeError:
            logger.warning(
                "Corrupted history file, resetting it. You might have to cleanp manually messages posted by the bot",
            )

    def save(self: "FileHistory") -> None:
        """Write message history to disk."""
        with self.path.open("w", encoding="utf-8") as history_file:
            json.dump(self.history, history_file)
