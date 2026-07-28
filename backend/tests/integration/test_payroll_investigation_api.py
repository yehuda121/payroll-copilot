"""Integration tests: investigation via /assistant/employee/chat (Scenarios A–D)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

langgraph = pytest.importorskip("langgraph")

from payroll_copilot.application.use_cases.payroll_investigation import (  # noqa: E402
    PayrollInvestigationUseCase,
)
from payroll_copilot.domain.entities import Employee  # noqa: E402
from payroll_copilot.domain.enums import (  # noqa: E402
    EmployeeStatus,
    EmploymentType,
    SalaryType,
    UserRole,
)
from payroll_copilot.domain.investigation.types import PeriodRef, PeriodSnapshot  # noqa: E402
from payroll_copilot.infrastructure.ai.agents.payroll_investigation_graph import (  # noqa: E402
    PayrollInvestigationGraph,
)
from payroll_copilot.presentation.api.rate_limit_deps import (  # noqa: E402
    limit_chat_by_ip,
    limit_chat_by_user,
)
from payroll_copilot.presentation.api.security import (  # noqa: E402
    AuthPrincipal,
    BoundEmployeeContext,
    get_auth_principal,
    require_accountant,
    require_bound_employee,
)
from payroll_copilot.presentation.main import app  # noqa: E402
import payroll_copilot.presentation.api.routes.assistant as assistant_routes  # noqa: E402


class _FakeInvestigationData:
    def __init__(
        self,
        *,
        periods: set[str],
        snapshots: dict[str, PeriodSnapshot],
        enrich_fill: dict[str, object] | None = None,
    ) -> None:
        self.periods = periods
        self.snapshots = snapshots
        self.enrich_fill = enrich_fill or {}
        self.seen_org: object | None = None
        self.seen_emp: object | None = None
        self.include_unpublished_flags: list[bool] = []

    async def list_available_payslip_periods(
        self,
        *,
        organization_id,
        employee_id,
        include_unpublished: bool = False,
    ) -> set[str]:
        self.seen_org = organization_id
        self.seen_emp = employee_id
        self.include_unpublished_flags.append(include_unpublished)
        return set(self.periods)

    async def load_period_snapshot(
        self,
        *,
        organization_id,
        employee_id,
        period: PeriodRef,
        include_unpublished: bool = False,
    ) -> PeriodSnapshot | None:
        self.include_unpublished_flags.append(include_unpublished)
        return self.snapshots.get(period.key)

    async def enrich_snapshot_from_original(
        self,
        snapshot: PeriodSnapshot,
        *,
        missing_keys: tuple[str, ...],
    ) -> PeriodSnapshot:
        merged = dict(snapshot.structured_fields)
        filled: list[str] = []
        for key in missing_keys:
            if key in self.enrich_fill:
                merged[key] = self.enrich_fill[key]
                filled.append(key)
        return PeriodSnapshot(
            period=snapshot.period,
            document_id=snapshot.document_id,
            storage_key=snapshot.storage_key,
            structured_fields=merged,
            finding_excerpts=list(snapshot.finding_excerpts),
            enrichment_applied=bool(filled),
            enrichment_notes=("filled:" + ",".join(filled)) if filled else "enrichment_no_fields",
        )


def _snap(period: PeriodRef, fields: dict) -> PeriodSnapshot:
    return PeriodSnapshot(
        period=period,
        document_id=uuid4(),
        storage_key=f"s3/{period.key}.pdf",
        structured_fields=fields,
    )


def _employee(*, organization_id, employee_id, employee_number: str = "E-100") -> Employee:
    return Employee(
        id=employee_id,
        organization_id=organization_id,
        employee_number=employee_number,
        first_name="Dana",
        last_name="Cohen",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _install_bound_employee(
    *,
    organization_id,
    employee_id,
    role: str = UserRole.EMPLOYEE.value,
) -> BoundEmployeeContext:
    employee = _employee(organization_id=organization_id, employee_id=employee_id)
    principal = AuthPrincipal(
        user_id=uuid4(),
        role=role,
        organization_id=organization_id,
        employee_id=employee_id if role == UserRole.EMPLOYEE.value else None,
        email="investigation-test@test.local",
    )
    bound = BoundEmployeeContext(
        principal=principal,
        employee=employee,
        national_id_encrypted=None,
    )

    async def _bound() -> BoundEmployeeContext:
        return bound

    async def _principal() -> AuthPrincipal:
        return principal

    async def _noop_limit() -> None:
        return None

    app.dependency_overrides[require_bound_employee] = _bound
    app.dependency_overrides[get_auth_principal] = _principal
    app.dependency_overrides[limit_chat_by_ip] = _noop_limit
    app.dependency_overrides[limit_chat_by_user] = _noop_limit
    return bound


def _install_investigation(data: _FakeInvestigationData, monkeypatch: pytest.MonkeyPatch) -> None:
    use_case = PayrollInvestigationUseCase(runner=PayrollInvestigationGraph(data))
    monkeypatch.setattr(
        assistant_routes,
        "_get_investigation_use_case",
        lambda: use_case,
    )


@pytest.mark.asyncio
async def test_employee_chat_scenario_a_explained(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, emp_id = uuid4(), uuid4()
    _install_bound_employee(organization_id=org_id, employee_id=emp_id)
    jul, jun = PeriodRef(2026, 7), PeriodRef(2026, 6)
    data = _FakeInvestigationData(
        periods={"2026-07", "2026-06"},
        snapshots={
            "2026-07": _snap(
                jul,
                {
                    "gross_salary": {"value": "12000"},
                    "net_salary": {"value": "9000"},
                },
            ),
            "2026-06": _snap(
                jun,
                {
                    "gross_salary": {"value": "11000"},
                    "net_salary": {"value": "9500"},
                },
            ),
        },
    )
    _install_investigation(data, monkeypatch)

    response = await client.post(
        "/api/v1/assistant/employee/chat",
        json={
            "message": "למה ירד לי הנטו בתלוש יולי 2026?",
            "locale": "he",
            "session_id": "inv-a",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["guardrail_status"] == "passed"
    assert body["locale"] == "he"
    assert "יולי 2026" in body["answer"]
    assert "יוני 2026" in body["answer"]
    assert data.seen_org == org_id
    assert data.seen_emp == emp_id
    assert False in data.include_unpublished_flags


@pytest.mark.asyncio
async def test_employee_chat_scenario_b_lookback(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, emp_id = uuid4(), uuid4()
    _install_bound_employee(organization_id=org_id, employee_id=emp_id)
    jul, apr = PeriodRef(2026, 7), PeriodRef(2026, 4)
    data = _FakeInvestigationData(
        periods={"2026-07", "2026-04"},
        snapshots={
            "2026-07": _snap(
                jul,
                {"gross_salary": {"value": "12000"}, "net_salary": {"value": "9000"}},
            ),
            "2026-04": _snap(
                apr,
                {"gross_salary": {"value": "12000"}, "net_salary": {"value": "9200"}},
            ),
        },
    )
    _install_investigation(data, monkeypatch)

    response = await client.post(
        "/api/v1/assistant/employee/chat",
        json={
            "message": "What changed on my payslip for July 2026?",
            "locale": "en",
            "session_id": "inv-b",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "2026-04" in body["answer"] or "April 2026" in body["answer"]
    assert body["requires_human_review"] is False


@pytest.mark.asyncio
async def test_employee_chat_scenario_c_enrichment(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, emp_id = uuid4(), uuid4()
    _install_bound_employee(organization_id=org_id, employee_id=emp_id)
    jul, jun = PeriodRef(2026, 7), PeriodRef(2026, 6)
    data = _FakeInvestigationData(
        periods={"2026-07", "2026-06"},
        snapshots={
            "2026-07": _snap(
                jul,
                {"gross_salary": {"value": "12000"}, "net_salary": {"value": "9000"}},
            ),
            "2026-06": _snap(
                jun,
                {
                    "gross_salary": {"value": "11000"},
                    "net_salary": {"value": "8500"},
                    "overtime_hours": {"value": "2"},
                },
            ),
        },
        enrich_fill={"overtime_hours": {"value": "12"}},
    )
    _install_investigation(data, monkeypatch)

    response = await client.post(
        "/api/v1/assistant/employee/chat",
        json={
            "message": "why did my overtime increase in July 2026?",
            "locale": "en",
            "session_id": "inv-c",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "overtime" in body["answer"].lower() or "July 2026" in body["answer"]
    assert "s3_ephemeral_enrichment" in body["used_tools"]


@pytest.mark.asyncio
async def test_employee_chat_scenario_d_no_history(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, emp_id = uuid4(), uuid4()
    _install_bound_employee(organization_id=org_id, employee_id=emp_id)
    jul = PeriodRef(2026, 7)
    data = _FakeInvestigationData(
        periods={"2026-07"},
        snapshots={
            "2026-07": _snap(
                jul,
                {"gross_salary": {"value": "12000"}, "net_salary": {"value": "9000"}},
            ),
        },
    )
    _install_investigation(data, monkeypatch)

    response = await client.post(
        "/api/v1/assistant/employee/chat",
        json={
            "message": "למה ירד לי הנטו ביולי 2026?",
            "locale": "he",
            "session_id": "inv-d",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requires_human_review"] is True
    assert "יוני 2026" in body["answer"]
    assert "אינו זמין" in body["answer"] or "תעלו" in body["answer"]


@pytest.mark.asyncio
async def test_accountant_chat_scenario_a_uses_unpublished_flag(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, emp_id = uuid4(), uuid4()
    employee = _employee(
        organization_id=org_id,
        employee_id=emp_id,
        employee_number="E-42",
    )
    principal = AuthPrincipal(
        user_id=uuid4(),
        role=UserRole.ACCOUNTANT.value,
        organization_id=org_id,
        employee_id=None,
        email="accountant@test.local",
    )
    bound = BoundEmployeeContext(
        principal=principal,
        employee=employee,
        national_id_encrypted=None,
    )

    async def _principal() -> AuthPrincipal:
        return principal

    async def _accountant() -> AuthPrincipal:
        return principal

    async def _noop() -> None:
        return None

    async def _bind(*, employee_number: str, principal: AuthPrincipal):
        assert employee_number == "E-42"
        assert principal.organization_id == org_id
        return bound

    app.dependency_overrides[get_auth_principal] = _principal
    app.dependency_overrides[require_accountant] = _accountant
    app.dependency_overrides[limit_chat_by_ip] = _noop
    app.dependency_overrides[limit_chat_by_user] = _noop
    monkeypatch.setattr(assistant_routes, "bind_accountant_selected_employee", _bind)

    jul, jun = PeriodRef(2026, 7), PeriodRef(2026, 6)
    data = _FakeInvestigationData(
        periods={"2026-07", "2026-06"},
        snapshots={
            "2026-07": _snap(
                jul,
                {"gross_salary": {"value": "12000"}, "net_salary": {"value": "9000"}},
            ),
            "2026-06": _snap(
                jun,
                {"gross_salary": {"value": "11000"}, "net_salary": {"value": "8800"}},
            ),
        },
    )
    _install_investigation(data, monkeypatch)

    response = await client.post(
        "/api/v1/assistant/accountant/employee/chat",
        json={
            "message": "למה ירד לי הנטו ביולי 2026?",
            "locale": "he",
            "session_id": "inv-acc-a",
            "employee_number": "E-42",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "יולי 2026" in body["answer"]
    assert True in data.include_unpublished_flags
    assert data.seen_emp == emp_id
