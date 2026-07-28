/**
 * Digital form view-model.
 * Required → Expected → (optional Other). Missing required fields render empty.
 * Other extracted fields remain in the Document Model / structured_data;
 * employee primary view may hide them; accountant can show all.
 */

import type { TFunction } from 'i18next';
import type { ExtractedPayslipField } from '../../types/api';
import { isInternalReviewFieldKey } from '../guest/extraction-review';
import { isCanonicalPayrollFieldKey } from '../guest/payroll-field-keys';
import {
  detectEmployeeFieldType,
  fieldSpansColumns,
  formatFieldPreview,
  serializeFieldValue,
  type EmployeeFieldType,
} from './field-types';
import {
  displayOrderForKey,
  getPayslipFieldDefinition,
  looksLikeNationalIdDigits,
  requirementCategoryForKey,
  requiredOnPayslipKeys,
  type FieldRequirementCategory,
} from './payslip-field-registry';

export type DigitalFormFieldModel = {
  key: string;
  label: string;
  type: EmployeeFieldType;
  /** Serialized editable value */
  value: string;
  rawValue: unknown;
  preview: string;
  columnSpan: 1 | 2;
  sectionId: string;
  requirementCategory: FieldRequirementCategory;
  /** True when required_on_payslip and value is empty (not fabricated). */
  missingRequired: boolean;
};

export type DigitalFormSectionModel = {
  id: string;
  /** When null, UI renders without a section heading (continuous form). */
  titleKey: string | null;
  fields: DigitalFormFieldModel[];
};

export type DigitalFormAudience = 'employee' | 'accountant';

function hasNonEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  return String(value).trim() !== '';
}

function fieldLabel(key: string, t: TFunction, sourceText?: string | null): string {
  if (key.startsWith('custom_field_') && sourceText?.trim()) {
    return sourceText.trim();
  }
  if (isCanonicalPayrollFieldKey(key)) {
    return t(`payroll.fields.${key}`);
  }
  const def = getPayslipFieldDefinition(key);
  if (def) return t(def.label_i18n_key, { defaultValue: key });
  return t(`validate.field.${key}`, { defaultValue: key });
}

function sectionIdForKey(key: string): string {
  return getPayslipFieldDefinition(key)?.section ?? 'other';
}

function categorySortRank(category: FieldRequirementCategory): number {
  if (category === 'required') return 0;
  if (category === 'expected') return 1;
  return 2;
}

function nationalIdSatisfied(
  byKey: Map<string, ExtractedPayslipField>,
  drafts: Record<string, { value: string; dirty?: boolean }>,
): { ok: boolean; sourceKey: 'national_id' | 'employee_id' | null } {
  const nidDraft = drafts.national_id;
  if (nidDraft?.dirty && nidDraft.value.trim()) return { ok: true, sourceKey: 'national_id' };
  if (hasNonEmptyValue(byKey.get('national_id')?.value)) return { ok: true, sourceKey: 'national_id' };
  if (nidDraft && !nidDraft.dirty && nidDraft.value.trim()) return { ok: true, sourceKey: 'national_id' };

  // Legacy: employee_id only satisfies National ID when it looks like Israeli ID digits.
  const legacyDraft = drafts.employee_id;
  const legacyValue = legacyDraft?.dirty
    ? legacyDraft.value
    : (legacyDraft?.value || serializeFieldValue(byKey.get('employee_id')?.value));
  if (looksLikeNationalIdDigits(legacyValue)) {
    return { ok: true, sourceKey: 'employee_id' };
  }
  return { ok: false, sourceKey: null };
}

function resolveDisplayValue(
  field: ExtractedPayslipField | undefined,
  draft: { value: string; dirty?: boolean } | undefined,
): string {
  if (draft?.dirty) return draft.value;
  if (draft?.value != null && draft.value !== '') return draft.value;
  if (field) return serializeFieldValue(field.value);
  return '';
}

