"""Organize one or more local Google Drive ZIP downloads into a shared tree."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import parse_qs, urlparse


SHORTCUT_SUFFIX = ".gshortcut"


@dataclass(frozen=True)
class ArchiveMember:
    """A file member and the archive that owns it."""

    archive_path: Path
    member_name: str


class ZipOrganizer:
    """Merge ZIP contents into ``output_dir / 'organized'`` in archive order."""

    def __init__(self, archives: Iterable[Path], output_dir: Path):
        self.archives = [Path(archive) for archive in archives]
        self.output_dir = Path(output_dir)
        self.download_root = self.output_dir / "organized"
        self.extracted_files: set[PurePosixPath] = set()
        self.created_folders: set[PurePosixPath] = set()
        self.shortcuts: list[tuple[PurePosixPath, ArchiveMember]] = []
        self.warnings: list[str] = []

    @staticmethod
    def safe_relative_path(member_name: str) -> PurePosixPath | None:
        """Return a safe archive-relative path, rejecting zip-slip paths."""
        path = PurePosixPath(member_name.replace("\\", "/"))
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            return None
        return path

    def local_path(self, relative_path: PurePosixPath) -> Path:
        """Return an output path for an already validated relative path."""
        return self.download_root.joinpath(*relative_path.parts)

    def ensure_folder(self, relative_path: PurePosixPath) -> None:
        """Create a directory once and remember it for subsequent archives."""
        if not relative_path.parts:
            self.download_root.mkdir(parents=True, exist_ok=True)
            return
        if relative_path not in self.created_folders:
            folder = self.local_path(relative_path)
            folder.mkdir(parents=True, exist_ok=True)
            self.created_folders.add(relative_path)

    def write_member(self, member: ArchiveMember, destination: Path) -> None:
        """Copy one member to disk without using ZipFile.extract()."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(member.archive_path) as archive, archive.open(member.member_name) as source:
            with destination.open("wb") as target:
                shutil.copyfileobj(source, target)

    def process_archive(self, archive_path: Path) -> None:
        """Extract regular files from one archive and retain its shortcuts for later."""
        if archive_path.suffix.lower() != ".zip":
            raise ValueError(f"Not a ZIP archive: {archive_path}")
        if not archive_path.is_file():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    relative_path = self.safe_relative_path(info.filename)
                    if relative_path is None:
                        self.warnings.append(f"Unsafe archive path skipped: {info.filename}")
                        continue
                    if info.is_dir():
                        self.ensure_folder(relative_path)
                        continue

                    member = ArchiveMember(archive_path, info.filename)
                    if relative_path.suffix.lower() == SHORTCUT_SUFFIX:
                        self.shortcuts.append((relative_path, member))
                        continue
                    if relative_path in self.extracted_files:
                        self.warnings.append(
                            f"Duplicate path skipped (first archive wins): {relative_path} in {archive_path.name}"
                        )
                        continue

                    destination = self.local_path(relative_path)
                    if destination.exists() or destination.is_symlink():
                        self.warnings.append(f"Existing output file skipped: {destination}")
                    else:
                        self.write_member(member, destination)
                    self.extracted_files.add(relative_path)
                    self.ensure_folder(relative_path.parent)
        except zipfile.BadZipFile as error:
            raise ValueError(f"Invalid ZIP archive: {archive_path}") from error

    @staticmethod
    def shortcut_target_path(payload: object) -> PurePosixPath | None:
        """Return a relative target path if the shortcut JSON provides one."""
        if not isinstance(payload, dict):
            return None
        for key in ("targetPath", "target_path", "path", "relativePath"):
            value = payload.get(key)
            if isinstance(value, str):
                return ZipOrganizer.safe_relative_path(value)
        url = payload.get("url")
        if isinstance(url, str):
            query = parse_qs(urlparse(url).query)
            for key in ("targetPath", "target_path", "path", "relativePath"):
                if query.get(key):
                    return ZipOrganizer.safe_relative_path(query[key][0])
        return None

    def read_shortcut_target(self, member: ArchiveMember) -> PurePosixPath | None:
        try:
            with zipfile.ZipFile(member.archive_path) as archive, archive.open(member.member_name) as source:
                return self.shortcut_target_path(json.load(source))
        except (json.JSONDecodeError, OSError, zipfile.BadZipFile) as error:
            self.warnings.append(f"Unreadable shortcut retained: {member.member_name} ({error})")
            return None

    def create_shortcut(self, shortcut_path: PurePosixPath, member: ArchiveMember) -> bool:
        """Create a relative symlink, or retain the original shortcut if unresolved."""
        target_path = self.read_shortcut_target(member)
        destination = self.local_path(shortcut_path.with_suffix(""))
        target = self.local_path(target_path) if target_path else None

        if target is None or not (target.exists() or target.is_symlink()):
            self.warnings.append(f"Unresolved shortcut retained: {shortcut_path}")
            retained_path = self.local_path(shortcut_path)
            if not retained_path.exists() and not retained_path.is_symlink():
                self.write_member(member, retained_path)
            return False
        if destination.exists() or destination.is_symlink():
            self.warnings.append(f"Shortcut destination already exists: {destination}")
            return False

        destination.parent.mkdir(parents=True, exist_ok=True)
        relative_target = os.path.relpath(target, destination.parent)
        destination.symlink_to(relative_target, target_is_directory=target.is_dir())
        return True

    def organize(self) -> None:
        """Process archives in order, then create every resolvable shortcut."""
        self.download_root.mkdir(parents=True, exist_ok=True)
        for archive_path in self.archives:
            print(f"Processing: {archive_path}")
            self.process_archive(archive_path)

        resolved_shortcuts = sum(
            self.create_shortcut(shortcut_path, member)
            for shortcut_path, member in self.shortcuts
        )
        print(f"Organized {len(self.extracted_files)} file(s) in {self.download_root}")
        print(f"Created {resolved_shortcuts} shortcut symlink(s)")
        for warning in self.warnings:
            print(f"Warning: {warning}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge local Google Drive ZIP downloads into one organized folder."
    )
    parser.add_argument("archives", nargs="+", type=Path, help="ZIP archives in merge order")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("downloads"),
        help="Parent directory for the shared organized folder (default: downloads)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        ZipOrganizer(args.archives, args.output).organize()
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
