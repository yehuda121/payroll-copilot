# Payroll Copilot — Rule Engine Design

## Philosophy

The Rule Engine is the **core deterministic brain** of Payroll Copilot. It:

- Evaluates payroll data against configurable rules
- Produces structured findings with severity and confidence
- Has **zero dependency on AI** for pass/fail decisions
- Supports hot-addition of rules without modifying existing rule code

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ValidationOrchestrator                    │
│  Builds ValidationContext → selects applicable rules → runs  │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                      RuleRegistry                            │
│  Discovers and registers Rule implementations at startup     │
└─────────────────────────────┬───────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  LegalRuleSet   │  │ DepartmentRules │  │  ContractRules  │
│  (YAML-backed)  │  │  (Plugin-based) │  │  (RAG-assisted) │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │ HistoricalRules │
                    │  (DB comparison)│
                    └─────────────────┘
```

---

## Rule Interface

Every rule is an independent class implementing:

```python
class Rule(Protocol):
    rule_id: str           # e.g. "legal.overtime.daily_limit"
    category: RuleCategory
    priority: int          # Lower = earlier evaluation
    
    def applies_to(self, context: ValidationContext) -> bool:
        """Whether this rule should run for this payslip."""
        
    def evaluate(self, context: ValidationContext) -> RuleResult | None:
        """Return finding if violation detected; None if pass."""
```

### ValidationContext

Immutable snapshot containing:

| Field | Source |
|-------|--------|
| `payslip` | Extracted structured payslip data |
| `employee` | Employee master record (point-in-time) |
| `department` | Department + rule profile |
| `contract_clauses` | RAG-retrieved clauses (if needed) |
| `historical_payslips` | Previous N months |
| `attendance` | Vacation/sick/work days for period |
| `legal_config` | Loaded YAML rules |
| `org_rules` | Custom org/department rules from DB |
| `period` | Year/month being validated |
| `field_confidences` | OCR confidence per payslip field |

---

## Rule Categories

| Category | Source | Examples |
|----------|--------|----------|
| `legal` | YAML files | Minimum wage, youth employment, break rules |
| `tax` | YAML `tax.yaml` | Tax brackets, credits |
| `pension` | YAML `pension.yaml` | Employer/employee contributions |
| `overtime` | YAML `overtime.yaml` | Daily/weekly limits, rates |
| `vacation` | YAML `vacation.yaml` | Accrual, usage |
| `transportation` | YAML `transportation.yaml` | Travel allowance |
| `holiday` | YAML `holidays.yaml` | Holiday pay |
| `department` | Python plugins | Lawyer overtime caps, intern hour limits |
| `contract` | RAG + rules | Individual agreement terms |
| `historical` | DB comparison | Salary drift, anomaly detection |
| `company` | DB `rule_definitions` | Org-specific policies |

---

## YAML Legal Rules

Stored in `config/rules/labor_law/`. Loaded at startup, versioned in DB.

### Example: `overtime.yaml`

```yaml
version: "2026.1.0"
effective_from: "2026-01-01"
rules:
  daily_overtime_limit:
    id: legal.overtime.daily_limit
    description:
      he: "מגבלת שעות נוספות יומיות"
      en: "Daily overtime limit"
    parameters:
      max_hours: 2
      applies_to_employment_types: [full_time, part_time]
    legal_reference:
      he: "חוק שעות עבודה ומנוחה, תשי\"א-1951, סעיף 16"
    severity: warning

  overtime_rate_first_two_hours:
    id: legal.overtime.rate_tier_1
    parameters:
      hours_range: [0, 2]
      multiplier: 1.25
    severity: critical
```

### YAML Loader

- Parses YAML into typed `LegalRuleConfig` Pydantic models
- Validates schema on load; rejects malformed files
- Computes SHA256 hash for versioning
- Watches for file changes after MCP-approved updates

---

## Department Rule Plugins

Departments map to rule profiles via `departments.rule_profile`:

```yaml
# config/rules/departments/lawyers.yaml
profile: lawyers
additional_rules:
  - rule_class: LawyersOvertimeCapRule
  - rule_class: CourtDayAllowanceRule
