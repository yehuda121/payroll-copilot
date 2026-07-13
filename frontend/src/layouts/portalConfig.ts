import type { PortalConfig } from '../types/navigation';

export const EMPLOYEE_PORTAL: PortalConfig = {
  portalName: 'Employee Portal',
  portalSubtitle: 'Personal payroll & documents',
  basePath: '/employee',
  navItems: [
    { label: 'Dashboard', path: '/employee' },
    { label: 'Upload Documents', path: '/employee/upload' },
    { label: 'My Payslips', path: '/employee/payslips' },
    { label: 'Attendance', path: '/employee/attendance' },
    { label: 'Employment Contract', path: '/employee/contract' },
    { label: 'Payroll AI Chat', path: '/employee/chat' },
    { label: 'Validation History', path: '/employee/validation-history' },
  ],
};

export const ACCOUNTANT_PORTAL: PortalConfig = {
  portalNameKey: 'accountant.navigation.portalName',
  portalSubtitleKey: 'accountant.navigation.portalSubtitle',
  basePath: '/accountant',
  navItems: [
    { labelKey: 'accountant.navigation.dashboard', path: '/accountant' },
    { labelKey: 'accountant.navigation.employees', path: '/accountant/employees' },
    { labelKey: 'accountant.navigation.bulkUpload', path: '/accountant/bulk-upload' },
    { labelKey: 'accountant.navigation.batchMonitor', path: '/accountant/batch-monitor' },
    { labelKey: 'accountant.navigation.rules', path: '/accountant/rules' },
    { labelKey: 'accountant.navigation.findings', path: '/accountant/findings' },
    { labelKey: 'accountant.navigation.manualReview', path: '/accountant/approvals' },
    { labelKey: 'accountant.navigation.auditLogs', path: '/accountant/audit-logs' },
  ],
};

export const ADMIN_PORTAL: PortalConfig = {
  portalName: 'Admin Portal',
  portalSubtitle: 'System configuration & compliance',
  basePath: '/admin',
  navItems: [
    { label: 'System Dashboard', path: '/admin' },
    { label: 'Users & Roles', path: '/admin/users' },
    { label: 'Rule Packs', path: '/admin/rule-packs' },
    { label: 'Department Rules', path: '/admin/department-rules' },
    { label: 'MCP Legal Sync', path: '/admin/mcp-sync' },
    { label: 'AI Models', path: '/admin/ai-models' },
    { label: 'RAG Management', path: '/admin/rag' },
    { label: 'System Configuration', path: '/admin/configuration' },
    { label: 'Audit Logs', path: '/admin/audit-logs' },
    { label: 'Document Lab', path: '/admin/document-lab' },
  ],
};
