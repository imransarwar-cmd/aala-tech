Native Payroll Revision — Validation
====================================

Module version: 19.0.2.0.0

The delivered module creates 17 native salary rules, 18 native input
definitions, one employer-contribution category and one salary structure.
It defines no custom benefit business model and has no setup wizard.

Passed in the build environment:

* 22 standalone tests executing the actual XML salary-rule formulas.
* Python syntax and XML parsing.
* Salary-rule links, input owners, native-only model declarations and package checks.
* Inherited salary-rule view selectors checked against the inspected dependency.

The 8 real Odoo integration tests are provided but have not been executed.
A running Odoo 19 database is not available in the build environment.
Live installation, database migration and optional accounting integration
therefore require testing with your installed addons.

From the extracted module directory::

    python3 qa/validate_package.py
    python3 -m unittest discover -s qa -p 'test_native_rules.py' -v

For a fresh staging installation with both addons in the addons path::

    odoo-bin -c YOUR_STAGING_CONFIG -d YOUR_STAGING_DATABASE \
        -i dvz_employee_benefits --test-enable \
        --test-tags /dvz_employee_benefits --stop-after-init

Use -u instead of -i when testing an upgrade. The migration refuses to
discard business records from the earlier separate-benefits design.

Dependency interfaces were inspected in Odoo Mates om_hr_payroll 19.0.1.4.1,
commit 828360acf884585c291f008713fe506da44147f9:

https://github.com/odoomates/hr/tree/19.0/om_hr_payroll
