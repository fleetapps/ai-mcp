# -*- coding: utf-8 -*-
"""Resolve the governance scope that applies to a user's AI session.

With OAuth there is no per-connection key to hang a scope on: the user signs in
as themselves, so the scope has to be resolved from the user. This edition
resolves it to the single active scope, which is the same one for everybody.

Per-user assignment - a sales team governed differently from finance - is what
AI MCP Pro adds, by putting an ``mcp_scope_id`` on the user and
overriding the method below.
"""
from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def mcp_effective_scope(self):
        """The governance scope for this user's AI session.

        Ordered by id so the answer is stable rather than dependent on the
        order rows happen to come back in: two administrators looking at the
        same database must see the same scope in effect.
        """
        self.ensure_one()
        return self.env["mcp.scope"].sudo().search(
            [("active", "=", True)], order="id", limit=1)
