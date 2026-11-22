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

        if view_type == "form":
            # The original dvz_sale_project_naming module defines Department as
            # sale.order.dvz_division_id (Many2one) and the System field as "system".
            # Preserve that existing field and position it immediately before System.
            from lxml import etree

            department_field = (
                "dvz_department_ids"
                if "dvz_department_ids" in self._fields
                else "dvz_division_id"
            )
            # Remove only the alternative/obsolete department field from the final view.
            alternative_field = (
                "dvz_division_id"
                if department_field == "dvz_department_ids"
                else "dvz_department_ids"
            )
            for old_node in arch.xpath(".//field[@name='%s']" % alternative_field):
                old_parent = old_node.getparent()
                if old_parent is not None:
                    old_parent.remove(old_node)

            department_nodes = arch.xpath(
                ".//field[@name='%s']" % department_field
            )
            department_node = department_nodes[0] if department_nodes else etree.Element(
                "field",
                name=department_field,
                string="Department",
                widget="many2many_tags" if department_field == "dvz_department_ids" else "many2one",
            )
            for duplicate in department_nodes[1:]:
                duplicate_parent = duplicate.getparent()
                if duplicate_parent is not None:
                    duplicate_parent.remove(duplicate)

            current_parent = department_node.getparent()
            if current_parent is not None:
                current_parent.remove(department_node)

            # Actual System field in dvz_sale_project_naming is named "system".
            system_nodes = arch.xpath(".//field[@name='system']")
            if system_nodes:
                system_node = system_nodes[0]
                system_parent = system_node.getparent()
                system_parent.insert(
                    list(system_parent).index(system_node),
                    department_node,
                )
            else:
                # Safe fallback if a customization removed the System field.
                user_nodes = arch.xpath(".//field[@name='user_id']")
                if user_nodes:
                    user_node = user_nodes[0]
                    user_parent = user_node.getparent()
                    user_parent.insert(
                        list(user_parent).index(user_node) + 1,
                        department_node,
                    )

        if view_type in ("list", "tree"):
            # Build the requested optional list columns in a deterministic order:
            # Analytic Code first, Department immediately after it.
            from lxml import etree

            # Detect the actual Department field installed in this database.
            department_field = (
                "dvz_department_ids"
                if "dvz_department_ids" in self._fields
                else "dvz_division_id"
            )

            # Remove old/duplicate Department and Analytic Code nodes so the final
            # architecture contains one copy in the requested position.
            for field_name in (
                "dvz_department_ids",
                "dvz_division_id",
                "dvz_analytic_code_display",
                "dvz_project_code",
            ):
                for node in arch.xpath(".//field[@name='%s']" % field_name):
                    node_parent = node.getparent()
                    if node_parent is not None:
                        node_parent.remove(node)

            user_nodes = arch.xpath(".//field[@name='user_id']")
            if user_nodes:
                anchor = user_nodes[0]
                parent = anchor.getparent()
                insert_at = list(parent).index(anchor) + 1
                analytic_node = etree.Element(
                    "field",
                    name="dvz_analytic_code_display",
                    string="Analytic Code",
                    optional="hide",
                )
                department_node = etree.Element(
                    "field",
                    name=department_field,
                    string="Department",
                    widget="many2many_tags" if department_field == "dvz_department_ids" else "many2one",
                    optional="hide",
                )
                parent.insert(insert_at, analytic_node)
                parent.insert(insert_at + 1, department_node)

            # Ensure all requested date fields are present in the list but hidden
            # by default in the optional-columns menu.
            def keep_or_add_optional(field_name, label, anchor_name=None):
                nodes = arch.xpath(".//field[@name='%s']" % field_name)
                if nodes:
                    node = nodes[0]
                    for duplicate in nodes[1:]:
                        dup_parent = duplicate.getparent()
                        if dup_parent is not None:
                            dup_parent.remove(duplicate)
                    node.set("string", label)
                    node.set("optional", "hide")
                    return node

                node = etree.Element(
                    "field",
                    name=field_name,
                    string=label,
                    optional="hide",
                )
                if anchor_name:
                    anchors = arch.xpath(".//field[@name='%s']" % anchor_name)
                    if anchors:
                        anchor_node = anchors[0]
                        anchor_parent = anchor_node.getparent()
                        anchor_parent.insert(
                            list(anchor_parent).index(anchor_node) + 1,
                            node,
                        )
                        return node

                # Fallback: append to the main list container.
                containers = arch.xpath(".//list")
                if containers:
                    containers[0].append(node)
                return node

            keep_or_add_optional("create_date", "Creation Date", "name")
            keep_or_add_optional("date_order", "SO Date", "create_date")
            keep_or_add_optional("validity_date", "Expiration Date", "date_order")

            # Rename the existing untaxed amount column to VAT only; value unchanged.
            for node in arch.xpath(".//field[@name='amount_untaxed']"):
                node.set("string", "VAT")
                node.set("optional", "hide")

            # Keep Analytic Code before Department after the salesperson.
            # Other existing columns are retained.
        return arch, view
