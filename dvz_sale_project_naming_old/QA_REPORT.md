# QA report — 19.0.1.1.0

## Executed

- **79 standalone unittest tests passed.** Run with:
  `python -m unittest discover -s dvz_sale_project_naming/qa -p 'test_*.py' -v`
- All Python sources parsed and bytecode-compiled.
- All XML files parsed for well-formedness. This is not Odoo schema/view validation.
- Manifest version and declared data files checked; explicit `mail` dependency present.
- Both Division menus point to the same model/action; the Orders menu is available to Sales users.
- Division form contains one chatter, list includes activity widget, key fields are tracked.
- No second chatter or new smart buttons added to the SO form.
- Layout tested for all eight screenshot field roles, Division-first order, existing node
  reuse, tag/image widgets, domains/options/context, group/visibility scopes, duplicate
  matches, hidden/nested fields, external labels and repeat-application idempotence.
- Missing/ambiguous/unsupported custom widgets remain in place; helper performs no ORM writes.
- Original `sale.order` business methods compared by Python AST against the supplied
  version 19.0.1.0.0: unchanged. The only added method is `_get_view` for layout.
- `naming.py`, project-creation hooks, salesperson model, project model, division ACL
  and division multi-company rule verified byte-for-byte unchanged from 19.0.1.0.0.
- Final ZIP archive CRC integrity and single-root module structure verified.

## Not executed

Live Odoo installation, upgrade, ORM integration tests, JavaScript/browser rendering,
actual custom/Studio combined-view behavior, real notifications and multi-addon runtime
interactions. The environment has no Odoo registry or PostgreSQL server.

## Included live tests

28 Odoo integration tests are packaged, not run: 19 existing naming/project-generation
tests and 9 tests for division chatter, restricted master writes, activities, views and menus.

## Important limitations

The custom technical field names and combined XML from the user's database are unknown.
Layout selection uses conservative exact-label/type matching. An ambiguous match is not
forced. Offline XML tests cannot establish that every real customization will be matched.
No changes have been made to the user's running server or database.
