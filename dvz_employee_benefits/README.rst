Employee Benefits and Allowances — Odoo 19 Community
====================================================

This addon extends ``om_hr_payroll`` directly. Installation creates 17 ordinary
salary rules and the ordinary salary structure **DVZ Employee Benefits**. PF has
separate employee and employer rules, so the 17 rules cover 16 business benefits.

Open the records in the existing payroll screens:

* **Payroll → Configuration → Salary Structures**: DVZ Employee Benefits.
* **Payroll → Configuration → Salary Rules**: use the Employee Benefits filter.
* **Payroll → Employees → Contracts**: choose the employee employment version,
  assign its salary structure and enter the allowance and PF values.
* **Payroll → Employee Payslips → Worked Days & Inputs → Other Inputs**: enter
  the period's one-time amounts, overtime hours or leave/notice days.

The Python formula is visible in each salary rule's normal Computation field.
There is no separate benefit-type catalog, benefit-payment model, approval
ledger or setup wizard. Payroll follows the addon's existing payslip workflow.

Install
-------

1. Install Odoo 19 Community and the Odoo Mates ``om_hr_payroll`` addon.
2. Copy the ``dvz_employee_benefits`` folder into your custom addons directory.
3. Restart Odoo, update the Apps list and install **Employee Benefits and
   Allowances**. Search by technical name ``dvz_employee_benefits`` if necessary.
4. Open the created salary structure and review its rules before assigning it
   to employees. There is no second setup step.

The supplied structure inherits the Odoo Mates base structure containing Basic,
Gross and Net. It does not supply tax, absence, loan or other company-specific
rules. To retain those existing rules, add the 17 benefit rules to your current
structure through its standard Salary Rules tab instead.

Recurring cash allowances are configured on each employment version. One-time
amounts use native payslip inputs. Daily/hourly divisors, overtime multiplier
and PF rates start at zero and require your company's values when used. Leave
encashment does not change Time Off balances. EOSB uses an approved amount;
the module does not assume a country's entitlement formula.

For the full code-to-input mapping, formulas and worked examples, see
``docs/CONFIGURATION.rst``.

Upgrade from the earlier separate-benefits design
------------------------------------------------

This release replaces that design with native payroll records. If the earlier
release has actual recurring benefit entries, payments or calculation history,
the upgrade is blocked to prevent losing those records. Review and migrate that
data before upgrading. Do not remove the migration guard or uninstall the old
release simply to bypass it. A fresh installation has no legacy data to migrate.

Compatibility and verification
------------------------------

The integration targets Odoo 19 ``hr.version`` employment records and native
``hr.payslip.input`` entries from Odoo Mates Payroll. Payroll configuration
requires Payroll Manager access; the compensation fields also require Employees
Administrator / HR Manager access.

Source, XML and calculation checks are included with the delivery. Installation
against your database and its other payroll customizations must be verified in
a test database before a production payroll run.
