import { describe, expect, it } from 'vitest';
import {
  CONTRACT_FIELD_KEYS,
  ID_APPENDIX_CHILDREN_KEY,
  ID_CARD_FIELD_KEYS,
} from './document-fixed-forms';
import {
  documentFieldRegistryCoverage,
  documentFieldSectionsForType,
  getDocumentFieldDefinition,
  orderedFormFieldKeys,
  sectionTitleI18nKey,
} from './document-field-registry';

describe('document-field-registry', () => {
  it('covers every identity card and contract fixed-form key', () => {
    const { missing, extraFormKeys } = documentFieldRegistryCoverage();
    expect(missing).toEqual([]);
    expect(extraFormKeys).toEqual([]);
  });

  it('uses registry i18n keys — never raw canonical paths as labels', () => {
    for (const key of ID_CARD_FIELD_KEYS) {
      const def = getDocumentFieldDefinition('national_id', key);
      expect(def?.label_i18n_key).toBe(`employee.documents.fields.${key}`);
      expect(def?.label_i18n_key).not.toContain('fixedFields');
    }
    for (const key of CONTRACT_FIELD_KEYS) {
      const def = getDocumentFieldDefinition('contract', key);
      expect(def?.label_i18n_key).toBe(`employee.documents.fields.${key}`);
      expect(def?.label_i18n_key).not.toContain('fixedFields');
    }
  });

  it('groups employment contract into Employment then Compensation', () => {
    const sections = documentFieldSectionsForType('contract', CONTRACT_FIELD_KEYS);
    expect(sections.map((s) => s.id)).toEqual(['employment', 'compensation']);
    expect(sections[0].fields.map((f) => f.canonical_key)).toEqual([
      'employment_commencement_date',
      'salary_basis',
      'effective_from',
      'effective_to',
    ]);
    expect(sections[1].fields.map((f) => f.canonical_key)).toEqual([
      'contractual_monthly_salary',
      'contractual_hourly_rate',
      'contractual_daily_rate',
    ]);
  });

  it('orders form keys by display_order for contract', () => {
    expect(orderedFormFieldKeys('contract')).toEqual([
      'employment_commencement_date',
      'salary_basis',
      'effective_from',
      'effective_to',
      'contractual_monthly_salary',
      'contractual_hourly_rate',
      'contractual_daily_rate',
    ]);
  });

  it('registers appendix children collection and nested child fields', () => {
    expect(getDocumentFieldDefinition('id_appendix', ID_APPENDIX_CHILDREN_KEY)?.section).toBe(
      'family',
    );
    expect(getDocumentFieldDefinition('id_appendix', 'child_name')?.label_i18n_key).toBe(
      'employee.documents.fields.child_name',
    );
    expect(getDocumentFieldDefinition('id_appendix', 'child_birth_date')?.label_i18n_key).toBe(
      'employee.documents.fields.child_birth_date',
    );
    const sections = documentFieldSectionsForType('id_appendix');
    expect(sections).toHaveLength(1);
    expect(sections[0].id).toBe('family');
    expect(sections[0].fields.map((f) => f.canonical_key)).toEqual([ID_APPENDIX_CHILDREN_KEY]);
  });

  it('exposes section title i18n keys', () => {
    expect(sectionTitleI18nKey('employment')).toBe('employee.documents.fieldSections.employment');
    expect(sectionTitleI18nKey('compensation')).toBe(
      'employee.documents.fieldSections.compensation',
    );
  });
});
