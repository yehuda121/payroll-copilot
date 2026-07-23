import { PortalPage } from '../../components/PortalPage';
import {
  AnalyticsDashboardLayout,
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
  AnalyticsStatCard,
  AnalyticsStatGrid,
  BarChartCard,
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import { useAdminOrgCensus } from '../../hooks/useAdminOrgCensus';

export function OrgCensusAnalyticsPage() {
  const { data, loading, error, reload } = useAdminOrgCensus();

  const caseloadRows =
    data?.employees_per_payroll_accountant.map((row) => ({
      name: row.payroll_accountant_id.slice(0, 8),
      value: row.employee_count,
      fullId: row.payroll_accountant_id,
    })) ?? [];

  const orgRows = data?.organizations ?? [];
  const hasData = Boolean(data && (data.companies_count > 0 || data.employees_count > 0));

  return (
    <PortalPage
      title="Organization Analytics"
      description="Company census: employees, payroll accountants, and assignment coverage."
    >
      <AnalyticsDashboardLayout>
        {loading && !data ? <AnalyticsLoadingState cards={4} /> : null}

        {error ? (
          <AnalyticsErrorState
            title="Unable to load organization analytics"
            message={error}
            onRetry={reload}
          />
        ) : null}

        {!loading && !error && data && !hasData ? (
          <AnalyticsEmptyState
            title="No organization statistics yet"
            description="Census metrics appear after companies and employees are provisioned."
          />
        ) : null}

        {data && hasData ? (
          <>
            <AnalyticsStatGrid>
              <AnalyticsStatCard label="Companies" value={data.companies_count} />
              <AnalyticsStatCard label="Employees" value={data.employees_count} />
              <AnalyticsStatCard
                label="Payroll accountants"
                value={data.payroll_accountants_count}
              />
              <AnalyticsStatCard
                label="Employees without accountant"
                value={data.employees_without_payroll_accountant}
              />
            </AnalyticsStatGrid>

            {caseloadRows.length > 0 ? (
              <BarChartCard
                title="Employees per payroll accountant"
                data={caseloadRows}
                xKey="name"
                layout="vertical"
                series={[
                  {
                    dataKey: 'value',
                    name: 'Employees',
                    color: ANALYTICS_CHART_COLORS.primary,
                  },
                ]}
              />
            ) : (
              <AnalyticsEmptyState
                title="No accountant assignments"
                description="Employees do not yet have payroll_accountant_id set."
              />
            )}

            {orgRows.length > 0 ? (
              <section className="analytics-chart-card" aria-label="Organization statistics">
                <h2>Organization statistics</h2>
                <div className="analytics-chart-card__body analytics-chart-card__body--auto">
                  <table className="analytics-table">
                    <thead>
                      <tr>
                        <th scope="col">Organization</th>
                        <th scope="col">Employees</th>
                        <th scope="col">Accountants</th>
                        <th scope="col">Unassigned</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orgRows.map((org) => (
                        <tr key={org.organization_id}>
                          <td>
                            <code>{org.organization_id.slice(0, 8)}…</code>
                          </td>
                          <td>{org.employees_count}</td>
                          <td>{org.payroll_accountants_count}</td>
                          <td>{org.employees_without_payroll_accountant}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}
          </>
        ) : null}
      </AnalyticsDashboardLayout>
    </PortalPage>
  );
}
