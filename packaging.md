# Packaging

Chosen: **PyInstaller** (simpler single-step build; good Windows support; no heavy C toolchain like Nuitka).

## Build steps
1) Create venv and install deps:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
```
2) Build:
```
pyinstaller --noconfirm --windowed --name GameLibraryManager --add-data "external/scanner/GameShortcutMaker;external/scanner/GameShortcutMaker" src/main.py
```
3) Output:
- `dist/GameLibraryManager/GameLibraryManager.exe`
- includes bundled scanner under `external/scanner/GameShortcutMaker`

## Notes
- Paths are resolved relative to project root; scanner launch uses `PYTHONPATH` injection so packaged app can import `external.scanner.GameShortcutMaker.app`.
- If additional data files are added (screenshots, themes), include via `--add-data`.
