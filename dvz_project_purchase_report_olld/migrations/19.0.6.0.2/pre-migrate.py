"""The Project Profit & Loss dashboard was removed: drop its SQL view.

Odoo normally drops the view when it removes the model, but doing it
explicitly (before the new code loads) avoids any dependency problem with
the dashboard's Estimated Budget field on the analytic account.
"""


def migrate(cr, version):
    cr.execute("DROP VIEW IF EXISTS dvz_project_dashboard CASCADE")
