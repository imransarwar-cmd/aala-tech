Validation Record
=================

Addon: ``dvz_leave_policy``

Display name: Leave Policy Management

Version: ``19.0.3.0.0``

Target: Odoo 19 Community

Checked: 18 November 2026

Executed checks
---------------

* All 14 database-independent annual calculation and eligibility tests passed.
  They cover the calendar year, configurable entitlement, actual-day and leap-year
  proration, date basis, rounding, permanent status, verified probation boundaries,
  missing dates, invalid quantities and the annual entitlement cap.
* All addon Python files compiled successfully.
* The addon imported using the official Odoo 19.0 source and its installed Python
  dependencies. Seventeen dependency modules and all six ORM test modules also
  imported. This checks Python/API import compatibility, not database installation.
* All 10 XML files passed the official Odoo import RelaxNG schema. Four standalone
  list/search architectures passed their native view schemas.
* Static resolution checked 61 external references, 163 view-field references,
  25 object-button methods and 4 inherited XPath targets.
* The source preset contains 31 valid fields and 11 valid literal selections.
  Python factory values match the XML preset.
* No remaining compilation, import, schema or reference errors were reported.
* The ZIP integrity, manifest paths and generic naming were checked. It contains
  the addon source, views, security, preset, migration guards, documentation and
  tests. Python caches, the source PDF, employee workbooks, credentials and the
  verification runtime are excluded.

Database tests supplied, not executed
------------------------------------

The addon contains 69 ORM test methods across six modules:

* 15 policy and approval-configuration cases.
* 14 annual allocation and balance-protection cases.
* 11 leave workflow and authorization cases.
* 12 one-employee setup cases.
* 13 encashment, provenance and settlement-lock cases.
* 4 WFH commitments and task-delivery cases.

These definitions were imported but were **not executed against a database**.
PostgreSQL startup in this workspace was previously blocked by Unix socket
creation returning ``PermissionError: [Errno 1] Operation not permitted``.
No new database or socket attempt was made for this revision.

No successful database installation, ORM execution, upgrade migration execution,
concurrency test, browser acceptance test or production deployment is claimed.
The single-employee workflow has been implemented and its test definitions
supplied; no real employee has been selected or configured in a live Odoo server.

Scope checked
-------------

This revision contains only the supplied leave policy's annual calendar-year
entitlement, verified eligibility, full/half-day requests, approvals, emergency
and exception handling, WFH commitments and updates, verified actual-absence
classification, and full unused-day year-end encashment.

The preset creates one generic draft and three linked leave types. The setup
requires exactly one existing employee, actual approvers and verified employee
facts. It has no company-wide default. Probation can remain unconfirmed without
an invented paid-eligibility date.

Annual allocation preview/generation checks the selected employee's existing
overlapping paid balances, including another paid type. Repeated generation
reuses an exact grant; it does not top up or reinterpret manual balances.
Generated allocations remain subject to ordinary native approval.

The source does not specify the exact proration formula, rounding, numeric
full-day/WFH notice, probation length or daily encashment rate. The first three
are documented configuration choices; employee facts and rates must be verified.
See ``POLICY_MAPPING.rst``.

Encashment uses all reconciled unused days and a manually approved daily rate.
LWP classification and payment-reference recording do not post payroll,
accounting or bank transactions.

Upgrade limits
--------------

The pre-migration guard stops an automatic upgrade when active/used earlier
policies, nonannual allocations or settlements depend on removed behavior.
This prevents a silent reinterpretation of historical balances. Those cases
need a reviewed migration or a separate extension.

A successful upgrade removes only the two obsolete addon-owned scheduled jobs.
The legacy standard draft is archived only if it is unused and unassigned.
No employee balance is automatically migrated.

Staging verification
--------------------

Use the actual executable, configuration and dedicated Odoo 19 staging database::

    python3 /path/to/odoo-bin -c /path/to/odoo.conf -d YOUR_TEST_DATABASE \
        -i dvz_leave_policy --test-enable --test-tags /dvz_leave_policy \
        --stop-after-init

Use ``-u dvz_leave_policy`` instead of ``-i`` for an installed copy. Review the
installation and test results before use on a live database, including any
third-party customizations.

To run the independent calculations from the addon directory::

    python3 -m unittest discover -s tests -p test_engine_offline.py -v
