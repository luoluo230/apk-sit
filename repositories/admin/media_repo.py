"""Media storage repository wrappers."""

from __future__ import annotations

from services.media_library import media_root, save_uploaded_files


def root_path() -> str:
    return media_root()


def save_files(files, scope: str, bucket: str):
    return save_uploaded_files(files, scope=scope, bucket=bucket)
