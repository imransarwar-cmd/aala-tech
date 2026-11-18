Auto-Check / One-Employee Policy Configuration
==============================================

Target: Odoo 19 Community | addon: dvz_leave_policy | version: 19.0.4.0.0

What installation prepares automatically
----------------------------------------
- A generic, inactive Leave and Absence Policy draft using the shared PDF.
- Annual Leave (24 working days), Leave Without Pay, and Work From Home leave types.
- HOD + HR review for paid leave and WFH, half-day notice, unpaid absences,
  documented exceptions and year-end encashment as supported by the addon.
- No assignment to employees, automatic grants or payroll postings.

What happens when you click 'Auto-Check Employee'
------------------------------------------------
1. Reads this employee's previously saved leave eligibility fields.
2. Reads this employee's recorded Time Off Approver as HOD.
3. If hr.contract is installed and accessible, inspects only this employee's
   running contract. A contract start is *not* assumed to be joining date.
4. If a contract records trial_date_end, proposes a probation end and an
   eligible date based on the policy's inclusive-date setting.
5. Detects missing or conflicting dates and reports them on screen.
6. Prefills HR and Management approvers only when one unambiguous approver
   has already been configured on the selected policy.
7. It does not silently mark somebody 'permanent' or invent 3/6 months.

Apply one employee
------------------
1. Open Time Off > Configuration > Set Up One Employee.
2. Select the employee, click Auto-Check Employee.
3. Review the audit notes and confirm the original joining date, probation
   date, actual employment status, and HOD, HR and Management approvers.
4. Review any policy-source options not specified in the PDF; check
   'Employee Details, Approvers, Types and Source Choices Verified'.
5. Click Apply to This Employee. This activates the valid draft if necessary,
   assigns only that employee, and does not create an allocation.
6. Click Preview Employee Allocation; investigate conflicts or missing dates.
7. Click Generate Employee Allocation; follow the normal Odoo approval flow.
8. Test a valid leave, an over-balance request, a probation paid-leave request,
   a half-day notice violation and the separate HOD / HR approvals in staging.

Important limitations
---------------------
- The supplied policy has NO stated probation period length, so no duration is
  guessed. If neither the employee nor a readable contract has a verified
  probation end, HR must enter it.
- HR and Management approvers must come from actual company users; no default
  user is guessed by group membership.
- The source does not specify the daily proration formula or salary/encashment
  rate. Any initial defaults require explicit review.
- The source does not authorize automatic payroll deductions or direct
  modification of historical payroll.
- This package has NOT been installed or run against your production DB.
