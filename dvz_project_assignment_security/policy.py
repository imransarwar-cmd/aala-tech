"""Pure domain construction; deliberately no searches or cached assignment ID lists.

The internal ``any!`` operator is converted to an Odoo 19 Domain by the private
res.users wrapper. It avoids recursive project -> task -> project record rules.
It bypasses rules ONLY for the existential assignment test, not for reading the
record. Normal ACLs, our outer rules, and native company rules still apply.
"""

HOD_GROUP = 'dvz_project_assignment_security.group_project_hod'
SYSTEM_GROUP = 'base.group_system'
SCOPES = frozenset({
    'project_read', 'project_write', 'task', 'project_related', 'milestone_read', 'burndown',
})


def full_project_domain(uid):
    """A real project assignment, not merely being a follower or task assignee."""
    return [('user_id', '=', uid)]


def own_tasks_domain(uid, company_ids):
    return [
        ('user_ids', 'in', [uid]),
        ('company_id', 'in', list(company_ids) + [False]),
    ]


def assignment_domain(uid, scope, company_ids=(), *, portal=False, hod=False, system=False):
    """Return a fresh domain for a trusted current user and trusted company IDs.

    Returning [] here does not grant an ACL or override other global rules.
    HOD access covers all project-linked tasks, not other people's personal tasks.
    """
    if scope not in SCOPES:
        raise ValueError('Unknown assignment security scope: %s' % scope)
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        raise ValueError('A positive internal user ID is required')
    if portal or system:
        return []
    if hod:
        if scope == 'task':
            return ['|', ('project_id', '!=', False), ('user_ids', 'in', [uid])]
        return []
    full = full_project_domain(uid)
    if scope == 'project_write':
        return full
    if scope == 'project_read':
        return ['|'] + full + [
            ('dvz_access_task_ids', 'any!', own_tasks_domain(uid, company_ids)),
        ]
    if scope == 'burndown':
        # Aggregated burndown IDs are not task IDs. Restrict its project rows;
        # Odoo's native SQL query separately applies project.task record rules.
        return [('project_id', 'any!', assignment_domain(uid, 'project_read', company_ids))]
    if scope == 'task':
        return ['|', ('user_ids', 'in', [uid]), ('project_id', 'any!', full)]
    if scope == 'project_related':
        return [('project_id', 'any!', full)]
    # Milestone metadata is also readable when attached to an assigned task.
    return ['|', ('project_id', 'any!', full),
            ('task_ids', 'any!', own_tasks_domain(uid, company_ids))]
