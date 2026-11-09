# DVZ Honeywell Project Delivery Costing

Extension only. It does not modify `dvz_project_purchase_report`.

## Behaviour
- Enable **Honeywell Delivery Costing** on the required analytic project.
- A costing line is created only from a completed customer delivery (`stock.move` in `done`).
- Partial delivery works: only the actually delivered stock move quantity/cost is included.
- Backorders create later costing lines when those deliveries are completed.
- Cost uses linked stock valuation layers (actual company-currency valuation); standard cost is only a fallback.
- The Sales Order line's analytic distribution decides which project receives the cost and at what percentage.
- Existing completed deliveries are backfilled when the Honeywell flag is enabled or when the Delivered Cost button is opened.

## Install
Depend on the existing `dvz_project_purchase_report` addon and install this addon separately.
