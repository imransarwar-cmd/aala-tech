19.0.4.0.0
------------
* Add Auto-Check Employee to the one-employee setup wizard.
* Read previously verified employee joining, probation and eligibility dates.
* Optionally inspect a unique readable running HR contract for its recorded
  trial/probation end, without assuming a standard probation duration.
* Prefill the recorded HOD and uniquely assigned policy HR/Management approvers.
* Display review warnings and prevent unverified automatic activation or grants.
* Keep no extra business features beyond the supplied Leave and Absence Policy.

Changelog
=========

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
