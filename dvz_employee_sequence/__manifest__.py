# -*- coding: utf-8 -*-
{
    "name": "Employee Sequence Number",
    "version": "19.0.1.0.0",
    "summary": "Auto-generates an Employee Code on new employees in the "
                "format: first 3 letters of Department + 2-digit year + "
                "sequential number (e.g. ENG26001).",
    "author": "Genius Valley",
    "category": "Human Resources",
    "license": "OPL-1",
    "depends": [
        "hr",
    ],
    "data": [
        "data/ir_sequence_data.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
