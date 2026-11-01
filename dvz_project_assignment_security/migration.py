"""Upgrade-only legacy conversion with a private, auditable CSV report."""
import base64
import csv
import io
import logging

from .upgrade_plan import legacy_assignment_plan

_logger = logging.getLogger(__name__)
REPORT_NAME = 'DVZ_Project_Manager_Migration_19.0.1.1.0.csv'


def _csv_text(value):
    # Avoid spreadsheet formula execution when a name starts with a formula char.
    text = str(value or '')
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r', '\n') else text


def migrate_legacy_assignments(env):
    """Called only by the versioned post-migration as the upgrade administrator.

    Legacy storage is kept (admin-only, read-only) but grants no access. No task
    assignment, user role, company access or existing manager is overwritten.
    """
    Project = env['project.project'].with_context(active_test=False)
    projects = Project.search([('dvz_assigned_user_ids', '!=', False)], order='id')
    if not projects:
        return {'migrated': 0, 'review': 0, 'attachment_id': False}
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow([
        'Project ID', 'Project Name', 'Company', 'Previous Project Manager ID',
        'Previous Project Manager', 'Legacy User IDs', 'Legacy Users',
        'Resulting Project Manager ID', 'Resulting Project Manager', 'Status', 'Details',
    ])
    moved = review = 0
    for project in projects:
        old_manager = project.user_id
        users = project.dvz_assigned_user_ids
        plan_users = [{
            'id': user.id, 'active': user.active, 'share': user.share,
            'company_ok': not project.company_id or project.company_id in user.company_ids,
        } for user in users]
        target, status, detail = legacy_assignment_plan(old_manager.id, plan_users)
        if target:
            project.with_context(tracking_disable=True, mail_notrack=True).write({'user_id': target})
            moved += 1
        if status.startswith('review_'):
            review += 1
            _logger.warning('Project manager migration review: project=%s status=%s: %s',
                            project.id, status, detail)
        values = [
            project.id, project.name, project.company_id.display_name,
            old_manager.id, old_manager.name,
            ', '.join(str(user.id) for user in users), ', '.join(user.name for user in users),
            project.user_id.id, project.user_id.name, status, detail,
        ]
        writer.writerow([_csv_text(value) for value in values])
    module = env.ref('base.module_dvz_project_assignment_security')
    # Attachment inherits access from ir.module.module (Settings administrators),
    # is explicitly private, and has no public access token.
    attachment = env['ir.attachment'].create({
        'name': REPORT_NAME,
        'type': 'binary',
        'datas': base64.b64encode(output.getvalue().encode('utf-8-sig')),
        'mimetype': 'text/csv',
        'res_model': 'ir.module.module',
        'res_id': module.id,
        'public': False,
        'description': 'Upgrade audit: old project assignments to native Project Manager. '
                       'Rows marked review require administrator attention.',
    })
    _logger.info('Project manager migration completed: moved=%s review=%s private_report_id=%s',
                 moved, review, attachment.id)
    return {'migrated': moved, 'review': review, 'attachment_id': attachment.id}
