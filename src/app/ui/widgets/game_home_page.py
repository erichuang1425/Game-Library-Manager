"""Game Homepage widget - a rich, scrollable detail page for a single game.

Displays:
- Hero banner image fetched from source thread with gradient fallback
- Game icon overlapping the banner with title, developer, version, category
- Rating (interactive stars), status badge, stats row
- Description / overview from F95zone
- Tags (genre chips) in a flow layout
- Download links grouped by host with priority indicators
- Technical details (paths, shortcut info) in collapsible section
- Changelog in collapsible section
- Cheat codes in collapsible section
- Extra downloads (walkthroughs, mods, saves) in collapsible section
- Custom XPath-extracted content in collapsible section
"""
from __future__ import annotations

import webbrowser
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QThread
from PySide6.QtGui import (
    QColor, QPixmap, QDesktopServices, QCursor,
    QPainter, QLinearGradient, QBrush, QPen,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QGridLayout, QMenu,
    QGraphicsDropShadowEffect, QApplication, QSpacerItem,
)

from app.models import Game
from app.models.custom_paths import CustomXPaths, F95_DEFAULT_XPATHS
from app.services import pixmap_for_game, best_icon_path
from app.services.banner_cache import (
    get_cached_banner, fetch_and_cache_banner, scaled_banner,
    BannerFetchWorker,
)
from app.services.f95_api import (
    ThreadInfo, DownloadLink, ExtraLink,
    get_host_display_info, get_best_download_link,
    group_download_links_by_host,
)
from app.services.version_parser import parse_version, compare_versions, CompareResult
from app.ui.theme import (
    current_theme, primary_btn_style, secondary_btn_style,
    ghost_btn_style, chip_style, card_style, status_color,
    collapsible_header_style,
)
from app.ui.icons import AppIcons
from app.ui.widgets.game_grid.display_utils import (
    status_label, stars, relative_time,
)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_BANNER_HEIGHT = 280
_ICON_SIZE = 108
_ICON_OVERLAP = 54   # How far the icon overlaps into the banner


