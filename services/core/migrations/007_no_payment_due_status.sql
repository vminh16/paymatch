-- 007_no_payment_due_status.sql
-- Invoices with total <= 0 (downward adjustment, trade discount, 0 đ) end in `no_payment_due` instead of the
-- approval queue (docs/05-api/merchant-api.md §2, architecture.md decision 27/11/2026).

ALTER TABLE core.invoices DROP CONSTRAINT IF EXISTS invoices_status_check;
ALTER TABLE core.invoices ADD CONSTRAINT invoices_status_check CHECK (status IN (
    'new', 'investigating', 'auto_pay_eligible', 'pending_approval',
    'blocked', 'approved', 'scheduled', 'paying', 'paid',
    'payment_failed', 'escrow_held', 'no_payment_due', 'rejected'
));
