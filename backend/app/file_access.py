from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path, PurePosixPath

MAX_REPOSITORY_FILE_BYTES = 1_048_576
MAX_TOOL_OUTPUT_BYTES = 32_768
TEXT_SNIFF_BYTES = 8_192


class FileAccessError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class SecureTextRead:
    content: str
    total_lines: int
    start_line: int
    end_line: int
    truncated: bool


def _raise_file_access_error(message: str, status_code: int) -> None:
    raise FileAccessError(message, status_code)


def _validate_secure_repo_path(repo_root: Path, file_path: str) -> Path:
    clean_relative = file_path.strip().lstrip("/\\")
    if not clean_relative:
        _raise_file_access_error("File path must be a non-empty string.", 400)

    repo_root = repo_root.resolve()
    normalized_parts = PurePosixPath(clean_relative.replace("\\", "/")).parts
    if ".git" in normalized_parts:
        _raise_file_access_error("Git metadata is not accessible.", 403)

    raw_target = repo_root / clean_relative

    current = raw_target
    while True:
        if current.is_symlink():
            _raise_file_access_error("Symlinks are not allowed.", 403)
        if current == repo_root:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    target_path = raw_target.resolve()

    try:
        if not target_path.is_relative_to(repo_root):
            _raise_file_access_error("Path traversal attempt detected.", 403)
    except ValueError:
        _raise_file_access_error("Path traversal attempt detected.", 403)

    if not target_path.exists() or not target_path.is_file():
        _raise_file_access_error("Requested file does not exist in repository.", 404)

    if target_path.stat().st_size > MAX_REPOSITORY_FILE_BYTES:
        _raise_file_access_error("File size exceeds maximum limit (1MB).", 400)

    mime_type, _ = guess_type(str(target_path))
    if mime_type and mime_type.startswith("image/"):
        _raise_file_access_error("Binary or image files are not supported.", 415)

    with target_path.open("rb") as handle:
        sniff = handle.read(TEXT_SNIFF_BYTES)

    if b"\x00" in sniff:
        _raise_file_access_error("Binary or image files are not supported.", 415)

    try:
        sniff.decode("utf-8")
    except UnicodeDecodeError:
        _raise_file_access_error("Binary or image files are not supported.", 415)

    return target_path


def read_secure_text_file(
    repo_root: Path,
    file_path: str,
    *,
    start_line: int = 1,
    num_lines: int | None = None,
    max_output_bytes: int | None = None,
) -> SecureTextRead:
    target_path = _validate_secure_repo_path(repo_root, file_path)

    effective_start_line = max(1, start_line)
    effective_num_lines = None if num_lines is None else max(0, num_lines)
    selected_lines: list[str] = []
    total_lines = 0
    truncated = False
    output_bytes = 0

    with target_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            total_lines = line_number
            if line_number < effective_start_line:
                continue
            if effective_num_lines is not None and len(selected_lines) >= effective_num_lines:
                continue
            if truncated:
                continue

            clean_line = line.rstrip("\r\n")
            line_bytes = len(clean_line.encode("utf-8"))
            extra_bytes = line_bytes + (1 if selected_lines else 0)
            if max_output_bytes is not None and output_bytes + extra_bytes > max_output_bytes:
                truncated = True
                continue

            selected_lines.append(clean_line)
            output_bytes += extra_bytes

    if effective_start_line > 1 and total_lines and effective_start_line > total_lines:
        return read_secure_text_file(
            repo_root,
            file_path,
            start_line=1,
            num_lines=num_lines,
            max_output_bytes=max_output_bytes,
        )

    content = "\n".join(selected_lines)
    end_line = effective_start_line + len(selected_lines) - 1 if selected_lines else 0
    return SecureTextRead(
        content=content,
        total_lines=total_lines,
        start_line=effective_start_line if selected_lines else 1 if total_lines else effective_start_line,
        end_line=end_line,
        truncated=truncated,
    )