class _BannerWidget(QWidget):
    """Custom widget that paints a banner image with gradient overlay.

    If a pixmap is set, it fills the widget with a cropped/scaled image
    and applies a cinematic bottom-fade gradient so text is readable.
    Otherwise it draws the ambient color gradient fallback.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._ambient_color: QColor = QColor(100, 160, 255)
        self._bg_color: QColor = QColor(14, 16, 20)
        self.setFixedHeight(_BANNER_HEIGHT)

    def set_banner(self, pixmap: Optional[QPixmap]) -> None:
        self._pixmap = pixmap
        self.update()

    def set_colors(self, ambient: QColor, bg: QColor) -> None:
        self._ambient_color = ambient
        self._bg_color = bg
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()

        if self._pixmap and not self._pixmap.isNull():
            # Draw the banner image cropped to fill
            scaled = scaled_banner(self._pixmap, w, h)
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)

            # Cinematic bottom-fade gradient overlay for readability
            fade = QLinearGradient(0, 0, 0, h)
            fade.setColorAt(0.0, QColor(0, 0, 0, 0))
            fade.setColorAt(0.4, QColor(0, 0, 0, 0))
            fade.setColorAt(0.75, QColor(
                self._bg_color.red(), self._bg_color.green(),
                self._bg_color.blue(), 180,
            ))
            fade.setColorAt(1.0, QColor(
                self._bg_color.red(), self._bg_color.green(),
                self._bg_color.blue(), 240,
            ))
            p.fillRect(0, 0, w, h, QBrush(fade))

            # Subtle top vignette
            top_fade = QLinearGradient(0, 0, 0, h // 3)
            top_fade.setColorAt(0.0, QColor(0, 0, 0, 80))
            top_fade.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(0, 0, w, h // 3, QBrush(top_fade))
        else:
            # Fallback: ambient color gradient
            grad = QLinearGradient(0, 0, w, h)
            ac = self._ambient_color
            grad.setColorAt(0.0, QColor(ac.red(), ac.green(), ac.blue(), 90))
            grad.setColorAt(0.35, QColor(ac.red(), ac.green(), ac.blue(), 50))
            grad.setColorAt(1.0, self._bg_color)
            p.fillRect(0, 0, w, h, QBrush(grad))

            # Decorative radial highlight
            highlight = QLinearGradient(0, 0, w * 0.7, h * 0.5)
            highlight.setColorAt(0.0, QColor(ac.red(), ac.green(), ac.blue(), 40))
            highlight.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(0, 0, w, h, QBrush(highlight))

        p.end()


class GameHomePage(QWidget):
    """Full-page game homepage with rich detail sections."""

    play_clicked = Signal(str)          # game_id
    back_clicked = Signal()             # navigate back to grid
    game_changed = Signal(str)          # game_id (when edits are made)
    download_requested = Signal(str, str)  # game_id, download_url
    rating_changed = Signal(str, object)   # game_id, rating or None
    open_source_clicked = Signal(str)   # game_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._game: Optional[Game] = None
        self._thread_info: Optional[ThreadInfo] = None
        self._custom_xpaths: Optional[CustomXPaths] = None
        self._section_btns: List[QPushButton] = []
        self._banner_widget: Optional[_BannerWidget] = None
        self._fetch_thread: Optional[QThread] = None
        self._fetch_worker: Optional[BannerFetchWorker] = None

        self._build_ui()

    def _build_ui(self) -> None:
        theme = current_theme()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Scrollable content (back button is now an overlay on the banner) --
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {theme.bg.name(QColor.HexArgb)}; border: none; }}"
        )

        self._content = QWidget()
        self._content.setStyleSheet(
            f"background: {theme.bg.name(QColor.HexArgb)};"
        )
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, theme.spacing_xl)
        self._layout.setSpacing(0)

        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

        # Floating back button (drawn on top of banner)
        self._back_btn = QPushButton(f"{AppIcons.UI_ARROW_LEFT}  Back")
        self._back_btn.setParent(scroll)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background: rgba(0,0,0,120); "
            f"color: #ffffff; "
            f"border: 1px solid rgba(255,255,255,30); "
            f"border-radius: {theme.radius_md}px; "
            f"padding: 6px 16px; "
            f"font-weight: 600; font-size: 13px; "
            f"}} "
            f"QPushButton:hover {{ background: rgba(0,0,0,180); "
            f"border-color: rgba(255,255,255,60); }}"
        )
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_clicked.emit)
        self._back_btn.move(theme.spacing_md, theme.spacing_md)
        self._back_btn.raise_()

        # Floating source page button
        self._source_btn = QPushButton("Open Source Page")
        self._source_btn.setParent(scroll)
        self._source_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background: rgba(0,0,0,120); "
            f"color: #ffffff; "
            f"border: 1px solid rgba(255,255,255,30); "
            f"border-radius: {theme.radius_md}px; "
            f"padding: 6px 16px; "
            f"font-weight: 500; font-size: 12px; "
            f"}} "
            f"QPushButton:hover {{ background: rgba(0,0,0,180); "
            f"border-color: rgba(255,255,255,60); }}"
        )
        self._source_btn.setCursor(Qt.PointingHandCursor)
        self._source_btn.setVisible(False)
        self._source_btn.clicked.connect(self._on_open_source)
        self._source_btn.raise_()

        # Position the source button on resize
        self._scroll = scroll

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition_floating_buttons()

    def _reposition_floating_buttons(self) -> None:
        theme = current_theme()
        self._back_btn.move(theme.spacing_md, theme.spacing_md)
        # Source button at top-right
        if self._source_btn.isVisible():
            btn_w = self._source_btn.sizeHint().width()
            self._source_btn.move(
                self._scroll.width() - btn_w - theme.spacing_md - 12,
                theme.spacing_md,
            )

    def show_game(
        self,
        game: Game,
        thread_info: Optional[ThreadInfo] = None,
        custom_xpaths: Optional[CustomXPaths] = None,
    ) -> None:
        """Populate the homepage with game data."""
        self._game = game
        self._thread_info = thread_info
        self._custom_xpaths = custom_xpaths or F95_DEFAULT_XPATHS
        self._section_btns.clear()
        self._rebuild_content()

    def set_banner_pixmap(self, game_id: str, pixmap: Optional[QPixmap]) -> None:
        """Called when a banner image has been fetched (may be from background thread)."""
        if self._game and self._game.game_id == game_id and self._banner_widget:
            self._banner_widget.set_banner(pixmap)

    def _rebuild_content(self) -> None:
        """Clear and rebuild all content sections."""
        layout = self._layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

        if not self._game:
            return

        theme = current_theme()
        game = self._game
        info = self._thread_info

        # Source button visibility
        if game.source_url:
            self._source_btn.setVisible(True)
        else:
            self._source_btn.setVisible(False)
        QTimer.singleShot(0, self._reposition_floating_buttons)

        # 1. Banner / Hero section with real image
        self._build_banner_section(layout, theme, game, info)

        # 2. Overlapping header area (icon + title + meta)
        #    This creates the overlap effect where the icon sits on the banner edge
        self._build_hero_header(layout, theme, game, info)

        # Content wrapper with generous padding
        content_wrapper = QWidget()
        content_wrapper.setStyleSheet(
            f"background: transparent;"
        )
        cw_layout = QVBoxLayout(content_wrapper)
        cw_layout.setContentsMargins(
            theme.spacing_xl + 8, theme.spacing_sm,
            theme.spacing_xl + 8, theme.spacing_lg,
        )
        cw_layout.setSpacing(theme.spacing_xl)

        # 3. Stats row (rating, status, last played, etc.)
        self._build_stats_row(cw_layout, theme, game, info)

        # 4. Action buttons row
        self._build_action_row(cw_layout, theme, game, info)

        # 5. Description / Overview in a card
        self._build_description_section(cw_layout, theme, game, info)

        # 6. Tags / Genre
        self._build_tags_section(cw_layout, theme, game, info)

        # 7. Download links
        if info and info.download_links:
            self._build_downloads_section(cw_layout, theme, game, info)

        # 8. Changelog (collapsible)
        changelog = (info.changelog if info else "") or ""
        if changelog:
            self._build_collapsible_text(
                cw_layout, theme, "CHANGELOG", changelog
            )

        # 9. Cheat Codes (collapsible)
        cheat_codes = (info.cheat_codes if info else "") or ""
        if cheat_codes:
            self._build_collapsible_text(
                cw_layout, theme, "CHEAT CODES", cheat_codes
            )

        # 10. Extras (walkthroughs, mods, saves)
        extras = (info.extras if info else []) or []
        if extras:
            self._build_extras_section(cw_layout, theme, extras)

        # 11. Technical Details (collapsible, less prominent)
        self._build_technical_section(cw_layout, theme, game, info)

        # 12. Custom XPath content (collapsible)
        if self._custom_xpaths and self._custom_xpaths.custom:
            self._build_custom_section(cw_layout, theme)

        layout.addWidget(content_wrapper)
        layout.addStretch(1)

    # ================================================================
    #  Section builders
    # ================================================================

    def _build_banner_section(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the hero banner with real image or gradient fallback."""
        banner = _BannerWidget()
        self._banner_widget = banner

        # Set ambient color
        color_hex = game.dominant_color_hex or theme.accent.name()
        ambient = QColor(color_hex) if color_hex else theme.accent
        banner.set_colors(ambient, theme.bg)

        # Try to load cached banner image immediately
        banner_url = ""
        if game.banner_url:
            banner_url = game.banner_url
        elif info and info.banner_url:
            banner_url = info.banner_url

        if banner_url:
            # Try cached first (instant, no network)
            cached_pm = get_cached_banner(banner_url)
            if cached_pm and not cached_pm.isNull():
                banner.set_banner(cached_pm)
            else:
                # Start background fetch
                self._start_banner_fetch(game.game_id, banner_url)

        layout.addWidget(banner)

    def _start_banner_fetch(self, game_id: str, url: str) -> None:
        """Fetch banner image in a background thread."""
        # Clean up any previous fetch
        self._cleanup_fetch_thread()

        self._fetch_thread = QThread()
        self._fetch_worker = BannerFetchWorker(game_id, url)
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_banner_fetched)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_thread.start()

    def _on_banner_fetched(self, game_id: str, pixmap: object) -> None:
        """Handle banner fetch completion."""
        if pixmap and isinstance(pixmap, QPixmap) and not pixmap.isNull():
            self.set_banner_pixmap(game_id, pixmap)
            # Store the URL on the game model for future cache hits
            if self._game and self._game.game_id == game_id:
                banner_url = ""
                if self._thread_info and self._thread_info.banner_url:
                    banner_url = self._thread_info.banner_url
                elif self._game.banner_url:
                    banner_url = self._game.banner_url
                if banner_url:
                    self._game.banner_url = banner_url
        self._cleanup_fetch_thread()

    def _cleanup_fetch_thread(self) -> None:
        """Clean up background fetch resources."""
        if self._fetch_thread and self._fetch_thread.isRunning():
            self._fetch_thread.quit()
            self._fetch_thread.wait(2000)
        self._fetch_thread = None
        self._fetch_worker = None

    def _build_hero_header(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the overlapping hero header with icon, title, and metadata.

        This section overlaps the bottom of the banner by using negative margin,
        creating a modern app-store style layout.
        """
        # Container with negative top margin to overlap banner
        header_container = QWidget()
        header_container.setStyleSheet("background: transparent;")
        hc_layout = QVBoxLayout(header_container)
        hc_layout.setContentsMargins(
            theme.spacing_xl + 8, 0,
            theme.spacing_xl + 8, 0,
        )
        hc_layout.setSpacing(theme.spacing_sm)

        # -- Icon + Title row --
        header_row = QHBoxLayout()
        header_row.setSpacing(theme.spacing_lg)

        # Game icon (large, with ring and shadow)
        icon_frame = QFrame()
        icon_frame.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        icon_frame.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_xl}px; "
            f"border: 3px solid {theme.surface_raised.name(QColor.HexArgb)}; "
            f"}}"
        )
        icon_inner = QVBoxLayout(icon_frame)
        icon_inner.setContentsMargins(4, 4, 4, 4)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_sz = _ICON_SIZE - 14  # account for border + padding
        pm = pixmap_for_game(game, icon_sz)
        if pm and not pm.isNull():
            scaled = pm.scaled(
                QSize(icon_sz, icon_sz), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon_label.setPixmap(scaled)
        icon_inner.addWidget(icon_label)

        # Drop shadow on the icon
        shadow = QGraphicsDropShadowEffect(icon_frame)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 100))
        icon_frame.setGraphicsEffect(shadow)

        header_row.addWidget(icon_frame)

        # Title + meta column
        meta_col = QVBoxLayout()
        meta_col.setSpacing(6)

        # Title (large, bold)
        title_lbl = QLabel(game.title)
        title_lbl.setStyleSheet(
            f"font-size: 26px; font-weight: 800; "
            f"color: {theme.text.name()}; "
            f"background: transparent; border: none; "
            f"letter-spacing: -0.3px;"
        )
        title_lbl.setWordWrap(True)
        meta_col.addWidget(title_lbl)

        # Developer + version + category badges row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(theme.spacing_sm)

        developer = (info.developer if info else "") or game.developer or ""
        if developer:
            dev_lbl = QLabel(f"by {developer}")
            dev_lbl.setStyleSheet(
                f"font-size: 14px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none; "
                f"font-weight: 500;"
            )
            meta_row.addWidget(dev_lbl)

        # Version badge
        version = game.installed_version_raw or (info.version if info else "") or ""
        if version:
            ver_badge = QLabel(f"  v{version}  ")
            ver_badge.setStyleSheet(
                f"font-size: 11px; color: {theme.bg.name()}; "
                f"background: {theme.accent.name()}; "
                f"border-radius: {theme.radius_sm + 2}px; "
                f"padding: 3px 10px; font-weight: 700; border: none;"
            )
            meta_row.addWidget(ver_badge)

        # Update indicator
        if info and info.version and game.installed_version_raw:
            inst_vi = parse_version(game.installed_version_raw)
            src_vi = parse_version(info.version)
            cmp = compare_versions(inst_vi, src_vi)
            if cmp == CompareResult.OLDER:
                upd_badge = QLabel(f" {AppIcons.STS_UPDATE} Update available: v{info.version} ")
                upd_badge.setStyleSheet(
                    f"font-size: 11px; color: {theme.bg.name()}; "
                    f"background: {theme.warning.name()}; "
                    f"border-radius: {theme.radius_sm + 2}px; "
                    f"padding: 3px 10px; font-weight: 700; border: none;"
                )
                meta_row.addWidget(upd_badge)

        # Category badge
        category = (info.category if info else "") or game.f95_category or ""
        if category:
            cat_colors = {
                "completed": theme.success,
                "ongoing": theme.accent,
                "abandoned": theme.error,
                "on hold": theme.warning,
            }
            cat_color = cat_colors.get(category.lower(), theme.text_muted)
            cat_badge = QLabel(f"  {category}  ")
            cat_badge.setStyleSheet(
                f"font-size: 11px; color: {cat_color.name()}; "
                f"border: 1px solid {cat_color.name()}; "
                f"border-radius: {theme.radius_sm + 2}px; "
                f"padding: 3px 10px; font-weight: 600; background: transparent;"
            )
            meta_row.addWidget(cat_badge)

        meta_row.addStretch(1)
        meta_col.addLayout(meta_row)

        header_row.addLayout(meta_col, 1)
        hc_layout.addLayout(header_row)

        layout.addWidget(header_container)

    def _build_stats_row(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build a visually distinct stats bar with rating, status, and metadata."""
        stats_card = QFrame()
        stats_card.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"}}"
        )
        stats_inner = QHBoxLayout(stats_card)
        stats_inner.setContentsMargins(
            theme.spacing_lg, theme.spacing_md,
            theme.spacing_lg, theme.spacing_md,
        )
        stats_inner.setSpacing(theme.spacing_xl)

        # -- Rating stars --
        rating_box = QVBoxLayout()
        rating_box.setSpacing(2)

        rating_label = QLabel("RATING")
        rating_label.setStyleSheet(
            f"font-size: 9px; font-weight: 700; letter-spacing: 1px; "
            f"color: {theme.text_muted.name()}; "
            f"background: transparent; border: none;"
        )
        rating_box.addWidget(rating_label)

        stars_row = QHBoxLayout()
        stars_row.setSpacing(2)
        self._star_buttons = []
        current_rating = game.rating or 0
        stars_filled = max(0, min(5, round(current_rating / 2)))

        for i in range(5):
            star_btn = QPushButton("\u2605" if i < stars_filled else "\u2606")
            star_btn.setFlat(True)
            star_btn.setCursor(Qt.PointingHandCursor)
            star_btn.setFixedSize(28, 28)
            filled_color = theme.accent.name() if i < stars_filled else theme.text_muted.name()
            star_btn.setStyleSheet(
                f"QPushButton {{ font-size: 18px; color: {filled_color}; "
                f"background: transparent; border: none; padding: 0; }}"
                f"QPushButton:hover {{ color: {theme.accent.lighter(120).name()}; }}"
            )
            star_value = (i + 1) * 2
            star_btn.clicked.connect(
                lambda checked, val=star_value: self._on_rating_clicked(val)
            )
            star_btn.setToolTip(f"Rate {star_value}/10")
            self._star_buttons.append(star_btn)
            stars_row.addWidget(star_btn)

        if current_rating:
            rating_num = QLabel(f"{current_rating}/10")
            rating_num.setStyleSheet(
                f"font-size: 13px; font-weight: 700; "
                f"color: {theme.accent.name()}; "
                f"background: transparent; border: none;"
            )
            stars_row.addWidget(rating_num)

        rating_box.addLayout(stars_row)
        stats_inner.addLayout(rating_box)

        # Vertical divider
        stats_inner.addWidget(self._vertical_divider(theme))

        # -- Status badge --
        status_box = QVBoxLayout()
        status_box.setSpacing(2)
        status_header = QLabel("STATUS")
        status_header.setStyleSheet(
            f"font-size: 9px; font-weight: 700; letter-spacing: 1px; "
            f"color: {theme.text_muted.name()}; "
            f"background: transparent; border: none;"
        )
        status_box.addWidget(status_header)

        sc = status_color(theme, game.status)
        status_badge = QLabel(f"  {status_label(game.status)}  ")
        status_badge.setStyleSheet(
            f"font-size: 12px; color: {theme.bg.name()}; "
            f"background: {sc.name()}; "
            f"border-radius: {theme.radius_sm + 2}px; "
            f"padding: 4px 14px; font-weight: 700; border: none;"
        )
        status_box.addWidget(status_badge)
        stats_inner.addLayout(status_box)

        # Vertical divider
        stats_inner.addWidget(self._vertical_divider(theme))

        # -- Last played --
        lp = relative_time(game.last_played)
        if lp:
            lp_box = QVBoxLayout()
            lp_box.setSpacing(2)
            lp_header = QLabel("LAST PLAYED")
            lp_header.setStyleSheet(
                f"font-size: 9px; font-weight: 700; letter-spacing: 1px; "
                f"color: {theme.text_muted.name()}; "
                f"background: transparent; border: none;"
            )
            lp_box.addWidget(lp_header)
            lp_val = QLabel(lp)
            lp_val.setStyleSheet(
                f"font-size: 13px; font-weight: 600; "
                f"color: {theme.text.name()}; "
                f"background: transparent; border: none;"
            )
            lp_box.addWidget(lp_val)
            stats_inner.addLayout(lp_box)
            stats_inner.addWidget(self._vertical_divider(theme))

        # -- Launch count --
        if game.launch_count > 0:
            lc_box = QVBoxLayout()
            lc_box.setSpacing(2)
            lc_header = QLabel("PLAYS")
            lc_header.setStyleSheet(
                f"font-size: 9px; font-weight: 700; letter-spacing: 1px; "
                f"color: {theme.text_muted.name()}; "
                f"background: transparent; border: none;"
            )
            lc_box.addWidget(lc_header)
            lc_val = QLabel(str(game.launch_count))
            lc_val.setStyleSheet(
                f"font-size: 13px; font-weight: 600; "
                f"color: {theme.text.name()}; "
                f"background: transparent; border: none;"
            )
            lc_box.addWidget(lc_val)
            stats_inner.addLayout(lc_box)
            stats_inner.addWidget(self._vertical_divider(theme))

        # -- Thread stats (likes / replies) --
        if info:
            if info.likes > 0:
                likes_box = QVBoxLayout()
                likes_box.setSpacing(2)
                likes_header = QLabel("LIKES")
                likes_header.setStyleSheet(
                    f"font-size: 9px; font-weight: 700; letter-spacing: 1px; "
                    f"color: {theme.text_muted.name()}; "
                    f"background: transparent; border: none;"
                )
                likes_box.addWidget(likes_header)
                likes_val = QLabel(f"\u2764 {info.likes:,}")
                likes_val.setStyleSheet(
                    f"font-size: 13px; font-weight: 600; "
                    f"color: {theme.accent_alt.name()}; "
                    f"background: transparent; border: none;"
                )
                likes_box.addWidget(likes_val)
                stats_inner.addLayout(likes_box)
                stats_inner.addWidget(self._vertical_divider(theme))

            if info.replies > 0:
                rep_box = QVBoxLayout()
                rep_box.setSpacing(2)
                rep_header = QLabel("REPLIES")
                rep_header.setStyleSheet(
                    f"font-size: 9px; font-weight: 700; letter-spacing: 1px; "
                    f"color: {theme.text_muted.name()}; "
                    f"background: transparent; border: none;"
                )
                rep_box.addWidget(rep_header)
                rep_val = QLabel(f"{info.replies:,}")
                rep_val.setStyleSheet(
                    f"font-size: 13px; font-weight: 600; "
                    f"color: {theme.text.name()}; "
                    f"background: transparent; border: none;"
                )
                rep_box.addWidget(rep_val)
                stats_inner.addLayout(rep_box)

        stats_inner.addStretch(1)
        layout.addWidget(stats_card)

    def _build_action_row(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the primary action buttons row."""
        action_row = QHBoxLayout()
        action_row.setSpacing(theme.spacing_md)

        # Play button (large, primary, prominent)
        play_btn = QPushButton(f"{AppIcons.ACT_PLAY}  Play Now")
        play_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background: {theme.accent.name()}; "
            f"color: {theme.bg.name()}; "
            f"border: none; "
            f"border-radius: {theme.radius_lg}px; "
            f"padding: 12px 32px; "
            f"font-weight: 700; font-size: 15px; "
            f"}} "
            f"QPushButton:hover {{ background: {theme.accent.lighter(112).name()}; }} "
            f"QPushButton:pressed {{ background: {theme.accent.darker(110).name()}; }}"
        )
        play_btn.setCursor(Qt.PointingHandCursor)
        play_btn.setMinimumHeight(48)
        play_btn.setMinimumWidth(160)
        play_btn.clicked.connect(
            lambda: self.play_clicked.emit(game.game_id) if self._game else None
        )
        action_row.addWidget(play_btn)

        # Download button (secondary, if links available)
        if info and info.download_links:
            best = get_best_download_link(info.download_links)
            if best:
                host_info = get_host_display_info(best.host_type)
                dl_btn = QPushButton(
                    f"{AppIcons.ACT_DOWNLOAD}  Download ({host_info['name']})"
                )
                dl_btn.setStyleSheet(secondary_btn_style(theme))
                dl_btn.setCursor(Qt.PointingHandCursor)
                dl_btn.setMinimumHeight(48)
                dl_btn.clicked.connect(
                    lambda: self._on_download_clicked(best.url)
                )
                dl_btn.setToolTip(f"Download from {host_info['name']}")
                action_row.addWidget(dl_btn)

        # Open folder button (ghost)
        if game.shortcut_path or game.game_folder_path:
            folder_btn = QPushButton(f"Open Folder")
            folder_btn.setStyleSheet(ghost_btn_style(theme))
            folder_btn.setCursor(Qt.PointingHandCursor)
            folder_btn.setMinimumHeight(48)
            folder_btn.clicked.connect(
                lambda: self._open_game_folder(game)
            )
            action_row.addWidget(folder_btn)

        action_row.addStretch(1)
        layout.addLayout(action_row)

    def _build_description_section(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the description/overview section in a card."""
        description = ""
        if info and info.description:
            description = info.description
        elif info and info.overview:
            description = info.overview
        elif game.notes:
            description = game.notes

        if not description:
            return

        layout.addWidget(self._section_label("ABOUT THIS GAME", theme))

        desc_frame = QFrame()
        desc_frame.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"}}"
        )
        desc_inner = QVBoxLayout(desc_frame)
        desc_inner.setContentsMargins(
            theme.spacing_xl, theme.spacing_lg,
            theme.spacing_xl, theme.spacing_lg,
        )

        desc_label = QLabel(description[:3000])
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"font-size: 13px; color: {theme.text.name()}; "
            f"line-height: 1.7; background: transparent; border: none;"
        )
        desc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        desc_inner.addWidget(desc_label)

        layout.addWidget(desc_frame)

    def _build_tags_section(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the tags / genre chips section using a flow layout."""
        all_tags = []
        if game.tags:
            all_tags.extend(game.tags)
        if game.f95_tags:
            for t in game.f95_tags:
                if t not in all_tags:
                    all_tags.append(t)
        if info and info.genre_tags:
            for t in info.genre_tags:
                if t not in all_tags:
                    all_tags.append(t)
        if info and info.tags:
            for t in info.tags:
                if t not in all_tags:
                    all_tags.append(t)

        if not all_tags:
            return

        layout.addWidget(self._section_label("TAGS & GENRE", theme))

        # Flow layout via wrapping QWidget
        tags_container = QWidget()
        tags_container.setStyleSheet("background: transparent;")
        tags_flow = _FlowLayout(tags_container)
        tags_flow.setSpacing(8)

        genre_set = set(info.genre_tags) if info and info.genre_tags else set()
        user_set = set(game.tags) if game.tags else set()

        for tag in all_tags[:25]:
            chip = QLabel(f"  {tag}  ")
            if tag in genre_set:
                chip.setStyleSheet(
                    f"font-size: 12px; color: {theme.accent.name()}; "
                    f"background: rgba({theme.accent.red()},{theme.accent.green()},"
                    f"{theme.accent.blue()},30); "
                    f"border-radius: {theme.radius_sm + 2}px; "
                    f"padding: 4px 12px; font-weight: 600; border: none;"
                )
            elif tag in user_set:
                chip.setStyleSheet(
                    f"font-size: 12px; color: {theme.text.name()}; "
                    f"background: {theme.chip_bg.name(QColor.HexArgb)}; "
                    f"border-radius: {theme.radius_sm + 2}px; "
                    f"padding: 4px 12px; font-weight: 500; "
                    f"border: 1px solid {theme.chip_border.name(QColor.HexArgb)};"
                )
            else:
                chip.setStyleSheet(
                    f"font-size: 12px; color: {theme.text_muted.name()}; "
                    f"background: {theme.surface_alt.name(QColor.HexArgb)}; "
                    f"border-radius: {theme.radius_sm + 2}px; "
                    f"padding: 4px 12px; border: none;"
                )
            chip.setToolTip(tag)
            tags_flow.addWidget(chip)

        if len(all_tags) > 25:
            more = QLabel(f" +{len(all_tags) - 25} more ")
            more.setStyleSheet(
                f"font-size: 12px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none; "
                f"font-style: italic;"
            )
            tags_flow.addWidget(more)

        layout.addWidget(tags_container)

    def _build_downloads_section(
        self, layout: QVBoxLayout, theme, game: Game, info: ThreadInfo
    ) -> None:
        """Build the download links section grouped by host."""
        layout.addWidget(self._section_label("DOWNLOADS", theme))

        groups = group_download_links_by_host(info.download_links)

        dl_frame = QFrame()
        dl_frame.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"}}"
        )
        dl_inner = QVBoxLayout(dl_frame)
        dl_inner.setContentsMargins(
            theme.spacing_lg, theme.spacing_lg,
            theme.spacing_lg, theme.spacing_lg,
        )
        dl_inner.setSpacing(theme.spacing_md)

        first = True
        for host_type, links in sorted(groups.items(), key=lambda x: x[1][0].priority):
            if not first:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setFixedHeight(1)
                sep.setStyleSheet(
                    f"background: {theme.outline.name(QColor.HexArgb)}; border: none;"
                )
                dl_inner.addWidget(sep)
            first = False

            host_info = get_host_display_info(host_type)

            # Host header row
            host_row = QHBoxLayout()
            host_row.setSpacing(theme.spacing_sm)

            host_name = QLabel(host_info["name"])
            host_name.setStyleSheet(
                f"font-size: 14px; font-weight: 700; color: {theme.text.name()}; "
                f"background: transparent; border: none;"
            )
            host_row.addWidget(host_name)

            priority = host_info["priority"]
            if priority <= 3:
                prio_badge = QLabel("  Recommended  ")
                prio_badge.setStyleSheet(
                    f"font-size: 10px; color: {theme.bg.name()}; "
                    f"background: {theme.success.name()}; "
                    f"border-radius: {theme.radius_sm}px; "
                    f"padding: 2px 8px; font-weight: 700; border: none;"
                )
                host_row.addWidget(prio_badge)
            elif priority > 6:
                prio_badge = QLabel("  Slower  ")
                prio_badge.setStyleSheet(
                    f"font-size: 10px; color: {theme.warning.name()}; "
                    f"background: transparent; font-weight: 600; border: none;"
                )
                host_row.addWidget(prio_badge)

            if host_info.get("has_limit"):
                limit_lbl = QLabel("has limits")
                limit_lbl.setStyleSheet(
                    f"font-size: 10px; color: {theme.text_muted.name()}; "
                    f"background: transparent; border: none; font-style: italic;"
                )
                host_row.addWidget(limit_lbl)

            host_row.addStretch(1)
            dl_inner.addLayout(host_row)

            for link in links[:5]:
                link_row = QHBoxLayout()
                link_row.setSpacing(theme.spacing_sm)

                label_text = link.label or link.host_type.title()
                if link.file_size:
                    label_text += f" ({link.file_size})"

                link_btn = QPushButton(f"{AppIcons.ACT_DOWNLOAD}  {label_text}")
                link_btn.setStyleSheet(ghost_btn_style(theme))
                link_btn.setCursor(Qt.PointingHandCursor)
                link_btn.setToolTip(link.url)
                link_btn.clicked.connect(
                    lambda checked, url=link.url: self._on_download_clicked(url)
                )
                link_row.addWidget(link_btn)

                if not link.is_available:
                    unavail = QLabel("Unavailable")
                    unavail.setStyleSheet(
                        f"font-size: 10px; color: {theme.error.name()}; "
                        f"background: transparent; border: none; font-weight: 600;"
                    )
                    link_row.addWidget(unavail)

                link_row.addStretch(1)
                dl_inner.addLayout(link_row)

        layout.addWidget(dl_frame)

    def _build_extras_section(
        self, layout: QVBoxLayout, theme, extras: List[ExtraLink]
    ) -> None:
        """Build the extras section (walkthroughs, mods, saves)."""
        header_btn = self._collapsible_header("EXTRAS (Walkthroughs, Mods, Saves)", theme)
        layout.addWidget(header_btn)

        extras_frame = QFrame()
        extras_frame.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"}}"
        )
        extras_inner = QVBoxLayout(extras_frame)
        extras_inner.setContentsMargins(
            theme.spacing_lg, theme.spacing_lg,
            theme.spacing_lg, theme.spacing_lg,
        )
        extras_inner.setSpacing(theme.spacing_sm)

        categories: Dict[str, List[ExtraLink]] = {}
        for extra in extras:
            cat = extra.category or "other"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(extra)

        cat_icons = {
            "walkthrough": "\U0001F4D6",
            "mod": "\U0001F527",
            "save": "\U0001F4BE",
            "cheat": "\U0001F3AE",
            "other": "\U0001F4E6",
        }

        for cat, cat_extras in categories.items():
            icon = cat_icons.get(cat, "\U0001F4E6")
            cat_label = QLabel(f"{icon}  {cat.title()}")
            cat_label.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: {theme.text.name()}; "
                f"background: transparent; border: none;"
            )
            extras_inner.addWidget(cat_label)

            for extra in cat_extras[:10]:
                link_row = QHBoxLayout()
                link_btn = QPushButton(
                    f"{AppIcons.ACT_DOWNLOAD}  {extra.label or extra.url[:60]}"
                )
                link_btn.setStyleSheet(ghost_btn_style(theme))
                link_btn.setCursor(Qt.PointingHandCursor)
                link_btn.setToolTip(extra.url)
                link_btn.clicked.connect(
                    lambda checked, url=extra.url: self._on_extra_download(url)
                )
                link_row.addWidget(link_btn)
                link_row.addStretch(1)
                extras_inner.addLayout(link_row)

        header_btn._section_widgets = [extras_frame]
        layout.addWidget(extras_frame)

    def _build_technical_section(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the technical details section (paths, shortcut info)."""
        header_btn = self._collapsible_header("TECHNICAL DETAILS", theme)
        layout.addWidget(header_btn)

        tech_frame = QFrame()
        tech_frame.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"}}"
        )
        tech_inner = QGridLayout(tech_frame)
        tech_inner.setContentsMargins(
            theme.spacing_lg, theme.spacing_lg,
            theme.spacing_lg, theme.spacing_lg,
        )
        tech_inner.setSpacing(theme.spacing_sm)
        tech_inner.setColumnStretch(1, 1)

        row = 0

        def add_row(label: str, value: str) -> None:
            nonlocal row
            if not value:
                return
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"font-size: 11px; color: {theme.text_muted.name()}; "
                f"font-weight: 700; background: transparent; border: none; "
                f"letter-spacing: 0.5px;"
            )
            val = QLabel(value)
            val.setStyleSheet(
                f"font-size: 11px; color: {theme.text.name()}; "
                f"background: transparent; border: none;"
            )
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            tech_inner.addWidget(lbl, row, 0, Qt.AlignTop)
            tech_inner.addWidget(val, row, 1)
            row += 1

        add_row("Game ID", game.game_id)
        add_row("Shortcut Type", game.shortcut_type.upper() if game.shortcut_type else "")
        add_row("Shortcut Path", game.shortcut_path)
        add_row("Target Path", game.backup_target_path)
        add_row("Working Dir", game.backup_working_dir)
        add_row("Arguments", game.backup_args)
        add_row("Install Path", game.install_path)
        add_row("Executable", game.executable_path)
        add_row("Game Folder", game.game_folder_path)
        add_row("Archive Folder", game.archive_folder_path)
        add_row("Compressed Archive", game.compressed_archive_path)
        add_row("Save Folder", game.save_folder_path)
        add_row("Source URL", game.source_url)
        add_row("F95 Thread ID", str(game.f95_thread_id) if game.f95_thread_id else "")
        add_row("Installed Version", game.installed_version_raw)
        add_row("Source Version", game.source_version_raw)
        add_row("Confidence", game.confidence)
        add_row("Download Host", game.download_host)

        # Start collapsed
        tech_frame.hide()
        header_btn._collapsed = True
        header_btn._section_widgets = [tech_frame]
        header_btn.setText(f"\u25B8  TECHNICAL DETAILS")

        layout.addWidget(tech_frame)

    def _build_custom_section(
        self, layout: QVBoxLayout, theme
    ) -> None:
        """Build section for custom XPath-extracted content."""
        if not self._custom_xpaths or not self._custom_xpaths.custom:
            return

        header_btn = self._collapsible_header("CUSTOM DATA", theme)
        layout.addWidget(header_btn)

        custom_frame = QFrame()
        custom_frame.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"}}"
        )
        custom_inner = QVBoxLayout(custom_frame)
        custom_inner.setContentsMargins(
            theme.spacing_lg, theme.spacing_lg,
            theme.spacing_lg, theme.spacing_lg,
        )
        custom_inner.setSpacing(theme.spacing_sm)

        for label, xpath in self._custom_xpaths.custom.items():
            field_label = QLabel(f"{label}:")
            field_label.setStyleSheet(
                f"font-size: 12px; font-weight: 700; color: {theme.text.name()}; "
                f"background: transparent; border: none;"
            )
            custom_inner.addWidget(field_label)

            xpath_label = QLabel(f"XPath: {xpath}")
            xpath_label.setStyleSheet(
                f"font-size: 10px; color: {theme.text_muted.name()}; "
                f"font-family: monospace; background: transparent; border: none;"
            )
            xpath_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            custom_inner.addWidget(xpath_label)

        header_btn._section_widgets = [custom_frame]
        layout.addWidget(custom_frame)

    def _build_collapsible_text(
        self, layout: QVBoxLayout, theme, title: str, text: str
    ) -> None:
        """Build a collapsible section with plain text content."""
        header_btn = self._collapsible_header(title, theme)
        layout.addWidget(header_btn)

        text_frame = QFrame()
        text_frame.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"}}"
        )
        text_inner = QVBoxLayout(text_frame)
        text_inner.setContentsMargins(
            theme.spacing_lg, theme.spacing_lg,
            theme.spacing_lg, theme.spacing_lg,
        )

        text_label = QLabel(text[:3000])
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            f"font-size: 12px; color: {theme.text.name()}; "
            f"line-height: 1.6; background: transparent; border: none;"
        )
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_inner.addWidget(text_label)

        header_btn._section_widgets = [text_frame]
        layout.addWidget(text_frame)

    # ================================================================
    #  Helpers
    # ================================================================

    def _vertical_divider(self, theme) -> QFrame:
        """Create a vertical line divider for the stats bar."""
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFixedWidth(1)
        line.setFixedHeight(36)
        line.setStyleSheet(
            f"background: {theme.outline.name(QColor.HexArgb)}; border: none;"
        )
        return line

    def _section_label(self, text: str, theme) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.text_muted.name()}; "
            f"font-size: 11px; font-weight: 800; "
            f"letter-spacing: 1.5px; "
            f"padding: {theme.spacing_md}px 0 {theme.spacing_xs}px; "
            f"background: transparent; border: none;"
        )
        return lbl

    def _collapsible_header(self, text: str, theme) -> QPushButton:
        btn = QPushButton(f"\u25BE  {text}")
        btn.setStyleSheet(collapsible_header_style(theme))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)
        btn._section_text = text
        btn._collapsed = False
        btn._section_widgets = []
        btn.clicked.connect(lambda: self._toggle_section(btn))
        self._section_btns.append(btn)
        return btn

    def _toggle_section(self, btn: QPushButton) -> None:
        btn._collapsed = not btn._collapsed
        icon = "\u25B8" if btn._collapsed else "\u25BE"
        btn.setText(f"{icon}  {btn._section_text}")
        for w in btn._section_widgets:
            w.setVisible(not btn._collapsed)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    # ================================================================
    #  Event handlers
    # ================================================================

    def _on_rating_clicked(self, rating: int) -> None:
        if not self._game:
            return
        if self._game.rating == rating:
            self.rating_changed.emit(self._game.game_id, None)
            self._game.rating = None
        else:
            self.rating_changed.emit(self._game.game_id, rating)
            self._game.rating = rating
        self._update_star_display()

    def _update_star_display(self) -> None:
        if not self._game:
            return
        theme = current_theme()
        current_rating = self._game.rating or 0
        stars_filled = max(0, min(5, round(current_rating / 2)))
        for i, btn in enumerate(self._star_buttons):
            filled = i < stars_filled
            btn.setText("\u2605" if filled else "\u2606")
            color = theme.accent.name() if filled else theme.text_muted.name()
            btn.setStyleSheet(
                f"QPushButton {{ font-size: 18px; color: {color}; "
                f"background: transparent; border: none; padding: 0; }}"
                f"QPushButton:hover {{ color: {theme.accent.lighter(120).name()}; }}"
            )

    def _on_open_source(self) -> None:
        if self._game and self._game.source_url:
            self.open_source_clicked.emit(self._game.game_id)

    def _on_download_clicked(self, url: str) -> None:
        if self._game:
            self.download_requested.emit(self._game.game_id, url)

    def _on_extra_download(self, url: str) -> None:
        """Open extra download link in browser."""
        if url:
            webbrowser.open(url)

    def _open_game_folder(self, game: Game) -> None:
        """Open the game folder or shortcut folder."""
        import os
        folder = game.game_folder_path or game.archive_folder_path or ""
        if not folder and game.shortcut_path:
            folder = os.path.dirname(game.shortcut_path)
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(
                QDesktopServices.openUrl.__class__(f"file:///{folder}")
            )

    @property
    def current_game_id(self) -> Optional[str]:
        return self._game.game_id if self._game else None


