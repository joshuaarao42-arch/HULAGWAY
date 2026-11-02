from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def format_bytes(n: float) -> str:
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{sign}{n:.0f} {unit}" if unit == "B" else f"{sign}{n:.1f} {unit}"
        n /= 1024
    return f"{sign}{n:.1f} TB"


def format_saved(orig: int, new: int) -> str:
    """Percentage of storage saved (negative when the output is larger)."""
    if not orig:
        return "-"
    return f"{(1 - new / orig) * 100:.1f}%"


def collect_images(folder: Path, recursive: bool, extensions: Iterable[str]) -> list[Path]:
    exts = {e.lower() for e in extensions}
    pattern = "**/*" if recursive else "*"
    found = [p for p in Path(folder).glob(pattern) if p.is_file() and p.suffix.lower() in exts]
    return sorted(found, key=lambda p: str(p).lower())


def open_path(path: Path | str) -> bool:
    """Open a file or folder with the system default application."""
    p = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
        return True
    except Exception:
        return False


def reveal_in_folder(path: Path | str) -> bool:
    """Show a file in its folder (selecting it where the OS supports that)."""
    p = Path(path)
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
        return True
    except Exception:
        return False
