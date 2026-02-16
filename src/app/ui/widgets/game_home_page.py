"""Game Homepage widget - a rich, scrollable detail page for a single game.

Displays:
- Banner / header image with ambient color
- Game icon, title, developer, version, category badge
- Rating (interactive stars), status badge
- Description / overview from F95zone
- Tags (genre chips)
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

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QColor, QPixmap, QDesktopServices, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QGridLayout, QMenu,
    QGraphicsDropShadowEffect, QApplication,
)

from app.models import Game
from app.models.custom_paths import CustomXPaths, F95_DEFAULT_XPATHS
from app.services import pixmap_for_game, best_icon_path
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

        self._build_ui()

    def _build_ui(self) -> None:
        theme = current_theme()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Top bar with back button --
        top_bar = QFrame()
        top_bar.setFixedHeight(40)
        top_bar.setStyleSheet(
            f"QFrame {{ background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-bottom: 1px solid {theme.outline.name(QColor.HexArgb)}; }}"
            f"QFrame QLabel {{ background: transparent; border: none; }}"
            f"QFrame QPushButton {{ background: transparent; border: none; }}"
        )
        top_hbox = QHBoxLayout(top_bar)
        top_hbox.setContentsMargins(theme.spacing_md, 0, theme.spacing_md, 0)
        top_hbox.setSpacing(theme.spacing_sm)

        self._back_btn = QPushButton(f"{AppIcons.UI_ARROW_LEFT}  Back to Library")
        self._back_btn.setStyleSheet(ghost_btn_style(theme))
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_clicked.emit)
        top_hbox.addWidget(self._back_btn)
        top_hbox.addStretch(1)

        self._source_btn = QPushButton(f"Open Source Page")
        self._source_btn.setStyleSheet(secondary_btn_style(theme))
        self._source_btn.setCursor(Qt.PointingHandCursor)
        self._source_btn.setVisible(False)
        self._source_btn.clicked.connect(self._on_open_source)
        top_hbox.addWidget(self._source_btn)

        outer.addWidget(top_bar)

        # -- Scrollable content --
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, theme.spacing_xl)
        self._layout.setSpacing(0)

        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

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

    def _rebuild_content(self) -> None:
        """Clear and rebuild all content sections."""
        # Clear existing content
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

        # 1. Banner / Hero section
        self._build_banner_section(layout, theme, game, info)

        # Content wrapper with padding
        content_wrapper = QWidget()
        cw_layout = QVBoxLayout(content_wrapper)
        cw_layout.setContentsMargins(
            theme.spacing_xl, theme.spacing_lg,
            theme.spacing_xl, theme.spacing_lg
        )
        cw_layout.setSpacing(theme.spacing_lg)

        # 2. Game info header (icon + title + meta)
        self._build_info_header(cw_layout, theme, game, info)

        # 3. Action buttons row
        self._build_action_row(cw_layout, theme, game, info)

        # 4. Description / Overview
        self._build_description_section(cw_layout, theme, game, info)

        # 5. Tags / Genre
        self._build_tags_section(cw_layout, theme, game, info)

        # 6. Download links
        if info and info.download_links:
            self._build_downloads_section(cw_layout, theme, game, info)

        # 7. Changelog (collapsible)
        changelog = (info.changelog if info else "") or ""
        if changelog:
            self._build_collapsible_text(
                cw_layout, theme, "CHANGELOG", changelog
            )

        # 8. Cheat Codes (collapsible)
        cheat_codes = (info.cheat_codes if info else "") or ""
        if cheat_codes:
            self._build_collapsible_text(
                cw_layout, theme, "CHEAT CODES", cheat_codes
            )

        # 9. Extras (walkthroughs, mods, saves)
        extras = (info.extras if info else []) or []
        if extras:
            self._build_extras_section(cw_layout, theme, extras)

        # 10. Technical Details (collapsible, less prominent)
        self._build_technical_section(cw_layout, theme, game, info)

        # 11. Custom XPath content (collapsible)
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
        """Build the hero banner area at the top."""
        banner = QFrame()
        banner_height = 200

        # Try to use ambient color for gradient background
        color_hex = game.dominant_color_hex or theme.accent.name()
        bg_color = QColor(color_hex) if color_hex else theme.accent

        # Gradient from game's ambient color to surface
        banner.setFixedHeight(banner_height)
        banner.setStyleSheet(
            f"QFrame {{ "
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 rgba({bg_color.red()},{bg_color.green()},{bg_color.blue()},80),"
            f"stop:1 {theme.bg.name(QColor.HexArgb)}); "
            f"border: none; }}"
        )

        # If we have a banner URL from thread info, show it
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)

        if info and info.banner_url:
            banner_label = QLabel()
            banner_label.setAlignment(Qt.AlignCenter)
            banner_label.setStyleSheet("background: transparent; border: none;")
            banner_label.setText(
                f"Banner: {info.banner_url[:80]}..."
                if len(info.banner_url) > 80
                else f"Banner: {info.banner_url}"
            )
            banner_label.setStyleSheet(
                f"color: {theme.text_muted.name()}; font-size: 10px; "
                f"background: transparent; border: none;"
            )
            banner_layout.addStretch(1)
            banner_layout.addWidget(banner_label, 0, Qt.AlignCenter)
            banner_layout.addStretch(1)

        layout.addWidget(banner)

    def _build_info_header(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the icon + title + metadata header row."""
        header = QHBoxLayout()
        header.setSpacing(theme.spacing_lg)

        # Game icon (large)
        icon_frame = QFrame()
        icon_frame.setFixedSize(96, 96)
        icon_frame.setStyleSheet(
            f"QFrame {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; border: none; }}"
        )
        icon_inner = QVBoxLayout(icon_frame)
        icon_inner.setContentsMargins(4, 4, 4, 4)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        pm = pixmap_for_game(game, 88)
        if pm and not pm.isNull():
            scaled = pm.scaled(
                QSize(88, 88), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon_label.setPixmap(scaled)
        icon_inner.addWidget(icon_label)

        # Add shadow to icon
        shadow = QGraphicsDropShadowEffect(icon_frame)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        icon_frame.setGraphicsEffect(shadow)

        header.addWidget(icon_frame)

        # Title + meta column
        meta_col = QVBoxLayout()
        meta_col.setSpacing(4)

        # Title
        title_lbl = QLabel(game.title)
        title_lbl.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {theme.text.name()}; "
            f"background: transparent; border: none;"
        )
        title_lbl.setWordWrap(True)
        meta_col.addWidget(title_lbl)

        # Developer + version + category row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(theme.spacing_md)

        developer = (info.developer if info else "") or game.developer or ""
        if developer:
            dev_lbl = QLabel(f"by {developer}")
            dev_lbl.setStyleSheet(
                f"font-size: 13px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none;"
            )
            meta_row.addWidget(dev_lbl)

        # Version badge
        version = game.installed_version_raw or (info.version if info else "") or ""
        if version:
            ver_badge = QLabel(f"v{version}")
            ver_badge.setStyleSheet(
                f"font-size: 11px; color: {theme.bg.name()}; "
                f"background: {theme.accent.name()}; "
                f"border-radius: {theme.radius_sm}px; "
                f"padding: 2px 8px; font-weight: 600; border: none;"
            )
            meta_row.addWidget(ver_badge)

        # Update indicator
        if info and info.version and game.installed_version_raw:
            inst_vi = parse_version(game.installed_version_raw)
            src_vi = parse_version(info.version)
            cmp = compare_versions(inst_vi, src_vi)
            if cmp == CompareResult.OLDER:
                upd_badge = QLabel(f"{AppIcons.STS_UPDATE} Update: {info.version}")
                upd_badge.setStyleSheet(
                    f"font-size: 11px; color: {theme.warning.name()}; "
                    f"font-weight: 600; background: transparent; border: none;"
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
            cat_badge = QLabel(category)
            cat_badge.setStyleSheet(
                f"font-size: 11px; color: {cat_color.name()}; "
                f"border: 1px solid {cat_color.name()}; "
                f"border-radius: {theme.radius_sm}px; "
                f"padding: 2px 8px; font-weight: 500; background: transparent;"
            )
            meta_row.addWidget(cat_badge)

        meta_row.addStretch(1)
        meta_col.addLayout(meta_row)

        # Rating + status + last played row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(theme.spacing_md)

        # Interactive rating stars
        self._star_buttons = []
        current_rating = game.rating or 0
        stars_filled = max(0, min(5, round(current_rating / 2)))
        for i in range(5):
            star_btn = QPushButton("\u2605" if i < stars_filled else "\u2606")
            star_btn.setFlat(True)
            star_btn.setCursor(Qt.PointingHandCursor)
            star_btn.setFixedSize(24, 24)
            star_btn.setStyleSheet(
                f"QPushButton {{ font-size: 16px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none; padding: 0; }}"
                f"QPushButton:hover {{ color: {theme.accent.name()}; }}"
            )
            star_value = (i + 1) * 2
            star_btn.clicked.connect(
                lambda checked, val=star_value: self._on_rating_clicked(val)
            )
            star_btn.setToolTip(f"Rate {star_value}/10")
            self._star_buttons.append(star_btn)
            stats_row.addWidget(star_btn)

        if current_rating:
            rating_text = QLabel(f"{current_rating}/10")
            rating_text.setStyleSheet(
                f"font-size: 12px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none;"
            )
            stats_row.addWidget(rating_text)

        # Status badge
        sc = status_color(theme, game.status)
        status_badge = QLabel(f"  {status_label(game.status)}  ")
        status_badge.setStyleSheet(
            f"font-size: 11px; color: {theme.bg.name()}; "
            f"background: {sc.name()}; "
            f"border-radius: {theme.radius_sm}px; "
            f"padding: 2px 10px; font-weight: 600; border: none;"
        )
        stats_row.addWidget(status_badge)

        # Last played
        lp = relative_time(game.last_played)
        if lp:
            lp_lbl = QLabel(f"{AppIcons.UI_CLOCK}  {lp}")
            lp_lbl.setStyleSheet(
                f"font-size: 11px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none;"
            )
            stats_row.addWidget(lp_lbl)

        # Launch count
        if game.launch_count > 0:
            lc_lbl = QLabel(f"Played {game.launch_count}x")
            lc_lbl.setStyleSheet(
                f"font-size: 11px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none;"
            )
            stats_row.addWidget(lc_lbl)

        # Thread stats
        if info:
            if info.likes > 0:
                likes_lbl = QLabel(f"\u2764 {info.likes}")
                likes_lbl.setStyleSheet(
                    f"font-size: 11px; color: {theme.text_muted.name()}; "
                    f"background: transparent; border: none;"
                )
                stats_row.addWidget(likes_lbl)
            if info.replies > 0:
                replies_lbl = QLabel(f"\U0001F4AC {info.replies}")
                replies_lbl.setStyleSheet(
                    f"font-size: 11px; color: {theme.text_muted.name()}; "
                    f"background: transparent; border: none;"
                )
                stats_row.addWidget(replies_lbl)

        stats_row.addStretch(1)
        meta_col.addLayout(stats_row)

        header.addLayout(meta_col, 1)
        layout.addLayout(header)

    def _build_action_row(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the primary action buttons row."""
        action_row = QHBoxLayout()
        action_row.setSpacing(theme.spacing_sm)

        # Play button (primary)
        play_btn = QPushButton(f"{AppIcons.ACT_PLAY}  Play")
        play_btn.setStyleSheet(primary_btn_style(theme))
        play_btn.setCursor(Qt.PointingHandCursor)
        play_btn.setMinimumHeight(40)
        play_btn.setMinimumWidth(120)
        play_btn.clicked.connect(
            lambda: self.play_clicked.emit(game.game_id) if self._game else None
        )
        action_row.addWidget(play_btn)

        # Download button (if download links available)
        if info and info.download_links:
            best = get_best_download_link(info.download_links)
            if best:
                host_info = get_host_display_info(best.host_type)
                dl_btn = QPushButton(
                    f"{AppIcons.ACT_DOWNLOAD}  Download ({host_info['name']})"
                )
                dl_btn.setStyleSheet(secondary_btn_style(theme))
                dl_btn.setCursor(Qt.PointingHandCursor)
                dl_btn.setMinimumHeight(40)
                dl_btn.clicked.connect(
                    lambda: self._on_download_clicked(best.url)
                )
                dl_btn.setToolTip(f"Download from {host_info['name']}")
                action_row.addWidget(dl_btn)

        action_row.addStretch(1)

        # Source URL button
        if game.source_url:
            self._source_btn.setVisible(True)
        else:
            self._source_btn.setVisible(False)

        layout.addLayout(action_row)

    def _build_description_section(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the description/overview section."""
        description = ""
        if info and info.description:
            description = info.description
        elif info and info.overview:
            description = info.overview
        elif game.notes:
            description = game.notes

        if not description:
            return

        layout.addWidget(self._section_divider(theme))
        layout.addWidget(self._section_label("DESCRIPTION", theme))

        desc_frame = QFrame()
        desc_frame.setStyleSheet(
            f"QFrame {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; "
            f"padding: {theme.spacing_md}px; border: none; }}"
        )
        desc_inner = QVBoxLayout(desc_frame)
        desc_inner.setContentsMargins(
            theme.spacing_md, theme.spacing_md,
            theme.spacing_md, theme.spacing_md
        )

        desc_label = QLabel(description[:2000])
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"font-size: 13px; color: {theme.text.name()}; "
            f"line-height: 1.6; background: transparent; border: none;"
        )
        desc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        desc_inner.addWidget(desc_label)

        layout.addWidget(desc_frame)

    def _build_tags_section(
        self, layout: QVBoxLayout, theme, game: Game, info: Optional[ThreadInfo]
    ) -> None:
        """Build the tags / genre chips section."""
        # Combine user tags, f95 tags, and genre tags
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

        layout.addWidget(self._section_divider(theme))
        layout.addWidget(self._section_label("TAGS & GENRE", theme))

        tags_flow = QHBoxLayout()
        tags_flow.setSpacing(6)

        # Show genre tags distinctly
        genre_set = set(info.genre_tags) if info and info.genre_tags else set()
        user_set = set(game.tags) if game.tags else set()

        for tag in all_tags[:20]:  # Limit display
            chip = QLabel(tag)
            if tag in genre_set:
                # Genre chips: accent-tinted
                chip.setStyleSheet(
                    f"font-size: 11px; color: {theme.accent.name()}; "
                    f"background: rgba({theme.accent.red()},{theme.accent.green()},"
                    f"{theme.accent.blue()},25); "
                    f"border-radius: {theme.radius_sm}px; "
                    f"padding: 3px 10px; border: none;"
                )
            elif tag in user_set:
                # User tags: standard chip
                chip.setStyleSheet(
                    f"font-size: 11px; color: {theme.text.name()}; "
                    f"background: {theme.chip_bg.name(QColor.HexArgb)}; "
                    f"border-radius: {theme.radius_sm}px; "
                    f"padding: 3px 10px; "
                    f"border: 1px solid {theme.chip_border.name(QColor.HexArgb)};"
                )
            else:
                # F95 tags: muted
                chip.setStyleSheet(
                    f"font-size: 11px; color: {theme.text_muted.name()}; "
                    f"background: {theme.surface_alt.name(QColor.HexArgb)}; "
                    f"border-radius: {theme.radius_sm}px; "
                    f"padding: 3px 10px; border: none;"
                )
            chip.setToolTip(tag)
            tags_flow.addWidget(chip)

        if len(all_tags) > 20:
            more = QLabel(f"+{len(all_tags) - 20} more")
            more.setStyleSheet(
                f"font-size: 11px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none;"
            )
            tags_flow.addWidget(more)

        tags_flow.addStretch(1)
        layout.addLayout(tags_flow)

    def _build_downloads_section(
        self, layout: QVBoxLayout, theme, game: Game, info: ThreadInfo
    ) -> None:
        """Build the download links section grouped by host."""
        layout.addWidget(self._section_divider(theme))
        layout.addWidget(self._section_label("DOWNLOADS", theme))

        groups = group_download_links_by_host(info.download_links)

        dl_frame = QFrame()
        dl_frame.setStyleSheet(
            f"QFrame {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; border: none; }}"
        )
        dl_inner = QVBoxLayout(dl_frame)
        dl_inner.setContentsMargins(
            theme.spacing_md, theme.spacing_md,
            theme.spacing_md, theme.spacing_md
        )
        dl_inner.setSpacing(theme.spacing_sm)

        for host_type, links in sorted(groups.items(), key=lambda x: x[1][0].priority):
            host_info = get_host_display_info(host_type)

            # Host header row
            host_row = QHBoxLayout()
            host_row.setSpacing(theme.spacing_sm)

            host_name = QLabel(host_info["name"])
            host_name.setStyleSheet(
                f"font-size: 13px; font-weight: 600; color: {theme.text.name()}; "
                f"background: transparent; border: none;"
            )
            host_row.addWidget(host_name)

            # Priority indicator
            priority = host_info["priority"]
            if priority <= 3:
                prio_color = theme.success
                prio_text = "Recommended"
            elif priority <= 6:
                prio_color = theme.text_muted
                prio_text = ""
            else:
                prio_color = theme.warning
                prio_text = "Slower"

            if prio_text:
                prio_badge = QLabel(prio_text)
                prio_badge.setStyleSheet(
                    f"font-size: 10px; color: {prio_color.name()}; "
                    f"background: transparent; border: none;"
                )
                host_row.addWidget(prio_badge)

            if host_info.get("has_limit"):
                limit_lbl = QLabel("(has limits)")
                limit_lbl.setStyleSheet(
                    f"font-size: 10px; color: {theme.text_muted.name()}; "
                    f"background: transparent; border: none;"
                )
                host_row.addWidget(limit_lbl)

            host_row.addStretch(1)
            dl_inner.addLayout(host_row)

            # Individual links
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
                        f"background: transparent; border: none;"
                    )
                    link_row.addWidget(unavail)

                link_row.addStretch(1)
                dl_inner.addLayout(link_row)

            # Separator between host groups
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setFixedHeight(1)
            sep.setStyleSheet(
                f"background: {theme.outline.name(QColor.HexArgb)}; border: none;"
            )
            dl_inner.addWidget(sep)

        layout.addWidget(dl_frame)

    def _build_extras_section(
        self, layout: QVBoxLayout, theme, extras: List[ExtraLink]
    ) -> None:
        """Build the extras section (walkthroughs, mods, saves)."""
        layout.addWidget(self._section_divider(theme))

        header_btn = self._collapsible_header("EXTRAS (Walkthroughs, Mods, Saves)", theme)
        layout.addWidget(header_btn)

        extras_frame = QFrame()
        extras_frame.setStyleSheet(
            f"QFrame {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; border: none; }}"
        )
        extras_inner = QVBoxLayout(extras_frame)
        extras_inner.setContentsMargins(
            theme.spacing_md, theme.spacing_md,
            theme.spacing_md, theme.spacing_md
        )
        extras_inner.setSpacing(theme.spacing_sm)

        # Group by category
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
                f"font-size: 12px; font-weight: 600; color: {theme.text.name()}; "
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
        layout.addWidget(self._section_divider(theme))

        header_btn = self._collapsible_header("TECHNICAL DETAILS", theme)
        layout.addWidget(header_btn)

        tech_frame = QFrame()
        tech_frame.setStyleSheet(
            f"QFrame {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; border: none; }}"
        )
        tech_inner = QGridLayout(tech_frame)
        tech_inner.setContentsMargins(
            theme.spacing_md, theme.spacing_md,
            theme.spacing_md, theme.spacing_md
        )
        tech_inner.setSpacing(theme.spacing_sm)

        row = 0

        def add_row(label: str, value: str) -> None:
            nonlocal row
            if not value:
                return
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"font-size: 11px; color: {theme.text_muted.name()}; "
                f"font-weight: 600; background: transparent; border: none;"
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

        layout.addWidget(self._section_divider(theme))
        header_btn = self._collapsible_header("CUSTOM DATA", theme)
        layout.addWidget(header_btn)

        custom_frame = QFrame()
        custom_frame.setStyleSheet(
            f"QFrame {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; border: none; }}"
        )
        custom_inner = QVBoxLayout(custom_frame)
        custom_inner.setContentsMargins(
            theme.spacing_md, theme.spacing_md,
            theme.spacing_md, theme.spacing_md
        )
        custom_inner.setSpacing(theme.spacing_sm)

        for label, xpath in self._custom_xpaths.custom.items():
            field_label = QLabel(f"{label}:")
            field_label.setStyleSheet(
                f"font-size: 12px; font-weight: 600; color: {theme.text.name()}; "
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
        layout.addWidget(self._section_divider(theme))
        header_btn = self._collapsible_header(title, theme)
        layout.addWidget(header_btn)

        text_frame = QFrame()
        text_frame.setStyleSheet(
            f"QFrame {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; border: none; }}"
        )
        text_inner = QVBoxLayout(text_frame)
        text_inner.setContentsMargins(
            theme.spacing_md, theme.spacing_md,
            theme.spacing_md, theme.spacing_md
        )

        text_label = QLabel(text[:3000])
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            f"font-size: 12px; color: {theme.text.name()}; "
            f"line-height: 1.5; background: transparent; border: none;"
        )
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_inner.addWidget(text_label)

        header_btn._section_widgets = [text_frame]
        layout.addWidget(text_frame)

    # ================================================================
    #  Helpers
    # ================================================================

    def _section_divider(self, theme) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background: {theme.outline.name(QColor.HexArgb)}; border: none;"
        )
        return line

    def _section_label(self, text: str, theme) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.text_muted.name()}; "
            f"font-size: 11px; font-weight: 700; "
            f"letter-spacing: 1px; "
            f"padding: {theme.spacing_sm}px 0 {theme.spacing_xs}px; "
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
        current_rating = self._game.rating or 0
        stars_filled = max(0, min(5, round(current_rating / 2)))
        for i, btn in enumerate(self._star_buttons):
            btn.setText("\u2605" if i < stars_filled else "\u2606")

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

    @property
    def current_game_id(self) -> Optional[str]:
        return self._game.game_id if self._game else None
