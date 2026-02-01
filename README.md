Game Library Manager (v4)
=========================

PySide6 desktop app for organising large Windows game libraries represented by shortcuts. It tracks sources, versions, archives, and health, while keeping a fast, dense grid for everyday browsing — now with sharper icons and clearer scan summaries.

## What it does
- **Library grid**: Comfortable/Compact densities, responsive card scaling, quick pills (All / Missing / Updates / Source), tag chips to filter, sorting by Title / Last Played / Rating / Launch Count / Last Checked, focus mode to hide Details.
- **Metadata editing**: Status, 1–10 rating, tags, notes, source URL, installed version, archive folder + compressed archive paths (pick/open), launch stats, and backup target info per game.
- **Scanning**: Reads the top level of a shortcuts root for `.lnk / .url / .html`, resolves targets, and merges into the library while preserving user edits. Detects duplicate shortcut sets (Game.lnk, Game (1).lnk, …) and can quarantine extras before import. Shows a scan summary (new/updated/icons refreshed) and keeps the progress dialog responsive.
- **Icons**: High-quality pipeline pulls the best available source (shortcut → resolved target → archive) at 1024px and downscales once, so cards stay sharp even after resizing; scanning primes icons for newly touched games.
- **Launching**: Opens the stored shortcut; falls back to resolved target/args/working dir; updates launch count and last played.
- **Collections**: Manual lists plus smart collections (presets: Low confidence, HTML only, Backlog, Unplayed). Sidebar shows live counts; create/rename/delete; add selected game with one click.
- **Update tracking**: Background fetch + parse with retries/cache (6h TTL); f95zone-specific parser; Updates view shows Update / Up-to-date / Unknown / Newer local; optional “Open sources only” mode; mark installed from source; bulk source URL import with fuzzy matching and optional overwrite.
- **Health checks**: Flags missing shortcuts/targets/source URLs/archive folders/files/game folders and version mismatches; quick Fix/Open/Remove actions; per-issue resolve/ignore; density + severity filters; hinting focuses the right Details field.
- **Appearance & UX**: Theme system (dark, light, neubrutalism, neumorphism, glassmorphism), font family + scale, responsive typography buckets, details toggle with size guard, splitter persistence, focus mode, guarded top-level windows (debug).
- **Storage & logging**: Library/settings in `%APPDATA%/GameLibraryManager` (`library.json`, `settings.json`). Rotating `manager.log` with fallbacks and a one-time toast when the log path falls back.

## First run
1. `pip install -r requirements.txt`
2. `python src/main.py`
3. Click **Scan** and choose your shortcuts root (top-level only). Duplicate shortcut groups can be quarantined automatically if you accept the prompt.
4. Select a game, set **Source URL**, and optionally archive paths/installed version in **Details**.
5. Press **Check Updates** (dropdown has “Open sources only”). Results land in **Updates**; mark installed from source if desired.
6. Open **Health Checks** to fix or ignore flagged items.

## Running & packaging
- Source run: `python src/main.py` (ensure `src` is on `PYTHONPATH`; Windows required for `.lnk` resolution).
- Requirements: see `requirements.txt` (PySide6, pywin32, lxml).
- Packaging: see `packaging.md` for the PyInstaller command that bundles the external scanner.

## Bundled scanner
`Tools > Scanner` launches the included `external/scanner/GameShortcutMaker` project without blocking the UI. It can generate the shortcut root that this manager consumes.

## Known limits
- Only the top level of the shortcuts root is scanned.
- Generic HTML parsing may miss versions on heavily customised pages; status falls back to UNKNOWN rather than guessing.
- Tests are lightweight scripts (`src/tests`) rather than a full runner.
