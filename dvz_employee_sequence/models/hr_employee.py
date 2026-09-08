# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    dvz_employee_code = fields.Char(
        string="Employee Code",
        copy=False,
        readonly=True,
        index=True,
        help="Automatically generated on creation - format: first 3 "
             "letters of the employee's Department (uppercase) + the "
             "2-digit year + a running sequence number, separated by "
             "dashes, e.g. ENG-26-001. If no Department is set at "
             "creation time, 'GEN' (General) is used instead.",
    )

    def _dvz_generate_employee_code(self, vals):
        department_id = vals.get("department_id")
        dept_code = "GEN"
        if department_id:
            department = self.env["hr.department"].browse(department_id)
            # Strip anything that isn't a letter before taking the first
            # 3 characters, so department names starting with punctuation
            # or numbers still produce a sensible 3-letter code.
            letters_only = "".join(ch for ch in department.name if ch.isalpha())
            if letters_only:
                dept_code = letters_only[:3].upper()

        year_2digit = str(date.today().year)[-2:]
        running_number = self.env["ir.sequence"].next_by_code("hr.employee.dvz.code") or "000"

        return f"{dept_code}-{year_2digit}-{running_number}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("dvz_employee_code"):
                vals["dvz_employee_code"] = self._dvz_generate_employee_code(vals)
        return super().create(vals_list)
