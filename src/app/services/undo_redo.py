"""Undo/Redo system using the Command pattern.

Provides an UndoStack that tracks undoable actions and allows
reversing them with Ctrl+Z / Ctrl+Shift+Z.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime
import copy

if TYPE_CHECKING:
    from app.models import Game


class Command(ABC):
    """Abstract base class for undoable commands."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the action."""
        pass

    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Reverse the command."""
        pass

    def redo(self) -> None:
        """Re-execute the command (default: same as execute)."""
        self.execute()


@dataclass
class GameFieldChangeCommand(Command):
    """Command for changing a single field on a game."""

    game: "Game"
    field_name: str
    old_value: Any
    new_value: Any
    save_callback: Optional[Callable[[], None]] = None

    @property
    def description(self) -> str:
        return f"Change {self.field_name} on '{self.game.title}'"

    def execute(self) -> None:
        setattr(self.game, self.field_name, self.new_value)
        if self.save_callback:
            self.save_callback()

    def undo(self) -> None:
        setattr(self.game, self.field_name, self.old_value)
        if self.save_callback:
            self.save_callback()


@dataclass
class GameMultiFieldChangeCommand(Command):
    """Command for changing multiple fields on a game at once."""

    game: "Game"
    old_values: Dict[str, Any]
    new_values: Dict[str, Any]
    action_name: str = "Edit game"
    save_callback: Optional[Callable[[], None]] = None

    @property
    def description(self) -> str:
        return f"{self.action_name}: '{self.game.title}'"

    def execute(self) -> None:
        for field_name, value in self.new_values.items():
            setattr(self.game, field_name, value)
        if self.save_callback:
            self.save_callback()

    def undo(self) -> None:
        for field_name, value in self.old_values.items():
            setattr(self.game, field_name, value)
        if self.save_callback:
            self.save_callback()


@dataclass
class BatchGameChangeCommand(Command):
    """Command for changing fields on multiple games."""

    games: List["Game"]
    field_name: str
    old_values: Dict[str, Any]  # game_id -> old value
    new_value: Any
    save_callback: Optional[Callable[[], None]] = None

    @property
    def description(self) -> str:
        return f"Batch {self.field_name} change ({len(self.games)} games)"

    def execute(self) -> None:
        for game in self.games:
            setattr(game, self.field_name, self.new_value)
        if self.save_callback:
            self.save_callback()

    def undo(self) -> None:
        for game in self.games:
            old_val = self.old_values.get(game.game_id)
            if old_val is not None:
                setattr(game, self.field_name, old_val)
        if self.save_callback:
            self.save_callback()


@dataclass
class AddGameCommand(Command):
    """Command for adding a game to the library."""

    game: "Game"
    games_list: List["Game"]
    save_callback: Optional[Callable[[], None]] = None

    @property
    def description(self) -> str:
        return f"Add game: '{self.game.title}'"

    def execute(self) -> None:
        if self.game not in self.games_list:
            self.games_list.append(self.game)
        if self.save_callback:
            self.save_callback()

    def undo(self) -> None:
        if self.game in self.games_list:
            self.games_list.remove(self.game)
        if self.save_callback:
            self.save_callback()


@dataclass
class RemoveGameCommand(Command):
    """Command for removing a game from the library."""

    game: "Game"
    games_list: List["Game"]
    index: int = -1
    save_callback: Optional[Callable[[], None]] = None

    @property
    def description(self) -> str:
        return f"Remove game: '{self.game.title}'"

    def execute(self) -> None:
        if self.game in self.games_list:
            self.index = self.games_list.index(self.game)
            self.games_list.remove(self.game)
        if self.save_callback:
            self.save_callback()

    def undo(self) -> None:
        if self.game not in self.games_list:
            if 0 <= self.index < len(self.games_list):
                self.games_list.insert(self.index, self.game)
            else:
                self.games_list.append(self.game)
        if self.save_callback:
            self.save_callback()


class UndoStack:
    """Manages a stack of undoable commands with redo support."""

    def __init__(self, max_size: int = 50):
        """Initialize the undo stack.

        Args:
            max_size: Maximum number of commands to keep in history
        """
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._max_size = max_size
        self._listeners: List[Callable[[], None]] = []

    def push(self, command: Command, execute: bool = True) -> None:
        """Push a command onto the stack.

        Args:
            command: The command to push
            execute: Whether to execute the command immediately
        """
        if execute:
            command.execute()

        self._undo_stack.append(command)
        self._redo_stack.clear()  # Clear redo stack on new action

        # Enforce max size
        while len(self._undo_stack) > self._max_size:
            self._undo_stack.pop(0)

        self._notify_listeners()

    def undo(self) -> Optional[Command]:
        """Undo the most recent command.

        Returns:
            The undone command, or None if nothing to undo
        """
        if not self._undo_stack:
            return None

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        self._notify_listeners()
        return command

    def redo(self) -> Optional[Command]:
        """Redo the most recently undone command.

        Returns:
            The redone command, or None if nothing to redo
        """
        if not self._redo_stack:
            return None

        command = self._redo_stack.pop()
        command.redo()
        self._undo_stack.append(command)
        self._notify_listeners()
        return command

    def can_undo(self) -> bool:
        """Check if there are commands to undo."""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if there are commands to redo."""
        return len(self._redo_stack) > 0

    def undo_description(self) -> Optional[str]:
        """Get description of the command that would be undone."""
        if self._undo_stack:
            return self._undo_stack[-1].description
        return None

    def redo_description(self) -> Optional[str]:
        """Get description of the command that would be redone."""
        if self._redo_stack:
            return self._redo_stack[-1].description
        return None

    def clear(self) -> None:
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify_listeners()

    def history(self) -> List[str]:
        """Get list of action descriptions in undo stack."""
        return [cmd.description for cmd in self._undo_stack]

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Add a listener that is called when the stack changes."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        """Remove a previously added listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        """Notify all listeners of a stack change."""
        for listener in self._listeners:
            try:
                listener()
            except Exception:
                pass

    @property
    def undo_count(self) -> int:
        """Number of commands that can be undone."""
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        """Number of commands that can be redone."""
        return len(self._redo_stack)


