# Changelog

## 19.0.1.1.0 — 2026-11-01

- Rename the existing native Project / Administrator role to Project Manager,
  retaining its XML ID and memberships. Keep HOD - All Projects.
- Remove Assigned Project Users from the form and all access domains.
- Use only native Project Manager for whole-project access; keep native task
  Assignees for task-only access.
- Preserve former multi-user data as admin-only read-only compatibility storage.
- Add versioned safe single-user conversion and a private administrator CSV audit;
  do not overwrite an existing manager or choose between multiple old users.
- Add case-insensitive all-name-parts search to the standard Projects search
  field and native project dropdowns, with existing domains and rules retained.
- Restore the native role label on uninstall if it has not been customized again.
- Expand offline tests and included (unexecuted) live Odoo regression tests.

## 19.0.1.0.0 — Previous release

- Initial assignment security with the native Project Manager plus a separate
  multi-user Assigned Project Users field; HOD access and global rule guards.
- This release supersedes the former multi-user assignment workflow.
