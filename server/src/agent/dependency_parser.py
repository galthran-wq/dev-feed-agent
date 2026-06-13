"""Parse the package names a developer depends on from common manifest files.

A descriptive signal for the interest profile: the libraries someone reaches for
say a lot about what they build. Pure functions — no I/O — so they're easy to test.
"""

import json
import re
import tomllib

# Split a PEP 508 requirement string ("fastapi>=0.115,<1 ; python_version>'3.10'")
# down to its package name.
_NAME_BOUNDARY = re.compile(r"[<>=!~;\[\(\s@]")


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _req_name(requirement: str) -> str:
    return _normalize(_NAME_BOUNDARY.split(requirement.strip(), 1)[0])


def _dedupe(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def parse_pyproject(content: str) -> list[str]:
    data = tomllib.loads(content)
    names: list[str] = []
    project = data.get("project", {})
    for dep in project.get("dependencies", []) or []:
        names.append(_req_name(dep))
    for group in (project.get("optional-dependencies", {}) or {}).values():
        names.extend(_req_name(dep) for dep in group)
    # Poetry-style table: keys are package names.
    poetry = data.get("tool", {}).get("poetry", {})
    for dep_name in poetry.get("dependencies", {}) or {}:
        if dep_name.lower() != "python":
            names.append(_normalize(dep_name))
    return _dedupe(names)


def parse_requirements(content: str) -> list[str]:
    names: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-", "git+", "http://", "https://")):
            continue
        names.append(_req_name(line))
    return _dedupe(names)


def parse_package_json(content: str) -> list[str]:
    data = json.loads(content)
    names: list[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        names.extend(_normalize(name) for name in (data.get(key, {}) or {}))
    return _dedupe(names)


def parse_dependencies(filename: str, content: str) -> list[str]:
    """Dispatch on filename. Returns [] for unknown/unparseable files (never raises)."""
    name = filename.rsplit("/", 1)[-1].lower()
    try:
        if name == "pyproject.toml":
            return parse_pyproject(content)
        if name.startswith("requirements") and name.endswith(".txt"):
            return parse_requirements(content)
        if name == "package.json":
            return parse_package_json(content)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, ValueError):
        return []
    return []
