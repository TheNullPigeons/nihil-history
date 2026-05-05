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


def get_workspace() -> str | None:
    if not nxcdb_available():
        return None
    ok, out = _run(["-gw"])
    if not ok:
        return None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            return line.split(":", 1)[1].strip()
        return line
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
    """Set workspace, creating it first if needed. Returns True on success."""
    if not nxcdb_available():
        return False
    if set_workspace(name):
        return True
    if create_workspace(name):
        return set_workspace(name)
    return False
