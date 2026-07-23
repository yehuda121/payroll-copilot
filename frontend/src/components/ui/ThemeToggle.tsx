import { useTranslation } from 'react-i18next';
import { useTheme } from '../../theme/ThemeProvider';
import { MoonIcon, SunIcon } from './icons';

export function ThemeToggle() {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      className="btn btn--ghost btn--icon"
      onClick={toggleTheme}
      aria-label={
        theme === 'light' ? t('common.themeToDark') : t('common.themeToLight')
      }
      title={theme === 'light' ? t('common.themeDark') : t('common.themeLight')}
    >
      {theme === 'light' ? (
        <MoonIcon aria-hidden="true" />
      ) : (
        <SunIcon aria-hidden="true" />
      )}
    </button>
  );
}
