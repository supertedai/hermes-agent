# Rollback

Trigger: enqueue changes duplicate cards, mutates running claims, or violates dispatcher-only spawn ownership.

Rollback: revert the integration commit and restore the prior cron prompt/schedule through the human-owned cron UI. Deduplicate any cards by the idempotency key using normal Kanban operations. Proof: focused tests and board readback show no duplicate active key and no running claim was released.
