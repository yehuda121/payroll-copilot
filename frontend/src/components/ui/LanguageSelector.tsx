import { useAppLocale } from '../../hooks/useAppLocale';
import type { AppLocale } from '../../i18n';

export function LanguageSelector() {
  const { locale, setLocale, supportedLocales, localeMeta, t } = useAppLocale();

  return (
    <label className="language-selector">
      <span className="language-selector__label">{t('common.language')}</span>
      <select
        className="language-selector__select"
        value={locale}
        aria-label={t('common.language')}
        onChange={(event) => setLocale(event.target.value as AppLocale)}
      >
        {supportedLocales.map((code) => (
          <option key={code} value={code}>
            {localeMeta[code].label}
          </option>
        ))}
      </select>
    </label>
  );
}
