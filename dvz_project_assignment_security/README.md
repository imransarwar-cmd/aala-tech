# Odoo 19 — Native Project Manager, Assignment Security and Project Search

Technical module: `dvz_project_assignment_security`  
Version: `19.0.1.1.0`  
Deployment: self-hosted Odoo 19. Depends on the native Project app only.

**This replaces version 19.0.1.0.0 of the SAME module. Upgrade it; do not uninstall.**
The existing SO Project Naming, SO–Invoice Linker and Internal Transfer modules do not need to be replaced.

## What changed

The existing Project access role is displayed as **Project Manager** instead of
**Administrator**. Its original external ID, `project.group_project_manager`, and
memberships are retained; no duplicate manager role is created. The choices are
No / User / Project Manager / HOD - All Projects. The native role's model-level
management/configuration permissions remain unchanged; assignment record rules
still limit which project/task records it can access.

The **Assigned Project Users** field has been removed from the project form.
Use only the existing **Project Manager** field (`project.project.user_id`) for
whole-project assignment, and the native task **Assignees** for individual tasks.
No new assignment field, assignment wizard, or smart button is added.

The standard project search field and project selection dropdowns support
case-insensitive, all-parts name search. The naming format itself is unchanged.

## Access policy

| Situation | Project access | Task access |
| --- | --- | --- |
| Person selected in the existing Project Manager field | That project | All current and future tasks in that project, including unassigned tasks and tasks assigned to others |
| Person assigned to a task but not selected as Project Manager | Readable parent project for task navigation | Only their assigned tasks; not sibling tasks |
| No assignment | No corresponding project | No corresponding tasks |
| HOD - All Projects | All projects allowed by company and other applicable global rules | All project-linked tasks in those companies |

The visibility test is the same for ordinary Users and Project Managers. A role
alone does not assign any project. Selecting a Project User as the responsible
person does not promote them to the Project Manager role or grant extra model ACLs.

HODs and Settings Administrators can change the Project Manager field. Other
managers can create a project for themselves (native ACLs permitting), but cannot
reassign a project or give themselves access by changing task/project links.
The form remains read-only for manager reassignment by non-HODs. This is intentional.

Settings Administrators and sudo/superuser operations remain administrative
exceptions. Do not give those privileges to restricted managers. HODs do not gain
access to other people's project-less personal tasks. Company membership is never
expanded by an assignment, and archived records still require the native Archived
filter/context.

Task-only access includes a readable parent project header and its ordinary fields;
it is NOT a field-by-field confidentiality layer. The full-project dashboard,
project updates and unrelated tasks remain restricted.

## Example matching the screenshot

Project name: `S00716 || ASD-TE-4128-VO`  
Project Manager: `Asad Aslam`

Asad can access that project and all its tasks. His Project access setting may be
Project Manager. Other users see only tasks individually assigned to them, unless
they are the native manager of another project or have HOD/admin privileges.

**The native Project Manager field holds one person.** Several whole-project
assignees cannot be represented in that single field. Other contributors should
be assigned to their own tasks. Do not expect the removed multi-user field to
continue granting access.

## Search examples

In Projects, enter a term and select **Project (All Name Parts)**. The same
matching is used by normal project dropdowns using Odoo's name_search mechanism.
The existing Project Manager search/filter remains available for searching by
responsible person's name.

For `S00716 || ASD-TE-4128-VO`, all of these match:

| Input | Meaning |
| --- | --- |
| `S00716` or `00716` | SO number or a fragment |
| `ASD` | Salesperson abbreviation present in the name |
| `TE` | Division code present in the name |
| `4128` | Project reference |
| `VO` | Suffix present in the name |
| `ASD 4128` or `4128 ASD` | Both parts in either order |
| `S00716 TE VO` | Three parts together |
| `ASD-TE-4128-VO` | Complete project code |
| `S00716 || ASD-TE-4128-VO` | Complete project name |

Every entered part must occur in the same project name. Spaces and common code
separators are treated as separators. Matching is by substring, not fuzzy spelling:
`VO` (letter O) and `V0` (zero) are different. Type the suffix exactly as stored.
A project with suffix `V0` is searchable by `V0`.

Only stored project-name text is searched. A code or SO number omitted from the
name is not invented or retrieved from inaccessible SO records. No projects are
renamed or backfilled by this update. The existing naming module can continue
using the full SO-inclusive name shown above.

Exact comparisons and unrelated search operators retain native semantics.
Contains/not-contains on display_name use the all-parts behavior. Direct custom
filters on the underlying `name` field retain native Odoo behavior. Other apps
with their own custom selectors/search handlers may need separate adaptation.
Search does not use sudo, bypass record rules, override company filters, or reveal
unassigned projects. Saved filters and other domains still intersect with results.

## Upgrade from 19.0.1.0.0

1. Back up the database **and filestore**, and test on a staging copy. Keep a
   Settings Administrator account available. Review any projects with multiple
   old Assigned Project Users or a different existing Project Manager before deployment.
2. Replace the existing `dvz_project_assignment_security` directory with the one
   inside this ZIP, in your configured custom-addons path. Do not keep two copies
   of the same technical module in different addons paths.
3. Restart Odoo and **upgrade the existing module** from Apps (remove the default
   Apps filter if needed). A restart or Update Apps List alone is not an upgrade.
