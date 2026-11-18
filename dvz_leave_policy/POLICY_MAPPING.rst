Shared Policy Mapping
=====================

Source: the supplied **Leave and Absence Policy**, revision **10 March 2025**.
Company and author names are omitted. The source date is informational; deployment
uses separately reviewed effective dates.

.. list-table:: Source rules and this addon
   :header-rows: 1
   :widths: 40 60

   * - Source rule
     - Implementation
   * - Permanent employees; no paid leave during probation.
     - Explicit employee assignment, actual employment status and verified joining/
       first-paid dates. Probation may have no confirmed first-paid date and receives
       no paid grant. Verified actual absence uses Leave Without Pay.
   * - 24 working days per calendar year; new joiners prorated.
     - January-to-December annual entitlement using the employee's working calendar.
       Full and half days share the same Annual Leave type and balance.
   * - Full-day leave needs prior notice and HOD plus HR approval.
     - Prior-approval enforcement, HOD then HR signatures and the employee's native
       Time Off approver as HOD. Actual HR users are configured on the policy.
   * - Half-day approval at least one day ahead; choose morning or afternoon.
     - One calendar day's notice and Odoo's AM/PM selection.
   * - Failure to return after a half-day becomes a full day.
     - An administrator can correct an approved morning half-day only when a later
       same-day return was scheduled and verified failure evidence is recorded.
       A missing punch alone is insufficient; no afternoon return is invented.
   * - WFH needs prior HOD/HR approval and unapproved actual absence is LWP.
     - WFH is worked time with prior approvals. Verified actual unapproved absence
       can be classified as unpaid; a pending future request is not an absence.
   * - WFH availability, productivity, communication and updates to HOD/HR.
     - Availability/communication commitments and an explicit completed-task update
       sent to both roles after work starts. Delivery is recorded; productivity is
       not inferred from the commitments or message.
   * - Unauthorized absence is LWP except emergencies.
     - Emergency treatment can waive notice without fabricating approvals.
       Actual unpaid classification needs verified evidence and an authorized user.
   * - Repeated unauthorized absence may lead to discipline.
     - Records support human review. The addon issues no automatic warnings,
       suspensions or terminations.
   * - Exceptions need Management, HOD and HR.
     - Required exception reason and all three signatures before final approval.
       Management can sign before or after the ordered HOD/HR steps.
   * - Unused leave is encashed at year end.
     - All reconciled unused days multiplied by an entered approved daily rate.
       Rate and payment references are retained, with no payroll or payment posting.

Unspecified details
-------------------

The document does not give the exact proration formula, date basis, rounding,
full-day/WFH numeric notice duration, probation length or encashment rate.
Actual-day proration on joining-date basis with downward half-day rounding is the
preset's visible implementation choice. Full-day and WFH notice values begin at
zero while prior approval remains required. Employee dates and settlement rates
must come from verified records; none are guessed. The document does not give an
exact WFH reporting schedule, so completed-task sending is accepted after work starts.

What setup changes
------------------

**Set Up One Employee** requires an existing employee and actual approvers. A draft
can be saved without assignment. Applying setup assigns only that employee, with
no company-wide default and no automatic allocation. Optional preview/generation
checks only that employee and refuses unreviewed overlapping paid balances.
Repeated generation reuses the same grant.

A compatible active policy can be assigned without changing its rules or routes.
Existing types are reused only when already compatible. The generic draft and
three source types retain their external IDs. Upgrade guards require review of
active/used earlier configurations that relied on removed features; no automatic
balance migration is promised. Further business rules belong in separate addons.
