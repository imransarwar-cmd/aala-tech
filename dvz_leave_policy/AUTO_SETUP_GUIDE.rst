Employee Policy Assignment and Eligibility
=========================================

Target: Odoo 19 Community | addon: dvz_leave_policy | version: 19.0.5.0.0

Why the earlier Invalid Operation appeared
-----------------------------------------
The earlier setup wizard checked paid eligibility before it could assign the
policy. Version 19.0.5.0.0 separates these operations. Joining date, permanent
status and paid-eligibility dates can be completed later. Missing dates never
prevent policy assignment; they still prevent an unverified paid grant/request.

One-time company configuration
------------------------------
1. Upgrade the installed addon, restart Odoo and refresh the browser.
2. Open Time Off > Configuration > Leave Policies.
3. Open the intended policy. If still Draft, review the source choices, configure
   the leave types and select actual HR/Management approvers, then Activate.
4. Click Use for New Employees. The form shows that this is the company's default.
5. Repeat only for other companies that need a different default.

Only one policy is the default for each company. Selecting a replacement changes
future employee creation. It does not reassign existing employees or alter their
balances. Stop Automatic Assignment removes the default for future employees.
Draft/retired/archived policies cannot be selected as defaults. A future effective
start is allowed for onboarding; request dates are checked independently.

Check a new employee
--------------------
1. Create an employee in the configured company. Save with eligibility status
   Not Confirmed and no joining/probation/first-paid dates if those facts are not
   known yet.
2. Open the employee's Leave Policy tab. The company default should be assigned.
3. Confirm that no paid allocation was created by employee creation.
4. Set the employee's real HOD / Time Off Approver before the approval workflow
   is used. The company policy supplies its configured HR and Management routes.
5. When HR has confirmed eligibility, enter Joining Date for Leave, Permanent
   status and either First Paid Leave Date or the actual Probation End Date.
6. Preview the employee's allocation, review existing balances and generate the
   pending allocation if appropriate. Complete normal allocation approval.
7. Check a valid paid request, a probation paid request, an over-balance request,
   half-day notice and the separate HOD/HR approvals on a test database.

Existing employee with the reported error
-----------------------------------------
1. Open the employee > Leave Policy > Set Up This Employee.
2. Select the intended policy and actual approvers; review the configuration.
3. Unknown eligibility facts can remain blank or Not Confirmed.
4. Click Apply to This Employee. The policy is assigned without a paid grant.
5. Preview Employee Allocation reports missing eligibility details separately.
   Complete verified dates/status before generating an allocation.

The wizard still rejects conflicting dates (for example a probation end before
the joining date), wrong companies, invalid approvers and unreviewed policy rules.
These checks protect recorded facts; they do not require an invented date.

Auto-Check Employee
-------------------
Auto-Check reads the selected employee's saved leave fields, Time Off Approver
and accessible native Odoo 19 contract/probation fields. A recorded contract start
is displayed as a reference only because it may differ from the original joining
date. A recorded probation end can propose a first-paid date using the policy's
inclusive-end setting. The employee is not automatically made Permanent.

If the current user cannot read HR contract information, the check reports that
limitation and uses the saved leave fields. The check clears stale suggestions
and cannot be rerun on an already-applied setup; open a fresh setup to review
changed employee facts. Read the notes and resolve conflicting records before
using a suggestion. Saving or checking the wizard does not itself assign policy,
approve leave, generate a grant or post payroll.

Local Mac upgrade
-----------------
Stop the running Odoo instance and any other upgrade process first. From the
custom addons parent directory containing both dvz_leave_policy and the other
required custom modules, with ../odoo-bin as the executable::

    ../odoo-bin -d YOUR_DATABASE -u dvz_leave_policy --addons-path=../addons,. --no-http --stop-after-init

Replace YOUR_DATABASE with the intended database. This example assumes the
custom addons directory is directly inside the Odoo source directory. If your
normal launch uses a configuration file or more addon directories, pass
that real configuration and preserve all required addon paths. Do not launch
parallel upgrades. A PostgreSQL lock timeout must be resolved before the module
can finish upgrading. Restart Odoo using the normal launch command afterwards.

Installation and upgrade never choose a real employee, infer a probation length,
rewrite existing balances or automatically select a company default. The default
selection is a one-time configuration action. See VALIDATION.rst for exactly which
checks were run and the supplied database test suite.
