from odoo import models
from odoo.fields import Domain

from ..policy import HOD_GROUP, SYSTEM_GROUP, assignment_domain


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _dvz_assignment_rule_domain(self, scope, company_ids):
        """Private ir.rule helper; called with the current user, never client IDs.

        Do not replace the domains with search(...).ids: ir.rule caches domains.
        A data-dependent ID list would make assignment changes stale.
        """
        self.ensure_one()
        domain = assignment_domain(
            self.id, scope, company_ids,
            portal=self.share,
            hod=self.has_group(HOD_GROUP),
            system=self.has_group(SYSTEM_GROUP),
        )
        # any! is an internal Odoo 19 operator, allowed through a trusted Domain.
        return Domain(domain, internal=True)

    def _dvz_can_administer_project_assignments(self):
        self.ensure_one()
        return self.env.su or self.has_group(HOD_GROUP) or self.has_group(SYSTEM_GROUP)
