# AI MCP for Odoo

Ask Claude, ChatGPT, Gemini or Cursor about your Odoo data.

An [MCP](https://modelcontextprotocol.io) server that runs **inside Odoo 19** —
no extra process, no middleware, no external Python dependencies. Sign in with
your normal Odoo login, paste one URL into your assistant, and start asking
questions.

```
Odoo → AI MCP → Connect your AI → copy the URL → paste into Claude → Allow
```

## What it does

- **OAuth 2.1 sign-in** (PKCE, Client ID Metadata Documents, RFC 8707/9207/7009).
  No API keys, no config files, no `mcp-remote`.
- **A guided Connect screen** that checks every precondition *before* you leave
  for your assistant — public HTTPS address, reachability from the internet,
  permissions — and fixes the common ones in one click.
- **Seven read tools**: `list_capabilities`, `list_models`, `get_schema`,
  `search_records`, `count_records`, `name_search`, `read_group`.
- **A permission matrix** you control: one row per Odoo model, switchable in a
  list.
- **An audit row per call** — user, tool, model, IP, duration, token estimate.

## What it deliberately does not do

It is **read-only**. There is no create, update, delete or method-call tool,
so there is nothing to misconfigure into writing.

Governed writes with a human approval queue, per-user scopes, field
blacklists, record filters, method allow-lists, long-lived API keys and
compliance-grade audit retention are in **AI MCP Governance**.

## Safety model

Three independent gates, and the group that makes the menu visible is not one
of them:

1. The scope is read-only — no writing verb exists in this module.
2. The permission matrix names each readable model, one row at a time.
3. **Every call runs as the signed-in Odoo user**, so `ir.model.access`,
   record rules, field groups and multi-company isolation all apply
   underneath. The assistant can never see more than that person can.

Results are never silently truncated: replies carry `has_more`, so an
assistant says an answer is partial rather than reporting a page as the whole
set.

## Install

Drop `ai_mcp/` into your addons path and install it from Apps. Odoo 19.

Your Odoo needs a **public HTTPS address**; the Connect screen tells you if it
does not have one and offers to pin it.

## Requirements

Odoo 19 (Community or Enterprise). No Python packages beyond what Odoo already
ships.

## Extending it

Tools are records, not hard-coded Python. Ship an `mcp.capability` and some
`mcp.tool` rows, add a `_handler_<name>` method by inheriting `mcp.engine`, and
you have extended the connector — no controller changes, upgrade-safe.

If your handler **writes**, you must declare it in
`mcp.tool._write_handlers()` *and* override `mcp.engine._check_write_permitted`.
Doing neither means it is refused, not silently executed.

## Licence

LGPL-3. See [LICENSE](LICENSE).
