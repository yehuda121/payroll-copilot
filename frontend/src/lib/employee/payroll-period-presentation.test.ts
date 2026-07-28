import { describe, expect, it } from 'vitest';
import { applyPayrollPeriodPresentation } from './payroll-period-presentation';
import { proposedPayrollPeriodValue } from './payroll-period-proposal';

describe('payroll period presentation', () => {
  it('marks extracted period as passed without approval', () => {
    const result = applyPayrollPeriodPresentation({
      fields: [
        {
          key: 'pay_period',
          value: '01/07/2026',
          confidence: 1,
          source_text: null,
          status: 'FOUND',
        },
      ],
      drafts: {},
      validationMap: {},
      periodApproved: false,
      proposedExplanation: 'proposed',
      workspaceYear: 2026,
      workspaceMonth: 7,
    });
    expect(result.requiresApproval).toBe(false);
    expect(result.validationMap.pay_period?.status).toBe('passed');
    expect(result.validationMap.pay_period?.requiresApproval).toBe(false);
  });

  it('proposes 01/workspace_month/workspace_year as warning when missing', () => {
    const result = applyPayrollPeriodPresentation({
      fields: [],
      drafts: {},
      validationMap: {},
      periodApproved: false,
      proposedExplanation: 'The payroll period was not found in the payslip',
      workspaceYear: 2026,
      workspaceMonth: 6,
    });
    expect(result.requiresApproval).toBe(true);
    expect(result.proposedValue).toBe('01/06/2026');
    expect(result.displayDrafts.pay_period?.value).toBe('01/06/2026');
    expect(result.validationMap.pay_period?.status).toBe('uncertain');
    expect(result.validationMap.pay_period?.requiresApproval).toBe(true);
    expect(result.validationMap.pay_period?.status).not.toBe('failed');
  });

  it('marks proposed period as passed after user approval without forcing dirty', () => {
    const result = applyPayrollPeriodPresentation({
      fields: [],
      drafts: {
        pay_period: { value: '01/06/2026', clear: false, dirty: true },
      },
      validationMap: {},
      periodApproved: true,
      proposedExplanation: 'proposed',
      workspaceYear: 2026,
      workspaceMonth: 6,
    });
    expect(result.requiresApproval).toBe(false);
    expect(result.validationMap.pay_period?.status).toBe('passed');
    expect(result.validationMap.pay_period?.requiresApproval).toBe(false);
    expect(result.validationMap.pay_period?.userApproved).toBe(true);
    expect(result.displayDrafts.pay_period?.value).toBe('01/06/2026');
    expect(result.displayDrafts.pay_period?.dirty).toBe(true);
  });

  it('does not keep dirty after approval once period is persisted on fields', () => {
    const result = applyPayrollPeriodPresentation({
      fields: [
        {
          key: 'pay_period',
          value: '01/06/2026',
          confidence: 1,
          source_text: null,
          status: 'FOUND',
        },
      ],
      drafts: {
        pay_period: { value: '01/06/2026', clear: false, dirty: false },
      },
      validationMap: {},
      periodApproved: true,
      proposedExplanation: 'proposed',
      workspaceYear: 2026,
      workspaceMonth: 6,
    });
    expect(result.requiresApproval).toBe(false);
    expect(result.displayDrafts.pay_period?.dirty).toBe(false);
    expect(result.proposedValue).toBe(proposedPayrollPeriodValue(2026, 6));
  });
});
