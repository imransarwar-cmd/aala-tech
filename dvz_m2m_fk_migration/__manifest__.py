# -*- coding: utf-8 -*-
{
    "name": "DVZ Sale M2M FK Migration Bridge",
    "version": "19.0.1.0.0",
    "summary": "One-time bridge to repair Sale Order Division/System M2M foreign keys before upgrading DVZ Sale Report Fields.",
    "author": "Genius Valley",
    "category": "Technical",
    "license": "OPL-1",
    "depends": ["sale", "aala_rest_api"],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "auto_install": False,
    "application": False,
}
