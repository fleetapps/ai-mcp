# -*- coding: utf-8 -*-
# Manifest reference:
# https://www.odoo.com/documentation/19.0/developer/reference/backend/module.html
{
    "name": "AI MCP",
    "version": "19.0.1.0.0",
    "category": "Extra Tools/AI",
    "summary": "Ask Claude, ChatGPT, Gemini or Cursor about your Odoo data. "
               "One-click OAuth 2.1 sign-in, read-only, runs as the real user, "
               "fully audited. Open source.",
    "description": """
AI MCP
======

Let your team *ask questions about their Odoo data* from Claude, ChatGPT,
Gemini, Cursor, Copilot, VS Code — any Model Context Protocol client — and get
answers in seconds. The MCP server runs **inside Odoo**: no extra process, no
middleware, and **zero external Python dependencies**.

Connect in about a minute
-------------------------
* "Sign in with Odoo" — the OAuth 2.1 connect flow Anthropic and OpenAI
  recommend. No API keys, no config files, no ``mcp-remote``. Paste one URL and
  click *Allow*.
* A guided **Connect** screen that checks every precondition *before* you leave
  for your assistant — public HTTPS address, reachability, permissions — and
  fixes the common ones in a click, so you never discover a problem by watching
  Claude fail.
* One-click install links for VS Code and Cursor, a QR code for mobile, and a
  "Run a test question as me" button that proves the whole chain works from
  inside Odoo.

Safe by construction
--------------------
* **Read-only.** This edition ships searching, counting, name resolution and
  aggregation. There is no write tool to misconfigure.
* **Runs as the signed-in user.** Every request executes as that person, so
  ``ir.model.access``, record rules, field groups and multi-company isolation
  all apply underneath the MCP permission matrix. The AI can never see more
  than the person using it.
* **A permission matrix you control.** One row per model, switchable in a list.
  It can only ever take access away, never add it.
* **Everything is recorded.** One audit row per call — user, tool, model, IP,
  duration and a token estimate — readable by each user for their own activity.
* **Results are never silently truncated**: replies carry ``has_more``, so an
  assistant says an answer is partial instead of reporting a page as the whole
  set.

Works with both generations of MCP client
-----------------------------------------
The transport is **dual-era**: protocol revision ``2026-07-28`` (per-request
metadata, ``server/discover``, no handshake) *and* the older handshake-based
revisions (``2025-06-18``, ``2025-03-26``). Connectors built against either
generation keep working.

Extensible by design
--------------------
Tools are *records*, not hard-coded Python. A capability bundles tools; a
scope switches capabilities on or off. Ship new ``mcp.capability`` /
``mcp.tool`` data plus a handler method on ``mcp.engine`` and you have extended
the connector — no controller surgery, upgrade-safe.

Need governed writes?
---------------------
**AI MCP Pro** adds create/update/delete with a human approval queue,
per-user scopes, field blacklists, record filters, method allow-lists,
long-lived API keys for headless callers, and compliance-grade audit retention.

Provider-agnostic. Multi-company aware. Fully translatable. LGPL-3.
""",
    "author": "Fleet",
    "website": "https://fleet.ke",
    "support": "developers@fleet.ke",
    "maintainer": "Fleet",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail"],
    "data": [
        # security (groups + rules first, then the access matrix)
        "security/mcp_security.xml",
        "security/ir.model.access.csv",
        # seed data
        "data/mcp_capability_data.xml",
        "data/mcp_scope_data.xml",
        "data/ir_cron.xml",
        # web / OAuth consent templates
        "views/oauth_templates.xml",
        # backend views + actions. The matrix/picker load first: the scope form
        # has a button that references the picker action by xml id.
        "views/mcp_model_access_views.xml",
        "views/mcp_views.xml",
        "views/mcp_registry_views.xml",
        "views/mcp_oauth_views.xml",
        "views/mcp_connect_views.xml",
        "views/res_config_settings_views.xml",
        # menus last (they reference the actions defined above)
        "views/mcp_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_mcp_free/static/src/connect/connect.scss",
            "ai_mcp_free/static/src/connect/connect.js",
            "ai_mcp_free/static/src/connect/connect.xml",
        ],
    },
    # The store falls back to the icon when there is no banner. Deliberate:
    # the only banner available advertises writes, a free trial and a product
    # name none of which belong to this edition, and a wrong banner costs more
    # than no banner.
    "images": [
        "static/description/shot_ask.png",
    ],
    "pre_init_hook": "pre_init_check",
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
}
