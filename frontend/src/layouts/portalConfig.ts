import type { PortalConfig } from '../types/navigation';
import { env } from '../config/env';

export const EMPLOYEE_PORTAL: PortalConfig = {
  portalNameKey: 'employee.navigation.portalName',
  portalSubtitleKey: 'employee.navigation.portalSubtitle',
  basePath: '/employee',
  showUserEmail: true,
  navItems: [
    { labelKey: 'employee.navigation.documents', path: '/employee/documents' },
    { labelKey: 'employee.navigation.payslips', path: '/employee/payslips' },
    { labelKey: 'employee.navigation.chat', path: '/employee/chat' },
  ],
};

export const ACCOUNTANT_PORTAL: PortalConfig = {
  portalNameKey: 'accountant.navigation.portalName',
  portalSubtitleKey: 'accountant.navigation.portalSubtitle',
  basePath: '/accountant',
  navItems: [
    { labelKey: 'accountant.navigation.employees', path: '/accountant/employees' },
    { labelKey: 'accountant.navigation.bulkUpload', path: '/accountant/bulk-upload' },
    { labelKey: 'accountant.navigation.analytics', path: '/accountant/analytics' },
  ],
};

const ADMIN_NAV_CORE = [
  { label: 'System Dashboard', path: '/admin' },
  { label: 'Organization Analytics', path: '/admin/analytics' },
  { label: 'AI Quality Analytics', path: '/admin/analytics/quality' },
  { label: 'AI Models', path: '/admin/ai-models' },
] as const;

/** Unfinished / lab surfaces — available in Vite DEV only, never in production builds. */
const ADMIN_NAV_DEV_ONLY = [
  { label: 'Users & Roles', path: '/admin/users' },
  { label: 'Rule Packs', path: '/admin/rule-packs' },
  { label: 'Department Rules', path: '/admin/department-rules' },
  { label: 'MCP Legal Sync', path: '/admin/mcp-sync' },
  { label: 'RAG Management', path: '/admin/rag' },
  { label: 'System Configuration', path: '/admin/configuration' },
  { label: 'Audit Logs', path: '/admin/audit-logs' },
  { label: 'Document Lab', path: '/admin/document-lab' },
] as const;

export const ADMIN_PORTAL: PortalConfig = {
  portalName: 'Admin Portal',
  portalSubtitle: 'System configuration & compliance',
  basePath: '/admin',
  navItems: [
    ...ADMIN_NAV_CORE,
    ...(env.isDevRuntime ? [...ADMIN_NAV_DEV_ONLY] : []),
  ],
};
