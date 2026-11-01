"""Restore the native role label only if our label is still in use."""


def uninstall_hook(env):
    group = env.ref('project.group_project_manager', raise_if_not_found=False)
    if group and group.with_context(lang='en_US').name == 'Project Manager':
        group.with_context(lang='en_US').write({
            'name': 'Administrator',
            'comment': 'Administrator: Can manage projects and stages, '
                       'with access to reporting and configuration.',
        })
