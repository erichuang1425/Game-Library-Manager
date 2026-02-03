"""Base class for archive format handlers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


# Progress callback type: (filename, current, total)
ProgressCallback = Callable[[str, int, int], None]


@dataclass
class ExtractionResult:
    """Result of archive extraction."""
    success: bool
    extracted_path: str = ""
    file_count: int = 0
    total_size: int = 0
    error: str = ""
    password_used: str = ""


@dataclass
class ArchiveInfo:
    """Information about an archive file."""
    path: str
    is_encrypted: bool = False
    file_count: int = 0
    total_size: int = 0


class FormatHandler(ABC):
    """
    Abstract base class for archive format handlers.

    Each handler implements support for a specific archive format
    (ZIP, RAR, 7z, etc.) with a consistent interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the format."""
        pass

    @property
    @abstractmethod
    def extensions(self) -> List[str]:
        """File extensions supported by this handler (lowercase, with dot)."""
        pass

    @property
    @abstractmethod
    def magic_bytes(self) -> List[bytes]:
        """Magic byte sequences that identify this format."""
        pass

    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        """
        Check if this handler can process the given file.

        Args:
            path: Path to the archive file

        Returns:
            True if this handler can extract the file
        """
        pass

    @abstractmethod
    def get_info(self, path: Path) -> ArchiveInfo:
        """
        Get information about an archive without extracting.

        Args:
            path: Path to the archive file

        Returns:
            ArchiveInfo with file details
        """
        pass

    @abstractmethod
    def extract(
        self,
        path: Path,
        destination: Path,
        password: Optional[str] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """
        Extract the archive to the destination.

        Args:
            path: Path to the archive file
            destination: Directory to extract to
            password: Optional password for encrypted archives
            progress: Optional callback for progress updates

        Returns:
            ExtractionResult with extraction status
        """
        pass

    @abstractmethod
    def try_password(self, path: Path, password: str) -> bool:
        """
        Test if a password works for an encrypted archive.

        Args:
            path: Path to the archive file
            password: Password to test

        Returns:
            True if the password is correct
        """
        pass

    def is_available(self) -> bool:
        """
        Check if this handler's dependencies are available.

        Override in subclasses that require external libraries.

        Returns:
            True if the handler can be used
        """
        return True

    def get_missing_dependency_message(self) -> str:
        """
        Get a message explaining how to install missing dependencies.

        Returns:
            Installation instructions or empty string if no deps missing
        """
        return ""
