# Automatic SO reservation
Separate addon (depends only sale_stock). On sale.order confirmation, calls native picking.action_assign() on existing outgoing deliveries when Auto Reserve on Confirm is checked. Does not generate manual holds or edit stock.move.line.
