# F95zone Advanced Integration Roadmap

## Executive Summary

This roadmap outlines advanced F95zone integration features for Game Library Manager v4. These features transform the application from a passive library organizer into an active game acquisition and management platform with deep F95zone integration.

---

## Current F95zone Integration (Baseline)

### Existing Features
- **F95 Parser** (`f95_parser.py`): XPath-based version extraction from thread pages
- **Update Checker** (`update_checker.py`): Background fetch with 6h cache, retry logic
- **Bulk Source Import**: Fuzzy matching for URL-to-game assignment
- **Version Comparison**: Intelligent parsing of version formats (numeric, build, season)

### Current Limitations
- Read-only: Cannot interact with F95zone beyond fetching public pages
- Manual downloads: User must download games externally
- No authentication: Cannot access member-only content or download links
- No archive management: Downloaded files managed outside the app

---

## Phase 6: Enhanced Bulk Import & Auto-Assignment

### 6.1 Smart URL Bulk Import
**Goal**: Intelligently import and assign F95zone URLs with minimal user intervention

| Feature | Description | Effort |
|---------|-------------|--------|
| Clipboard Monitor | Watch clipboard for F95zone URLs, prompt to import | Low |
| Batch URL Paste | Paste multiple URLs, auto-parse thread titles | Medium |
| Thread Title Extraction | Fetch page and extract game title automatically | Low |
| Fuzzy Match Preview | Show confidence scores with match explanations | Medium |
| Auto-Assignment Rules | User-defined rules for automatic matching | High |
| Import History | Track imported URLs with timestamps | Low |

**Implementation Notes:**
```python
# New module: src/app/services/bulk_import_service.py
class BulkImportService:
    def extract_thread_title(self, url: str) -> str:
        """Fetch F95 thread and extract title from <h1>"""

    def suggest_matches(self, title: str, games: list[Game]) -> list[MatchResult]:
        """Return ranked matches with confidence scores"""

    def apply_auto_rules(self, url: str, title: str) -> Optional[Game]:
        """Check user-defined rules for automatic assignment"""
```

### 6.2 URL Pattern Recognition
**Goal**: Automatically detect and parse F95zone URLs from various sources

| Feature | Description | Effort |
|---------|-------------|--------|
| URL Normalization | Convert mobile/shortened URLs to canonical form | Low |
| Thread ID Extraction | Parse thread ID from any URL variant | Low |
| Category Detection | Identify game type (Completed, Ongoing, Abandoned) | Medium |
| Tag Extraction | Pull tags from thread page | Medium |
| Developer Extraction | Extract developer name from thread title | Medium |

**URL Variants to Support:**
```
https://f95zone.to/threads/game-name.12345/
https://f95zone.to/threads/12345/
https://f95zone.to/goto/post?id=67890
https://f95zone.com/... (alternate domain)
Mobile variants
```

---

## Phase 7: F95zone Authentication & Session Management

### 7.1 Secure Login System
**Goal**: Enable authenticated access to F95zone for enhanced features

| Feature | Description | Effort |
|---------|-------------|--------|
| Login Dialog | Secure credential entry with remember option | Medium |
| Session Storage | Encrypted cookie/token storage | High |
| Session Refresh | Automatic session renewal before expiry | Medium |
| Multi-Factor Support | Handle 2FA if required | High |
| Logout & Clear | Secure session termination | Low |
| Connection Status | Visual indicator of auth state | Low |

**Security Considerations:**
```python
# New module: src/app/services/f95_auth.py
class F95AuthManager:
    """
    Security requirements:
    - Credentials encrypted at rest using Windows DPAPI
    - Session tokens stored in memory, cookies in encrypted file
    - Automatic logout on app close (optional)
    - Rate limiting to prevent account lockout
    - HTTPS-only connections
    """

    def login(self, username: str, password: str, remember: bool) -> AuthResult
    def refresh_session(self) -> bool
    def logout(self) -> None
    def get_session(self) -> requests.Session  # Pre-configured with cookies
```

