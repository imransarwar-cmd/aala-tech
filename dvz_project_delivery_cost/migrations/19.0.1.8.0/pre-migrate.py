"""Preserve per-analytic selections before the Boolean becomes computed."""

import json


SNAPSHOT_KEY = (
    'dvz_project_delivery_cost.legacy_enabled_analytic_ids_19_0_1_8_0'
)


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = 'account_analytic_account'
               AND column_name = 'dvz_project_delivery_costing'
        )
        """
    )
    if not cr.fetchone()[0]:
        return

    # Do not filter by active: archived selections must survive the upgrade.
    cr.execute(
        """
        SELECT id
          FROM account_analytic_account
         WHERE dvz_project_delivery_costing IS TRUE
         ORDER BY id
        """
    )
    legacy_ids = [row[0] for row in cr.fetchall()]
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_date, write_date)
             VALUES (%s, %s, NOW(), NOW())
        ON CONFLICT (key) DO NOTHING
        """,
        (SNAPSHOT_KEY, json.dumps(legacy_ids)),
    )
