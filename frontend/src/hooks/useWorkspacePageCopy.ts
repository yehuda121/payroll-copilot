import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useEmployeeWorkspace } from '../features/employee/EmployeeWorkspaceContext';

/**
 * Perspective-aware page titles/descriptions for shared employee pages
 * rendered under accountant workspace (`mode === 'accountant'`).
 */
export function useWorkspacePageCopy() {
  const { t } = useTranslation();
  const { mode, employeeName } = useEmployeeWorkspace();
  const name = employeeName?.trim() || t('common.emDash');

  return useMemo(
    () => ({
      mode,
      name,
      isAccountant: mode === 'accountant',
      documentsTitle:
        mode === 'accountant'
          ? t('accountant.workspace.documentsTitle', { name })
          : t('employee.documents.pageTitle'),
      documentsDescription:
        mode === 'accountant'
          ? t('accountant.workspace.documentsDescription', { name })
          : t('employee.documents.pageDescription'),
      payslipsTitle:
        mode === 'accountant'
          ? t('accountant.workspace.payslipsTitle', { name })
          : t('employee.payslips.pageTitle'),
      payslipsDescription:
        mode === 'accountant'
          ? t('accountant.workspace.payslipsDescription', { name })
          : t('employee.payslips.pageDescription'),
      chatTitle:
        mode === 'accountant'
          ? t('accountant.workspace.chatTitle', { name })
          : t('employee.pages.chatTitle'),
      chatDescription:
        mode === 'accountant'
          ? t('accountant.workspace.chatDescription', { name })
          : t('employee.pages.chatDescription'),
      monthDescription:
        mode === 'accountant'
          ? t('accountant.workspace.monthDescription', { name })
          : t('employee.workspace.pageDescription'),
    }),
    [employeeName, mode, t, name],
  );
}
