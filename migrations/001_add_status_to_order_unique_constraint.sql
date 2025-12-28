-- Migration: Add status to xt_order_update unique constraint
-- Date: 2025-12-28
-- Description: Modify unique constraint to include status field, allowing multiple states for the same order at the same timestamp

BEGIN;

-- Drop old unique constraint
ALTER TABLE xt_order_update
DROP CONSTRAINT IF EXISTS uq_xt_order_id_time_account;

-- Add new unique constraint with status field
ALTER TABLE xt_order_update
ADD CONSTRAINT uq_xt_order_id_time_account_status
UNIQUE (order_id, update_time, account_id, status);

COMMIT;

-- Rollback script (if needed):
-- BEGIN;
-- ALTER TABLE xt_order_update DROP CONSTRAINT IF EXISTS uq_xt_order_id_time_account_status;
-- ALTER TABLE xt_order_update ADD CONSTRAINT uq_xt_order_id_time_account UNIQUE (order_id, update_time, account_id);
-- COMMIT;
