# -*- coding: utf-8 -*-
"""The tool engine: what it advertises, what it refuses, and what it returns.

Two properties matter more than the rest and are tested first. A reply that
was capped must say so — a confidently wrong answer is worse than a refusal —
and a verb that writes must never execute here, because this edition has no
governance to put in front of it.
"""
import json

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env["mcp.engine"]
        cls.scope = cls.env.ref("ai_mcp.scope_readonly_default")

    def _call(self, name, args=None):
        result = self.engine.call_tool(self.scope, name, args or {}, {})
        return result, json.loads(result["content"][0]["text"])

    # ------------------------------------------------------------- truncation
    def test_a_capped_search_says_it_was_capped(self):
        """The highest-severity failure this engine can have.

        The cap protects the database; a *silent* cap makes the assistant
        report a full page as the complete answer. `has_more` is what lets it
        say the answer is partial instead.
        """
        self.env["res.partner"].create([
            {"name": "TEST cap %s" % i} for i in range(4)])
        _, payload = self._call("search_records", {"model": "res.partner", "limit": 2})
        self.assertEqual(payload["limit"], 2)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["records"]), 2,
                         "the extra probe row must never reach the client")
        self.assertTrue(payload["has_more"])

    def test_an_uncapped_search_reports_has_more_false(self):
        _, payload = self._call(
            "search_records",
            {"model": "res.country", "domain": "[('code', '=', 'BE')]"})
        self.assertFalse(payload["has_more"])
        self.assertEqual(payload["count"], len(payload["records"]))

    def test_read_group_reports_truncation_too(self):
        """A report missing its last groups still totals up and looks complete."""
        _, payload = self._call("read_group", {
            "model": "res.partner", "group_by": "country_id", "limit": 1})
        self.assertIn("has_more", payload)
        self.assertEqual(payload["limit"], 1)

    def test_the_row_cap_is_a_ceiling_a_client_cannot_raise(self):
        _, payload = self._call(
            "search_records", {"model": "res.country", "limit": 99999})
        self.assertLessEqual(payload["limit"], 200)

    # ------------------------------------------------------------ write guard
    def test_a_writing_verb_is_refused_rather_than_executed(self):
        """Fail-closed: a registry row must not be able to grant a write.

        A module that adds a mutating handler without adding the governance to
        go with it gets a refusal, not an unaudited, ungated write.
        """
        tool = self.env["mcp.tool"].search([("name", "=", "search_records")])
        with self.assertRaises(AccessError):
            # Simulate a downstream module having classified this as writing.
            self.engine._check_write_permitted(
                tool.new({"name": "x", "writes": True}), {})

    def test_no_shipped_tool_writes(self):
        self.assertFalse(self.env["mcp.tool"].search([("writes", "=", True)]))

    # --------------------------------------------------------------- listing
    def test_list_tools_carries_annotations_and_a_stable_order(self):
        first = [t["name"] for t in self.engine.list_tools(self.scope)]
        second = [t["name"] for t in self.engine.list_tools(self.scope)]
        self.assertEqual(first, second, "MCP asks for a deterministic tool list")
        for tool in self.engine.list_tools(self.scope):
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["openWorldHint"])
            self.assertNotIn("destructiveHint", tool["annotations"],
                             "meaningless while readOnlyHint is true")

    def test_read_tools_name_the_models_this_scope_can_reach(self):
        """So the first question does not cost a discovery round trip."""
        tools = {t["name"]: t["description"]
                 for t in self.engine.list_tools(self.scope)}
        self.assertIn("res.partner", tools["search_records"])
        self.assertNotIn("res.partner", tools["get_schema"],
                         "only the model-aware verbs carry the hint")

    def test_list_models_hides_archived_rows(self):
        """Advertising one promises access every later call refuses."""
        line = self.scope.line_for_model("res.country")
        line.active = False
        _, payload = self._call("list_models")
        self.assertNotIn("res.country",
                         [m["model"] for m in payload["models"]])
        line.active = True

    # ------------------------------------------------------------ enforcement
    def test_a_model_outside_the_matrix_is_refused_with_a_fix(self):
        result, payload = self._call(
            "search_records", {"model": "ir.config_parameter"})
        self.assertTrue(result["isError"])
        self.assertIn("ir.config_parameter", payload["message"])
        self.assertIn("Model Permissions", payload["message"],
                      "a refusal has to name the screen that fixes it")

    def test_an_unknown_model_is_refused_clearly(self):
        result, payload = self._call("search_records", {"model": "no.such.model"})
        self.assertTrue(result["isError"])
        self.assertIn("no model named", payload["message"])

    def test_an_unknown_tool_is_refused(self):
        result, _payload = self._call("definitely_not_a_tool")
        self.assertTrue(result["isError"])

    # ----------------------------------------------------------------- audit
    def test_every_call_lands_in_the_audit_log(self):
        before = self.env["mcp.audit.log"].search_count([])
        self._call("list_models")
        self.assertEqual(self.env["mcp.audit.log"].search_count([]), before + 1)

    def test_a_refused_call_is_audited_too(self):
        before = self.env["mcp.audit.log"].search_count([("status", "=", "error")])
        self._call("search_records", {"model": "ir.config_parameter"})
        self.assertEqual(
            self.env["mcp.audit.log"].search_count([("status", "=", "error")]),
            before + 1)

    # ------------------------------------------------------ prompts/resources
    def test_prompts_and_resources_answer_empty_rather_than_failing(self):
        """The transport advertises both; answering 'method not found' would
        make a client believe the server is broken rather than bare."""
        self.assertEqual(self.engine.list_prompts(self.scope), [])
        self.assertEqual(self.engine.list_resources(self.scope), [])
