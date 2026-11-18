Leave Policy Management
=======================

Technical name: ``dvz_leave_policy``. Version: ``19.0.4.0.0``.
Target: **Odoo 19 Community**, using Employees and Time Off.

This version implements the supplied **Leave and Absence Policy**. It contains a
populated generic draft and linked **Annual Leave**, **Leave Without Pay** and
**Work From Home** types. Installation creates no employees, assignments, leave
balances or payroll postings. Additional business rules belong in separate addons.

The source revision date, **10 March 2025**, is informational. Choose the actual
policy effective dates before use. ``POLICY_MAPPING.rst`` maps the source clauses
and identifies the limited implementation choices the document does not settle.

What the source policy does
--------------------------

* Permanent employees receive 24 working days per calendar year, with new-joiner
  proration. Paid leave is unavailable during probation; actual absence is LWP.
* Full and half days share one Annual Leave balance. Full-day requests need prior
  approval from HOD and HR. Half-days require one calendar day's notice and a
  morning/afternoon selection.
* A verified failed return after an approved morning half-day with a scheduled
  return later that day can become a full day. Missing attendance alone is not
  sufficient evidence.
* WFH requires HOD and HR approval beforehand, availability, timely communication
  and completed-task updates sent to both roles. It is worked time and does not
  consume Annual Leave.
* Verified actual unauthorized absence is LWP, subject to the emergency rule.
  Exceptions need Management, HOD and HR approval.
* All reconciled unused leave is encashed at year end using an actual approved
  daily rate entered on the settlement. The addon records payment references;
  it does not send money or post payroll deductions.

Set up exactly one existing employee
-----------------------------------

Open **Time Off > Configuration > Set Up One Employee**, or open the employee's
**Leave Policy** tab and select **Set Up This Employee**.

1. Select the existing employee and company, then click **Auto-Check Employee**.
   It reads previously verified joining and probation dates, a unique running
   contract when ``hr.contract`` is installed and accessible, and the employee's
   Time Off approver. It reports missing/conflicting records and displays the
   contract start as a reference (not presumed to be the original hire date).
   Where the running contract records an explicit trial end, the wizard can
   propose a first paid date from the policy's inclusive/end-date setting.
   The source **does not state a probation duration**. None is invented.
   Confirm the actual employment status, original joining date, recorded
   probation end and/or paid eligibility date. A probation employee can retain
   an empty first paid date.
2. Confirm the automatically detected HOD and select the actual HR and Management users. HOD becomes the employee's
   native Time Off approver. HR and Management need native Time Off Officer or
   Administrator access. The selected employee cannot approve their own request;
   HOD and HR must be different users.
3. Select the populated draft or a compatible active policy. Drafts can use
   existing compatible types or create missing dedicated types from blank
   selections. Existing types are never reconfigured by setup. An active policy's
   rules, dates, types and approval routes remain unchanged; the selected HR and
   Management users must already belong to those routes.
4. Review the automatic check notes, employee details, types and unspecified source choices, then check
   the single verification box. **Save Policy Draft** prepares configuration
   without assigning the employee. **Apply to This Employee** activates a draft
   when valid and assigns the policy only to the selected employee.
5. The result shows that employee, the prepared policy and the applied status.
   **Preview Employee Allocation** is optional. It checks only that employee's
   calendar year and displays the amount or an actionable review error.
6. **Generate Employee Allocation** recalculates the preview and creates one
   pending allocation. Normal allocation approval remains separate. Repeating
   the operation reuses the same grant.

Existing overlapping paid allocations, including another paid type, prevent a new
unreviewed grant. The wizard does not top up, replace or reinterpret existing
balances. Select the intended existing type and reconcile the recorded balance
before generating. No other employee is assigned or allocated by this setup.

Source choices requiring review
-------------------------------

The document requires new-joiner proration without giving an exact formula or
rounding. The preset uses actual calendar days, joining-date basis and downward
half-day rounding. These choices are visible on the draft. The document gives one
day's half-day notice but no numeric full-day or WFH notice duration; those values
start at zero while prior approval remains required.

No probation length or salary rate is invented. Auto-Check does not guess hiring dates from a contract start, determine permanent status from an open contract, allocate leave, post salary deductions, or contact any server outside the installed Odoo database. Use verified employee dates and
enter the approved daily rate and reference on each year-end settlement. An active
or retired policy retains its rules; use **Create Revision** for later changes.

Requests, WFH updates and corrections
------------------------------------

Emergency and exception fields can be completed on a new request before saving.
Use **HOD Approval**, **HR Approval** and **Approve Exception** for the required
signatures. Management may sign before or after HOD/HR, but an exception remains
pending until all required signatures are recorded. API calls enforce the same
rules as the form.

WFH commitments can also be completed before the initial save. **Send Task Update
to HOD and HR** opens an explicit send dialog after work starts. A saved draft is
not a sent update. Sender, recipients, message and sending time are retained.
Commitments and communication records do not independently measure productivity.

For an actual unauthorized absence, an administrator enters verified evidence and
uses **Record as Unpaid**. For a failed same-day morning return, enter verified
return evidence and use **Confirm Failed Return**. A pending future request or an
absent punch alone is not proof of an actual absence. An afternoon half-day is not
converted by inventing a same-day return. Disciplinary decisions remain human.

Year-end encashment
------------------

Open **Time Off > Policy Operations > Year-End Encashments** after the calendar
year has ended. Select the employee, policy and complete year; calculate the
recorded unused balance. Pending or ambiguous source records require reconciliation.
Enter the approved daily rate and its reference, then approve the encashment.
Approved source periods are protected from later leave/allocation changes.

After payment is made through the organization's normal process, **Record Payment**
stores the actual reference and date. It performs no payroll, accounting or bank
transaction. Settlements use day/half-day types and all reconciled unused days.

Installation and tests
----------------------

Copy ``dvz_leave_policy`` into an Odoo 19 addons path and install **Leave Policy
Management**. Substitute the real executable, configuration and test database::

    python3 /path/to/odoo-bin -c /path/to/odoo.conf -d STAGING_DATABASE \
        -i dvz_leave_policy --stop-after-init

For an upgrade and the addon tests on a staging database::

    python3 /path/to/odoo-bin -c /path/to/odoo.conf -d STAGING_DATABASE \
        -u dvz_leave_policy --test-enable --test-tags /dvz_leave_policy --stop-after-init

From the addon directory, run calculation tests without Odoo::

    python3 -m unittest discover -s tests -p test_engine_offline.py

``VALIDATION.rst`` records which checks were executed. Source-only upgrade guards
stop an automatic upgrade when active or used earlier configurations depend on
removed behavior. Review those configurations before migration; balances are not
silently changed. No live employee setup is claimed by distributing this addon.
