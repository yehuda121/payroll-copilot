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
  portalName: 'Accountant Portal',
  portalSubtitle: 'Bulk validation & workforce management',
  basePath: '/accountant',
  navItems: [
    { label: 'Dashboard', path: '/accountant' },
    { label: 'Employee Management', path: '/accountant/employees' },
    { label: 'Add Employee', path: '/accountant/employees/add' },
    { label: 'Bulk Payroll Upload', path: '/accountant/bulk-upload' },
    { label: 'Batch Monitor', path: '/accountant/batch-monitor' },
    { label: 'Validation Findings', path: '/accountant/findings' },
    { label: 'Approval Queue', path: '/accountant/approvals' },
    { label: 'Audit Logs', path: '/accountant/audit-logs' },
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
  ],
};
