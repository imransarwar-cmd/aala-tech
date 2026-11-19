Validation Record
=================

Addon: dvz_leave_policy
Display name: Leave Policy Management
Version: 19.0.5.0.0
Target: Odoo 19 Community
Checked: 19 November 2026

Executed checks
---------------
* All addon Python files compiled successfully.
* All 14 database-independent calculation and eligibility tests passed, including
  permanent status, missing dates, probation boundaries, calendar-year proration,
  leap years, rounding, finite quantities and annual entitlement limits.
* The addon imported using the official Odoo 19.0 source and its installed Python
  dependencies. The 17 dependency modules, new company/default-assignment models
  and all seven ORM test modules imported successfully.
* All 10 XML files passed the official Odoo import RelaxNG schema. Four standalone
  list/search architectures passed their official view schemas.
* Static resolution checked 63 external references, 171 view-field references,
  29 object-button methods and four inherited XPath targets.
* The source preset still contains 31 valid fields and 11 valid literal selections.
  Python factory defaults match the XML preset; entitlement rules did not change.
* Independent source review checked automatic employee creation, company defaults,
  explicit administrator assignments, native create permissions, copy behavior,
  protected inputs/context, assignment without eligibility, paid eligibility
  enforcement, current native employment-date reads and protected check results.

Database tests supplied, not executed
------------------------------------
The seven ORM test modules contain 96 test methods:

* 15 policy and approval-configuration cases.
* 14 annual allocation and balance-protection cases.
* 11 leave workflow and authorization cases.
* 25 one-employee setup and Auto-Check cases.
* 14 automatic employee-assignment cases.
* 13 encashment, provenance and settlement-lock cases.
* Four WFH commitments and task-delivery cases.

New regression definitions cover assigning a policy with missing dates and
unconfirmed status while still blocking unverified paid leave/allocations;
company-specific defaults and batches; ordinary HR-officer creation without
configuration privileges; copied employees; context/input protection; changing
and removing defaults; lifecycle guards; native probation data and unavailable
HR permissions; stale check results; and normal wizard Form saves.

These test definitions were imported but were NOT executed against a database.
PostgreSQL socket creation was unavailable in the earlier validation environment;
no new database connection or socket-start attempt was made for this revision.
No successful database installation, ORM test run, upgrade migration, concurrency
run, browser acceptance test or live employee configuration is claimed.

Release contents
----------------
The release contains only the addon source, views, security, source preset,
existing migration guards, documentation and tests. The package excludes Python
caches, source policy PDFs, employee workbooks, credentials and the Odoo validation
runtime. ZIP integrity and manifest entries are checked during release packaging.

Behavior under review
---------------------
Policy assignment is independent of paid eligibility. Selecting Use for New
Employees records one active default for that company. Employee creation copies
it without dates/status requirements or allocation side effects. Choosing another
default affects future employees only. Installation and upgrade do not pick a
default or bulk-reassign employees.

The one-employee wizard can assign a policy before HR confirms eligibility.
Unknown status and missing dates remain explicit; neither a probation duration
nor a permanent-status decision is invented. Paid request and allocation checks
retain the source policy rules, including its separately authorized exceptions.
The operational company default is separate from immutable policy rule versions.

Policy effective dates remain enforced for requests and allocations, allowing
onboarding before a policy's effective start. A configured inactive or invalid
company default raises a configuration error instead of silently leaving a new
employee ungoverned. Default policies must be replaced or the default removed
before retirement/archive.

Upgrade limits
--------------
The existing 19.0.3.0.0 migration guards remain in the package for upgrades from
older broad-feature versions. They stop an upgrade when active/used configurations
or historical balances depend on removed behavior. They do not rewrite balances.
Upgrading from 19.0.4.0.0 adds the company-default field and UI, removes the wizard's
eligibility-before-assignment gate and refreshes Auto-Check behavior. It does not
change existing employee dates, policy assignments or allocation balances.

Staging verification
--------------------
Use the actual executable, configuration and a dedicated Odoo 19 test database::

    python3 /path/to/odoo-bin -c /path/to/odoo.conf -d YOUR_TEST_DATABASE \
        -u dvz_leave_policy --test-enable --test-tags /dvz_leave_policy \
        --no-http --stop-after-init

Use -i instead of -u for a fresh installation. After upgrading, activate the
intended reviewed policy, select Use for New Employees and save a test employee
with missing eligibility dates. Confirm assignment without a paid allocation,
then verify the actual paid-leave/approval flow after entering verified HR facts.

To run the independent calculations from the addon directory::

    python3 -m unittest discover -s tests -p test_engine_offline.py -v

Official platform references used
---------------------------------
* https://www.odoo.com/documentation/19.0/developer/reference/orm.html
* https://www.odoo.com/documentation/19.0/developer/howtos/company.html
