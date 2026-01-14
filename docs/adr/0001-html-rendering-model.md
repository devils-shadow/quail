# ADR 0001: HTML Rendering Model

*Status:* accepted

## Context

Quail needs to render HTML emails for QA review without compromising security or
changing the sender’s HTML. The UI should offer a reliable HTML view alongside a
plaintext view, and avoid unsafe script execution or accidental outbound email.

## Decision

Use a sandboxed `<iframe>` with `srcdoc` for full HTML rendering:

- HTML rendering is admin-controlled (toggle in settings).
- The HTML view is shown in a dedicated “HTML” tab alongside “TEXT” and
  “ATTACHMENTS”.
- CID references are rewritten to local inline attachment URLs.
- The iframe uses `sandbox="allow-same-origin"` and blocks script execution by
  default.
- Plaintext remains available via `html2text` conversion.
- In dark mode, minimal HTML messages inherit the app theme for contrast.

## Consequences

**Positive**
- Preserves sender HTML as-is while isolating it inside a sandbox.
- Prevents script execution and keeps the UI stable.
- Provides deterministic QA review of HTML vs. plaintext.

**Negative**
- HTML rendering can still display remote assets if the HTML references them.
- The minimal HTML dark-mode adjustment is heuristic and may not apply to all
  layouts.

## Alternatives Considered

- Inline HTML rendering without iframe: rejected due to security risk and
  inconsistent isolation.
- Full sanitization of HTML: rejected because QA needs faithful rendering.
