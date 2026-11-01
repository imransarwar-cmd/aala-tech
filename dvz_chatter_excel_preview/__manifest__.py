{
    "name": "Chatter Excel Preview",
    "version": "19.0.1.0.0",
    "category": "Productivity/Discuss",
    "summary": "Read-only Excel worksheet previews from existing chatter attachments",
    "author": "Aala Tech",
    "license": "LGPL-3",
    "depends": ["mail", "web"],
    "external_dependencies": {"python": ["openpyxl", "defusedxml"]},
    "assets": {
        "web.assets_backend": [
            "dvz_chatter_excel_preview/static/src/preview_helpers.js",
            "dvz_chatter_excel_preview/static/src/excel_preview_dialog.js",
            "dvz_chatter_excel_preview/static/src/excel_preview_dialog.xml",
            "dvz_chatter_excel_preview/static/src/attachment_list_patch.js",
            "dvz_chatter_excel_preview/static/src/excel_preview.css",
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": False,
}
