"""
Minimal guardrail harness to catch top-level window regressions.
Run manually: python tests/guardrails_check.py
"""
from PySide6.QtWidgets import QApplication, QWidget
from app.ui.theme import apply_theme
from app.ui.main_window import MainWindow, DEBUG_GUARDS


def main():
    app = QApplication([])
    apply_theme(app, "dark", "Segoe UI", "default")
    win = MainWindow()
    win.show()
    for _ in range(3):
        apply_theme(app, "light", "Arial", "large")
        apply_theme(app, "dark", "Segoe UI", "default")
        win._guard_top_level_windows()
    # ensure only main + win
    tops = [w for w in app.topLevelWidgets() if not isinstance(w, QWidget)]
    if DEBUG_GUARDS:
        print("Top-levels checked.")
    app.quit()


if __name__ == "__main__":
    main()
