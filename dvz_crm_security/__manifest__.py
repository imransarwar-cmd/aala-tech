# -*- coding: utf-8 -*-
{
    "name": "CRM Team Leader Visibility",
    "version": "19.0.1.0.0",
    "summary": "Three explicit CRM visibility roles: Salesperson (own "
                "leads), Team Leader (own team's leads), Head (every "
                "team).",
    "description": """
CRM Visibility Roles
=====================
Adds three explicit, self-contained groups for crm.lead visibility -
each with its own clear record rule, so nothing depends on native Odoo
group configuration you can't see in this module:

- "CRM: Salesperson" - sees only leads where THEY are the Salesperson.
- "CRM: Team Leader" - sees their own leads (implies Salesperson above)
  PLUS every lead belonging to any Sales Team where they are set as
  that team's own Team Leader (crm.team's Team Leader field - NOT just
  team membership).
- "CRM: Head" - sees every lead, every team, no restriction. Also
  implies the native "Sales / Administrator" group for full CRM admin
  capability alongside the visibility (see the comment in
  security/security.xml if you'd rather Head only get the visibility
  without those extra admin permissions).

HOW TO ASSIGN ROLES (Settings > Users > open a user > Sales section,
once this module is installed):
- Salesperson: check "CRM: Salesperson".
- Team Leader: check "CRM: Team Leader" (this already includes
  Salesperson access, don't need to check both).
- Head: check "CRM: Head".

IMPORTANT: Team Leader visibility is decided by Sales Team's own Team
Leader field, not just team membership - a user only gets the wider
visibility for a team if THEY are set as that specific crm.team's "Team
Leader" (under CRM > Configuration > Sales Teams > open a team > Team
Leader).
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
