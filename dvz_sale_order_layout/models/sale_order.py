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
            # Avoid brittle inheritance selectors against Studio/customized views:
            # update the final combined architecture only when anchors exist.
            # Guarantee exactly one visible Department column immediately after Salesperson.
            # The actual Department field is the existing Many2many dvz_department_ids.
            # Remove obsolete dvz_division_id references and insert Department after user_id.
            user_nodes = arch.xpath(".//field[@name='user_id']")
            if user_nodes:
                user_node = user_nodes[0]
                parent = user_node.getparent()
                department_field = (
                    "dvz_department_ids"
                    if "dvz_department_ids" in self._fields
                    else "dvz_division_id"
                )
                for node in arch.xpath(".//field[@name='dvz_division_id'] | .//field[@name='dvz_department_ids']"):
                    node_parent = node.getparent()
                    if node_parent is not None:
                        node_parent.remove(node)
                from lxml import etree
                department_node = etree.Element(
                    "field",
                    name=department_field,
                    string="Department",
                    widget="many2many_tags" if department_field == "dvz_department_ids" else "many2one",
                    optional="show",
                )
                parent.insert(list(parent).index(user_node) + 1, department_node)

            # Ensure the list always contains the three date columns in the requested order.
            # Some Odoo/custom Sales Order trees already contain date_order (labelled
            # "Order Date") but do not contain create_date. Relabel existing date_order
            # and add create_date + validity_date instead of skipping the dates.
            from lxml import etree

            def keep_one_field(field_name):
                nodes = arch.xpath(".//field[@name='%s']" % field_name)
                if not nodes:
                    return None
                first = nodes[0]
                for duplicate in nodes[1:]:
                    parent = duplicate.getparent()
                    if parent is not None:
                        parent.remove(duplicate)
                return first

            create_node = keep_one_field("create_date")
            order_node = keep_one_field("date_order")
            validity_node = keep_one_field("validity_date")

            # Use date_order as the anchor where possible; otherwise place dates
            # after the order number/name column.
            anchor = order_node
            if anchor is None:
                name_nodes = arch.xpath(".//field[@name='name']")
                anchor = name_nodes[0] if name_nodes else None

            if anchor is not None:
                parent = anchor.getparent()
                if parent is not None:
                    index = list(parent).index(anchor)
                    if create_node is None:
                        create_node = etree.Element(
                            "field", name="create_date",
                            string="Creation Date", optional="show"
                        )
                    else:
                        create_node.set("string", "Creation Date")
                    if order_node is None:
                        order_node = etree.Element(
                            "field", name="date_order",
                            string="SO Date", optional="show"
                        )
                    else:
                        order_node.set("string", "SO Date")
                    if validity_node is None:
                        validity_node = etree.Element(
                            "field", name="validity_date",
                            string="Expiration Date", optional="show"
                        )
                    else:
                        validity_node.set("string", "Expiration Date")

                    # Remove date nodes before reinserting in exact sequence.
                    for node in (create_node, order_node, validity_node):
                        node_parent = node.getparent()
                        if node_parent is not None:
                            node_parent.remove(node)

                    parent.insert(index, create_node)
                    parent.insert(index + 1, order_node)
                    parent.insert(index + 2, validity_node)

            # Replace the Project Code display with Analytic Code after Department.
            if not arch.xpath(".//field[@name='dvz_analytic_code_display']"):
                department_field = (
                    "dvz_department_ids"
                    if "dvz_department_ids" in self._fields
                    else "dvz_division_id"
                )
                anchors = arch.xpath(".//field[@name='%s']" % department_field)
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
