"""Security helpers for restricting file access to the MILY workspace."""

from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when a requested path is outside the authorized workspace."""


def resolve_workspace_path(workspace: str | Path, requested_path: str | Path) -> Path:
    """Resolve a relative path and ensure it stays inside ``workspace``.

    The check resolves ``..`` segments and existing symlinks before comparing
    paths. Absolute paths are rejected so callers use workspace-relative paths.
    The returned path may not exist yet, which allows safe file creation.
    """
    root = Path(workspace).expanduser().resolve()
    raw = str(requested_path)
    if not raw or "\x00" in raw:
        raise PathSecurityError("Path must be a non-empty valid string")

    candidate_input = Path(raw).expanduser()
    if candidate_input.is_absolute():
        raise PathSecurityError("Absolute paths are not allowed")

    candidate = (root / candidate_input).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError("Path is outside the authorized workspace") from exc
    return candidate
