"""Protect existing v1 custom records during the native-only redesign.

Fresh installations do not run this migration. No v1 payroll history is
silently discarded or converted into an unapproved native input.
"""
from odoo.exceptions import UserError


def migrate(cr, version):
    if not version:
        return
    occupied = []
    for table in ('dvz_benefit_recurring', 'dvz_benefit_payment', 'dvz_benefit_snapshot'):
        cr.execute('SELECT to_regclass(%s)', [table])
        if cr.fetchone()[0]:
            # Fixed internal table names; no user-supplied SQL identifier.
            cr.execute('SELECT EXISTS (SELECT 1 FROM %s)' % table)
            if cr.fetchone()[0]:
                occupied.append(table)
    if occupied:
        raise UserError(
            'The previous benefits module contains employee benefits, payments or payroll history. '
            'Upgrade has stopped before changing those records. Keep the previous version active '
            'until its records have been explicitly migrated to native payroll fields and inputs. '
            'Do not uninstall it to bypass this safeguard. Tables with records: ' + ', '.join(occupied)
        )
    # Hide the former custom-model screens before their fields/models disappear.
    # The new release uses different XML IDs and only native payroll screens.
    cr.execute('''UPDATE ir_ui_view SET active = FALSE WHERE id IN (
        SELECT res_id FROM ir_model_data
        WHERE module = 'dvz_employee_benefits' AND model = 'ir.ui.view'
    )''')
    cr.execute('''UPDATE ir_ui_menu SET active = FALSE WHERE id IN (
        SELECT res_id FROM ir_model_data
        WHERE module = 'dvz_employee_benefits' AND model = 'ir.ui.menu'
    )''')
