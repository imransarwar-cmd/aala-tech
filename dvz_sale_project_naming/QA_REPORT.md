# Verification report — 19.0.1.0.0

## Executed in the build environment

- Standalone tests: **32 run, 32 passed**.
- Naming helper tests: 20.
- Package / static structure checks: 12.
- Python syntax parsing and bytecode compilation: **passed (12 files)**.
- XML parsing: **passed (5 files)**.
- Manifest data paths exist; ACL CSV and company rule inspected.
- No custom smart buttons and no explicit new project-create action in the add-on.

The count above refers to standalone test methods, not live Odoo workflows.
Structural security checks do not replace live access-rights tests.

## Not executed

No Odoo Python runtime or PostgreSQL instance is installed in this environment.
**Live Odoo installation, registry/view validation, posting/ORM transactions, access
rules, actual SO confirmation, automation execution, project template duplication,
and browser behavior were not run.**

19 Odoo integration test methods are included in `tests/test_sale_project_naming.py`.
They have been syntax-checked only; their runtime results are unknown.

The server's existing automated action and other installed custom modules were not
available for inspection. Test this add-on on a staging copy before production use.
No change has been made to the user's server or database.

## Standalone command output

```text
test_blank_code_no_partial_name (__main__.TestNaming.test_blank_code_no_partial_name) ... ok
test_code_only (__main__.TestNaming.test_code_only) ... ok
test_combined_name (__main__.TestNaming.test_combined_name) ... ok
test_false_suffix (__main__.TestNaming.test_false_suffix) ... ok
test_integer_reference_not_silently_accepted (__main__.TestNaming.test_integer_reference_not_silently_accepted) ... ok
test_invalid_division_separator (__main__.TestNaming.test_invalid_division_separator) ... ok
test_invalid_markup (__main__.TestNaming.test_invalid_markup) ... ok
test_invalid_reference (__main__.TestNaming.test_invalid_reference) ... ok
test_invalid_spaces (__main__.TestNaming.test_invalid_spaces) ... ok
test_invalid_suffix (__main__.TestNaming.test_invalid_suffix) ... ok
test_leading_zeroes (__main__.TestNaming.test_leading_zeroes) ... ok
test_length_limits (__main__.TestNaming.test_length_limits) ... ok
test_missing_division (__main__.TestNaming.test_missing_division) ... ok
test_missing_order_number (__main__.TestNaming.test_missing_order_number) ... ok
test_missing_reference (__main__.TestNaming.test_missing_reference) ... ok
test_missing_salesperson (__main__.TestNaming.test_missing_salesperson) ... ok
test_optional_suffix (__main__.TestNaming.test_optional_suffix) ... ok
test_reference_separators (__main__.TestNaming.test_reference_separators) ... ok
test_requested_example (__main__.TestNaming.test_requested_example) ... ok
test_trim_and_uppercase (__main__.TestNaming.test_trim_and_uppercase) ... ok
test_acl_no_portal_or_global_write (__main__.TestPackage.test_acl_no_portal_or_global_write) ... ok
test_field_placed_after_salesperson (__main__.TestPackage.test_field_placed_after_salesperson) ... ok
test_manifest_files_exist (__main__.TestPackage.test_manifest_files_exist) ... ok
test_module_imports_exist (__main__.TestPackage.test_module_imports_exist) ... ok
test_multi_company_rule (__main__.TestPackage.test_multi_company_rule) ... ok
test_native_project_creation_not_reimplemented (__main__.TestPackage.test_native_project_creation_not_reimplemented) ... ok
test_native_project_hooks_call_super (__main__.TestPackage.test_native_project_hooks_call_super) ... ok
test_no_invoice_or_accounting_model_override (__main__.TestPackage.test_no_invoice_or_accounting_model_override) ... ok
test_no_new_smart_buttons (__main__.TestPackage.test_no_new_smart_buttons) ... ok
test_odoo19_constraint_api (__main__.TestPackage.test_odoo19_constraint_api) ... ok
test_python_syntax (__main__.TestPackage.test_python_syntax) ... ok
test_xml_parses (__main__.TestPackage.test_xml_parses) ... ok

----------------------------------------------------------------------
Ran 32 tests in 0.020s

OK
```
