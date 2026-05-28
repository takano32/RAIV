from __future__ import annotations

import locale
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from constants import ARCHIVE_EXTENSIONS, IMAGE_EXTENSIONS

try:
    import rarfile
except ImportError:
    rarfile = None

try:
    import py7zr
except ImportError:
    py7zr = None


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def collect_images(folder: Path) -> list[Path]:
    folder = folder.resolve()
    images: list[Path] = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_EXTENSIONS:
                    images.append(folder / entry.name)
    except OSError:
        return []
    return sorted(images, key=lambda p: p.name.casefold())


def archive_display_name(member_name: str) -> str:
    return member_name.replace("\\", "/").lstrip("/")


def archive_member_output_path(temp_dir: Path, member_name: str) -> Path | None:
    parts = PurePosixPath(archive_display_name(member_name)).parts
    safe = []
    for part in parts:
        if part in {"", ".", "/"}:
            continue
        if part == ".." or ":" in part:
            return None
        safe.append(re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", part))
    return temp_dir.joinpath(*safe) if safe else None


def extract_zip_images(archive_path: Path, temp_dir: Path) -> tuple[list[Path], dict[Path, str]]:
    images: list[Path] = []
    names: dict[Path, str] = {}
    with zipfile.ZipFile(archive_path) as archive:
        members = sorted(
            [info for info in archive.infolist() if not info.is_dir() and is_image(Path(info.filename))],
            key=lambda item: item.filename.lower(),
        )
        for info in members:
            output = archive_member_output_path(temp_dir, info.filename)
            if output is None:
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            images.append(output.resolve())
            names[output.resolve()] = archive_display_name(info.filename)
    return images, names


def extract_rar_images(archive_path: Path, temp_dir: Path) -> tuple[list[Path], dict[Path, str]]:
    if rarfile is None:
        raise RuntimeError("rarfile is not installed")
    images: list[Path] = []
    names: dict[Path, str] = {}
    with rarfile.RarFile(archive_path) as archive:
        members = sorted(
            [info for info in archive.infolist() if not info.isdir() and is_image(Path(info.filename))],
            key=lambda item: item.filename.lower(),
        )
        for info in members:
            output = archive_member_output_path(temp_dir, info.filename)
            if output is None:
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            images.append(output.resolve())
            names[output.resolve()] = archive_display_name(info.filename)
    return images, names


def collect_archive_outputs(temp_dir: Path) -> tuple[list[Path], dict[Path, str]]:
    images = sorted(
        [p.resolve() for p in temp_dir.rglob("*") if p.is_file() and is_image(p)],
        key=lambda p: str(p.relative_to(temp_dir)).lower(),
    )
    names = {p: archive_display_name(str(p.relative_to(temp_dir))) for p in images}
    return images, names


def find_7z() -> Path | None:
    for name in ("7z", "7za", "7zr"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for candidate in (
        Path(os.environ.get("ProgramFiles", "")) / "7-Zip" / "7z.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "7-Zip" / "7z.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def extract_with_7z_command(archive_path: Path, temp_dir: Path) -> tuple[list[Path], dict[Path, str]]:
    tool = find_7z()
    if tool is None:
        raise RuntimeError("この形式を開くには py7zr/rarfile または 7z/7za/7zr が必要です。")
    completed = subprocess.run(
        [str(tool), "x", "-y", f"-o{temp_dir}", str(archive_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout.strip())
    return collect_archive_outputs(temp_dir)


def extract_archive_images(archive_path: Path, temp_dir: Path) -> tuple[list[Path], dict[Path, str]]:
    suffix = archive_path.suffix.lower()
    if suffix in {".zip", ".cbz"}:
        return extract_zip_images(archive_path, temp_dir)
    if suffix in {".7z", ".cb7"}:
        if py7zr is not None:
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                archive.extractall(path=temp_dir)
            return collect_archive_outputs(temp_dir)
        return extract_with_7z_command(archive_path, temp_dir)
    if suffix in {".rar", ".cbr"}:
        if rarfile is not None:
            try:
                return extract_rar_images(archive_path, temp_dir)
            except Exception:
                return extract_with_7z_command(archive_path, temp_dir)
        return extract_with_7z_command(archive_path, temp_dir)
    raise RuntimeError(f"対応していない形式です: {suffix}")
