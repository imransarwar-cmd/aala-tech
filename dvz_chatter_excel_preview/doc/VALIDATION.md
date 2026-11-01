# Validation record

Build: 19.0.1.0.0

## Executed

- 34 Python workbook-parser unit tests: PASS (genuine OOXML and CSV fixtures).
- 12 Python tests of the actual ORM method with record/environment test doubles: PASS.
- 14 JavaScript tests of actual helper, attachment-patch and dialog methods with service/lifecycle test doubles: PASS.
- Python compilation: PASS.
- JavaScript module syntax checks: PASS.
- XML well-formedness: PASS.
- CSS parsing: PASS.
- Manifest asset-path verification: PASS.
- Runtime model call scan for sudo/write/create/unlink/SQL execution: no such calls.
- ZIP integrity: validated when packaging.

46 Python + 14 JavaScript = 60 offline tests. Parameterized subcases are not counted as additional test methods.

## Not executed / not claimed

- Odoo registry/module installation or upgrade.
- Live ACL or record-rule behavior.
- Owl template compilation/rendering.
- Browser interactions within a running Odoo web client.
- Community/Enterprise build-specific integration.
- The 8 database integration tests supplied under `tests/`.

These require a staging Odoo 19 instance. Offline test doubles check implementation logic, not Odoo's real security subsystem. No change was made to any user's Odoo database or server.

## Toolchain

Python 3.13.5; openpyxl 3.1.5; defusedxml 0.7.1; Node.js 22.16.0.

Python/JavaScript test output is included alongside this file.
