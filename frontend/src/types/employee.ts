export type EmploymentType = 'full_time' | 'part_time' | 'contractor' | 'intern';
export type SalaryType = 'monthly' | 'hourly';
export type EmployeeStatus = 'active' | 'on_leave' | 'terminated';

/** Shape aligned with backend employee master data — UI placeholder only. */
export type EmployeeRecord = {
  employeeNumber: string;
  fullName: string;
  email: string;
  department: string;
  employmentType: EmploymentType;
  salaryType: SalaryType;
  baseSalaryOrRate: number;
  status: EmployeeStatus;
};
