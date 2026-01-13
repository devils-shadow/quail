# Glossary

- **.eml file:** The raw RFC822 representation of an email message stored on disk【104907567664902†L60-L62】.
- **Ingest:** The process by which Postfix pipes an incoming email to a script that saves the `.eml` file and extracts metadata into the SQLite database【104907567664902†L42-L47】【104907567664902†L60-L70】.
- **Shared Inbox:** A UI that shows all received messages to all authorized viewers. Quail does not have per‑user mailboxes or accounts【104907567664902†L27-L31】.
- **Quarantine:** A state applied to messages containing disallowed attachments. Quarantined messages are hidden from non‑admin users until an administrator reviews them【104907567664902†L71-L78】.
- **Retention Policy:** The length of time messages and attachments are retained before automatic deletion (default 30 days)【104907567664902†L87-L95】.
- **Admin PIN:** A shared secret that unlocks administrative functions. Stored as a salted hash and subject to rate‑limiting【104907567664902†L101-L106】.
- **ETag:** A response token used by the inbox API to avoid reloading unchanged lists.
- **FastAPI:** The Python web framework used to implement the Quail service【104907567664902†L49-L53】.
- **Postfix:** The mail transfer agent that receives inbound SMTP messages for configured domains (example: `mail.example.test`) and hands them off to the ingest script.
- **SQLite:** The embedded database used for storing message metadata and settings【104907567664902†L62-L70】.
- **WebSocket:** A planned upgrade path for real-time inbox updates (see `WEBSOCKET_INBOX_PLAN.md`).
