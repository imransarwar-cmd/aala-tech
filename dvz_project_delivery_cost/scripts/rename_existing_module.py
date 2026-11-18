"""One-time Odoo --pre-upgrade-scripts helper for the generic module name.

Run before refreshing Apps, with the application stopped and a database backup.
The caller owns the transaction; this script never commits or merges records.
"""

import re


TARGET_MODULE = 'dvz_project_delivery_cost'
TARGET_FIELD = 'dvz_project_delivery_costing'


def _require_free(cr, query, params, description):
    cr.execute(query, params)
    if cr.fetchone():
        raise RuntimeError('Rename stopped: destination already exists: ' + description)


def migrate(cr, version):
    cr.execute(
        """SELECT DISTINCT d.module
             FROM ir_model_data d
             JOIN ir_model m ON d.model = 'ir.model' AND d.res_id = m.id
             JOIN ir_module_module a ON a.name = d.module
            WHERE m.model = 'dvz.project.delivery.cost.line'
              AND a.state IN ('installed', 'to upgrade')"""
    )
    owners = [row[0] for row in cr.fetchall()]
    if owners == [TARGET_MODULE]:
        return
    if len(owners) != 1:
        raise RuntimeError('Rename requires exactly one installed delivery-costing module owner.')
    source = owners[0]

    try:
        from odoo.upgrade import util
    except ImportError as exc:
        raise RuntimeError(
            'Install the official Odoo upgrade-util package in the Odoo Python '
            'environment before running this helper. No changes were made.'
        ) from exc
    for name in ('rename_module', 'rename_field', 'rename_xmlid'):
        if not callable(getattr(util, name, None)):
            raise RuntimeError('The installed Odoo upgrade utilities do not provide ' + name)

    _require_free(cr, 'SELECT id FROM ir_module_module WHERE name = %s',
                  (TARGET_MODULE,), TARGET_MODULE)
    _require_free(cr, 'SELECT id FROM ir_model_data WHERE module = %s LIMIT 1',
                  (TARGET_MODULE,), 'target module external identifiers')
    _require_free(cr, "SELECT id FROM ir_model_data WHERE module = 'base' AND name = %s",
                  ('module_' + TARGET_MODULE,), 'target module registration identifier')

    cr.execute(
        """SELECT DISTINCT f.id, f.model, f.name
             FROM ir_model_fields f
             JOIN ir_model_data d ON d.model = 'ir.model.fields' AND d.res_id = f.id
            WHERE d.module = %s
              AND f.model IN ('account.analytic.account', 'res.config.settings')""",
        (source,),
    )
    source_fields = cr.fetchall()
    checkbox_names = [name for _, model, name in source_fields
                      if model == 'account.analytic.account' and name.endswith('_delivery_costing')]
    if len(checkbox_names) != 1:
        raise RuntimeError('Cannot uniquely identify the existing delivery-costing checkbox.')
    old_field = checkbox_names[0]
    if old_field == TARGET_FIELD or not all(
        re.fullmatch(r'[a-z][a-z0-9_]*', value) for value in (source, old_field)
    ):
        raise RuntimeError('Unexpected existing module/field identifiers; manual review is required.')

    field_map = []
    expected_fields = {
        ('account.analytic.account', old_field): TARGET_FIELD,
        ('res.config.settings', old_field + '_scope'): TARGET_FIELD + '_scope',
        ('res.config.settings', old_field + '_account_ids'): TARGET_FIELD + '_account_ids',
    }
    for field_id, model, old in source_fields:
        new = expected_fields.get((model, old))
        if not new:
            continue
        _require_free(cr, 'SELECT id FROM ir_model_fields WHERE model = %s AND name = %s',
                      (model, new), model + '.' + new)
        _require_free(
            cr,
            """SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s""",
            (model.replace('.', '_'), new), 'column ' + model + '.' + new,
        )
        # rename_field recreates generated field XML IDs; never rename them twice.
        new_xmlid = 'field_' + model.replace('.', '_') + '__' + new
        _require_free(
            cr,
            """SELECT id FROM ir_model_data WHERE name = %s AND module IN
               (SELECT module FROM ir_model_data
                 WHERE model = 'ir.model.fields' AND res_id = %s AND module != '__export__')""",
            (new_xmlid, field_id), 'generated field identifier ' + new_xmlid,
        )
        field_map.append((model, old, new))

    old_cost = old_field[:-3]
    explicit_ids = [
        ('view_account_analytic_account_form_' + old_cost,
         'view_account_analytic_account_form_' + TARGET_MODULE),
        ('res_config_settings_view_form_' + old_cost,
         'res_config_settings_view_form_' + TARGET_MODULE),
        ('action_' + old_field + '_settings', 'action_' + TARGET_FIELD + '_settings'),
        ('menu_' + old_field + '_settings', 'menu_' + TARGET_FIELD + '_settings'),
    ]
    xmlid_map = []
    for old, new in explicit_ids:
        cr.execute('SELECT id FROM ir_model_data WHERE module = %s AND name = %s', (source, old))
        if not cr.fetchone():
            continue
        _require_free(cr, 'SELECT id FROM ir_model_data WHERE module = %s AND name = %s',
                      (source, new), 'external identifier ' + new)
        xmlid_map.append((old, new))

    old_prefix, new_prefix = source + '.', TARGET_MODULE + '.'
    cr.execute(
        'SELECT id, key FROM ir_config_parameter WHERE left(key, length(%s)) = %s ORDER BY id',
        (old_prefix, old_prefix),
    )
    parameters = [(identifier, new_prefix + key[len(old_prefix):]) for identifier, key in cr.fetchall()]
    for _, new_key in parameters:
        _require_free(cr, 'SELECT id FROM ir_config_parameter WHERE key = %s',
                      (new_key,), 'configuration key ' + new_key)

    # All preflight checks precede writes. Preserve the module record/version,
    # cost model/table and every delivery-cost record.
    util.rename_module(cr, source, TARGET_MODULE)
    for model, old, new in field_map:
        util.rename_field(cr, model, old, new, update_references=True, skip_inherit='*')
    for old, new in xmlid_map:
        util.rename_xmlid(cr, TARGET_MODULE + '.' + old, TARGET_MODULE + '.' + new,
                          on_collision='fail')
    for identifier, new_key in parameters:
        cr.execute('UPDATE ir_config_parameter SET key = %s WHERE id = %s', (new_key, identifier))

    # Odoo 19 stores translated view architectures as JSONB. The replacements
    # contain only validated identifier characters, so JSON escaping is intact.
    cr.execute(
        """UPDATE ir_ui_view
              SET arch_db = replace(replace(arch_db::text, %s, %s), %s, %s)::jsonb
            WHERE arch_db IS NOT NULL AND id IN
                  (SELECT res_id FROM ir_model_data WHERE module = %s AND model = 'ir.ui.view')""",
        (source, TARGET_MODULE, old_cost, TARGET_MODULE, TARGET_MODULE),
    )
    cr.execute(
        """UPDATE ir_act_window
              SET context = replace(replace(context, %s, %s), %s, %s)
            WHERE context IS NOT NULL AND id IN
                  (SELECT res_id FROM ir_model_data
                    WHERE module = %s AND model = 'ir.actions.act_window')""",
        (source, TARGET_MODULE, old_cost, TARGET_MODULE, TARGET_MODULE),
    )
