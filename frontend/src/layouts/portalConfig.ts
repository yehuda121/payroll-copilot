import type { NavGroup, PortalConfig } from '../types/navigation';
import { env } from '../config/env';

export const EMPLOYEE_PORTAL: PortalConfig = {
  portalNameKey: 'employee.navigation.portalName',
  portalSubtitleKey: 'employee.navigation.portalSubtitle',
  basePath: '/employee',
  showUserEmail: true,
  navItems: [
    { labelKey: 'employee.navigation.chat', path: '/employee/chat' },
    { labelKey: 'employee.navigation.documents', path: '/employee/documents' },
    { labelKey: 'employee.navigation.payslips', path: '/employee/payslips' },
  ],
};

export const ACCOUNTANT_PORTAL: PortalConfig = {
  portalNameKey: 'accountant.navigation.portalName',
  portalSubtitleKey: 'accountant.navigation.portalSubtitle',
  basePath: '/accountant',
  navItems: [
    { labelKey: 'accountant.navigation.employees', path: '/accountant/employees' },
    { labelKey: 'accountant.navigation.vacations', path: '/accountant/vacations', badgeKey: 'vacationsUnseen' },
    { labelKey: 'accountant.navigation.sickLeaves', path: '/accountant/sick-leaves', badgeKey: 'sickLeavesUnseen' },
    { labelKey: 'accountant.navigation.bulkUpload', path: '/accountant/bulk-upload' },
    { labelKey: 'accountant.navigation.analytics', path: '/accountant/analytics' },
  ],
};

const ADMIN_NAV_GROUPS_CORE: NavGroup[] = [
  {
    labelKey: 'admin.nav.groups.monitoring',
    items: [{ labelKey: 'admin.nav.dashboard', path: '/admin' }],
  },
  {
    labelKey: 'admin.nav.groups.analytics',
    items: [
      { labelKey: 'admin.nav.orgAnalytics', path: '/admin/analytics' },
      { labelKey: 'admin.nav.qualityAnalytics', path: '/admin/analytics/quality' },
    ],
  },
  {
    labelKey: 'admin.nav.groups.aiPlatform',
    items: [{ labelKey: 'admin.nav.aiModels', path: '/admin/ai-models' }],
  },
  {
    labelKey: 'admin.nav.groups.knowledge',
    items: [
      { labelKey: 'admin.nav.legalKnowledge', path: '/admin/legal-knowledge' },
      { labelKey: 'admin.nav.ragEvaluation', path: '/admin/rag-evaluation' },
    ],
  },
];

const ADMIN_NAV_GROUPS_DEV: NavGroup[] = [
  {
    labelKey: 'admin.nav.groups.documentProcessing',
    items: [{ labelKey: 'admin.nav.documentLab', path: '/admin/document-lab' }],
  },
];

function flattenGroups(groups: NavGroup[]) {
  return groups.flatMap((group) => group.items);
}

const adminGroups = [
  ...ADMIN_NAV_GROUPS_CORE,
  ...(env.isDevRuntime ? ADMIN_NAV_GROUPS_DEV : []),
];

export const ADMIN_PORTAL: PortalConfig = {
  portalNameKey: 'admin.navigation.portalName',
  portalSubtitleKey: 'admin.navigation.portalSubtitle',
  basePath: '/admin',
  navGroups: adminGroups,
  navItems: flattenGroups(adminGroups),
};
