"""Safe read-only access to payslip document fixtures for developer tooling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ALLOWED_FIXTURE_GROUPS = frozenset({"valid", "invalid"})


@dataclass(frozen=True, slots=True)
class FixtureDocument:
    id: str
    group: str
    filename: str
    path: Path
    size_bytes: int
    media_type: str


class FixtureAccessError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def resolve_fixtures_root() -> Path:
    """Locate payslip fixtures for host and Docker-mounted layouts."""
    candidates = [
        Path("/app/tests/fixtures/documents/payslips"),
        Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "documents" / "payslips",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise FixtureAccessError(
        "fixtures_unavailable",
        "Fixture directory not found. Mount backend/tests/fixtures or run from the backend tree.",
    )


def _guess_media_type(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    return "application/octet-stream"


def list_fixture_documents() -> dict[str, list[FixtureDocument]]:
    root = resolve_fixtures_root()
    grouped: dict[str, list[FixtureDocument]] = {group: [] for group in sorted(ALLOWED_FIXTURE_GROUPS)}
    for group in ALLOWED_FIXTURE_GROUPS:
        group_dir = root / group
        if not group_dir.is_dir():
            continue
        for path in sorted(group_dir.iterdir()):
            if not path.is_file():
                continue
            grouped[group].append(
                FixtureDocument(
                    id=f"{group}/{path.name}",
                    group=group,
                    filename=path.name,
                    path=path,
                    size_bytes=path.stat().st_size,
                    media_type=_guess_media_type(path.name),
                )
            )
    return grouped


def resolve_fixture(fixture_id: str) -> FixtureDocument:
    normalized = fixture_id.replace("\\", "/").strip().lstrip("/")
    parts = [part for part in normalized.split("/") if part and part != "."]
    if len(parts) != 2:
        raise FixtureAccessError("invalid_fixture_id", "Fixture id must be '<group>/<filename>'.")
    group, filename = parts
    if group not in ALLOWED_FIXTURE_GROUPS:
        raise FixtureAccessError("invalid_fixture_group", f"Unknown fixture group: {group}")
    if ".." in filename or "/" in filename:
        raise FixtureAccessError("invalid_fixture_id", "Invalid fixture filename.")

    root = resolve_fixtures_root().resolve()
    candidate = (root / group / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FixtureAccessError("path_traversal", "Fixture path is outside the allowed directory.") from exc
    if not candidate.is_file():
        raise FixtureAccessError("fixture_not_found", f"Fixture not found: {fixture_id}")

    return FixtureDocument(
        id=f"{group}/{filename}",
        group=group,
        filename=filename,
        path=candidate,
        size_bytes=candidate.stat().st_size,
        media_type=_guess_media_type(filename),
    )


def read_fixture_bytes(fixture_id: str) -> tuple[FixtureDocument, bytes]:
    fixture = resolve_fixture(fixture_id)
    return fixture, fixture.path.read_bytes()
