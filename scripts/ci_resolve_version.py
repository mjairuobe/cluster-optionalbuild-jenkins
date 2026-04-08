#!/usr/bin/env python3
"""Schreibt .jenkins_runtime.env: SOFTWARE_VERSION + TREE_* pro Pfad aus modules.json."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_lib import all_paths, git_path_for_tree, load_modules, path_to_env_key, repo_root


def run_git(args: list[str]) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    return (r.stdout or "").strip()


def fetch_tags() -> None:
    subprocess.run(
        ["git", "fetch", "origin", "--tags", "--force"],
        cwd=repo_root(),
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "fetch", "--tags", "--force"],
        cwd=repo_root(),
        capture_output=True,
        check=False,
    )


def tree_short_5(git_rel_path: str) -> str:
    full = run_git(["rev-parse", f"HEAD:{git_rel_path}"])
    if not full or len(full) < 5:
        return "00000"
    return full[:5].lower()


def software_version() -> tuple[str, str, str, str, str]:
    fetch_tags()
    tags_out = run_git(["tag", "-l", "v[0-9]*.[0-9]*.[0-9]*"])
    tags = [t for t in tags_out.splitlines() if t.strip()]
    tags.sort(key=lambda t: [int(x) for x in t.lstrip("v").split(".")])
    latest = tags[-1] if tags else ""

    if latest:
        parts = latest.lstrip("v").split(".")
        major, minor = parts[0], parts[1]
        n = run_git(["rev-list", "--count", "--all", f"{latest}..HEAD"])
        build = n or "0"
    else:
        major, minor = "0", "1"
        build = run_git(["rev-list", "--all", "--count"]) or "0"

    sv = f"v{major}.{minor}.{build}"
    return sv, latest, major, minor, build


def main() -> int:
    os.chdir(repo_root())
    modules = load_modules()
    pkgs, svcs = all_paths(modules)

    sv, latest, major, minor, build = software_version()
    lines = [
        f"SOFTWARE_VERSION={sv}",
        f"BUILD_NUM={build}",
        f"LATEST_TAG={latest}",
        f"IMAGE_TAG={sv}",
        f"CI_MAJOR={major}",
        f"CI_MINOR={minor}",
    ]

    for p in pkgs + svcs:
        key = path_to_env_key(p, "TREE")
        lines.append(f"{key}={tree_short_5(git_path_for_tree(p))}")

    out = repo_root() / ".jenkins_runtime.env"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