**Storage Location:**
- Credentials: `%APPDATA%/GameLibraryManager/auth.encrypted`
- Session: In-memory only (or encrypted temp file)
- Use `cryptography` library with Windows DPAPI backend

### 7.2 Profile & Preferences Sync
**Goal**: Sync user data between F95zone and local library

| Feature | Description | Effort |
|---------|-------------|--------|
| Watched Threads Sync | Import user's watched threads as games | Medium |
| Likes Sync | Import liked threads | Medium |
| Bookmarks Import | Pull bookmarked threads | Medium |
| Alert Integration | Show F95 notifications in app | High |
| Profile Display | Show username/avatar in app | Low |

---

## Phase 8: Automatic Download System

### 8.1 Download Link Extraction
**Goal**: Parse and present download options from F95zone threads

| Feature | Description | Effort |
|---------|-------------|--------|
| Link Parser | Extract download links from thread body | High |
| Host Detection | Identify file hosts (MEGA, GDrive, Pixeldrain, etc.) | Medium |
| Version Matching | Associate links with specific versions | High |
| Mirror Grouping | Group alternative download mirrors | Medium |
| Link Validation | Check if links are still active | Medium |
| Changelog Extraction | Parse version changelog from thread | Medium |

**Supported Hosts (Initial):**
```python
SUPPORTED_HOSTS = {
    'mega.nz': MegaHandler,
    'drive.google.com': GDriveHandler,
    'pixeldrain.com': PixeldrainHandler,
    'workupload.com': WorkuploadHandler,
    'anonfiles.com': AnonfilesHandler,
    'gofile.io': GofileHandler,
    'mediafire.com': MediafireHandler,
    # Expandable via plugin system
}
```

### 8.2 Download Manager
**Goal**: Integrated download management with queue and progress tracking

| Feature | Description | Effort |
|---------|-------------|--------|
| Download Queue | Queue multiple downloads with priority | High |
| Progress Tracking | Real-time progress, speed, ETA | Medium |
| Pause/Resume | Interrupt and continue downloads | High |
| Retry Logic | Automatic retry on failure | Medium |
| Bandwidth Limiting | Optional speed throttling | Medium |
| Concurrent Downloads | Configurable parallel download limit | Medium |
| Download History | Track completed downloads | Low |
| Notification | System notification on completion | Low |

**Architecture:**
```python
# New module: src/app/services/download_manager.py
class DownloadManager(QObject):
    """
    Background download orchestrator with queue management.
    Uses QThread workers for non-blocking downloads.
    """

    # Signals
    download_started = Signal(str)  # download_id
    progress_updated = Signal(str, int, int)  # id, bytes_done, bytes_total
    download_completed = Signal(str, Path)  # id, file_path
    download_failed = Signal(str, str)  # id, error_message

    def queue_download(self, url: str, game: Game, priority: int = 0) -> str
    def pause(self, download_id: str) -> None
    def resume(self, download_id: str) -> None
    def cancel(self, download_id: str) -> None
    def get_queue_status(self) -> list[DownloadStatus]

# Per-host handlers
class HostHandler(ABC):
    @abstractmethod
    def resolve_direct_link(self, page_url: str) -> str

    @abstractmethod
    def download(self, url: str, dest: Path, progress_callback) -> None
```

### 8.3 Download UI Components
**Goal**: Intuitive download management interface

| Component | Description | Effort |
|-----------|-------------|--------|
| Downloads Panel | Dedicated panel showing queue/active/completed | Medium |
| Game Download Button | One-click download from Details panel | Low |
| Download Options Dialog | Choose version, host, destination | Medium |
| Queue Manager | Reorder, pause, cancel queued items | Medium |
| Storage Settings | Default download location, naming rules | Low |

