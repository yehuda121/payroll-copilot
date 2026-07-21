import { lazy, Suspense, type ComponentType, type ReactNode } from 'react';
import { Navigate, Outlet, Route } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthContext';
import { ProtectedRoute } from '../auth/ProtectedRoute';
import { getRoleHomePath } from '../auth/authProvider';
import { useAuth } from '../auth/AuthContext';
import { DialogProvider } from '../components/ui/Dialog';
import { Skeleton } from '../components/ui/Skeleton';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { UnsavedChangesProvider } from '../features/accountant/UnsavedChangesGuard';
import { AccountantLayout } from '../layouts/AccountantLayout';
import { AccountantEmployeeWorkspaceLayout } from '../layouts/AccountantEmployeeWorkspace';
import { AdminLayout } from '../layouts/AdminLayout';
import { EmployeeLayout } from '../layouts/EmployeeLayout';
import { PublicLayout } from '../layouts/PublicLayout';
import { LandingPage } from '../pages/public/LandingPage';
import { LoginPage } from '../pages/public/LoginPage';
import { SignupPage } from '../pages/public/SignupPage';

function lazyPage<T extends ComponentType<object>>(
  factory: () => Promise<{ [key: string]: T }>,
  exportName: string,
) {
  return lazy(async () => {
    const module = await factory();
    return { default: module[exportName] as T };
  });
}

const DocumentCenterPage = lazyPage(
  () => import('../pages/employee/DocumentCenter'),
  'DocumentCenterPage',
);
const MyPayslipsPage = lazyPage(() => import('../pages/employee/MyPayslips'), 'MyPayslipsPage');
const NationalIdReviewPage = lazyPage(
  () => import('../pages/employee/NationalIdReview'),
  'NationalIdReviewPage',
);
const PayslipMonthWorkspacePage = lazyPage(
  () => import('../pages/employee/PayslipMonthWorkspace'),
  'PayslipMonthWorkspacePage',
);
const PayrollChatPage = lazyPage(
  () => import('../pages/employee/PayrollChat'),
  'PayrollChatPage',
);

const AccountantAuditLogsPage = lazyPage(
  () => import('../pages/accountant/AccountantAuditLogs'),
  'AccountantAuditLogsPage',
);
const AddEmployeePage = lazyPage(
  () => import('../pages/accountant/AddEmployee'),
  'AddEmployeePage',
);
const ApprovalQueuePage = lazyPage(
  () => import('../pages/accountant/ApprovalQueue'),
  'ApprovalQueuePage',
);
const BatchProcessingMonitorPage = lazyPage(
  () => import('../pages/accountant/BatchProcessingMonitor'),
  'BatchProcessingMonitorPage',
);
const BulkPayrollUploadPage = lazyPage(
  () => import('../pages/accountant/BulkPayrollUpload'),
  'BulkPayrollUploadPage',
);
const EditEmployeePage = lazyPage(
  () => import('../pages/accountant/EditEmployee'),
  'EditEmployeePage',
);
const EmployeeManagementPage = lazyPage(
  () => import('../pages/accountant/EmployeeManagement'),
  'EmployeeManagementPage',
);
const EmployeeProfilePage = lazyPage(
  () => import('../pages/accountant/EmployeeProfile'),
  'EmployeeProfilePage',
);
const EmployeeSettingsPage = lazyPage(
  () => import('../pages/accountant/EmployeeSettings'),
  'EmployeeSettingsPage',
);
const PayrollRulesPage = lazyPage(
  () => import('../pages/accountant/PayrollRules'),
  'PayrollRulesPage',
);
const ValidationFindingsPage = lazyPage(
  () => import('../pages/accountant/ValidationFindings'),
  'ValidationFindingsPage',
);
const BatchItemReviewWorkspacePage = lazyPage(
  () => import('../pages/accountant/BatchItemReviewWorkspace'),
  'BatchItemReviewWorkspacePage',
);

const AdminAuditLogsPage = lazyPage(
  () => import('../pages/admin/AdminAuditLogs'),
  'AdminAuditLogsPage',
);
const AiModelsPage = lazyPage(() => import('../pages/admin/AiModels'), 'AiModelsPage');
const DepartmentRulesPage = lazyPage(
  () => import('../pages/admin/DepartmentRules'),
  'DepartmentRulesPage',
);
const DocumentLabPage = lazyPage(() => import('../pages/admin/DocumentLab'), 'DocumentLabPage');
const McpLegalSyncPage = lazyPage(
  () => import('../pages/admin/McpLegalSync'),
  'McpLegalSyncPage',
);
const RagManagementPage = lazyPage(
  () => import('../pages/admin/RagManagement'),
  'RagManagementPage',
);
const RulePacksPage = lazyPage(() => import('../pages/admin/RulePacks'), 'RulePacksPage');
const SystemConfigurationPage = lazyPage(
  () => import('../pages/admin/SystemConfiguration'),
  'SystemConfigurationPage',
);
const SystemDashboardPage = lazyPage(
  () => import('../pages/admin/SystemDashboard'),
  'SystemDashboardPage',
);
const UsersAndRolesPage = lazyPage(
  () => import('../pages/admin/UsersAndRoles'),
  'UsersAndRolesPage',
);

function RouteFallback() {
  return (
    <div className="app-route-fallback" aria-busy="true" aria-live="polite">
      <Skeleton className="app-route-fallback__title" label="Loading page" />
      <div className="app-route-fallback__body">
        <Skeleton className="app-route-fallback__card" />
        <Skeleton className="app-route-fallback__card" />
        <Skeleton className="app-route-fallback__card" />
      </div>
    </div>
  );
}