# Global undo stack instance
_global_undo_stack: Optional[UndoStack] = None


def get_undo_stack() -> UndoStack:
    """Get the global undo stack instance."""
    global _global_undo_stack
    if _global_undo_stack is None:
        _global_undo_stack = UndoStack()
    return _global_undo_stack


def create_field_change(
    game: "Game",
    field_name: str,
    new_value: Any,
    save_callback: Optional[Callable[[], None]] = None
) -> GameFieldChangeCommand:
    """Create a field change command, capturing the current value.

    Args:
        game: The game to modify
        field_name: Name of the field to change
        new_value: The new value to set
        save_callback: Optional callback to save after change

    Returns:
        A GameFieldChangeCommand ready to be pushed to the stack
    """
    old_value = getattr(game, field_name, None)
    # Deep copy mutable values
    if isinstance(old_value, (list, dict)):
        old_value = copy.deepcopy(old_value)
    if isinstance(new_value, (list, dict)):
        new_value = copy.deepcopy(new_value)

    return GameFieldChangeCommand(
        game=game,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        save_callback=save_callback
    )


def create_multi_field_change(
    game: "Game",
    new_values: Dict[str, Any],
    action_name: str = "Edit game",
    save_callback: Optional[Callable[[], None]] = None
) -> GameMultiFieldChangeCommand:
    """Create a multi-field change command.

    Args:
        game: The game to modify
        new_values: Dict of field_name -> new_value
        action_name: Description of the action
        save_callback: Optional callback to save after change

    Returns:
        A GameMultiFieldChangeCommand ready to be pushed to the stack
    """
    old_values = {}
    for field_name in new_values:
        old_val = getattr(game, field_name, None)
        if isinstance(old_val, (list, dict)):
            old_val = copy.deepcopy(old_val)
        old_values[field_name] = old_val

    return GameMultiFieldChangeCommand(
        game=game,
        old_values=old_values,
        new_values=new_values,
        action_name=action_name,
        save_callback=save_callback
    )


def create_batch_change(
    games: List["Game"],
    field_name: str,
    new_value: Any,
    save_callback: Optional[Callable[[], None]] = None
) -> BatchGameChangeCommand:
    """Create a batch change command.

    Args:
        games: List of games to modify
        field_name: Name of the field to change
        new_value: The new value to set on all games
        save_callback: Optional callback to save after change

    Returns:
        A BatchGameChangeCommand ready to be pushed to the stack
    """
    old_values = {}
    for game in games:
        old_val = getattr(game, field_name, None)
        if isinstance(old_val, (list, dict)):
            old_val = copy.deepcopy(old_val)
        old_values[game.game_id] = old_val

    return BatchGameChangeCommand(
        games=games,
        field_name=field_name,
        old_values=old_values,
        new_value=new_value,
        save_callback=save_callback
    )
