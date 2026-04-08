#!/usr/bin/env python3
"""Selektiver docker build: Tree-Tag + SOFTWARE_VERSION."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_lib import (
    all_paths,
    docker_build_invocation,
    image_for_service,
    load_modules,
    path_to_env_key,
    repo_root,
)


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
    build_cwd, dockerfile_args = docker_build_invocation()
    modules = load_modules()
    _, svcs = all_paths(modules)
    rt = load_env_file(root / ".jenkins_runtime.env")
    plan = load_env_file(root / ".jenkins_build_plan.env")
    sv = rt.get("SOFTWARE_VERSION", "v0.0.0")
    label = f"org.opencontainers.image.version={sv}"

    for svc in svcs:
        key = path_to_env_key(svc, "BUILDSVC")
        if plan.get(key) != "1":
            print(f"skip build {svc}")
            continue
        repo = image_for_service(modules, svc)
        tk = path_to_env_key(svc, "TREE")
        tree = rt.get(tk, "00000").lower()
        target = modules["docker"]["stage_targets"][svc]
        print(f"docker build --target {target} {repo}:{tree} + {sv}")
        cmd = [
            "docker",
            "build",
            *dockerfile_args,
            "--target",
            target,
            "-t",
            f"{repo}:{tree}",
            "-t",
            f"{repo}:{sv}",
            "--label",
            label,
            ".",
        ]
        subprocess.run(cmd, cwd=build_cwd, check=True)

    # LAST_TREE_* für alle Pfade in modules.json (Packages + Services)
    lines = []
    pkgs, svcs = all_paths(modules)
    for p in pkgs + svcs:
        tk = path_to_env_key(p, "TREE")
        lines.append(f"LAST_{tk}={rt.get(tk, '')}")
    (root / ".jenkins_last_trees").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote .jenkins_last_trees")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
