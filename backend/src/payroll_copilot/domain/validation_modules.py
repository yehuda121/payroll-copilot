"""Pluggable validation-module registry.

Payroll is one module among many; future modules register without redesigning
the accountant portal or orchestration shell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ValidationModuleDefinition:
    key: str
    label: str
    description: str
    supported_document_types: tuple[str, ...] = ()
    rule_categories: tuple[str, ...] = ()
    enabled: bool = True
    metadata: dict[str, str] = field(default_factory=dict)


class ValidationModule(Protocol):
    """Future module implementations plug into orchestrators via this port."""

    @property
    def definition(self) -> ValidationModuleDefinition: ...


_MODULES: dict[str, ValidationModuleDefinition] = {}


def register_validation_module(definition: ValidationModuleDefinition) -> ValidationModuleDefinition:
    _MODULES[definition.key] = definition
    return definition


def get_validation_module(key: str) -> ValidationModuleDefinition | None:
    return _MODULES.get(key)


def list_validation_modules(*, enabled_only: bool = False) -> list[ValidationModuleDefinition]:
    modules = list(_MODULES.values())
    if enabled_only:
        modules = [module for module in modules if module.enabled]
    return sorted(modules, key=lambda item: item.label)


def _bootstrap_builtin_modules() -> None:
    if _MODULES:
        return
    register_validation_module(
        ValidationModuleDefinition(
            key="payroll",
            label="Payroll Validation",
            description="Deterministic payslip labor-law and compensation checks.",
            supported_document_types=("payslip",),
            rule_categories=("legal", "overtime", "pension", "department", "historical"),
        )
    )
    register_validation_module(
        ValidationModuleDefinition(
            key="attendance",
            label="Attendance Validation",
            description="Attendance report consistency checks (foundation).",
            supported_document_types=("attendance",),
            rule_categories=("vacation", "holiday"),
            enabled=True,
        )
    )
    register_validation_module(
        ValidationModuleDefinition(
            key="contract",
            label="Contract Validation",
            description="Employment contract cross-checks (planned wiring).",
            supported_document_types=("contract",),
            rule_categories=("contract",),
            enabled=True,
        )
    )
    register_validation_module(
        ValidationModuleDefinition(
            key="tax",
            label="Tax Validation",
            description="Tax deduction consistency module (extensible placeholder).",
            supported_document_types=("payslip",),
            rule_categories=("tax",),
            enabled=True,
        )
    )
    register_validation_module(
        ValidationModuleDefinition(
            key="pension",
            label="Pension Validation",
            description="Pension contribution module.",
            supported_document_types=("payslip",),
            rule_categories=("pension",),
            enabled=True,
        )
    )
    register_validation_module(
        ValidationModuleDefinition(
            key="company_custom",
            label="Company Custom Module",
            description="Organization-specific rule packs.",
            supported_document_types=("payslip", "attendance", "contract"),
            rule_categories=("company",),
            enabled=True,
        )
    )


_bootstrap_builtin_modules()
