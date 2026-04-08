#!/usr/bin/env python3
"""Push nur gebaute Images (Tree + SOFTWARE_VERSION)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_lib import all_paths, image_for_service, load_modules, path_to_env_key, repo_root


def load_env_file(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    if not path.is_file():
        return d
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def main() -> int:
    root = repo_root()
    os.chdir(root)
    modules = load_modules()
    _, svcs = all_paths(modules)
    rt = load_env_file(root / ".jenkins_runtime.env")
    plan = load_env_file(root / ".jenkins_build_plan.env")
    sv = rt.get("SOFTWARE_VERSION", "v0.0.0")

    for svc in svcs:
        key = path_to_env_key(svc, "BUILDSVC")
        if plan.get(key) != "1":
            continue
        repo = image_for_service(modules, svc)
        tk = path_to_env_key(svc, "TREE")
        tree = rt.get(tk, "00000").lower()
        subprocess.run(["docker", "push", f"{repo}:{tree}"], cwd=root, check=True)
        subprocess.run(["docker", "push", f"{repo}:{sv}"], cwd=root, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
