Employee Benefits: Native Payroll Configuration
==============================================

1. Choose the salary structure
------------------------------

After installation, open **Payroll → Configuration → Salary Structures** and
select **DVZ Employee Benefits**. It already contains the 17 benefit salary
rules and inherits Basic, Gross and Net from the Odoo Mates base structure.
Assign the structure to each relevant employment version/contract.

If your existing structure contains tax, unpaid absence, loans or other custom
calculations, keep that structure and add the benefit rules through its normal
Salary Rules tab. Search for codes beginning with ``DVZ_``. Add each rule only
once, including the rules inherited through a parent structure.

The earnings rules use the ``ALW`` category. Employee PF uses ``DED`` with a
negative amount. Employer PF uses the separate company-contribution category,
so it does not increase employee gross or net. The standard total formulas are::

    Gross = categories.BASIC + categories.ALW
    Net = categories.BASIC + categories.ALW + categories.DED

Benefit rules must run before any totals or other rules that depend on them.
Review custom total formulas before adding the rules to a modified structure.

2. Enter recurring amounts and policy values
------------------------------------------

Open the employee's employment version in **Payroll → Employees → Contracts**.
Use the **Employee Benefits and Allowances** section for these period amounts:

* Fuel
* Accommodation
* Travel
* Mobile / telephone
* Meal / food
* Special duty
* Car maintenance
* Medical
* Air ticket

These are amounts per payslip period. They do not prorate automatically for
partial employment, attendance or unpaid leave. Configure those adjustments in
your payroll structure if required.

In **Daily and Hourly Benefit Rates**, choose the version wage or a custom salary
base. Enter the Salary Days Divisor before calculating leave encashment, notice
days or overtime. Overtime additionally needs Salary Hours per Day and OT
Multiplier. These values default to zero, so a quantity calculation cannot
silently use an assumed rate.

In **Provident Fund**, enable PF only for eligible employees, choose its wage or
custom base, and set employee and employer percentages separately. A positive
cap limits that contribution per payslip period; zero means no cap. Enter rates
as percentages: for example, ``5`` means 5%, not 0.05. The module supplies no
statutory PF percentage.

When migrating a legacy allowance, check the existing ``hra``,
``travel_allowance``, ``meal_allowance`` and ``medical_allowance`` fields and their
salary rules. If the matching legacy and new rules are both attached, do not
populate both amounts for the same allowance. The duplicate-allowance check
requires you to resolve this before payroll is calculated.

3. Enter one-time amounts and quantities
--------------------------------------

Create the payslip with one explicit employment version and its salary
structure. In **Worked Days & Inputs → Other Inputs**, enter the amount for the
relevant input code. For quantity inputs, the native field is still labelled
**Amount**, but its value represents days or hours as shown below.

.. list-table:: Benefit rules and payslip input codes
   :header-rows: 1
   :widths: 24 30 46

   * - Benefit
     - Rule / monetary input code
     - Calculation
   * - Leave encashment
     - ``DVZ_LEAVE_ENCASH``
     - Cash input plus ``DVZ_LEAVE_DAYS`` × salary base ÷ days divisor.
   * - Fuel
     - ``DVZ_FUEL``
     - Contract allowance plus the cash input.
   * - Accommodation
     - ``DVZ_ACCOMMODATION``
     - Contract allowance plus the cash input.
   * - PF — employee
     - ``DVZ_PF_EMPLOYEE``
     - Negative contribution from the configured PF base and employee percentage.
   * - PF — employer
     - ``DVZ_PF_EMPLOYER``
     - Employer contribution from the configured PF base and employer percentage; excluded from employee net.
   * - End-of-service benefits
     - ``DVZ_EOSB``
     - Enter the approved cash settlement amount.
   * - Travel
     - ``DVZ_TRAVEL``
     - Contract allowance plus the cash input.
   * - Ex-gratia
     - ``DVZ_EX_GRATIA``
     - Enter the approved cash amount.
   * - Mobile / telephone
     - ``DVZ_MOBILE``
     - Contract allowance plus the cash input.
   * - Meal / food
     - ``DVZ_MEAL``
     - Contract allowance plus the cash input.
   * - Overtime
     - ``DVZ_OT``
     - Cash input plus ``DVZ_OT_HOURS`` × salary base ÷ days divisor ÷ hours per day × OT multiplier.
   * - Special duty
     - ``DVZ_SPECIAL_DUTY``
     - Contract allowance plus the cash input.
   * - Car maintenance
     - ``DVZ_CAR_MAINT``
     - Contract allowance plus the cash input.
   * - Medical
     - ``DVZ_MEDICAL``
     - Contract allowance plus the cash input.
   * - Staff welfare
     - ``DVZ_WELFARE``
     - Enter the approved cash amount.
   * - Notice period
     - ``DVZ_NOTICE``
     - Cash input plus ``DVZ_NOTICE_DAYS`` × salary base ÷ days divisor.
   * - Air ticket
     - ``DVZ_AIR_TICKET``
     - Contract allowance plus the cash input.

Cash inputs add to calculated quantities and recurring amounts. To pay only a
manually calculated leave/OT/notice amount, enter its monetary input and leave
the corresponding quantity input at zero. To calculate it from days/hours,
enter the quantity and leave the monetary input at zero. Do not enter the same
payment in both places.

There are 18 native input definitions: 15 earning amounts plus the three
day/hour quantities. PF codes identify salary rules only; PF has no Other
Inputs and is calculated from the employment version's configured base, rates
and caps.

Use positive earning inputs. The PF employee rule applies its own negative
deduction sign. Payment approval remains the existing payslip review and
confirmation process; this module adds no separate payment approval screen.

4. Worked examples
------------------

The following are illustrative company settings, not prescribed policy rates.

**Net salary with PF:** version wage 10,000; fuel allowance 500; employee PF 1%
of wage; employer PF 1% of wage. Gross is 10,500, employee PF is -100, employee
net is 10,400 and employer PF is 100 outside employee net.

**Overtime:** salary base 12,000; days divisor 30; hours per day 8; OT multiplier
1.5; ``DVZ_OT_HOURS`` = 10; ``DVZ_OT`` = 0. OT is
``10 × 12,000 ÷ 30 ÷ 8 × 1.5 = 750``.

**Leave encashment:** salary base 12,000; days divisor 30;
``DVZ_LEAVE_DAYS`` = 5; ``DVZ_LEAVE_ENCASH`` = 0. Encashment is 2,000. Review and
update the leave entitlement separately; the monetary rule does not deduct
days from Time Off.

5. Review the payslip and existing customizations
-----------------------------------------------

Click **Compute Sheet**, review the native salary computation lines, then use
the existing payroll confirmation workflow. The salary rules and inputs are
ordinary ``om_hr_payroll`` records and can be inspected in the normal screens.

This module calculates cash payroll amounts. It does not create a PF fund
ledger, monthly EOSB provision, leave entitlement accrual, tax exemption,
attendance import, or separate reimbursement workflow. Configure accounting
accounts through your payroll-accounting addon if you use one.

The supplied structure belongs to the database's main company. The 17 new
benefit rules and the separate employer-contribution category are shared
records. For another company, review and copy/configure the native structure
and applicable category/rule records for that company's currency and payroll
configuration.

6. Earlier module release
-------------------------

The previous design used separate benefit types, recurring entries and payment
records. This release uses native payroll structures, salary rules, employment
version values and payslip inputs. If the earlier module contains business data,
the upgrade guard stops the update until that data has been reviewed and
migrated. Keep the original records and a database backup during migration.
