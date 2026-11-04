"""Account data and run logs in the user data folder (数据与隐私), shared by both apps."""

from __future__ import annotations

import configparser
from pathlib import Path

ACCOUNT_FILES = ("cookies.txt", ".cookies.txt")
LOG_PATTERNS = ("chaoxing*.log", "gui.log")


def clear_account_data(folder: Path, config_path: Path | None = None) -> None:
    """Blank the account, password and cookies login in config.ini and delete cookies files."""
    folder = Path(folder)
    config_path = Path(config_path) if config_path else folder / "config.ini"
    if config_path.exists():
        config = configparser.ConfigParser(interpolation=None)
        config.read(config_path, encoding="utf-8")
        if config.has_section("common"):
            for key in ("username", "password"):
                config["common"][key] = ""
            config["common"]["use_cookies"] = "false"
            with config_path.open("w", encoding="utf-8") as fh:
                config.write(fh)
    for name in ACCOUNT_FILES:
        try:
            (folder / name).unlink()
        except FileNotFoundError:
            pass


def log_files(folder: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in LOG_PATTERNS:
        found.extend(p for p in Path(folder).glob(pattern) if p.is_file())
    return found


def log_size_text(folder: Path) -> str:
    total = sum(p.stat().st_size for p in log_files(folder))
    if total < 1024 * 1024:
        return f"{total / 1024:.0f} KB"
    return f"{total / 1024 / 1024:.1f} MB"


def has_cookies(folder: Path) -> bool:
    return (Path(folder) / "cookies.txt").exists()
