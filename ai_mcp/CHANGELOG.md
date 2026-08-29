# Changelog

All notable changes to **AI MCP** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/); versions use
Odoo's `19.0.MAJOR.MINOR.PATCH` scheme.

## [19.0.1.0.0] — 2026-08-30

First open-source release. AI MCP is the free, read-only edition of the Odoo
MCP connector, extracted from the commercial AI MCP Governance suite and
published under LGPL-3.

### Added
- **MCP server inside Odoo**, dual-era: protocol revision `2026-07-28`
  (per-request metadata, `server/discover`, no handshake) and the older
  handshake revisions `2025-06-18` / `2025-03-26`, so connectors built against
  either generation work.
- **Self-contained OAuth 2.1 authorization server**: Client ID Metadata
  Documents, PKCE S256, RFC 9728 protected-resource metadata, RFC 8414 server
  metadata, RFC 8707 audience-bound tokens, RFC 9207 issuer identification,
  RFC 7009 revocation and refresh-token rotation. RFC 7591 dynamic
  registration is retained as a deprecated fallback. Users authenticate with
  their normal Odoo login, so SSO and 2FA just work.
- **Guided Connect screen**: readiness checks that name the fix and open the
  screen that applies it, a one-click "pin and freeze the public address" fix,
  a live waiting→connected status, per-client instructions, one-click install
  links for VS Code and Cursor, a QR code for mobile, starter prompts filtered
  to what the permission matrix can actually answer, and a "Run a test question
  as me" button that proves the whole chain end to end.
- **Seven read tools** across two capabilities: `list_capabilities`,
  `list_models`, `get_schema`, `search_records`, `count_records`,
  `name_search`, `read_group`.
- **Permission matrix** — one row per model, archivable, plus a bulk "Add
  Models" picker and a post-install hook that opens the default scope onto
  whichever business models the database actually has installed.
- **Audit trail** — one row per call with user, tool, model, IP, duration and a
  token estimate, visible to each user for their own activity, purged after 30
  days.
- **Correct public-origin resolution.** The address handed to clients is
  derived from the proxy's forwarded headers (`Forwarded`,
  `X-Forwarded-Proto`, `X-Forwarded-Ssl`, `Front-End-Https`, `CF-Visitor`), so
  a TLS-terminating proxy needs no configuration and a `web.base.url` that Odoo
  has rewritten to `http://` cannot downgrade the OAuth metadata.
- **Truncation is always reported.** `search_records`, `read_group` and
  `name_search` fetch one row past the cap and return `limit` and `has_more`,
  so an assistant says an answer is partial instead of presenting a full page
  as the complete set.
- **MCP tool annotations** (`readOnlyHint`, `openWorldHint`) and per-scope tool
  descriptions naming the models a connection can reach, so the first question
  does not cost a discovery round trip.
- Every employee holds the MCP user role by default. It is navigation, not
  authority: the read-only scope, the matrix and the user's own Odoo access
  rights are the three gates that actually decide anything.

### Notes
- This edition is read-only by construction — no mutating verb is implemented,
  and one arriving from another module is refused rather than executed. Writes,
  approvals, per-user scopes, field blacklists, record filters, method
  allow-lists, API keys and configurable audit retention are provided by AI MCP
  Governance.
