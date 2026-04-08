#!/usr/bin/env python3
"""Schreibt .jenkins_skip_pipeline und .jenkins_build_plan.env (ohne LIB_FORCE)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_lib import (
    all_paths,
    image_for_service,
    load_modules,
    package_local_dependency_graph,
    path_to_env_key,
    repo_root,
    required_stack_ok,
    service_local_dependencies,
    transitive_package_dependents,
)


def docker_ps_images() -> list[str]:
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Image}}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def normalize_img(s: str) -> str:
    s = s.strip()
    for p in ("docker.io/", "registry-1.docker.io/"):
        if s.startswith(p):
            s = s[len(p) :]
    return s


def has_running(want: str, images: list[str]) -> bool:
    w = normalize_img(want)
    return any(normalize_img(i) == w for i in images)


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def load_last_trees(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.startswith("LAST_TREE_"):
            out[k] = v.strip()
    return out


def tree_key_for_path(path: str) -> str:
    return path_to_env_key(path, "TREE")


def last_key_for_path(path: str) -> str:
    return "LAST_" + path_to_env_key(path, "TREE")


def main() -> int:
    root = repo_root()
    os.chdir(root)
    modules = load_modules()
    pkgs, svcs = all_paths(modules)

    env_path = root / ".jenkins_runtime.env"
    env = load_env(env_path)
    if not env:
        lines = []
        for svc in svcs:
            lines.append(f"{path_to_env_key(svc, 'BUILDSVC')}=1")
        (root / ".jenkins_skip_pipeline").write_text("false\n", encoding="utf-8")
        (root / ".jenkins_build_plan.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("ci_build_plan: keine .jenkins_runtime.env → alle BUILDSVC=1")
        return 0

    last_path = root / ".jenkins_last_trees"
    last = load_last_trees(last_path)
    first_run = not last_path.is_file() or not last

    pkg_graph = package_local_dependency_graph(root, pkgs)

    changed_packages: set[str] = set()
    if first_run:
        changed_packages = set(pkgs)
        print("Erster Lauf / leeres .jenkins_last_trees → alle lokalen Packages als geändert")
    else:
        for p in pkgs:
            tk = tree_key_for_path(p)
            lk = last_key_for_path(p)
            cur = env.get(tk, "")
            prev = last.get(lk, "")
            if cur != prev:
                changed_packages.add(p)
                print(f"Package geändert: {p} ({prev!r} -> {cur!r})")

    affected_packages = transitive_package_dependents(changed_packages, pkg_graph)

    images = docker_ps_images()
    stack_ok, stack_missing = required_stack_ok(modules, images)
    if not stack_ok:
        for m in stack_missing:
            print(f"Stack: fehlt {m}")

    lines: list[str] = []
    any_build = False
    for svc in svcs:
        key = path_to_env_key(svc, "BUILDSVC")
        tk = tree_key_for_path(svc)
        lk = last_key_for_path(svc)
        cur_tree = env.get(tk, "00000").lower()
        prev_tree = last.get(lk, "")

        deps = service_local_dependencies(root, svc, pkgs)
        dep_hit = bool(deps & affected_packages)

        need = 0
        if first_run:
            need = 1
        elif cur_tree != prev_tree:
            need = 1
        elif dep_hit:
            need = 1

        lines.append(f"{key}={need}")
        if need:
            any_build = True
            reason = []
            if first_run:
                reason.append("erster Lauf")
            if cur_tree != prev_tree:
                reason.append("Service-Baum geändert")
            if dep_hit:
                reason.append(
                    "lokale Libs betroffen: "
                    + ", ".join(sorted(deps & affected_packages))
                )
            print(f"BUILDSVC {svc}: 1 ({'; '.join(reason)})")

    all_images_current = 1
    if not stack_ok:
        all_images_current = 0

    for svc in svcs:
        repo = image_for_service(modules, svc)
        tk = tree_key_for_path(svc)
        tag = env.get(tk, "00000").lower()
        full = f"{repo}:{tag}"
        if not has_running(full, images):
            all_images_current = 0
            print(f"Nicht aktuell (läuft nicht): {full}")

    skip = bool(not any_build and all_images_current == 1 and stack_ok)
    (root / ".jenkins_skip_pipeline").write_text(("true" if skip else "false") + "\n", encoding="utf-8")

    (root / ".jenkins_build_plan.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("=== .jenkins_build_plan.env ===")
    print((root / ".jenkins_build_plan.env").read_text(encoding="utf-8"))
    print("=== .jenkins_skip_pipeline ===")
    print((root / ".jenkins_skip_pipeline").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
