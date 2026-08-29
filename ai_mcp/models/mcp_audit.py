# -*- coding: utf-8 -*-
"""Immutable audit trail - one row per tool call.

Every AI action is attributable to a real user, an auth source, a model and a
timestamp, with a rough token estimate for cost visibility. Rows are read-only
in the UI (no write access is granted anywhere) and purged on a fixed
retention.

The trail itself is deliberately not a paid feature: a connector that lets an
assistant read an ERP without recording what it read is not a cheaper product,
it is an unaccountable one. What AI MCP Governance adds is the *compliance*
layer on top - the instance-wide view across every user, a configurable
retention window, and reporting.
"""
from datetime import timedelta

from odoo import api, fields, models

# How long a row survives. Long enough to answer "what did my assistant do last
# month?", short enough that this is not an audit archive - which is a
# retention policy question, and therefore a Governance one.
RETENTION_DAYS = 30


class MCPAuditLog(models.Model):
    _name = "mcp.audit.log"
    _description = "MCP Audit Log"
    _order = "create_date desc"

    oauth_token_id = fields.Many2one("mcp.oauth.token", index=True, ondelete="set null")
    user_id = fields.Many2one("res.users", index=True, ondelete="set null")
    scope_id = fields.Many2one("mcp.scope", index=True, ondelete="set null")
    tool = fields.Char(index=True)
    model_name = fields.Char(string="Model", index=True)
    transport = fields.Selection(
        [("http", "Streamable HTTP"), ("oauth", "OAuth"),
         # A call the user made from the Connect screen to prove the chain
         # works. It runs through the real engine and every real gate, so it is
         # audited like any other call - and labelled honestly, so nobody
         # mistakes it later for something an assistant did.
         ("selftest", "Self-test")],
        default="http")
    remote_addr = fields.Char(string="Client IP")
    args_json = fields.Text(string="Arguments")
    status = fields.Selection(
        [("ok", "OK"), ("error", "Error"), ("denied", "Denied")], index=True,
        help="'Denied' means the call was refused before it ran.")
    duration_ms = fields.Integer(string="Duration (ms)")
    tokens_est = fields.Integer(
        string="Tokens (est.)",
        help="Rough size-based token estimate for cost tracking.")

    @api.model
    def cron_purge(self):
        cutoff = fields.Datetime.now() - timedelta(days=self._retention_days())
        self.sudo().search([("create_date", "<", cutoff)]).unlink()

    @api.model
    def _retention_days(self):
        """How many days of history to keep. Overridden to read a setting."""
        return RETENTION_DAYS
