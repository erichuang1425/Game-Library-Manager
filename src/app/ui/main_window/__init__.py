"""Main window package - modular MainWindow implementation.

This package splits the large MainWindow class into focused mixins:
- scan_mixin.py: Scan operations (~200 lines)
- update_mixin.py: Update check operations (~120 lines)
- filter_mixin.py: Filter and search operations (~200 lines)
- dialog_mixin.py: Dialog management (~230 lines)
- collection_mixin.py: Collection operations (~200 lines)
- game_ops_mixin.py: Game CRUD operations (~230 lines)
- actions_mixin.py: Keyboard shortcuts, export/import (~170 lines)
- ui_mixin.py: UI helpers, startup overlay (~230 lines)
- batch_mixin.py: Multi-select batch operations (~80 lines)
- window.py: Core MainWindow combining all mixins (~450 lines)

Total: ~2100 lines (down from ~2364 lines original through deduplication)
"""

from .window import MainWindow, DEBUG_GUARDS

__all__ = ["MainWindow", "DEBUG_GUARDS"]
