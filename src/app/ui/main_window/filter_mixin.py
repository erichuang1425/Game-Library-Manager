"""Filter and search operations mixin for MainWindow."""
from __future__ import annotations
from typing import TYPE_CHECKING, List

from app.models import Game
from app.services import (
    apply_collection, apply_quick_filter, apply_dropdown_filters,
    apply_search_filter, sort_games, count_quick_filter_matches,
    get_search_cache,
)
from app.ui.widgets import build_filter_chips
from app.logging_utils import kv

if TYPE_CHECKING:
    from .window import MainWindow


class FilterMixin:
    """Mixin providing filter and search operations for MainWindow."""

    def _init_search_cache(self: "MainWindow") -> None:
        """Initialize and populate the search cache from the full game list."""
        self._search_cache = get_search_cache()
        self._search_cache.build(self._all_games)

    def _invalidate_search_cache(self: "MainWindow", game_id: str) -> None:
        """Mark a single game as dirty in the search cache after edits."""
        self._search_cache.invalidate(game_id)

    def _rebuild_search_cache(self: "MainWindow") -> None:
        """Rebuild the search cache (e.g. after scan or import)."""
        self._search_cache.build(self._all_games)

    def _on_search_text_changed(self: "MainWindow") -> None:
        """Restart the debounce timer on each keystroke."""
        self._search_debounce.start()

    def _apply_search(self: "MainWindow") -> None:
        # 1) start from full list
        base = list(self._all_games)

        # 2) apply active collection filter
        if self._active_collection_id:
            c = self._get_collection(self._active_collection_id)
            if c:
                base = apply_collection(base, c)

        # quick filter counts (for pill labels)
        self._update_quick_filter_counts(base)

        # 3) apply quick filter
        base = apply_quick_filter(base, self._quick_filter)

        # 4) apply dropdown filters
        base = apply_dropdown_filters(
            base,
            status_filter=self._status_filter,
            confidence_filter=self._confidence_filter,
            type_filter=self._type_filter,
            tag_filter=self._tag_filter,
        )

        # 5) apply search text using cached haystacks
        search_text = self.search.text().strip()
        if search_text:
            self._filtered = self._search_cache.search(base, search_text)
        else:
            self._filtered = base

        # 6) sort
        self._filtered = sort_games(self._filtered, self._sort_by)

        # If the current selection was filtered out, clear selection/details
        if self._selected_game_id and not any(g.game_id == self._selected_game_id for g in self._filtered):
            self._selected_game_id = None
            if hasattr(self, "details"):
                self.details.show_game(None)
            self.add_to_collection_btn.setEnabled(False)
        if self._log_rate.allow("filter_state", 400):
            self._log.info(
                "filter_state %s",
                kv(
                    nav=self.sidebar.current_key() if hasattr(self.sidebar, "current_key") else "",
                    total=len(self._all_games),
                    filtered=len(self._filtered),
                    quick=self._quick_filter,
                    status=self._status_filter,
                    confidence=self._confidence_filter,
                    type=self._type_filter,
                    tag=self._tag_filter or "",
                    search=self.search.text().strip(),
                    sort=self._sort_by,
                ),
            )

        self._render()
        self._update_filter_chips()
        if self._tag_filter:
            from app.ui.theme import current_theme
            theme = current_theme()
            self.tag_filter_label.setStyleSheet(f"color:{theme.accent.name()}; font-weight:600;")
            self.tag_filter_label.setText(f"Tag: {self._tag_filter}")
            self.tag_filter_label.show()
            self.clear_tag_btn.setVisible(True)
        else:
            self.tag_filter_label.hide()
            self.clear_tag_btn.setVisible(False)
        if hasattr(self, "_update_filter_badge"):
            self._update_filter_badge()

    def _apply_quick_filter_buttons(self: "MainWindow") -> None:
        mapping = {
            "all": self.pill_all,
            "missing": self.pill_missing,
            "updates": self.pill_updates,
            "source": self.pill_source,
        }
        for key, btn in mapping.items():
            btn.setChecked(self._quick_filter == key)

    def _on_quick_filter(self: "MainWindow") -> None:
        sender = self.sender()
        if sender == self.pill_missing:
            self._quick_filter = "missing"
        elif sender == self.pill_updates:
            self._quick_filter = "updates"
        elif sender == self.pill_source:
            self._quick_filter = "source"
        else:
            self._quick_filter = "all"
        self._pulse_widget(sender)
        self._settings["quick_filter"] = self._quick_filter
        self._persist_settings()
        self._apply_search()

    def _on_filter_changed(self: "MainWindow") -> None:
        self._status_filter = self.status_filter.currentText().lower()
        self._confidence_filter = self.conf_filter.currentText().lower()
        self._type_filter = self.type_filter.currentText().lower()
        for key in ("status_filter", "confidence_filter", "type_filter"):
            self._settings[key] = getattr(self, f"_{key}")
        self._persist_settings()
        self._apply_search()

    def _on_status_filter_requested(self: "MainWindow", status: str) -> None:
        self._status_filter = status
        self.status_filter.setCurrentText(status.capitalize())
        self._settings["status_filter"] = status
        self._persist_settings()
        self._apply_search()

    def _on_tag_filter_requested(self: "MainWindow", tag: str) -> None:
        if self._tag_filter == tag:
            self._tag_filter = None
            self.statusBar().showMessage("Tag filter cleared", 2000)
        else:
            self._tag_filter = tag
            self.statusBar().showMessage(f"Filtered by tag: {tag}", 2000)
        if self._tag_filter:
            self._settings["tag_filter"] = self._tag_filter
        else:
            self._settings.pop("tag_filter", None)
        self._persist_settings()
        self._apply_search()

    def _clear_tag_filter(self: "MainWindow") -> None:
        self._tag_filter = None
        self.tag_filter_label.hide()
        self.clear_tag_btn.setVisible(False)
        self._settings.pop("tag_filter", None)
        self._persist_settings()
        self._apply_search()

    def _on_filter_chip_removed(self: "MainWindow", key: str) -> None:
        """Handle removal of a filter chip."""
        if key == "status":
            self._status_filter = "all"
            self.status_filter.setCurrentText("All")
        elif key == "confidence":
            self._confidence_filter = "all"
            self.conf_filter.setCurrentText("All")
        elif key == "type":
            self._type_filter = "all"
            self.type_filter.setCurrentText("All")
        elif key == "tag":
            self._tag_filter = None
            self.tag_filter_label.hide()
            self.clear_tag_btn.setVisible(False)
        elif key == "quick":
            self._quick_filter = "all"
        elif key == "search":
            self.search.clear()

        self._persist_settings()
        self._apply_search()

    def _clear_all_filters(self: "MainWindow") -> None:
        """Clear all active filters."""
        self._status_filter = "all"
        self._confidence_filter = "all"
        self._type_filter = "all"
        self._tag_filter = None
        self._quick_filter = "all"

        # Update UI
        self.status_filter.setCurrentText("All")
        self.conf_filter.setCurrentText("All")
        self.type_filter.setCurrentText("All")
        self.search.clear()
        self.tag_filter_label.hide()
        self.clear_tag_btn.setVisible(False)

        self._persist_settings()
        self._apply_search()

    def _update_filter_chips(self: "MainWindow") -> None:
        """Update the filter chips bar based on current filter state."""
        chips = build_filter_chips(
            status=self._status_filter,
            confidence=self._confidence_filter,
            type_filter=self._type_filter,
            tag=self._tag_filter,
            quick_filter=self._quick_filter,
            search_query=self.search.text().strip(),
        )
        self.filter_chips.set_filters(chips)

    def _on_sort_changed(self: "MainWindow") -> None:
        mapping = {
            "Title": "title",
            "Last Played": "last_played",
            "Rating": "rating",
            "Launch Count": "launch_count",
            "Last Checked": "last_checked",
        }
        self._sort_by = mapping.get(self.sort_combo.currentText(), "title")
        self._settings["sort_by"] = self._sort_by
        self._persist_settings()
        self._apply_search()

    def _update_quick_filter_counts(self: "MainWindow", games: List[Game]) -> None:
        counts = count_quick_filter_matches(games)
        self.pill_all.setText(f"All ({counts['all']})")
        self.pill_missing.setText(f"Missing ({counts['missing']})")
        self.pill_updates.setText(f"Updates ({counts['updates']})")
        self.pill_source.setText(f"Source ({counts['source']})")
