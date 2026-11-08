# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s)", (table,))
    row = cr.fetchone()
    return bool(row and row[0])


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def _drop_fks_on_column(cr, table, column):
    cr.execute(
        """
        SELECT DISTINCT c.conname
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
          JOIN unnest(c.conkey) AS k(attnum) ON TRUE
          JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
         WHERE c.contype = 'f'
           AND n.nspname = current_schema()
           AND t.relname = %s
           AND a.attname = %s
        """,
        (table, column),
    )
    for (name,) in cr.fetchall():
        cr.execute('ALTER TABLE "%s" DROP CONSTRAINT IF EXISTS "%s"' % (table, name))
        _logger.info("Dropped FK %s on %s.%s", name, table, column)


def _ensure_cascade_fk(cr, table, column, ref_table, ref_column="id"):
    if not (_table_exists(cr, table) and _column_exists(cr, table, column)):
        return
    _drop_fks_on_column(cr, table, column)
    name = "%s_%s_fkey" % (table, column)
    cr.execute(
        'ALTER TABLE "%s" ADD CONSTRAINT "%s" FOREIGN KEY ("%s") '
        'REFERENCES "%s"("%s") ON DELETE CASCADE'
        % (table, name, column, ref_table, ref_column)
    )
    _logger.info("Created CASCADE FK %s", name)


def _backup_links(cr):
    cr.execute(
        """
        CREATE TABLE IF NOT EXISTS dvz_sale_m2m_emergency_backup (
            order_id bigint PRIMARY KEY,
            legacy_division_id bigint,
            legacy_system_id bigint,
            division_ids bigint[] NOT NULL DEFAULT ARRAY[]::bigint[],
            system_ids bigint[] NOT NULL DEFAULT ARRAY[]::bigint[],
            backed_up_at timestamp without time zone NOT NULL DEFAULT NOW()
        )
        """
    )
    cr.execute("TRUNCATE TABLE dvz_sale_m2m_emergency_backup")

    div_legacy = "so.dvz_division_id" if _column_exists(cr, "sale_order", "dvz_division_id") else "NULL::bigint"
    sys_legacy = "so.system" if _column_exists(cr, "sale_order", "system") else "NULL::bigint"
    div_m2m = "ARRAY[]::bigint[]"
    sys_m2m = "ARRAY[]::bigint[]"
    if _table_exists(cr, "sale_order_dvz_division_rel"):
        div_m2m = "COALESCE((SELECT array_agg(r.division_id ORDER BY r.division_id) FROM sale_order_dvz_division_rel r WHERE r.order_id = so.id), ARRAY[]::bigint[])"
    if _table_exists(cr, "sale_order_dvz_system_rel"):
        sys_m2m = "COALESCE((SELECT array_agg(r.system_id ORDER BY r.system_id) FROM sale_order_dvz_system_rel r WHERE r.order_id = so.id), ARRAY[]::bigint[])"

    cr.execute(
        f"""
        INSERT INTO dvz_sale_m2m_emergency_backup
            (order_id, legacy_division_id, legacy_system_id, division_ids, system_ids)
        SELECT so.id, {div_legacy}, {sys_legacy}, {div_m2m}, {sys_m2m}
          FROM sale_order so
        """
    )
    _logger.info("Backed up %s Sale Orders before FK repair", cr.rowcount)


def post_init_hook(env):
    cr = env.cr
    _backup_links(cr)
    _ensure_cascade_fk(cr, "sale_order_dvz_division_rel", "division_id", "division_master")
    _ensure_cascade_fk(cr, "sale_order_dvz_division_rel", "order_id", "sale_order")
    _ensure_cascade_fk(cr, "sale_order_dvz_system_rel", "system_id", "system_master")
    _ensure_cascade_fk(cr, "sale_order_dvz_system_rel", "order_id", "sale_order")
    _logger.warning("DVZ M2M migration bridge completed. Existing relation FKs are now ON DELETE CASCADE.")


def uninstall_hook(env):
    # Intentionally keep the backup table for recovery. It contains IDs only.
    _logger.info("DVZ migration bridge uninstalled; emergency backup table retained.")
