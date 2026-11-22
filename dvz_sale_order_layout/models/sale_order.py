from copy import deepcopy

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    dvz_analytic_code_display = fields.Char(
        string="Analytic Code",
        compute="_compute_dvz_analytic_code_display",
        help="Displays the code/name of the analytic account already linked to this Sales Order or its linked project.",
    )

    def _dvz_find_analytic_account(self):
        """Resolve only an existing typed analytic-account relation; never create or guess one."""
        self.ensure_one()
        analytic_model = self.env["account.analytic.account"]
        candidate_fields = (
            "analytic_account_id",
            "account_id",
            "analytic_id",
        )
        for field_name in candidate_fields:
            field = self._fields.get(field_name)
            if (
                field
                and field.type == "many2one"
                and field.comodel_name == "account.analytic.account"
            ):
                account = self[field_name]
                if account:
                    return account

        # If the SO has a single linked project, reuse its existing analytic link.
        project_fields = ("project_id",)
        for field_name in project_fields:
            field = self._fields.get(field_name)
            if field and field.type == "many2one" and field.comodel_name == "project.project":
                project = self[field_name]
                if project:
                    for analytic_field in ("account_id", "analytic_account_id"):
                        pfield = project._fields.get(analytic_field)
                        if (
                            pfield
                            and pfield.type == "many2one"
                            and pfield.comodel_name == "account.analytic.account"
                        ):
                            account = project[analytic_field]
                            if account:
                                return account
        return analytic_model.browse()

    def _compute_dvz_analytic_code_display(self):
        for order in self:
            account = order._dvz_find_analytic_account()
            if not account:
                order.dvz_analytic_code_display = False
                continue
            # Prefer an actual code field if installed; otherwise the analytic account name
            # is the visible identifier in standard Odoo analytic-account setups.
            if "code" in account._fields and account.code:
                order.dvz_analytic_code_display = account.code
            else:
                order.dvz_analytic_code_display = account.name

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type not in ("form", "list", "tree"):
            return arch, view
        arch = deepcopy(arch)

        # Rename the displayed label only. The underlying amount_untaxed value
        # and all accounting computations remain untouched.
        for node in arch.xpath(".//field[@name='amount_untaxed']"):
            node.set("string", "VAT")

        # Replace the old Project Code display in both form and list architectures.
        for old_project_code in arch.xpath(".//field[@name='dvz_project_code']"):
            parent = old_project_code.getparent()
            if parent is not None:
                parent.remove(old_project_code)

        if view_type in ("list", "tree"):
            # Avoid brittle inheritance selectors against Studio/customized views:
            # update the final combined architecture only when anchors exist.
            # Hide an older duplicate Department/Division occurrence before Salesperson,
            # but retain the Department occurrence after user_id.
            user_nodes = arch.xpath(".//field[@name='user_id']")
            if user_nodes:
                user_node = user_nodes[0]
                parent = user_node.getparent()
                siblings = list(parent)
                user_index = siblings.index(user_node)
                for node in arch.xpath(".//field[@name='dvz_division_id']"):
                    if node.getparent() is parent and siblings.index(node) < user_index:
                        node.set("column_invisible", "True")

            # Insert SO Date and Expiration Date immediately after Creation Date.
            create_nodes = arch.xpath(".//field[@name='create_date']")
            if create_nodes:
                anchor = create_nodes[0]
                parent = anchor.getparent()
                siblings = list(parent)
                pos = siblings.index(anchor) + 1
                existing = {n.get("name") for n in arch.xpath(".//field")}
                for fname, label in (("date_order", "SO Date"), ("validity_date", "Expiration Date")):
                    if fname not in existing:
                        from lxml import etree
                        node = etree.Element("field", name=fname, string=label, optional="show")
                        parent.insert(pos, node)
                        pos += 1

            # Replace the Project Code display with Analytic Code after Department.
            if not arch.xpath(".//field[@name='dvz_analytic_code_display']"):
                anchors = arch.xpath(".//field[@name='dvz_division_id']")
                if not anchors:
                    anchors = arch.xpath(".//field[@name='user_id']")
                if anchors:
                    from lxml import etree
                    anchor = anchors[-1]
                    parent = anchor.getparent()
                    pos = list(parent).index(anchor) + 1
                    parent.insert(pos, etree.Element(
                        "field", name="dvz_analytic_code_display",
                        string="Analytic Code", optional="show"
                    ))

        return arch, view