**UI Mockup:**
```
+------------------------------------------+
| Downloads                           [x]  |
+------------------------------------------+
| Active (2)                               |
|  [=====>    ] Game A v0.5 - 45% - 2.3MB/s|
|  [=>        ] Game B v1.0 - 12% - 1.1MB/s|
+------------------------------------------+
| Queued (3)                               |
|  [ ] Game C v0.8 - Waiting...            |
|  [ ] Game D v2.1 - Waiting...            |
|  [ ] Game E v0.3 - Waiting...            |
+------------------------------------------+
| Completed (15)                    [Clear]|
|  [v] Game F v1.0 - 2.3 GB - 10 min ago  |
|  [v] Game G v0.5 - 890 MB - 1 hour ago  |
+------------------------------------------+
```

---

## Phase 9: Archive Management & Extraction

### 9.1 Automatic Extraction
**Goal**: Seamlessly extract downloaded archives to game folders

| Feature | Description | Effort |
|---------|-------------|--------|
| Format Detection | Support ZIP, RAR, 7z, multi-part archives | Medium |
| Auto-Extract | Option to extract immediately after download | Low |
| Extract Location | Configurable destination with templates | Medium |
| Password Handling | Common password database, prompt for custom | Medium |
| Multi-Part Joining | Automatically join split archives | High |
| Nested Archives | Handle archives within archives | Medium |
| Cleanup Option | Delete archive after successful extraction | Low |

**Password Management:**
```python
# Common F95zone passwords (stored encrypted)
COMMON_PASSWORDS = [
    'f95zone',
    'f95',
    'www.f95zone.to',
    # User can add custom passwords
]

class ArchiveExtractor:
    def extract(self, archive_path: Path, dest: Path, password: str = None) -> ExtractResult
    def detect_format(self, path: Path) -> ArchiveFormat
    def try_common_passwords(self, path: Path) -> Optional[str]
    def join_multipart(self, first_part: Path) -> Path
```

### 9.2 Game Folder Organization
**Goal**: Intelligently organize extracted games

| Feature | Description | Effort |
|---------|-------------|--------|
| Folder Naming | Configurable naming template | Medium |
| Version Folders | Option to keep multiple versions | Medium |
| Executable Detection | Find and highlight game executables | Medium |
| Shortcut Creation | Auto-create shortcuts after extraction | Medium |
| Library Auto-Add | Automatically add extracted game to library | Low |
| Save Game Preservation | Detect and backup save folders on update | High |

**Folder Template Variables:**
```
{title}         - Game title (sanitized)
{version}       - Current version
{developer}     - Developer name
{date}          - Download date
{thread_id}     - F95zone thread ID

Example: "D:/Games/{developer}/{title} [{version}]"
Result:  "D:/Games/DevStudio/Awesome Game [v0.5.1]"
```

### 9.3 Update Workflow
**Goal**: Streamlined update process for existing games

| Feature | Description | Effort |
|---------|-------------|--------|
| Update Detection | Notify when new version available | Low (exists) |
| One-Click Update | Download + extract + update metadata | Medium |
| Backup Current | Option to backup current version before update | Medium |
| Patch Support | Apply incremental patches when available | High |
| Rollback | Restore previous version from backup | Medium |
| Update Notes | Show changelog before updating | Low |

**Update Workflow:**
```
1. Detect update available (existing feature)
2. User clicks "Update" button
3. Show changelog and download options
4. Download new version to temp location
5. Backup current installation (optional)
6. Backup save games (auto-detect)
7. Extract new version
8. Restore save games
9. Update library metadata
10. Clean up temp files
11. Notify completion
```

---

## Phase 10: Advanced Automation

### 10.1 Scheduled Tasks
**Goal**: Automate routine operations

| Feature | Description | Effort |
|---------|-------------|--------|
| Auto Update Check | Scheduled check for all games | Low |
| Auto Download | Automatically download updates | Medium |
| Auto Extract | Extract downloads on schedule | Low |
| Cleanup Scheduler | Remove old backups, clear cache | Low |
| Report Generation | Periodic library reports | Low |

### 10.2 Watch Lists & Notifications
**Goal**: Proactive monitoring and alerts

