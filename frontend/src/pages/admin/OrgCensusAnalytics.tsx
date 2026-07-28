import { useTranslation } from 'react-i18next';
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
import './admin-ai.css';

export function OrgCensusAnalyticsPage() {
  const { t } = useTranslation();
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
      title={t('admin.orgAnalytics.title')}
      description={t('admin.orgAnalytics.description')}
    >
      <AnalyticsDashboardLayout>
        {loading && !data ? <AnalyticsLoadingState cards={4} /> : null}

        {error ? (
          <AnalyticsErrorState title={t('common.error')} message={error} onRetry={reload} />
        ) : null}

        {!loading && !error && data && !hasData ? (
          <AnalyticsEmptyState
            title={t('admin.orgAnalytics.empty')}
            description={t('admin.dashboard.emptyHint')}
          />
        ) : null}

        {data && hasData ? (
          <>
            <section className="admin-dashboard-section">
              <header className="admin-dashboard-section__header">
                <h2>{t('admin.orgAnalytics.sectionOverview')}</h2>
                <p>{t('admin.orgAnalytics.sectionOverviewDesc')}</p>
              </header>
              <AnalyticsStatGrid>
                <AnalyticsStatCard
                  label={t('admin.orgAnalytics.colOrg')}
                  value={data.companies_count}
                />
                <AnalyticsStatCard
                  label={t('admin.orgAnalytics.colEmployees')}
                  value={data.employees_count}
                />
                <AnalyticsStatCard
                  label={t('admin.orgAnalytics.colAccountants')}
                  value={data.payroll_accountants_count}
                />
                <AnalyticsStatCard
                  label={t('admin.orgAnalytics.colUnassigned')}
                  value={data.employees_without_payroll_accountant}
                />
              </AnalyticsStatGrid>
            </section>

            {caseloadRows.length > 0 ? (
              <section className="admin-dashboard-section">
                <header className="admin-dashboard-section__header">
                  <h2>{t('admin.orgAnalytics.sectionCaseload')}</h2>
                  <p>{t('admin.orgAnalytics.sectionCaseloadDesc')}</p>
                </header>
                <BarChartCard
                  title={t('admin.orgAnalytics.employeesPerAccountant')}
                  data={caseloadRows}
                  xKey="name"
                  layout="vertical"
                  series={[
                    {
                      dataKey: 'value',
                      name: t('admin.orgAnalytics.colEmployees'),
                      color: ANALYTICS_CHART_COLORS.primary,
                    },
                  ]}
                />
              </section>
            ) : null}

            {orgRows.length > 0 ? (
              <section className="admin-dashboard-section">
                <header className="admin-dashboard-section__header">
                  <h2>{t('admin.orgAnalytics.orgTable')}</h2>
                  <p>{t('admin.orgAnalytics.description')}</p>
                </header>
                <section className="analytics-chart-card" aria-label={t('admin.orgAnalytics.orgTable')}>
                  <div className="analytics-chart-card__body analytics-chart-card__body--auto">
                    <table className="analytics-table">
                      <thead>
                        <tr>
                          <th scope="col">{t('admin.orgAnalytics.colOrg')}</th>
                          <th scope="col">{t('admin.orgAnalytics.colEmployees')}</th>
                          <th scope="col">{t('admin.orgAnalytics.colAccountants')}</th>
                          <th scope="col">{t('admin.orgAnalytics.colUnassigned')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {orgRows.map((org) => (
                          <tr key={org.organization_id}>
                            <td>{org.organization_id}</td>
                            <td>{org.employees_count}</td>
                            <td>{org.payroll_accountants_count}</td>
                            <td>{org.employees_without_payroll_accountant}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </section>
            ) : null}
          </>
        ) : null}
      </AnalyticsDashboardLayout>
    </PortalPage>
  );
}