function LazyRoute({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<RouteFallback />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

function RootRedirect() {
  const { isAuthenticated, session } = useAuth();
  if (isAuthenticated && session) {
    return <Navigate to={getRoleHomePath(session.user.role)} replace />;
  }
  return <LandingPage />;
}

function AppProviders() {
  return (
    <DialogProvider>
      <UnsavedChangesProvider>
        <AuthProvider>
          <Outlet />
        </AuthProvider>
      </UnsavedChangesProvider>
    </DialogProvider>
  );
}

function L({ children }: { children: ReactNode }) {
  return <LazyRoute>{children}</LazyRoute>;
}

/** Route tree for createBrowserRouter / createRoutesFromElements. */
export const appRouteElements = (
  <Route element={<AppProviders />}>
    <Route element={<PublicLayout />}>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
    </Route>

    <Route element={<ProtectedRoute allowedRoles={['employee']} />}>
      <Route
        element={
          <ErrorBoundary scope="employee">
            <EmployeeLayout />
          </ErrorBoundary>
        }
      >
        <Route path="/employee" element={<Navigate to="/employee/documents" replace />} />
        <Route path="/employee/documents" element={<L><DocumentCenterPage /></L>} />
        <Route path="/employee/documents/national-id" element={<L><NationalIdReviewPage /></L>} />
        <Route path="/employee/upload" element={<Navigate to="/employee/payslips" replace />} />
        <Route path="/employee/payslips" element={<L><MyPayslipsPage /></L>} />
        <Route
          path="/employee/payslips/:year/:month"
          element={<L><PayslipMonthWorkspacePage /></L>}
        />
        <Route path="/employee/attendance" element={<Navigate to="/employee/documents" replace />} />
        <Route path="/employee/contract" element={<Navigate to="/employee/documents" replace />} />
        <Route path="/employee/chat" element={<L><PayrollChatPage /></L>} />
        <Route path="/employee/validation-history" element={<Navigate to="/employee/payslips" replace />} />
      </Route>
    </Route>

    <Route element={<ProtectedRoute allowedRoles={['payroll_accountant']} />}>
      <Route
        element={
          <ErrorBoundary scope="accountant">
            <AccountantLayout />
          </ErrorBoundary>
        }
      >
        <Route path="/accountant" element={<Navigate to="/accountant/employees" replace />} />
        <Route path="/accountant/employees" element={<L><EmployeeManagementPage /></L>} />
        <Route path="/accountant/employees/add" element={<L><AddEmployeePage /></L>} />
        <Route path="/accountant/employees/:employeeNumber" element={<L><EmployeeProfilePage /></L>} />
        <Route
          path="/accountant/employees/:employeeNumber/workspace"
          element={<AccountantEmployeeWorkspaceLayout />}
        >
          <Route index element={<Navigate to="documents" replace />} />
          <Route path="documents" element={<L><DocumentCenterPage /></L>} />
          <Route path="payslips" element={<L><MyPayslipsPage /></L>} />
          <Route path="payslips/:year/:month" element={<L><PayslipMonthWorkspacePage /></L>} />
          <Route path="chat" element={<L><PayrollChatPage /></L>} />
          <Route path="settings" element={<L><EmployeeSettingsPage /></L>} />
        </Route>
        <Route path="/accountant/employees/:employeeNumber/edit" element={<L><EditEmployeePage /></L>} />
        <Route path="/accountant/bulk-upload" element={<L><BulkPayrollUploadPage /></L>} />
        <Route
          path="/accountant/bulk-upload/jobs/:jobId/items/:itemId/resolve"
          element={<L><BatchItemReviewWorkspacePage /></L>}
        />
        <Route path="/accountant/batch-monitor" element={<L><BatchProcessingMonitorPage /></L>} />
        <Route path="/accountant/rules" element={<L><PayrollRulesPage /></L>} />
        <Route path="/accountant/findings" element={<L><ValidationFindingsPage /></L>} />
        <Route path="/accountant/approvals" element={<L><ApprovalQueuePage /></L>} />
        <Route path="/accountant/audit-logs" element={<L><AccountantAuditLogsPage /></L>} />
      </Route>
    </Route>

    <Route element={<ProtectedRoute allowedRoles={['developer_admin']} />}>
      <Route
        element={
          <ErrorBoundary scope="admin">
            <AdminLayout />
          </ErrorBoundary>
        }
      >
        <Route path="/admin" element={<L><SystemDashboardPage /></L>} />
        {import.meta.env.DEV ? (
          <>
            <Route path="/admin/users" element={<L><UsersAndRolesPage /></L>} />
            <Route path="/admin/rule-packs" element={<L><RulePacksPage /></L>} />
            <Route path="/admin/department-rules" element={<L><DepartmentRulesPage /></L>} />
            <Route path="/admin/mcp-sync" element={<L><McpLegalSyncPage /></L>} />
            <Route path="/admin/ai-models" element={<L><AiModelsPage /></L>} />
            <Route path="/admin/rag" element={<L><RagManagementPage /></L>} />
            <Route path="/admin/configuration" element={<L><SystemConfigurationPage /></L>} />
            <Route path="/admin/audit-logs" element={<L><AdminAuditLogsPage /></L>} />
            <Route path="/admin/document-lab" element={<L><DocumentLabPage /></L>} />
          </>
        ) : null}
      </Route>
    </Route>

    <Route path="*" element={<Navigate to="/" replace />} />
  </Route>
);