| Feature | Description | Effort |
|---------|-------------|--------|
| Thread Watch | Monitor threads not in library | Medium |
| New Release Alerts | Notify for followed developers | Medium |
| Tag Subscriptions | Alert when games with tags are posted | Medium |
| System Tray | Background monitoring with tray icon | Medium |
| Desktop Notifications | Windows toast notifications | Low |

### 10.3 Scripting & Plugins
**Goal**: Enable power user customization

| Feature | Description | Effort |
|---------|-------------|--------|
| Custom Host Handlers | Plugin system for new file hosts | High |
| Post-Download Hooks | Run scripts after download/extract | Medium |
| Custom Parsers | User-defined version extractors | High |
| API Exposure | Local REST API for external tools | High |

---

## Technical Architecture

### New Service Modules

```
src/app/services/
├── f95_auth.py           # Authentication & session management
├── f95_api.py            # F95zone API abstraction
├── download_manager.py   # Download orchestration
├── download_worker.py    # Per-download thread worker
├── host_handlers/        # File host implementations
│   ├── base.py
│   ├── mega.py
│   ├── gdrive.py
│   ├── pixeldrain.py
│   └── ...
├── archive_extractor.py  # Extraction & password handling
├── folder_organizer.py   # Game folder management
├── save_manager.py       # Save game detection & backup
└── automation.py         # Scheduled tasks & watches
```

### New UI Components

```
src/app/ui/
├── dialogs/
│   ├── login_dialog.py        # F95zone login
│   ├── download_options.py    # Download configuration
│   └── extraction_settings.py # Extract preferences
├── widgets/
│   ├── downloads_panel.py     # Download queue/history
│   ├── download_progress.py   # Individual download widget
│   └── connection_status.py   # Auth state indicator
└── system_tray.py             # Background operation tray
```

### Data Model Extensions

```python
@dataclass
class Game:
    # Existing fields...

    # New fields for Phase 6-10
    f95_thread_id: Optional[int] = None
    f95_category: Optional[str] = None  # Completed, Ongoing, Abandoned
    f95_tags: list[str] = field(default_factory=list)
    developer: Optional[str] = None

    download_history: list[DownloadRecord] = field(default_factory=list)
    current_download_id: Optional[str] = None

    install_path: Optional[str] = None
    executable_path: Optional[str] = None
    save_folder_path: Optional[str] = None

    backup_versions: list[BackupInfo] = field(default_factory=list)

@dataclass
class DownloadRecord:
    download_id: str
    url: str
    host: str
    version: str
    timestamp: datetime
    file_size: int
    status: DownloadStatus  # completed, failed, cancelled
    file_path: Optional[str]

@dataclass
class BackupInfo:
    version: str
    backup_path: str
    created_at: datetime
    size_bytes: int
```

### Dependencies

```
# requirements.txt additions

# Authentication & HTTP
requests>=2.31
httpx>=0.25  # Async HTTP with HTTP/2
beautifulsoup4>=4.12

# Encryption
cryptography>=41.0
keyring>=24.0  # Windows credential manager

# Archive handling
py7zr>=0.20  # 7z support
rarfile>=4.1  # RAR support (requires unrar binary)
patool>=2.0   # Universal archive handling

# File host APIs
mega.py>=1.0.8  # MEGA.nz API
google-api-python-client>=2.100  # Google Drive
gdown>=4.7  # GDrive public files

# Download management
aiofiles>=23.0  # Async file I/O
tqdm>=4.66  # Progress bars (CLI fallback)

# System integration
pywin32>=306  # Already included
winrt-Windows.UI.Notifications>=2.0  # Toast notifications
```

---

## Security & Privacy Considerations

### Credential Storage
- Use Windows DPAPI for encryption at rest
- Never log credentials or session tokens
- Implement secure memory wiping for sensitive data
- Optional: Integrate with Windows Credential Manager

### Network Security
- HTTPS-only connections to F95zone
- Certificate pinning (optional, may break)
- Proxy support for privacy
- No telemetry or external analytics

