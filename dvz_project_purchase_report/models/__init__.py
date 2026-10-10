# analytic_account FIRST: it adds the dvz_budget column that the SQL report
# views (created in each model's init()) read from.
from . import analytic_account
from . import purchase_order
from . import project_purchase_report
from . import project_sale_report
from . import project_reporting
from . import project_dashboard
