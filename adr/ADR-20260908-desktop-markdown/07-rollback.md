# Rollback

Rollback trigger: rendered Markdown still falls back, a new crash appears, or unrelated transcript surfaces regress.

Rollback handle: revert the exact implementation commit (after recording its hash), rebuild the desktop renderer, restart the affected desktop runtime, and read back the assistant DOM. Do not revert unrelated main-checkout changes.