function toFieldModel(
  key: string,
  field: ExtractedPayslipField | undefined,
  drafts: Record<string, { value: string; dirty?: boolean }>,
  t: TFunction,
  locale: string,
  options: { missingRequired: boolean },
): DigitalFormFieldModel {
  const draft = drafts[key];
  const value = resolveDisplayValue(field, draft);
  const type = detectEmployeeFieldType(key, draft?.dirty ? value : field?.value);
  const category = requirementCategoryForKey(key);
  return {
    key,
    label: fieldLabel(key, t, field?.source_text),
    type,
    value,
    rawValue: field?.value ?? null,
    preview: formatFieldPreview(value, type, locale),
    columnSpan: fieldSpansColumns(type, value),
    sectionId: sectionIdForKey(key),
    requirementCategory: category,
    missingRequired: options.missingRequired,
  };
}

/**
 * Build Digital Payslip sections.
 * - Required (`required_on_payslip`): always visible (empty when missing).
 * - Non-required: visible only when extracted (non-empty) or dirty draft.
 * - Employee: Other category hidden from primary view unless dirty.
 * - Accountant: includes Other extracted fields.
 */
export function buildDigitalFormSections(
  fields: ExtractedPayslipField[] | undefined,
  drafts: Record<string, { value: string; dirty?: boolean }>,
  t: TFunction,
  locale: string,
  options?: {
    audience?: DigitalFormAudience;
    /** Force include Other category (accountant toggle). */
    includeOther?: boolean;
    /**
     * requirement — Required / Expected / Other section titles (employee default).
     * registrySection — document sections without classification headings (batch form).
     */
    groupBy?: 'requirement' | 'registrySection';
    /** When set, only include these requirement categories (presentation filter). */
    requirementCategories?: FieldRequirementCategory[];
  },
): DigitalFormSectionModel[] {
  const audience = options?.audience ?? 'employee';
  const includeOther = options?.includeOther ?? audience === 'accountant';
  const groupBy =
    options?.groupBy ?? (audience === 'accountant' ? 'registrySection' : 'requirement');
  const categoryAllow = options?.requirementCategories
    ? new Set(options.requirementCategories)
    : null;

  const byKey = new Map<string, ExtractedPayslipField>();
  for (const field of fields ?? []) {
    const key = (field.key || '').trim();
    if (!key || isInternalReviewFieldKey(key)) continue;
    byKey.set(key, field);
  }

  const models: DigitalFormFieldModel[] = [];
  const used = new Set<string>();
  const nidState = nationalIdSatisfied(byKey, drafts);

  // 1) Required slots (including empty missing).
  for (const key of requiredOnPayslipKeys()) {
    if (key === 'national_id') {
      if (nidState.ok && nidState.sourceKey === 'employee_id' && !byKey.has('national_id')) {
        // Legacy: NID stored under employee_id — present as National ID slot.
        const model = toFieldModel('national_id', byKey.get('employee_id'), drafts, t, locale, {
          missingRequired: false,
        });
        // Prefer draft under national_id if present; else show legacy value via employee_id field payload.
        if (!drafts.national_id?.dirty) {
          model.value = resolveDisplayValue(byKey.get('employee_id'), drafts.employee_id);
          model.preview = formatFieldPreview(model.value, model.type, locale);
        }
        model.label = fieldLabel('national_id', t);
        models.push(model);
        used.add('national_id');
        // Keep employee_id available as Expected payroll ID only when it is NOT a NID-looking value.
        if (!looksLikeNationalIdDigits(resolveDisplayValue(byKey.get('employee_id'), drafts.employee_id))) {
          // no-op — employee_id handled in expected pass
        } else {
          used.add('employee_id');
        }
        continue;
      }
      const field = byKey.get('national_id');
      const draft = drafts.national_id;
      const value = resolveDisplayValue(field, draft);
      const missingRequired = !value.trim() && !nidState.ok;
      if (!value.trim() && nidState.ok) {
        // Satisfied via legacy employee_id already handled above, or draft-only.
        used.add('national_id');
        continue;
      }
      models.push(
        toFieldModel('national_id', field, drafts, t, locale, {
          missingRequired,
        }),
      );
      used.add('national_id');
      continue;
    }

    const field = byKey.get(key);
    const draft = drafts[key];
    const value = resolveDisplayValue(field, draft);
    const empty = !value.trim();
    models.push(
      toFieldModel(key, field, drafts, t, locale, {
        missingRequired: empty,
      }),
    );
    used.add(key);
  }

  // 2) Expected + Other from extraction / dirty drafts.
  const remainingKeys = new Set<string>([...byKey.keys(), ...Object.keys(drafts)]);
  for (const key of remainingKeys) {
    if (used.has(key)) continue;
    if (isInternalReviewFieldKey(key)) continue;

    const category = requirementCategoryForKey(key);
    if (category === 'other' && !includeOther) {
      // Preserve data; hide from employee primary view unless dirty custom edit.
      const draft = drafts[key];
      if (!(draft?.dirty)) continue;
    }

    const field = byKey.get(key);
    const draft = drafts[key];
    const value = resolveDisplayValue(field, draft);
    // Optional / expected: hide when never extracted (empty value, not a dirty draft).
    if (!value.trim() && !draft?.dirty) continue;

    models.push(
      toFieldModel(key, field, drafts, t, locale, {
        missingRequired: false,
      }),
    );
    used.add(key);
  }

  const filtered = categoryAllow
    ? models.filter((field) => categoryAllow.has(field.requirementCategory))
    : models;

  filtered.sort((a, b) => {
    const cat = categorySortRank(a.requirementCategory) - categorySortRank(b.requirementCategory);
    if (cat !== 0) return cat;
    return displayOrderForKey(a.key) - displayOrderForKey(b.key) || a.key.localeCompare(b.key);
  });

  if (filtered.length === 0) return [];

  if (groupBy === 'registrySection') {
    const sectionOrder = [
      'identity',
      'employer',
      'period',
      'earnings',
      'deductions',
      'payment',
      'other',
    ] as const;
    return sectionOrder
      .map((id) => ({
        id,
        titleKey: `employee.digitalForm.sections.${id}`,
        fields: filtered.filter((field) => field.sectionId === id),
      }))
      .filter((section) => section.fields.length > 0);
  }

  // Group by requirement category for clear Required → Expected → Other structure.
  const groups: Array<{ id: FieldRequirementCategory; titleKey: string }> = [
    { id: 'required', titleKey: 'employee.digitalForm.sectionRequired' },
    { id: 'expected', titleKey: 'employee.digitalForm.sectionExpected' },
    { id: 'other', titleKey: 'employee.digitalForm.sectionOther' },
  ];

  return groups
    .map((group) => ({
      id: group.id,
      titleKey: group.titleKey,
      fields: filtered.filter((field) => field.requirementCategory === group.id),
    }))
    .filter((section) => section.fields.length > 0);
}

