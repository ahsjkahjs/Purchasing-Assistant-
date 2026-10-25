#!/usr/bin/env python3
"""Create a clean distributable skill zip.

The generic skill packager does not exclude VCS metadata. This project packager
keeps .git, caches, virtual environments, local output, and secrets out of the
archive. It does not replace SKILL.md validation; run the official validator
before packaging when available.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "dist", "out"}
EXCLUDED_FILES = {".env", ".DS_Store", "Thumbs.db"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip", ".tmp", ".log"}


def should_include(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path.name in EXCLUDED_FILES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def package(skill_dir: Path, output: Path) -> Path:
    skill_dir = skill_dir.resolve()
    if not (skill_dir / "SKILL.md").is_file():
        raise SystemExit(f"错误：{skill_dir} 缺 SKILL.md")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{skill_dir.name}.zip"
    files = [path for path in sorted(skill_dir.rglob("*")) if should_include(path, skill_dir)]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        for path in files:
            arcname = Path(skill_dir.name) / path.relative_to(skill_dir)
            handle.write(path, arcname.as_posix())
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 Skill，排除 .git、缓存、密钥和本地输出")
    parser.add_argument("--skill", default=Path(__file__).resolve().parents[1], help="Skill 根目录")
    parser.add_argument("--output", default="dist", help="zip 输出目录")
    args = parser.parse_args()
    archive = package(Path(args.skill), Path(args.output))
    print(f"已生成干净安装包：{archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
