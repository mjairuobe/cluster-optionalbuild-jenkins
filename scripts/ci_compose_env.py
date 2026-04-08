#!/usr/bin/env python3
"""Exportiert DOCKER_IMAGE_<SLUG> für docker-compose (Shell: eval oder source via sh)."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_lib import all_paths, container_for_service, image_for_service, load_modules, path_to_env_key, repo_root


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


def tag_from_container(name: str, fallback: str) -> str:
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.Config.Image}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return fallback
    img = (r.stdout or "").strip()
    if not img:
        return fallback
    return img.split(":", 1)[-1]


def env_var_for_service(svc_path: str) -> str:
    slug = Path(svc_path).name.replace("-", "_").upper()
    return f"DOCKER_IMAGE_{slug}"


def main() -> int:
    root = repo_root()
    modules = load_modules()
    _, svcs = all_paths(modules)
    rt = load_env_file(root / ".jenkins_runtime.env")
    plan = load_env_file(root / ".jenkins_build_plan.env")
    sv = rt.get("SOFTWARE_VERSION", "v0.0.0")

    out: dict[str, str] = {"SOFTWARE_VERSION": sv}
    for svc in svcs:
        var = env_var_for_service(svc)
        repo = image_for_service(modules, svc)
        tk = path_to_env_key(svc, "TREE")
        exp = rt.get(tk, "00000").lower()
        key = path_to_env_key(svc, "BUILDSVC")
        cname = container_for_service(modules, svc)
        if plan.get(key) == "1":
            tag = exp
        else:
            tag = tag_from_container(cname, exp)
        out[var] = f"{repo}:{tag}"

    # Ausgabe als export-Zeilen für sh
    for k, v in sorted(out.items()):
        print(f"export {k}={shlex.quote(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
