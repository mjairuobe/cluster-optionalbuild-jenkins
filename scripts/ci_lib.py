"""Hilfen für modules.json und Pfade."""

from __future__ import annotations

import json
import re
import subprocess
from collections import deque
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def git_worktree_root() -> Path:
    """Git-Top-Level (kann über dem Template-Ordner liegen, z. B. Monorepo)."""
    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        return repo_root()
    return Path((r.stdout or "").strip())


def git_path_for_tree(rel_from_module_root: str) -> str:
    """Relativer Pfad für `git rev-parse HEAD:<path>`."""
    mod = repo_root()
    abs_path = (mod / rel_from_module_root).resolve()
    gw = git_worktree_root()
    try:
        return str(abs_path.relative_to(gw))
    except ValueError:
        return rel_from_module_root


def docker_build_invocation() -> tuple[Path, list[str]]:
    """
    (cwd, extra_args vor 'docker build').
    Monorepo: Build-Kontext = Git-Root, Dockerfile per -f <relativ zum Root>.
    Eigenes Repo (Template = Root): cwd = Repo-Root, kein -f nötig.
    """
    mod = repo_root()
    gw = git_worktree_root()
    if mod.resolve() == gw.resolve():
        return mod, []
    rel_df = (mod / "Dockerfile").resolve().relative_to(gw)
    return gw, ["-f", str(rel_df)]


def load_modules() -> dict:
    p = repo_root() / "modules.json"
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def all_paths(modules: dict) -> tuple[list[str], list[str]]:
    d = modules.get("dir", {})
    return list(d.get("packages", [])), list(d.get("services", []))


def path_to_env_key(path: str, prefix: str) -> str:
    """z. B. example-services/http-api -> TREE_example_services_http_api"""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_").upper()
    return f"{prefix}_{slug}"


def image_for_service(modules: dict, service_path: str) -> str:
    reg = modules.get("docker", {}).get("registry", "docker.io/example-org").rstrip("/")
    names = modules.get("docker", {}).get("images", {})
    short = names.get(service_path)
    if not short:
        short = Path(service_path).name
    return f"{reg}/{short}"


def container_for_service(modules: dict, service_path: str) -> str:
    c = modules.get("docker", {}).get("containers", {})
    return c.get(service_path, Path(service_path).name.replace("/", "-"))


def _strip_inline_comment(line: str) -> str:
    if "#" not in line:
        return line
    in_quotes = False
    quote_ch = ""
    out: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if not in_quotes and ch == "#":
            break
        if ch in "\"'":
            if not in_quotes:
                in_quotes = True
                quote_ch = ch
            elif ch == quote_ch:
                in_quotes = False
        out.append(ch)
        i += 1
    return "".join(out).strip()


def _parse_requirement_line_to_path(line: str, base_dir: Path) -> Path | None:
    """Erkennt lokale Pfad-Referenzen (-e, file:, reiner Pfad)."""
    s = _strip_inline_comment(line).strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("-e") or s.startswith("--editable"):
        rest = s.split(None, 1)
        if len(rest) < 2:
            return None
        rest = rest[1].strip()
    elif s.lower().startswith("file:"):
        rest = s[5:].strip()
    else:
        # reiner relativer/absoluter Pfad zu einem lokalen Paket
        if not (s.startswith(".") or "/" in s or s.startswith("~")):
            return None
        rest = s
    rest = rest.strip().strip('"').strip("'")
    if not rest:
        return None
    p = (base_dir / rest).resolve()
    return p


def local_package_paths_in_requirements(
    req_file: Path, root: Path, packages: list[str]
) -> set[str]:
    """Welche Einträge aus `packages` werden in dieser requirements.txt referenziert?"""
    if not req_file.is_file():
        return set()
    canon_pkgs = {p: (root / p).resolve() for p in packages}
    found: set[str] = set()
    base = req_file.parent
    for line in req_file.read_text(encoding="utf-8").splitlines():
        p = _parse_requirement_line_to_path(line, base)
        if p is None:
            continue
        for rel, cpath in canon_pkgs.items():
            if p == cpath:
                found.add(rel)
                break
    return found


def requirement_line_references_local_package(
    line: str, req_file: Path, root: Path, packages: list[str]
) -> bool:
    """True, wenn die Zeile eine lokale Paket-Referenz ist (für Runtime-Install ohne Wheel-Duplikat)."""
    base = req_file.parent
    p = _parse_requirement_line_to_path(line, base)
    if p is None:
        return False
    try:
        rp = p.resolve()
    except OSError:
        return False
    for pkg in packages:
        if rp == (root / pkg).resolve():
            return True
    return False


def runtime_requirements_lines(
    req_file: Path, root: Path, packages: list[str]
) -> list[str]:
    """requirements.txt ohne lokale Paket-Zeilen (Wheels werden separat installiert)."""
    if not req_file.is_file():
        return []
    out: list[str] = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        if requirement_line_references_local_package(line, req_file, root, packages):
            continue
        out.append(line)
    return out


