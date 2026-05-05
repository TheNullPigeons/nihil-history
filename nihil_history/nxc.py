from __future__ import annotations

import shutil
import subprocess


def nxcdb_available() -> bool:
    return shutil.which("nxcdb") is not None


def _run(args: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["nxcdb", *args],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def list_workspaces() -> list[str]:
    """Return all NXC workspaces. Empty list if nxcdb missing or fails."""
    if not nxcdb_available():
        return []
    ok, out = _run(["-gw"])
    if not ok:
        return []
    names: list[str] = []
    for line in out.splitlines():
        cleaned = line.lstrip(" *").strip()
        if cleaned:
            names.append(cleaned)
    return names


def get_workspace() -> str | None:
    """Return active NXC workspace (line marked with '*'), or None."""
    if not nxcdb_available():
        return None
    ok, out = _run(["-gw"])
    if not ok:
        return None
    for line in out.splitlines():
        if line.lstrip().startswith("*"):
            return line.lstrip(" *").strip()
    return None


def create_workspace(name: str) -> bool:
    if not nxcdb_available():
        return False
    ok, _ = _run(["-cw", name])
    return ok


def set_workspace(name: str) -> bool:
    if not nxcdb_available():
        return False
    ok, _ = _run(["-sw", name])
    return ok


def ensure_workspace(name: str) -> bool:
    """Create workspace if missing, then set it active. Returns True on success."""
    if not nxcdb_available():
        return False
    if name not in list_workspaces():
        if not create_workspace(name):
            return False
    return set_workspace(name)
