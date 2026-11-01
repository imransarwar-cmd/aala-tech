from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _timesheet_create_project_prepare_values(self):
        values = super()._timesheet_create_project_prepare_values()
        values.update(self.order_id._dvz_project_naming_values())
        return values

    def _timesheet_create_project(self):
        # Core remains responsible for project/template/task creation and native links.
        project = super()._timesheet_create_project()
        # Core can append product/template text after prepare_values; enforce the exact format.
        if project and not project.is_template:
            values = self.order_id._dvz_project_naming_values()
            if values:
                project._dvz_apply_order_naming(self.order_id)
        return project
