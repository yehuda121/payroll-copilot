"""Versioned legal-rule file edits with audit trail (foundation)."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository


@dataclass(frozen=True, slots=True)
class RuleVersionRecord:
    version_id: str
    filename: str
    created_at: str
    reason: str
    actor_user_id: str | None
    previous_version_id: str | None


class RuleVersionStore:
    """Filesystem version store under config/rules/.versions — expandable later to DB."""

    def __init__(self, rules_root: Path | str) -> None:
        self._rules_root = Path(rules_root)
        self._versions_root = self._rules_root / ".versions"
        self._versions_root.mkdir(parents=True, exist_ok=True)

    def list_versions(self, filename: str) -> list[RuleVersionRecord]:
        safe = Path(filename).name
        index_path = self._versions_root / f"{safe}.index.json"
        if not index_path.exists():
            return []
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        return [RuleVersionRecord(**item) for item in payload.get("versions", [])]

    def read_current(self, filename: str) -> str:
        path = self._rules_root / Path(filename).name
        if not path.exists():
            raise FileNotFoundError(filename)
        return path.read_text(encoding="utf-8")

    def write_with_version(
        self,
        *,
        filename: str,
        content: str,
        reason: str,
        actor_user_id: UUID | None,
        audit: AuditLogRepository | None = None,
        organization_id: UUID | None = None,
    ) -> RuleVersionRecord:
        safe = Path(filename).name
        target = self._rules_root / safe
        if not target.exists():
            raise FileNotFoundError(filename)

        previous = self.list_versions(safe)
        version_id = str(uuid4())
        stamp = datetime.now(timezone.utc).isoformat()
        archive_dir = self._versions_root / safe.replace(".", "_")
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{version_id}.yaml"
        shutil.copy2(target, archive_path)

        record = RuleVersionRecord(
            version_id=version_id,
            filename=safe,
            created_at=stamp,
            reason=reason.strip() or "Rule edit",
            actor_user_id=str(actor_user_id) if actor_user_id else None,
            previous_version_id=previous[0].version_id if previous else None,
        )
        index_path = self._versions_root / f"{safe}.index.json"
        versions = [asdict(record), *[asdict(item) for item in previous]]
        index_path.write_text(
            json.dumps({"versions": versions}, indent=2),
            encoding="utf-8",
        )
        target.write_text(content, encoding="utf-8")
        return record

    def rollback(
        self,
        *,
        filename: str,
        version_id: str,
        reason: str,
        actor_user_id: UUID | None,
    ) -> RuleVersionRecord:
        safe = Path(filename).name
        archive_dir = self._versions_root / safe.replace(".", "_")
        archive_path = archive_dir / f"{version_id}.yaml"
        if not archive_path.exists():
            raise FileNotFoundError(version_id)
        content = archive_path.read_text(encoding="utf-8")
        return self.write_with_version(
            filename=safe,
            content=content,
            reason=f"Rollback to {version_id}: {reason}",
            actor_user_id=actor_user_id,
        )