def package_local_dependency_graph(
    root: Path, packages: list[str]
) -> dict[str, set[str]]:
    """Für jedes Package: welche anderen lokalen Packages (requirements.txt)."""
    g: dict[str, set[str]] = {p: set() for p in packages}
    for p in packages:
        req = root / p / "requirements.txt"
        g[p] = local_package_paths_in_requirements(req, root, packages)
    return g


def service_local_dependencies(
    root: Path, service_path: str, packages: list[str]
) -> set[str]:
    req = root / service_path / "requirements.txt"
    return local_package_paths_in_requirements(req, root, packages)


def transitive_package_dependents(
    changed: set[str], pkg_graph: dict[str, set[str]]
) -> set[str]:
    """
    pkg_graph[X] = lokale Packages, von denen X abhängt.
    Rückwärtskante: wenn dep sich ändert, müssen alle Pakete neu, die dep referenzieren.
    """
    reverse: dict[str, list[str]] = {}
    for pkg, deps in pkg_graph.items():
        for d in deps:
            reverse.setdefault(d, []).append(pkg)

    affected = set(changed)
    q: deque[str] = deque(changed)
    while q:
        cur = q.popleft()
        for dependent in reverse.get(cur, []):
            if dependent not in affected:
                affected.add(dependent)
                q.append(dependent)
    return affected


def compose_service_names() -> list[str]:
    """Service-Keys unter `services:` in docker-compose.yml."""
    p = repo_root() / "docker-compose.yml"
    if not p.is_file():
        return []
    names: list[str] = []
    in_services = False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("services:"):
            in_services = True
            continue
        if not in_services:
            continue
        if line.strip() and not line[0].isspace():
            break
        m = re.match(r"^  ([a-zA-Z0-9_.-]+):\s*$", line)
        if m:
            names.append(m.group(1))
    return names


def compose_service_image_line(service_name: str) -> str | None:
    """Rohe `image:`-Zeile für einen Compose-Service (2 Leerzeichen Einrückung)."""
    p = repo_root() / "docker-compose.yml"
    if not p.is_file():
        return None
    lines = p.read_text(encoding="utf-8").splitlines()
    in_block = False
    for line in lines:
        if re.match(rf"^  {re.escape(service_name)}:\s*$", line):
            in_block = True
            continue
        if in_block:
            if re.match(r"^  [a-zA-Z0-9_.-]+:\s*$", line):
                break
            m = re.match(r"^\s+image:\s*(.+)$", line)
            if m:
                return m.group(1).strip()
    return None


def expand_compose_image_var(raw: str) -> str:
    """${VAR:-mongo:7} -> mongo:7; sonst unverändert."""
    s = raw.strip().strip('"').strip("'")
    if ":-" in s and s.startswith("${") and s.endswith("}"):
        s = s[2:-1]
        s = s.split(":-", 1)[-1]
    return s.strip()


def _image_base_name(image_ref: str) -> str:
    """z. B. docker.io/library/mongo:7 -> mongo; mongo@sha256:... -> mongo."""
    s = image_ref.strip()
    for pfx in ("docker.io/", "registry-1.docker.io/"):
        if s.startswith(pfx):
            s = s[len(pfx) :]
    s = s.split("@", 1)[0]
    repo = s.split(":", 1)[0]
    return repo.split("/")[-1].lower()


def _image_tag(image_ref: str) -> str | None:
    s = image_ref.strip().split("@", 1)[0]
    if ":" not in s:
        return None
    return s.rsplit(":", 1)[-1]


def required_stack_ok(modules: dict, running_images: list[str]) -> tuple[bool, list[str]]:
    """
    `required_stack_services`: Compose-Service-Namen, die laufen müssen (z. B. mongo).
    Vergleich über `image:` aus docker-compose (kein fest codiertes Image im Skript).
    """
    req = modules.get("required_stack_services")
    if not req:
        return True, []
    known = set(compose_service_names())
    missing: list[str] = []
    for name in req:
        if name not in known:
            missing.append(f"{name} (fehlt in docker-compose services)")
            continue
        raw = compose_service_image_line(name)
        if not raw:
            missing.append(f"{name} (kein image: in docker-compose)")
            continue
        want = expand_compose_image_var(raw)
        want_base = _image_base_name(want)
        want_tag = _image_tag(want)
        ok = False
        for ri in running_images:
            r = ri.strip()
            if _image_base_name(r) != want_base:
                continue
            if want_tag is None:
                ok = True
                break
            rt = _image_tag(r)
            if rt == want_tag or rt is None:
                ok = True
                break
        if not ok:
            missing.append(f"{name} (compose: {want}, kein passender Container in docker ps)")
    return len(missing) == 0, missing
