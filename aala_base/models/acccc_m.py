class AccountMove(models.Model):
    """Inherits from the account.move model for adding the depreciation
    field to the account"""
    _inherit = 'account.move'

    has_due = fields.Boolean(string='Has due')
    is_warning = fields.Boolean(string='Is warning')
    due_amount = fields.Float(string="Due Amount",
                              related='partner_id.due_amount')