"""Build a source-only Windows demo ZIP without local credentials or user data."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "release"
ZIP_PATH = OUTPUT_DIR / f"NeighLoop-local-Windows-{datetime.now():%Y-%m-%d}.zip"
PREFIX = "NeighLoop/"

ROOT_FILES = [
    "README.md", "LOCAL_RUN.md", "PLAN.md", "题目要求.txt", ".gitignore",
    "Open-NeighLoop.bat", "open_local.ps1", "setup_local.ps1", "start_local.ps1",
    "stop_local.ps1", "build_local_package.py",
]
BACKEND_FILES = ["requirements.txt", ".env.example"]
FRONTEND_FILES = [
    "README.md", "index.html", "package.json", "package-lock.json", "vite.config.ts",
    "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json", ".oxlintrc.json", ".gitignore",
]


def package_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    files.extend(ROOT / "backend" / name for name in BACKEND_FILES)
    files.extend((ROOT / "backend").glob("*.py"))
    files.extend((ROOT / "backend" / "services").rglob("*.py"))
    files.extend((ROOT / "backend" / "tests").rglob("*.py"))
    files.extend(ROOT / "frontend" / name for name in FRONTEND_FILES)
    files.extend(path for path in (ROOT / "frontend" / "src").rglob("*") if path.is_file())
    files.extend(path for path in (ROOT / "frontend" / "public").rglob("*") if path.is_file())
    files.extend(path for path in (ROOT / "docs").rglob("*") if path.is_file())
    unique = sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())
    missing = [str(path.relative_to(ROOT)) for path in unique if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Package inputs are missing: {missing}")
    return unique


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    entries = package_files()
    checksums = []
    with ZipFile(ZIP_PATH, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in entries:
            relative = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            archive.writestr(PREFIX + relative, content)
            checksums.append(f"{hashlib.sha256(content).hexdigest()}  {relative}")
        archive.writestr(PREFIX + "PACKAGE_MANIFEST.sha256", "\n".join(checksums) + "\n")
    print(f"Created {ZIP_PATH.name}: {len(entries)} project files, {ZIP_PATH.stat().st_size:,} bytes")
    print(f"SHA256 {hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
