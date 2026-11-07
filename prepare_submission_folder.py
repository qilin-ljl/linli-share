"""Prepare a clean evaluation folder with the user-authorized DeepSeek key."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "release" / "NeighLoop-submission-final"

ROOT_FILES = ["Open-NeighLoop.bat", "open_local.ps1", "setup_local.ps1",
              "start_local.ps1", "stop_local.ps1"]
BACKEND_FILES = [".env.example", "requirements.txt", "auth.py", "database.py", "main.py",
                 "migrate_features.py", "migrations.py", "models.py",
                 "refresh_demo_slots.py", "seed.py", "seed_more.py"]
FRONTEND_FILES = ["index.html", "package.json", "package-lock.json", "vite.config.ts",
                  "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json", ".oxlintrc.json"]
DOC_FILES = ["ER.png", "ER_OVERVIEW.png", "TECH_STACK.md", "TECH_STACK_CARD.png"]


def read_deepseek_key() -> str:
    env = ROOT / "backend" / ".env"
    if not env.is_file():
        raise FileNotFoundError("backend/.env is missing")
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise ValueError("DEEPSEEK_API_KEY is empty in backend/.env")


def submission_env() -> bytes:
    values = [
        "DATABASE_URL=sqlite:///./neighloop.db",
        f"DEEPSEEK_API_KEY={read_deepseek_key()}",
        "DEEPSEEK_MODEL=deepseek-flash",
        "VISION_API_KEY=", "VISION_BASE_URL=", "VISION_MODEL=",
        "CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173",
        f"JWT_SECRET_KEY={secrets.token_urlsafe(48)}",
        "NEIGHLOOP_DEMO_MODE=true",
        "ENVIRONMENT=development",
    ]
    return ("\n".join(values) + "\n").encode("utf-8")


def source_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {
        "README.md": ROOT / "submission" / "README.md",
        "TEST_DATA_AND_PASSWORDS.txt": ROOT / "submission" / "TEST_DATA_AND_PASSWORDS.txt",
    }
    paths.update({name: ROOT / name for name in ROOT_FILES})
    paths.update({f"backend/{name}": ROOT / "backend" / name for name in BACKEND_FILES})
    paths.update({f"frontend/{name}": ROOT / "frontend" / name for name in FRONTEND_FILES})
    paths.update({f"docs/{name}": ROOT / "docs" / name for name in DOC_FILES})
    for folder in ("backend/services", "backend/tests", "frontend/src", "frontend/public"):
        paths.update({path.relative_to(ROOT).as_posix(): path
                      for path in (ROOT / folder).rglob("*") if path.is_file() and path.suffix != ".pyc"})
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Submission inputs missing: {missing}")
    return dict(sorted(paths.items()))


def main() -> None:
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise FileExistsError(f"Submission folder already contains files: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payloads = {name: path.read_bytes() for name, path in source_paths().items()}
    payloads["backend/.env"] = submission_env()
    checksums = []
    for name, content in sorted(payloads.items()):
        target = OUTPUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        checksums.append(f"{hashlib.sha256(content).hexdigest()}  {name}")
    (OUTPUT / "PACKAGE_MANIFEST.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"Prepared {OUTPUT}: {len(payloads)} project files")


if __name__ == "__main__":
    main()
