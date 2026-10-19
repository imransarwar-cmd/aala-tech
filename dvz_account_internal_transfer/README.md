# Internal Bank/Cash Transfers for Odoo 19 Community

Depends on `base_accounting_kit` (Cybrosys). Install from Apps after updating the apps list.

Go to Accounting > Internal Transfers. Configure separate Default Accounts on each Bank/Cash journal, and a Miscellaneous/General journal for posting. Create a transfer, choose source and destination bank/cash journals, amount (in company currency), and post.

Posting creates ONE balanced journal entry: debit destination ledger account and credit source ledger account. Reversing posts a separate opposite journal entry; it does not delete history. This is an accounting transfer, NOT a bank statement line or payment, and does not automatically reconcile imported bank statements.

Important: Only same-company, company-currency transfers are supported. For multi-currency, bank suspense/outstanding-account reconciliation, or statement matching, additional workflows are required. Posting is limited to Accounting Managers; invoicing users have read-only access. Test on staging and verify account mappings, accounting lock dates and bank reconciliation before production use.
