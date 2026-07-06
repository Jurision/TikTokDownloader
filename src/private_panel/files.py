from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from .models import FileEntry


def _is_anchored_path(path: str) -> bool:
    posix_path = PurePosixPath(path)
    windows_path = PureWindowsPath(path)
    return (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
    )


def _reject_anchored_path(path: str, message: str) -> None:
    if _is_anchored_path(path):
        raise ValueError(message)


def _resolve_under(root: Path, relative: str) -> Path:
    root_path = Path(root).resolve()
    _reject_anchored_path(relative, "Path escapes output root")
    target = root_path.joinpath(relative).resolve()
    if target != root_path and root_path not in target.parents:
        raise ValueError("Path escapes output root")
    return target


def _modified_at(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def list_files(output_root: Path, output_dir: str) -> list[FileEntry]:
    directory = _resolve_under(output_root, output_dir)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError("Job output path is not a directory")
    entries = []
    directory_path = directory.resolve()
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        if resolved_path != directory_path and directory_path not in resolved_path.parents:
            continue
        relative_path = path.relative_to(directory).as_posix()
        entries.append(
            FileEntry(
                name=path.name,
                relative_path=relative_path,
                size=path.stat().st_size,
                modified_at=_modified_at(path),
            )
        )
    return entries


def resolve_job_file(output_root: Path, output_dir: str, relative_path: str) -> Path:
    directory = _resolve_under(output_root, output_dir)
    _reject_anchored_path(relative_path, "Path escapes job output directory")
    target = directory.joinpath(relative_path).resolve()
    if target != directory and directory not in target.parents:
        raise ValueError("Path escapes job output directory")
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    return target
