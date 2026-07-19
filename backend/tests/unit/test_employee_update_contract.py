import pytest
from pydantic import ValidationError

from payroll_copilot.presentation.api.routes.employees import EmployeeUpdateRequest


def test_employee_update_rejects_email_changes() -> None:
    with pytest.raises(ValidationError, match="email"):
        EmployeeUpdateRequest.model_validate(
            {
                "first_name": "Updated",
                "email": "new-address@example.com",
            }
        )
