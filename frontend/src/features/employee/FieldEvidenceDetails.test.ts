import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import i18n from '../../i18n';
import { FieldEvidenceDetails } from './FieldEvidenceDetails';

describe('FieldEvidenceDetails', () => {
  void i18n.changeLanguage('en');

  it('renders primary evidence and conflict alternatives without internal objects', () => {
    const html = renderToStaticMarkup(
      createElement(FieldEvidenceDetails, {
        evidence: {
          available: true,
          candidate_id: 'cand_p2_a4',
          source: 'layout_analysis',
          page: 2,
          section: 'p2_s1',
          row: 'p2_r7',
          column: 1,
          label: 'Gross salary',
          value: '15,230',
          association_strategy: 'same_row',
          association_confidence: 'high',
          bbox: [120, 20, 50, 12],
          conflict: true,
          alternatives: [
            {
              candidate_id: 'cand_p2_a4_alt0',
              page: 2,
              section: 'p2_s1',
              row: 'p2_r7',
              column: 2,
              label: 'Gross salary',
              value: '15,200',
              association_strategy: 'nearest_neighbor',
              association_confidence: 'low',
              bbox: [190, 20, 50, 12],
              conflict: true,
              reason: 'association_engine_alternative',
            },
          ],
        },
      }),
    );

    expect(html).toContain('cand_p2_a4');
    expect(html).toContain('Gross salary');
    expect(html).toContain('15,230');
    expect(html).toContain('15,200');
    expect(html).toContain('same_row');
    expect(html).not.toContain('[object Object]');
  });

  it('states explicitly when evidence is unavailable', () => {
    const html = renderToStaticMarkup(
      createElement(FieldEvidenceDetails, {
        evidence: {
          available: false,
          candidate_id: null,
          page: null,
          section: null,
          row: null,
          column: null,
          label: null,
          value: null,
          association_strategy: null,
          association_confidence: null,
          bbox: null,
          conflict: false,
          alternatives: [],
        },
      }),
    );
    expect(html).toContain('not available');
  });
});
