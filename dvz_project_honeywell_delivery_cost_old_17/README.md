# DVZ Honeywell Delivery Costing

Version 19.0.1.5.0.

Delivered Cost is based on actual completed customer delivery stock moves of the Sales Order that created the project.

Matching flow:

1. Analytic Account -> existing linked project.project
2. project.project.dvz_origin_sale_id -> originating Sales Order
3. Completed customer stock moves whose sale line belongs to that Sales Order
4. Cost line created at 100% for each completed stock move

There is intentionally no stock-move check for project_id, task_id, or analytic_distribution.
Partial deliveries and backorders are handled by their completed stock moves.


## v1.6 calculation rule
Delivered Cost = Sales Order line Unit Price x actual Done customer-delivery quantity.
Stock valuation and product standard cost are not used. Existing cost lines are recalculated when the Delivered Cost smart button sync runs.
