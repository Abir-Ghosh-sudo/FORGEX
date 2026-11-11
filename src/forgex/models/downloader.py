"""Hugging Face Hub model weight downloader for FORGEX.

Downloads model files only. Does not use hosted inference APIs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forgex.models.errors import ModelDownloadError

logger = logging.getLogger(__name__)


class HuggingFaceDownloadError(ModelDownloadError):
    """Raised when a Hugging Face Hub download fails."""


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Result of a model download operation."""

    repo_id: str
    local_path: Path
    revision: str | None = None
    files: tuple[str, ...] = ()
    from_cache: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class HuggingFaceDownloader:
    """Downloads model repositories/files from Hugging Face Hub."""

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        token: str | None = None,
        local_files_only: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir).expanduser().resolve() if cache_dir else None
        self.token = token
        self.local_files_only = local_files_only

    def download_model(
        self,
        repo_id: str,
        *,
        revision: str | None = None,
        allow_patterns: list[str] | tuple[str, ...] | None = None,
        ignore_patterns: list[str] | tuple[str, ...] | None = None,
        filename: str | None = None,
        local_dir: str | Path | None = None,
        progress_callback: Callable[[str], None] | None = None,
        local_files_only: bool | None = None,
    ) -> DownloadResult:
        """Download a model repo or a specific file from Hugging Face Hub."""
        repo = (repo_id or "").strip()
        if not repo:
            raise HuggingFaceDownloadError("repo_id cannot be empty.")

        offline_mode = self.local_files_only if local_files_only is None else local_files_only

        try:
            from huggingface_hub import hf_hub_download, snapshot_download
        except Exception as exc:
            raise HuggingFaceDownloadError(
                "huggingface-hub is not installed. Install 'huggingface-hub' to download models.",
                repo_id=repo,
            ) from exc

        try:
            if progress_callback:
                progress_callback(f"Resolving {repo}...")

            if filename:
                path_str = hf_hub_download(
                    repo_id=repo,
                    filename=filename,
                    revision=revision,
                    token=self.token,
                    cache_dir=str(self.cache_dir) if self.cache_dir else None,
                    local_dir=str(Path(local_dir).expanduser().resolve()) if local_dir else None,
                    local_files_only=offline_mode,
                )
                local_path = Path(path_str).resolve()
                files = (filename,)
            else:
                path_str = snapshot_download(
                    repo_id=repo,
                    revision=revision,
                    allow_patterns=list(allow_patterns) if allow_patterns else None,
                    ignore_patterns=list(ignore_patterns) if ignore_patterns else None,
                    token=self.token,
                    cache_dir=str(self.cache_dir) if self.cache_dir else None,
                    local_dir=str(Path(local_dir).expanduser().resolve()) if local_dir else None,
                    local_files_only=offline_mode,
                )
                local_path = Path(path_str).resolve()
                files = self._list_downloaded_files(local_path, allow_patterns)

            if progress_callback:
                progress_callback(f"Model available at {local_path}")

            return DownloadResult(
                repo_id=repo,
                local_path=local_path,
                revision=revision,
                files=files,
                from_cache=offline_mode,
                metadata={"local_dir": str(local_dir) if local_dir else None},
            )
        except HuggingFaceDownloadError:
            raise
        except Exception as exc:
            logger.exception("Hugging Face download failed for %s", repo)
            raise HuggingFaceDownloadError(
                f"Failed to download model '{repo}': {exc}",
                repo_id=repo,
            ) from exc

    @staticmethod
    def _list_downloaded_files(
        root: Path,
        allow_patterns: list[str] | tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        if not root.exists() or not root.is_dir():
            return ()
        try:
            files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
            files.sort()
            return tuple(files[:200])
        except Exception:
            return ()

    def is_available(self) -> bool:
        try:
            import huggingface_hub  # noqa: F401

            return True
        except Exception:
            return False


__all__ = [
    "DownloadResult",
    "HuggingFaceDownloadError",
    "HuggingFaceDownloader",
]