# ============================================================================
#  Flow Layout helper (for tag chips that wrap)
# ============================================================================

class _FlowLayout(QVBoxLayout):
    """Simple flow layout that wraps widgets into rows.

    Uses nested QHBoxLayouts to simulate CSS flex-wrap behavior.
    Rebuilds on the parent's resize.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._widgets: List[QWidget] = []
        self._spacing = 8
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(4)

    def setSpacing(self, spacing: int) -> None:  # noqa: N802
        self._spacing = spacing
        super().setSpacing(4)

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802
        self._widgets.append(widget)
        self._relayout()

    def _relayout(self) -> None:
        """Rebuild rows of widgets to fit available width."""
        # Clear existing rows
        while self.count():
            child = self.takeAt(0)
            if child.layout():
                # Remove widgets from sub-layout without deleting them
                sub = child.layout()
                while sub.count():
                    item = sub.takeAt(0)
                    # Don't delete the actual widgets, just detach
                del sub

        parent_w = self.parentWidget()
        avail_width = parent_w.width() if parent_w else 600
        if avail_width < 100:
            avail_width = 600

        row = QHBoxLayout()
        row.setSpacing(self._spacing)
        row_width = 0

        for w in self._widgets:
            w_hint = w.sizeHint().width() + self._spacing
            if row_width + w_hint > avail_width and row_width > 0:
                row.addStretch(1)
                super().addLayout(row)
                row = QHBoxLayout()
                row.setSpacing(self._spacing)
                row_width = 0

            row.addWidget(w)
            row_width += w_hint

        if row_width > 0:
            row.addStretch(1)
            super().addLayout(row)
