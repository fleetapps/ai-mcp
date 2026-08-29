# -*- coding: utf-8 -*-
"""One-click setup surface (Settings -> AI MCP).

Everything the administrator needs to turn the connector on and hand a URL to
Claude/ChatGPT/Cursor lives here. Persisted values use ir.config_parameter so
they survive upgrades and are easy to set from data or the shell.

Audit retention and the per-user default scope are deliberately absent: this
edition keeps a fixed 30 days for everyone and applies one scope to everyone,
which is one fewer dial to get wrong. Both become settings in AI MCP
Governance, where there is something to tune them against.
"""
from odoo import api, fields, models

from .mcp_url import PARAM_PUBLIC_BASE_URL, public_base_url


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # -- master switches ----------------------------------------------------
    mcp_enabled = fields.Boolean(
        string="Enable MCP Server",
        config_parameter="ai_mcp.enabled", default=True)
    mcp_oauth_enabled = fields.Boolean(
        string="Sign in with Odoo (OAuth 2.1)",
        config_parameter="ai_mcp.oauth_enabled", default=True,
        help="The recommended, browser-based connect flow. No API keys, no "
             "config files - the user just clicks Allow.")
    mcp_dynamic_registration = fields.Boolean(
        string="Allow dynamic client registration",
        config_parameter="ai_mcp.dynamic_registration", default=True,
        help="RFC 7591, deprecated by the MCP specification in favour of Client "
             "ID Metadata Documents. Kept for clients that cannot host a "
             "metadata document. Disable to lock the server to CIMD and "
             "pre-registered clients.")
    mcp_allowed_origins = fields.Char(
        string="Allowed browser origins",
        config_parameter="ai_mcp.allowed_origins",
        help="Comma-separated origins permitted to call the MCP endpoint from "
             "a browser, e.g. https://app.example.com. Empty is the safe "
             "default: MCP clients are not browsers, and accepting any origin "
             "exposes the endpoint to DNS-rebinding attacks. This server's own "
             "origin is always allowed.")

    # -- token lifetimes ----------------------------------------------------
    mcp_access_token_ttl = fields.Integer(
        string="Access token lifetime (seconds)",
        config_parameter="ai_mcp.access_token_ttl", default=3600)
    mcp_refresh_token_ttl = fields.Integer(
        string="Refresh token lifetime (seconds)",
        config_parameter="ai_mcp.refresh_token_ttl", default=2592000)

    mcp_public_base_url = fields.Char(
        string="Public address override",
        config_parameter=PARAM_PUBLIC_BASE_URL,
        help="Leave empty unless this server cannot work out its own public "
             "address. It normally can: it reads the proxy's forwarded "
             "headers, so a TLS-terminating reverse proxy is handled without "
             "configuration. Set this only for a front end that announces "
             "nothing at all, e.g. https://erp.example.com — it then wins over "
             "everything, including web.base.url.")

    # -- read-only connection info (the address clients actually reach) -----
    mcp_base_url = fields.Char(compute="_compute_mcp_urls")
    mcp_endpoint_url = fields.Char(compute="_compute_mcp_urls")
    mcp_metadata_url = fields.Char(compute="_compute_mcp_urls")

    @api.depends_context("uid")
    def _compute_mcp_urls(self):
        # Not web.base.url: behind a proxy that routinely holds an http://
        # spelling of the right host, and an http:// URL copied from here is
        # one every AI client refuses. See models/mcp_url.py.
        base = public_base_url(self.env)
        for rec in self:
            rec.mcp_base_url = base
            rec.mcp_endpoint_url = f"{base}/mcp"
            rec.mcp_metadata_url = f"{base}/.well-known/oauth-protected-resource"

    def action_open_connect(self):
        """Open the Connect screen — readiness checks, URL, QR and live status."""
        return self.env["ir.actions.actions"]._for_xml_id(
            "ai_mcp.mcp_connect_action")
