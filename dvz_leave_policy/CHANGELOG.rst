Changelog
=========

19.0.5.0.0
-----------

* Separate employee policy assignment from paid-leave eligibility. Missing joining,
  probation and first-paid dates, or unconfirmed status, no longer block setup.
* Add one configurable company default selected with Use for New Employees;
  assign it when a new employee is saved, without creating a leave allocation.
* Preserve explicit administrator assignments and existing employee records.
* Keep permanent-status, verified-date and balance checks for paid leave/grants.
* Read accessible native Odoo 19 probation information during Auto-Check, preserve
  its permissions, and prevent stale/forged check results or editing applied setup.
* Add regression cases for assignment, multi-company/access controls, incomplete
  eligibility and employee copies; retain the source policy's business rules.

19.0.4.0.0
------------
* Add Auto-Check Employee to the one-employee setup wizard.
* Read previously verified employee joining, probation and eligibility dates.
* Optionally inspect a unique readable running HR contract for its recorded
  trial/probation end, without assuming a standard probation duration.
* Prefill the recorded HOD and uniquely assigned policy HR/Management approvers.
* Display review warnings and prevent unverified automatic activation or grants.
* Keep no extra business features beyond the supplied Leave and Absence Policy.

19.0.3.0.0
-----------

* Limited the addon to the supplied Leave and Absence Policy.
* Added required selection of exactly one existing employee, verified employee
  facts and actual HOD, HR and Management approvers.
* Added separate draft preparation, one-employee application and optional annual
  allocation preview/generation with duplicate and existing-balance protection.
* Allowed compatible active-policy assignment without changing policy rules.
* Reduced WFH to the source commitments and explicit updates to both HOD and HR.
* Reduced year-end treatment to full unused-day encashment at an approved rate.
* Removed optional controls, scheduled automation and the Attendances dependency.
* Added upgrade guards for earlier active/used configurations; no balances are
  silently converted or rewritten.

19.0.2.0.0
-----------

* Added a generic source preset, configuration setup and broader optional controls.
  The additional controls are removed in 19.0.3.0.0.

19.0.1.0.0
-----------

* Initial generic Leave Policy Management addon using the ``dvz_`` technical prefix.