/** True when the form has Expected/Other fields beyond the primary Required set. */
export function digitalFormHasSecondaryFields(
  fields: ExtractedPayslipField[] | undefined,
  drafts: Record<string, { value: string; dirty?: boolean }>,
  t: TFunction,
  locale: string,
  options?: {
    audience?: DigitalFormAudience;
    includeOther?: boolean;
  },
): boolean {
  const secondary = buildDigitalFormSections(fields, drafts, t, locale, {
    ...options,
    groupBy: 'registrySection',
    requirementCategories: ['expected', 'other'],
  });
  return secondary.some((section) => section.fields.length > 0);
}

/** Initial collapsed Digital Payslip field count (presentation only). */
export const INITIAL_DIGITAL_FORM_VISIBLE_COUNT = 10;

/** Always lead with these keys when present; remaining keep build order. */
export const DIGITAL_FORM_PRIORITY_KEYS = [
  'employee_name',
  'national_id',
  'employee_number',
  'pay_period',
] as const;

/**
 * Presentation order for collapsed/expanded Digital Payslip lists.
 * Does not change extraction or required-field rules.
 */
export function orderDigitalFormFieldsForDisplay(
  fields: DigitalFormFieldModel[],
): DigitalFormFieldModel[] {
  const byKey = new Map(fields.map((field) => [field.key, field]));
  const ordered: DigitalFormFieldModel[] = [];
  const used = new Set<string>();
  for (const key of DIGITAL_FORM_PRIORITY_KEYS) {
    const match = byKey.get(key);
    if (!match) continue;
    ordered.push(match);
    used.add(key);
  }
  for (const field of fields) {
    if (used.has(field.key)) continue;
    ordered.push(field);
  }
  return ordered;
}

/** True when collapsed accountant view should offer Show more (> initial visible count). */
export function digitalFormNeedsShowMore(fieldCount: number): boolean {
  return fieldCount > INITIAL_DIGITAL_FORM_VISIBLE_COUNT;
}
