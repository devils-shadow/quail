# ADR 0006: Public Inbox Access Model

*Status:* proposed

## Context

A public inbox that lists all messages by default enables email harvesting.
Quail 2.0 requires a public access model that limits exposure while preserving
a sink-style workflow.

## Decision

Require a filter before displaying any public inbox messages. Accept only
localpart or full address for filtering, normalize to lowercase, and disable
wildcard search. Restrict public message views to HTML and plaintext only.

## Consequences

- Changes public UI behavior and default visibility.
- Reduces exposure to scraping and enumeration.
- Requires new UI states for "no filter" and "empty results".

## Alternatives Considered

- Keep the shared public inbox visible by default.
- Require authentication for all inbox access.
- Allow wildcard search with rate limits.
