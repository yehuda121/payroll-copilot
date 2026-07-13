import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthContext';
import { ProtectedRoute } from '../auth/ProtectedRoute';
import { getRoleHomePath } from '../auth/authProvider';
import { useAuth } from '../auth/AuthContext';
import { AccountantLayout } from '../layouts/AccountantLayout';
import { AdminLayout } from '../layouts/AdminLayout';
import { EmployeeLayout } from '../layouts/EmployeeLayout';
import { PublicLayout } from '../layouts/PublicLayout';
import { AccountantDashboardPage } from '../pages/accountant/AccountantDashboard';
import { AccountantAuditLogsPage } from '../pages/accountant/AccountantAuditLogs';
import { AddEmployeePage } from '../pages/accountant/AddEmployee';
import { ApprovalQueuePage } from '../pages/accountant/ApprovalQueue';
import { BatchProcessingMonitorPage } from '../pages/accountant/BatchProcessingMonitor';
import { BulkPayrollUploadPage } from '../pages/accountant/BulkPayrollUpload';
import { EditEmployeePage } from '../pages/accountant/EditEmployee';
import { EmployeeManagementPage } from '../pages/accountant/EmployeeManagement';
import { EmployeeProfilePage } from '../pages/accountant/EmployeeProfile';
import { PayrollRulesPage } from '../pages/accountant/PayrollRules';
import { ValidationFindingsPage } from '../pages/accountant/ValidationFindings';
import { AdminAuditLogsPage } from '../pages/admin/AdminAuditLogs';
import { AiModelsPage } from '../pages/admin/AiModels';
import { DepartmentRulesPage } from '../pages/admin/DepartmentRules';
import { DocumentLabPage } from '../pages/admin/DocumentLab';
import { McpLegalSyncPage } from '../pages/admin/McpLegalSync';
import { RagManagementPage } from '../pages/admin/RagManagement';
import { RulePacksPage } from '../pages/admin/RulePacks';
import { SystemConfigurationPage } from '../pages/admin/SystemConfiguration';
import { SystemDashboardPage } from '../pages/admin/SystemDashboard';
import { UsersAndRolesPage } from '../pages/admin/UsersAndRoles';
import { AttendancePage } from '../pages/employee/Attendance';
import { EmployeeDashboardPage } from '../pages/employee/EmployeeDashboard';
import { EmploymentContractPage } from '../pages/employee/EmploymentContract';
import { MyPayslipsPage } from '../pages/employee/MyPayslips';
import { PayrollChatPage } from '../pages/employee/PayrollChat';
import { UploadDocumentsPage } from '../pages/employee/UploadDocuments';
import { ValidationHistoryPage } from '../pages/employee/ValidationHistory';
import { LandingPage } from '../pages/public/LandingPage';
import { LoginPage } from '../pages/public/LoginPage';
import { SignupPage } from '../pages/public/SignupPage';

function RootRedirect() {
  const { isAuthenticated, session } = useAuth();
  if (isAuthenticated && session) {
    return <Navigate to={getRoleHomePath(session.user.role)} replace />;
  }
  return <LandingPage />;
}

export function AppRoutes() {
  return (
    <AuthProvider>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
        </Route>

        <Route element={<ProtectedRoute allowedRoles={['employee']} />}>
          <Route element={<EmployeeLayout />}>
            <Route path="/employee" element={<EmployeeDashboardPage />} />
            <Route path="/employee/upload" element={<UploadDocumentsPage />} />
            <Route path="/employee/payslips" element={<MyPayslipsPage />} />
            <Route path="/employee/attendance" element={<AttendancePage />} />
            <Route path="/employee/contract" element={<EmploymentContractPage />} />
            <Route path="/employee/chat" element={<PayrollChatPage />} />
            <Route path="/employee/validation-history" element={<ValidationHistoryPage />} />
          </Route>
        </Route>

        <Route element={<ProtectedRoute allowedRoles={['payroll_accountant']} />}>
          <Route element={<AccountantLayout />}>
            <Route path="/accountant" element={<AccountantDashboardPage />} />
            <Route path="/accountant/employees" element={<EmployeeManagementPage />} />
            <Route path="/accountant/employees/add" element={<AddEmployeePage />} />
            <Route path="/accountant/employees/:employeeNumber" element={<EmployeeProfilePage />} />
            <Route path="/accountant/employees/:employeeNumber/edit" element={<EditEmployeePage />} />
            <Route path="/accountant/bulk-upload" element={<BulkPayrollUploadPage />} />
            <Route path="/accountant/batch-monitor" element={<BatchProcessingMonitorPage />} />
            <Route path="/accountant/rules" element={<PayrollRulesPage />} />
            <Route path="/accountant/findings" element={<ValidationFindingsPage />} />
            <Route path="/accountant/approvals" element={<ApprovalQueuePage />} />
            <Route path="/accountant/audit-logs" element={<AccountantAuditLogsPage />} />
          </Route>
        </Route>

        <Route element={<ProtectedRoute allowedRoles={['developer_admin']} />}>
          <Route element={<AdminLayout />}>
            <Route path="/admin" element={<SystemDashboardPage />} />
            <Route path="/admin/users" element={<UsersAndRolesPage />} />
            <Route path="/admin/rule-packs" element={<RulePacksPage />} />
            <Route path="/admin/department-rules" element={<DepartmentRulesPage />} />
            <Route path="/admin/mcp-sync" element={<McpLegalSyncPage />} />
            <Route path="/admin/ai-models" element={<AiModelsPage />} />
            <Route path="/admin/rag" element={<RagManagementPage />} />
            <Route path="/admin/configuration" element={<SystemConfigurationPage />} />
            <Route path="/admin/audit-logs" element={<AdminAuditLogsPage />} />
            <Route path="/admin/document-lab" element={<DocumentLabPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
