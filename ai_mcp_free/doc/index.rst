======
AI MCP
======

Ask Claude, ChatGPT, Gemini or Cursor about your Odoo data. AI MCP is a
`Model Context Protocol <https://modelcontextprotocol.io>`_ server that runs
inside Odoo — no extra process, no middleware, no external Python
dependencies.

It is **read-only**: an assistant can search, count, resolve names and
aggregate, and cannot create, update or delete anything.

Installation
============

Drop ``ai_mcp_free`` into your addons path and install it from Apps.

Your Odoo must be reachable on a **public HTTPS address**. The Connect screen
checks this for you and offers to fix the usual causes in one click.

Configuration
=============

Nothing is required. Installing seeds a read-only scope and opens it onto the
business models your database actually has (sales, purchasing, invoicing,
inventory, CRM, projects, HR — whichever are installed).

Optional settings live under :menuselection:`Settings --> AI MCP`:

* **Enable MCP Server** — the master switch.
* **Sign in with Odoo (OAuth 2.1)** — leave on; it is the only way to connect.
* **Dynamic client registration** — RFC 7591, deprecated upstream. Turn it off
  to accept only Client ID Metadata Documents.
* **Allowed browser origins** — empty is the safe default. MCP clients are not
  browsers, and echoing an arbitrary origin invites DNS-rebinding attacks.
* **Public address override** — only needed for a front end that announces
  nothing at all. The server normally works its own address out.
* **Token lifetimes** — access and refresh, in seconds.

Usage
=====

Go to :menuselection:`AI MCP --> Connect your AI`.

1. Clear anything the readiness checks flag. Each one names the fix and opens
   the screen that applies it.
2. Copy the server URL.
3. In Claude: :menuselection:`Settings --> Connectors --> Add custom
   connector`, paste the URL, click **Connect**, then **Allow**. Leave Client
   ID and Client Secret empty — the server registers your client itself.
   VS Code and Cursor have one-click install links on the same screen.
4. Ask a question. The starter prompts on the screen are filtered to ones your
   permissions can actually answer.

Deciding what an assistant can read
===================================

:menuselection:`AI MCP --> Permissions --> Model Permissions` is one row per
Odoo model. Toggle **Read**, or archive a row to suspend access without losing
it. Use **Add Models** to add a set at once.

This matrix can only ever take access away. Every call executes as the
signed-in Odoo user, so the effective permission is whichever is narrower —
this matrix, or that person's own Odoo rights.

Seeing what happened
====================

:menuselection:`AI MCP --> My AI Activity` shows every call made on your
behalf: the tool, the model, when, how long it took and a token estimate.
History is kept for 30 days.

Going further
=============

`AI MCP Pro <https://apps.odoo.com/apps/modules/19.0/mcp_governance_suite>`_
adds governed writes with a human approval queue, per-user scopes, field
blacklists, record filters, method allow-lists, API keys for headless callers,
and configurable audit retention.

Bug Tracker
===========

Please report issues to the maintainer at developers@fleet.ke.

Credits
=======

This module is maintained by `Fleet <https://fleet.ke>`_.

Licensed under the GNU Lesser General Public License v3.
