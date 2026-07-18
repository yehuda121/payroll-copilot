import { useTranslation } from 'react-i18next';
import type {
  FieldEvidenceAlternative,
  FieldEvidenceDetails as FieldEvidenceDetailsType,
} from '../../types/api';

type Props = {
  evidence: FieldEvidenceDetailsType;
};

const display = (value: unknown, fallback: string): string =>
  value == null || value === '' ? fallback : String(value);

export function FieldEvidenceDetails({ evidence }: Props) {
  const { t } = useTranslation();
  const empty = t('common.emDash');
  const showOriginal =
    Boolean(evidence.user_edited || evidence.reason === 'user_edited') &&
    Boolean(evidence.candidate_id || evidence.page != null || evidence.value != null);

  if (!evidence.available && !showOriginal) {
    return (
      <p className="field-evidence__unavailable">
        {evidence.reason === 'user_edited'
          ? t('explainability.userEdited')
          : t('explainability.unavailable')}
      </p>
    );
  }

  return (
    <div className="field-evidence">
      {showOriginal && (
        <p className="field-evidence__conflict" role="status">
          {t('explainability.userEditedOriginal')}
        </p>
      )}
      <h4 className="field-evidence__heading">{t('explainability.primaryCandidate')}</h4>
      <dl className="field-evidence__grid">
        <EvidenceRow
          label={t('explainability.evidenceSource')}
          value={
            evidence.source === 'layout_analysis'
              ? t('explainability.layoutEvidence')
              : evidence.source
          }
          empty={empty}
        />
        <EvidenceRow label={t('explainability.sourcePage')} value={evidence.page} empty={empty} />
        <EvidenceRow label={t('explainability.detectedLabel')} value={evidence.label} empty={empty} />
        <EvidenceRow label={t('explainability.detectedValue')} value={evidence.value} empty={empty} />
        <EvidenceRow label={t('explainability.section')} value={evidence.section} empty={empty} />
        <EvidenceRow label={t('explainability.row')} value={evidence.row} empty={empty} />
        <EvidenceRow label={t('explainability.column')} value={evidence.column} empty={empty} />
        <EvidenceRow
          label={t('explainability.strategy')}
          value={evidence.association_strategy}
          empty={empty}
        />
        <EvidenceRow
          label={t('explainability.associationConfidence')}
          value={evidence.association_confidence}
          empty={empty}
        />
        <EvidenceRow
          label={t('explainability.candidateId')}
          value={evidence.candidate_id}
          empty={empty}
          code
        />
        <EvidenceRow
          label={t('explainability.boundingBox')}
          value={evidence.bbox?.join(', ')}
          empty={empty}
          code
        />
      </dl>

      {evidence.conflict && (
        <p className="field-evidence__conflict" role="status">
          {t('explainability.conflict')}
        </p>
      )}

      {evidence.alternatives.length > 0 && (
        <section className="field-evidence__alternatives">
          <h4>{t('explainability.alternatives')}</h4>
          {evidence.alternatives.map((alternative, index) => (
            <Alternative
              key={alternative.candidate_id ?? index}
              alternative={alternative}
              empty={empty}
            />
          ))}
        </section>
      )}
    </div>
  );
}

function EvidenceRow({
  label,
  value,
  empty,
  code = false,
}: {
  label: string;
  value: unknown;
  empty: string;
  code?: boolean;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={code ? 'field-evidence__code' : undefined}>
        {display(value, empty)}
      </dd>
    </div>
  );
}

function Alternative({
  alternative,
  empty,
}: {
  alternative: FieldEvidenceAlternative;
  empty: string;
}) {
  const { t } = useTranslation();
  return (
    <article className="field-evidence__alternative">
      <div>
        <strong>{display(alternative.value, empty)}</strong>
        <span>{display(alternative.label, empty)}</span>
      </div>
      <dl>
        <EvidenceRow
          label={t('explainability.strategy')}
          value={alternative.association_strategy}
          empty={empty}
        />
        <EvidenceRow
          label={t('explainability.associationConfidence')}
          value={alternative.association_confidence}
          empty={empty}
        />
        <EvidenceRow
          label={t('explainability.alternativeReason')}
          value={
            alternative.reason === 'association_engine_alternative'
              ? t('explainability.alternativeGeometry')
              : alternative.reason === 'association_engine_primary_not_selected'
                ? t('explainability.alternativePrimary')
              : alternative.reason
          }
          empty={empty}
        />
      </dl>
    </article>
  );
}
