{
    'name': 'Project Assignment Security - Users, Managers and HOD',
    'version': '19.0.1.1.0',
    'summary': 'Native Project Manager assignment, restricted roles, and all-name-parts search',
    'category': 'Services/Project',
    'author': 'DVZ Customizations',
    'license': 'LGPL-3',
    'depends': ['project'],
    'data': [
        'security/project_groups.xml',
        'security/project_rules.xml',
        'views/project_project_views.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