disabled_rules:
  - legal.overtime.daily_limit  # Lawyers have different arrangement
```

### Adding a New Department

1. Add department record in DB (or seed)
2. Create `config/rules/departments/{profile}.yaml`
3. Implement rule classes in `domain/rules/departments/{profile}/`
4. Register in `RuleRegistry` via entry point or auto-discovery

**No changes to ValidationOrchestrator or other departments.**

---

## Rule Implementation Pattern

```python
@register_rule
class DailyOvertimeLimitRule:
    rule_id = "legal.overtime.daily_limit"
    category = RuleCategory.OVERTIME
    priority = 100

    def applies_to(self, context: ValidationContext) -> bool:
        return context.employee.employment_type in (
            EmploymentType.FULL_TIME,
            EmploymentType.PART_TIME,
        )

    def evaluate(self, context: ValidationContext) -> RuleResult | None:
        config = context.legal_config.overtime.daily_overtime_limit
        actual = context.payslip.overtime_hours_daily_max
        if actual is None:
            return RuleResult.missing_data(self.rule_id, "overtime_hours")
        if actual > config.parameters.max_hours:
            return RuleResult.violation(
                rule_id=self.rule_id,
                severity=config.severity,
                expected=config.parameters.max_hours,
                actual=actual,
                legal_reference=config.legal_reference,
                confidence=context.field_confidence("overtime_hours"),
            )
        return None
```

---

## Contract Rules (RAG-Assisted, Deterministic Evaluation)

1. `ContractClauseRule.applies_to()` checks if employee has indexed contract
2. Emits `RAGQuery` for relevant topic (e.g., "overtime compensation")
3. `RAGRetriever` returns clauses with scores
4. Rule parses **structured constraints** from clause text using predefined patterns (regex + optional LLM pre-processing stored at index time — not at validation time)
5. Deterministic comparison against payslip values

If RAG confidence < threshold → finding severity downgraded to `info` with "manual review recommended".

---

## Historical Rules

Compare current payslip against rolling N-month history:

| Rule | Logic |
|------|-------|
| `historical.salary_drift` | > X% change without contract update |
| `historical.overtime_anomaly` | > 2 std dev from employee mean |
| `historical.tax_consistency` | Tax bracket change without salary change |
| `historical.missing_deduction` | Recurring deduction absent |

Uses DB queries only; fully deterministic.

---

## Org Custom Rules (Database)

`rule_definitions.rule_config` JSONB supports parameterized rules without code:

```json
{
  "rule_type": "threshold",
  "field": "transportation_allowance",
  "max_value": 500,
  "severity": "warning"
}
```

Generic `ConfigurableThresholdRule` interprets these at runtime.

Complex org rules get dedicated rule classes registered per org.

---

## Evaluation Pipeline

```
1. Build ValidationContext
2. RuleRegistry.get_applicable_rules(context)
   - Filter by applies_to()
   - Apply department profile (enable/disable)
   - Sort by priority
3. For each rule:
   a. evaluate(context)
   b. Collect findings
4. Compute overall_result:
   - any critical → critical
   - any warning → warnings
   - else → pass
5. Compute overall_confidence (min of finding confidences)
6. Persist ValidationRun + Findings
```

Rules are **independent** — no rule depends on another rule's output. If ordering matters, use priority and encode in single rule.

---

## Extensibility Checklist

| To add... | Action |
|-----------|--------|
| New legal rule | Edit YAML + implement evaluator if new logic type |
| New department | DB record + profile YAML + rule classes |
| New org policy | Insert `rule_definitions` row |
| New rule category | Add enum + registry namespace |
| Disable rule for dept | Department profile `disabled_rules` |

---

## Performance

- YAML configs cached in memory (invalidated on MCP approval)
- Historical queries use indexed `(employee_id, period)` lookups
- Batch validation: rules are stateless; parallelize across payslips via Celery
- Target: < 500ms per payslip for full rule suite (excluding RAG)

---

## Testing Strategy

- Unit test each rule with fixture ValidationContext
- YAML schema validation tests
- Golden payslip fixtures (anonymized) with expected findings
- Property-based tests for calculation rules (overtime, tax)
- Regression suite when YAML versions change
