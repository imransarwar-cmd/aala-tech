# -*- coding: utf-8 -*-
{
    "name": "CRM Team Leader Visibility",
    "version": "19.0.1.0.0",
    "summary": "Adds a 'Team Leader' role that sees their whole team's "
                "leads - on top of Odoo's existing Salesperson (own "
                "leads only) and Sales Manager (everything) roles.",
    "description": """
CRM Team Leader Visibility
===========================
Odoo's CRM already has two visibility levels built in, out of the box:

- "Sales / My Pipeline" (sales_team.group_sale_salesman): a regular
  salesperson sees only THEIR OWN leads.
- "Sales / Administrator" (sales_team.group_sale_manager): sees EVERY
  lead across every Sales Team - this is your "Head" role, nothing
  extra needed, just assign this native group.

What's missing natively is a middle tier: someone who should see every
lead belonging to their OWN Sales Team (every member's leads, not just
their own), but NOT other teams' leads. This module adds exactly that
as a new group, "CRM: Team Leader".

HOW TO ASSIGN ROLES (Settings > Users > open a user > Sales section):
- Salesperson (sees own leads only): "Sales / My Pipeline" (this is
  usually already the default for regular users).
- Team Leader (sees their whole team's leads): "Sales / My Pipeline"
  AND "CRM: Team Leader" (Settings > Users, under a "Sales" or similar
  section once this module is installed - both checked).
- Head (sees every team): "Sales / Administrator" (this already implies
  full visibility, no need to also check Team Leader).

IMPORTANT: "their own team" is decided by Sales Team's own Team Leader
field, not just team membership - a user only gets the wider visibility
for a team if THEY are set as that specific crm.team's "Team Leader"
(the team's own user_id field), under CRM > Configuration > Sales
Teams > (open a team) > Team Leader.
    """,
    "author": "Genius Valley",
    "category": "Sales/CRM",
    "license": "OPL-1",
    "depends": ["crm", "sales_team"],
    "data": [
        "security/security.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
