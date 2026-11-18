from odoo import _
from odoo.exceptions import UserError


def pre_init_hook(env):
    """Require the metadata rename when an earlier addon already owns the data."""
    env.cr.execute(
        """
        SELECT DISTINCT module.name
          FROM ir_model_data AS data
          JOIN ir_model AS model
            ON data.model = 'ir.model' AND data.res_id = model.id
          JOIN ir_module_module AS module ON module.name = data.module
         WHERE model.model = %s
           AND module.name != %s
           AND module.state IN ('installed', 'to upgrade', 'to install')
        """,
        ('dvz.project.delivery.cost.line', 'dvz_project_delivery_cost'),
    )
    if env.cr.fetchall():
        raise UserError(_(
            'An existing delivery costing addon already owns your records. '
            'Run the included scripts/rename_existing_module.py with Odoo\'s '
            '--pre-upgrade-scripts option and upgrade dvz_project_delivery_cost. '
            'Follow the existing-installation steps in README.md.'
        ))
