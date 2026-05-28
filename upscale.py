from __future__ import annotations

import locale
import subprocess
import time
from pathlib import Path

from PySide6.QtGui import QImage

from constants import APP_DIR


def command_working_dir(command: str) -> Path:
    stripped = command.strip()
    if stripped.startswith('"'):
        end = stripped.find('"', 1)
        exe = stripped[1:end] if end > 1 else ""
    else:
        exe = stripped.split(maxsplit=1)[0]
    exe_path = Path(exe)
    if exe_path.is_absolute() and exe_path.is_file():
        return exe_path.parent
    if (APP_DIR / exe_path).is_file():
        return APP_DIR
    return exe_path.parent if exe_path.is_file() else APP_DIR


def run_upscale_engine(
    source: Path,
    output_path: Path,
    command_template: str,
    scale: int,
    denoise: int | str,
    tile: int,
    model: str,
    temporary_output: bool = False,
) -> dict:
    values = {
        "input": str(source),
        "output": str(output_path),
        "scale": scale,
        "denoise": denoise,
        "tile": tile,
        "model": model,
    }
    command = command_template.format(**values)
    working_dir = command_working_dir(command_template)
    try:
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            cwd=str(working_dir),
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        image = QImage(str(output_path)) if completed.returncode == 0 and output_path.exists() else QImage()
        if temporary_output and output_path.exists():
            output_path.unlink(missing_ok=True)
        return {
            "path": source,
            "code": completed.returncode,
            "output": completed.stdout.strip(),
            "image": image,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    except Exception as exc:
        return {"path": source, "code": 1, "output": str(exc), "image": QImage()}
