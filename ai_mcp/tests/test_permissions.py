# -*- coding: utf-8 -*-
"""The classification seam every extension has to pass through.

Tools are data. A module can add a ``mcp.tool`` row pointing at a new handler
without touching a line of this module's code — which is the point, and also
the one way something mutating could slip in classified as a read. These tests
fail when a handler exists that nobody has classified, so the gap is found at
build time rather than the first time an assistant deletes something.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from ..models.mcp_capability import HANDLER_SELECTION, WRITE_HANDLERS

# Every verb this edition implements, and the fact that all of them read.
READ_HANDLERS = {
    "list_capabilities", "list_models", "get_schema",
    "search_records", "count_records", "name_search", "read_group",
}


@tagged("post_install", "-at_install")
class TestHandlerClassification(TransactionCase):

    def test_every_selectable_handler_is_classified(self):
        """Neither read nor write means nothing decided whether it mutates."""
        declared = {key for key, _label in HANDLER_SELECTION}
        unclassified = declared - READ_HANDLERS - set(WRITE_HANDLERS)
        self.assertFalse(
            unclassified,
            "these handlers are classified neither read nor write: %s"
            % sorted(unclassified))

    def test_every_selectable_handler_is_implemented(self):
        """A tool row can only name a verb the engine actually has."""
        engine = self.env["mcp.engine"]
        for key, _label in HANDLER_SELECTION:
            self.assertTrue(
                hasattr(engine, "_handler_%s" % key),
                "mcp.tool.handler offers '%s' with no _handler_%s on the engine"
                % (key, key))

    def test_no_engine_handler_is_missing_from_the_selection(self):
        """The mirror of the check above: an implemented verb nobody can pick
        is dead code, and one that a later release exposes by accident has
        never been through the classification above."""
        engine = self.env["mcp.engine"]
        implemented = {name[len("_handler_"):] for name in dir(engine)
                       if name.startswith("_handler_")}
        declared = {key for key, _label in HANDLER_SELECTION}
        self.assertFalse(
            implemented - declared,
            "implemented but not selectable: %s" % sorted(implemented - declared))

    def test_this_edition_declares_no_writing_verb(self):
        self.assertEqual(set(WRITE_HANDLERS), set())
        self.assertEqual({key for key, _label in HANDLER_SELECTION},
                         READ_HANDLERS)


@tagged("post_install", "-at_install")
class TestScopeEnforcement(TransactionCase):
    """The matrix narrows; it never widens."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env["mcp.engine"]
        cls.scope = cls.env["mcp.scope"].create({"name": "TEST enforcement"})

    def test_a_scope_with_no_rows_permits_nothing(self):
        with self.assertRaises(AccessError):
            self.engine._require_line(self.scope, "res.partner", "read")

    def test_a_row_with_read_off_permits_nothing(self):
        line = self.scope.add_models(["res.partner"])
        line.can_read = False
        with self.assertRaises(AccessError):
            self.engine._require_line(self.scope, "res.partner", "read")

    def test_an_archived_row_permits_nothing(self):
        line = self.scope.add_models(["res.country"])
        line.active = False
        with self.assertRaises(AccessError):
            self.engine._require_line(self.scope, "res.country", "read")

    def test_a_readable_row_resolves(self):
        self.scope.add_models(["res.currency"])
        line = self.engine._require_line(self.scope, "res.currency", "read")
        self.assertEqual(line.model_name, "res.currency")

    def test_the_matrix_cannot_grant_what_the_user_lacks(self):
        """Every call runs as the signed-in user, so their own rights are the
        floor. A scope opened onto res.users must not let a plain employee
        read another user's record through the connector."""
        employee = self.env["res.users"].create({
            "name": "MCP Enforcement Employee",
            "login": "mcp_enforcement_employee",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.scope.add_models(["ir.config_parameter"])
        result = self.engine.with_user(employee).call_tool(
            self.scope, "search_records", {"model": "ir.config_parameter"}, {})
        self.assertTrue(
            result["isError"],
            "the ORM's own access check must still refuse this")
