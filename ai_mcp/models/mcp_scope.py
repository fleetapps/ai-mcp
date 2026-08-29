# -*- coding: utf-8 -*-
"""Governance scope: which models an assistant may read, and nothing wider.

A scope answers two orthogonal questions for a connection:

1. *Which MCP tools are even visible?*  -> capability_ids
2. *Which data may those tools touch?*  -> line_ids (one row per model)

Both are ANDed with the acting user's native Odoo permissions, so a scope can
only ever *narrow* access, never widen it. This is defence-in-depth: even a
misconfigured scope cannot hand an AI more than the underlying user already has.

This edition is read-only by construction. There is no create/update/delete
switch on a row, because there is no write tool to honour one - see
``models/mcp_capability.py``. Per-operation permissions, field blacklists,
record domains, method allow-lists and the human approval gate live in AI MCP
Governance, which adds them to these same models.
"""
from odoo import fields, models

# Fixed safety limits. Both are deliberately constants rather than per-scope
# settings: they exist to stop a run-away query on a 100k-row model, and a
# sensible ceiling serves that without another dial to get wrong. AI MCP
# Governance turns them into per-scope fields for deployments that need to
# raise or lower them.
MAX_RECORDS = 200
RATE_LIMIT_PER_HOUR = 500

# The models a business actually asks questions about. Referencing any of these
# from a data file would break installation on a database without that app, so
# they are resolved at run time instead - ir.model._get returns an empty
# recordset for a model that is not installed, and the absent ones are skipped.
# Ordered deliberately: sales first, because that is what the first question is
# almost always about.
SUGGESTED_MODELS = (
    "sale.order",
    "sale.order.line",
    "purchase.order",
    "purchase.order.line",
    "account.move",
    "account.move.line",
    "product.template",
    "product.product",
    "stock.quant",
    "stock.picking",
    "crm.lead",
    "project.project",
    "project.task",
    "hr.employee",
)


class MCPScope(models.Model):
    _name = "mcp.scope"
    _description = "MCP Governance Scope"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    description = fields.Text(
        translate=True,
        help="Shown to admins; not exposed to the AI client.")
    capability_ids = fields.Many2many(
        "mcp.capability", string="Capabilities",
        help="Which capability bundles (and therefore which tools) this scope "
             "exposes. Empty means every installed capability.")
    line_ids = fields.One2many("mcp.scope.line", "scope_id", copy=True)
    line_count = fields.Integer(compute="_compute_line_count")

    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def allowed_capabilities(self):
        """Effective capabilities: explicit selection, else all installed."""
        self.ensure_one()
        if self.capability_ids:
            return self.capability_ids.filtered("active")
        return self.env["mcp.capability"].search([("active", "=", True)])

    def line_for_model(self, model_name):
        """The matrix row governing this model, or an empty recordset.

        Filtered on `active` explicitly rather than relying on the one2many to
        do it: a caller running with ``active_test=False`` in context would
        otherwise resolve an archived row and be granted access an
        administrator believed they had suspended.
        """
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.active and l.model_name == model_name)[:1]

    # ------------------------------------------------------------ bulk adding
    def existing_model_ids(self):
        """Model ids already on this scope, *including archived rows*.

        The uniqueness constraint is enforced in the database, which does not
        know about archiving. Reading ``line_ids`` would silently hide an
        archived row and the insert would then fail on that constraint.
        """
        self.ensure_one()
        return set(self.env["mcp.scope.line"].with_context(active_test=False)
                   .search([("scope_id", "=", self.id)]).mapped("model_id").ids)

    def add_models(self, model_names):
        """Add matrix rows for `model_names`, skipping what is already there.

        Safe to re-run and safe to hand a model that is not installed: an
        absent model resolves to an empty recordset and is skipped. Returns the
        rows actually created, so a caller can report a count honestly.
        """
        self.ensure_one()
        seen = self.existing_model_ids()
        values = []
        for name in model_names:
            model = self.env["ir.model"]._get(name)
            # `seen` also absorbs duplicates inside model_names itself, which
            # would otherwise hit the constraint on the second row.
            if not model or model.id in seen:
                continue
            seen.add(model.id)
            values.append({
                "scope_id": self.id,
                "model_id": model.id,
                "can_read": True,
            })
        Line = self.env["mcp.scope.line"]
        return Line.create(values) if values else Line.browse()

    def readable_model_names(self):
        """Models this scope can currently read, deterministically ordered.

        Sorted because MCP asks for a deterministic tool list, and these names
        are spelled out in the read tools' descriptions.
        """
        self.ensure_one()
        return sorted(set(self.line_ids
                          .filtered(lambda l: l.active and l.can_read)
                          .mapped("model_name")))


class MCPScopeLine(models.Model):
    """One model's permissions inside a scope - the row of the access matrix.

    Enforcement is always ``min(this row, the acting user's Odoo rights)``. A
    row can only ever *narrow* what the bound user could already do; it can
    never widen it. That is why this is safe to expose as a flat, quickly
    editable matrix: the worst a misconfiguration can do is grant something the
    user already had.
    """
    _name = "mcp.scope.line"
    _description = "MCP Model Permission"
    _order = "scope_id, model_name"
    _rec_name = "model_name"

    scope_id = fields.Many2one(
        "mcp.scope", required=True, ondelete="cascade", index=True)
    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    model_name = fields.Char(related="model_id.model", store=True, index=True)
    # Not stored: ir.model.name is translatable, and a stored related copy of a
    # translated field goes stale per-language. Display only.
    model_label = fields.Char(
        related="model_id.name", string="Model", readonly=True)
    active = fields.Boolean(
        default=True,
        help="Archive a row to suspend all AI access to this model without "
             "losing how it was configured.")
    can_read = fields.Boolean(string="Read", default=True)

    _model_uniq = models.Constraint(
        "UNIQUE (scope_id, model_id)",
        "Each model can appear only once per scope.")

    def action_open_scope(self):
        """Jump from a matrix row to the scope that owns it."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mcp.scope",
            "res_id": self.scope_id.id,
            "view_mode": "form",
        }
