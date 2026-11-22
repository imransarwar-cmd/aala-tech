# 19.0.1.1.0

- Place the existing Division field first in a separate Project Information section.
- Group recognized existing main-form project custom fields without creating duplicates.
- Move naming controls into a separate Project Naming section under Other Info.
- Add Division / Department Group By for quotations and sales orders.
- Add Sales > Orders > Divisions / Departments; retain the Configuration shortcut.
- Add standard chatter, activity support and tracking to existing division records.
- Preserve master-edit ACLs, company restrictions and existing project-naming business logic.
- Include conservative XML-layout tests and additional unexecuted Odoo integration tests.

# Changelog

## 19.0.1.0.0

- Added a separate company-specific Division / Department master.
- Added an explicitly configured salesperson abbreviation to internal users.
- Added SO reference/suffix inputs and code/name previews after Salesperson.
- Default name: SO number || salesperson-division-reference[-suffix].
- Added optional code-only names and immutable confirmation naming snapshots.
- Extended native project creation without adding another project-creation rule.
- Preserved native project links and smart buttons; no new smart buttons.
- Included standalone QA and unexecuted Odoo integration tests.

## 19.0.1.2.0
- Reuse `aala_rest_api.system.master` in Sales Orders.
- Add Department on System Master and hide its legacy Division field.
- Filter Sales Order System by selected Department.
- Add Systems menu directly after Departments under Sales > Orders.
- Rename department code label to Abbreviation and show Department dropdown by name only.
