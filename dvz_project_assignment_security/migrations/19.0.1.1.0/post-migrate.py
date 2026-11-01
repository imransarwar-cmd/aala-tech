from odoo import SUPERUSER_ID, api
from odoo.addons.dvz_project_assignment_security.migration import migrate_legacy_assignments


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    migrate_legacy_assignments(env)