4. Refresh the browser and sign out/in with a non-admin test user. Confirm the
   role label, native Project Manager assignment, task visibility and search.
5. Review the upgrade report described below and correct any flagged assignments
   as HOD or Settings Administrator.

Command-line alternative; replace paths and database name with your actual values
and use your deployment's maintenance procedure so no duplicate server process
serves the same database during the upgrade:

```bash
/path/to/odoo-bin -c /path/to/odoo.conf -d YOUR_DATABASE \
  -u dvz_project_assignment_security --stop-after-init
```

For a fresh installation only, use `-i` instead of `-u`. The versioned conversion
runs on upgrade from an older version, not on a fresh install.

## Safe conversion of the removed field

During upgrade:

| Old data | Conversion |
| --- | --- |
| Project Manager empty; exactly one eligible old assigned user | Set that user as the native Project Manager |
| Native manager already equals the sole old assigned user | No change |
| Native manager already set to someone else | Keep the existing manager; flag for review |
| Several old assigned users with no native manager | Do not choose arbitrarily; flag for review |
| Sole old user archived, external, or without project-company access | Do not assign; flag for review |

Thus, the screenshot's blank native manager plus one eligible Asad Aslam
assignment is the automatic-conversion case. This is conditional on the actual
stored values; the screenshots alone do not verify account eligibility.

The conversion never changes task assignees, role memberships, allowed companies,
project names, or an already populated manager field. Archived projects are
included. Old multi-user data remains **hidden, administrator-only and read-only**
for upgrade audit; it grants **no access**, and new writes to it are rejected.
The backend compatibility storage is retained deliberately rather than deleting
historical assignments. No normal-user form displays it.

When legacy data exists, an administrator-only CSV attachment is created:
`DVZ_Project_Manager_Migration_19.0.1.1.0.csv`.

A Settings Administrator can enable developer mode and find it under
**Settings → Technical → Database Structure → Attachments**, searching by the
filename. Its related model is `ir.module.module`, its related record is this
module, and it is not public. The attachment ID and review counts are also logged.
Inspect `review_*` rows. Previously selected extra users lose whole-project access
unless they are now the native manager; individual task assignments still work.
Custom ACLs granting broader access to technical attachments/module records must
be reviewed separately.

## Staging acceptance checks

Use ordinary User, Project Manager, HOD and Settings Administrator test accounts.
Create Project A with Manager A, Project B with Manager B, and one task in Project
B assigned to Manager A. Manager A must see Project A's tasks and only their own
task in Project B. Direct reads/searches of other Project B tasks must fail or
return nothing. HOD must see both projects within allowed companies.

Change Project Manager A to B as HOD and verify access revocation without clearing
record-rule caches. Confirm task-only users cannot reassign the native manager,
move tasks into hidden projects, or open a full-project dashboard.

Search each code part and mixed-order combinations as Manager A, then search for
an unassigned project's exact name: it must remain hidden. Test both the Projects
search and a native project dropdown. Check multi-company and archived filters.

Confirm a new SO using your existing project creation/naming automation. Verify
project/task creation and name generation still work for the roles running it.
This update does not change that automation and does not assign a project based
on the salesperson abbreviation. A salesperson and Project Manager are distinct.

## Test status and limitations

The packaged `QA_REPORT.json` and `qa/standalone_results.txt` record the executed
offline tests. Run them from the module folder with:

```bash
python -m unittest discover -s qa -p 'test_*.py' -v
```

The offline tests cover pure domains/search, upgrade decision logic, a fake ORM
upgrade workflow, package structure and Python/XML parsing. They are **not live
Odoo installation, migration, SQL-rule compilation, browser, or permissions tests**.
Odoo and PostgreSQL are unavailable in this build environment. Integration tests
are included under `tests/` but have not been executed here.

On a disposable staging database, an administrator can run the live suite:

```bash
/path/to/odoo-bin -c /path/to/staging.conf -d STAGING_DATABASE \
  -u dvz_project_assignment_security --test-enable \
  --test-tags /dvz_project_assignment_security --stop-after-init
```

Other installed record rules may further restrict results. Native portal sharing,
email notifications, followers, external links, Documents, Timesheets, accounting,
attachments outside this migration report and other custom dashboards are not a
complete security audit of this database. Existing report-scope guards are retained;
review all installed add-ons and actual user combinations on staging.

## Primary upstream references

Verified against Odoo's public 19.0 source on 2026-11-01:

- Native role and record rules: https://raw.githubusercontent.com/odoo/odoo/19.0/addons/project/security/project_security.xml
- Native manager field and project model: https://raw.githubusercontent.com/odoo/odoo/19.0/addons/project/models/project_project.py
- Native project form/search view: https://raw.githubusercontent.com/odoo/odoo/19.0/addons/project/views/project_project_views.xml
- display_name and name_search implementation: https://raw.githubusercontent.com/odoo/odoo/19.0/odoo/orm/models.py
- Upgrade script convention: https://raw.githubusercontent.com/odoo/documentation/19.0/content/developer/reference/upgrades/upgrade_scripts.rst
- Technical module ACL: https://raw.githubusercontent.com/odoo/odoo/19.0/odoo/addons/base/security/ir.model.access.csv

The delivered module is custom code, not an official Odoo module or an Odoo-certified
security implementation. Actual installation and acceptance testing remain required.
