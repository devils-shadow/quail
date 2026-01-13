# Phase 8 Acceptance Verification Checklist

Use this checklist to manually verify the Phase 8 acceptance criteria for the spam mitigation
features. This mirrors the acceptance list in `docs/QUAIL_SPAM_MITIGATION_PLAN.md` (Phase 8).

Automated coverage exists in `tests/test_phase8_acceptance.py`; use this checklist for
manual spot-checks or release validation.

## Manual Checklist

1. **OPEN delivers to Inbox**
   - Set a domain policy to `OPEN` with default action `INBOX`.
   - Ingest a message for that domain and confirm it appears in the inbox list.

2. **PAUSED blocks new Inbox entries**
   - Set a domain policy to `PAUSED` with default action `INBOX`.
   - Ingest a message and confirm it does not appear in the inbox list.

3. **RESTRICTED requires ALLOW rules**
   - Set a domain policy to `RESTRICTED` with default action `INBOX`.
   - Ingest a message that does not match any `ALLOW` rule and confirm it is quarantined.
   - Add an `ALLOW` rule matching the recipient local-part and confirm new matching messages land
     in the inbox.

4. **BLOCK rules default to Quarantine**
   - Create a `BLOCK` rule with action `QUARANTINE` for a subject pattern.
   - Ingest a matching message and confirm it is quarantined.

5. **Quarantine restore works**
   - From the quarantine view, select a quarantined message and restore it.
   - Confirm the message is visible in the inbox and no longer listed in quarantine.

6. **Retention jobs purge correctly**
   - Configure retention and quarantine retention days to short values.
   - Add inbox and quarantine messages older than those values.
   - Run the purge job and confirm both messages and files are removed.

7. **All admin actions logged**
   - Perform an admin action (e.g., update a domain policy or rule).
   - Confirm the action appears in the `admin_actions` table.

8. **UI remains responsive under expected load**
   - Seed the inbox with ~100 messages.
   - Load the inbox page and confirm it renders quickly and completely.