### Download Safety
- Virus scan integration (Windows Defender API)
- Quarantine suspicious files
- Hash verification when available
- Warn on executable downloads

---

## Implementation Roadmap

### Phase 6: Enhanced Bulk Import (Weeks 11-12)
- [ ] Clipboard monitoring service
- [ ] Thread title extraction
- [ ] Enhanced fuzzy matching with confidence scores
- [ ] Auto-assignment rule engine
- [ ] Import history tracking

### Phase 7: Authentication (Weeks 13-15)
- [ ] Login dialog with secure credential handling
- [ ] Session management with encrypted storage
- [ ] Session refresh mechanism
- [ ] Connection status indicator
- [ ] Logout and session clearing

### Phase 8: Download System (Weeks 16-20)
- [ ] Download link parser for F95 threads
- [ ] Host handler plugin architecture
- [ ] MEGA, Google Drive handlers
- [ ] Pixeldrain, Mediafire handlers
- [ ] Download manager with queue
- [ ] Progress tracking UI
- [ ] Pause/resume functionality
- [ ] Downloads panel widget

### Phase 9: Archive Management (Weeks 21-24)
- [ ] Multi-format archive extraction
- [ ] Password handling system
- [ ] Multi-part archive joining
- [ ] Folder organization templates
- [ ] Executable detection
- [ ] Shortcut auto-creation
- [ ] Save game detection & backup
- [ ] Update workflow with rollback

### Phase 10: Automation (Weeks 25-28)
- [ ] Scheduled update checks
- [ ] Auto-download option
- [ ] System tray integration
- [ ] Desktop notifications
- [ ] Thread watch lists
- [ ] Plugin system foundation

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| F95zone blocks automated access | Medium | High | Use realistic browser headers, rate limiting |
| File hosts change APIs | High | Medium | Plugin architecture for easy updates |
| Legal concerns | Medium | High | User responsible for content, app is just a tool |
| Account security | Medium | High | Encryption, secure storage, optional 2FA |
| Malware in downloads | Medium | High | Antivirus integration, quarantine |
| Rate limiting / IP bans | Medium | Medium | Configurable delays, proxy support |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Time from F95 URL to playable game | < 5 minutes (excluding download time) |
| Download success rate | > 95% |
| Extraction success rate | > 99% |
| Session persistence | > 7 days without re-login |
| Update detection accuracy | > 98% |

---

## Alternatives Considered

### Direct Browser Integration
- Use browser extension to send links to app
- Pros: Leverages existing auth, no need to store credentials
- Cons: Requires extension development, user must install

### Headless Browser (Selenium/Playwright)
- Automate full browser for complex interactions
- Pros: Handles JavaScript, can bypass anti-bot
- Cons: Heavy, slow, resource-intensive, brittle

### F95zone API (if available)
- Use official or reverse-engineered API
- Pros: Clean, fast, reliable
- Cons: May not exist, could change without notice

---

## Appendix: Host Handler Examples

### MEGA Handler
```python
class MegaHandler(HostHandler):
    def __init__(self):
        self.mega = Mega()
        self._login = None

    def resolve_direct_link(self, page_url: str) -> str:
        # MEGA links are direct, extract file ID
        return page_url

    def download(self, url: str, dest: Path, progress_cb) -> None:
        if self._login:
            self.mega.login(self._login)
        self.mega.download_url(url, dest_path=str(dest),
                               progress_cb=progress_cb)
```

### Google Drive Handler
```python
class GDriveHandler(HostHandler):
    def resolve_direct_link(self, page_url: str) -> str:
        # Convert share link to direct download
        file_id = self._extract_file_id(page_url)
        return f"https://drive.google.com/uc?id={file_id}&export=download"

    def download(self, url: str, dest: Path, progress_cb) -> None:
        gdown.download(url, str(dest), quiet=False)
```

---

*Roadmap created: 2026-02-02*
*Version: 1.0*
*Author: Claude Code*
