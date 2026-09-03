# -*- coding: utf-8 -*-
"""Bulk-adding models to a scope.

``add_models`` is reached from three places - the install hook, the Connect
screen's button and the picker wizard - so the rules it enforces (skip what is
already there, skip what is not installed, never duplicate) are worth pinning
once here rather than three times over.
"""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAddModels(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.scope = cls.env["mcp.scope"].create({"name": "TEST add models"})

    def _names(self):
        return set(self.scope.line_ids.mapped("model_name"))

    def test_adds_rows_with_read_access(self):
        lines = self.scope.add_models(["res.partner", "res.country"])
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(lines.mapped("can_read")))
        self.assertEqual(self._names(), {"res.partner", "res.country"})

    def test_a_model_that_is_not_installed_is_skipped_silently(self):
        """The whole reason this lives in code and not a data file.

        Naming a model from an uninstalled app in XML breaks the install; here
        it resolves to an empty recordset and is passed over.
        """
        lines = self.scope.add_models(
            ["res.partner", "definitely.not.a.model", "another.absent.model"])
        self.assertEqual(len(lines), 1)
        self.assertEqual(self._names(), {"res.partner"})

    def test_re_running_adds_nothing_and_does_not_raise(self):
        self.scope.add_models(["res.partner"])
        self.assertFalse(self.scope.add_models(["res.partner"]))
        self.assertEqual(len(self.scope.line_ids), 1)

    def test_duplicates_inside_one_call_are_collapsed(self):
        """Otherwise the second row hits the uniqueness constraint mid-create."""
        lines = self.scope.add_models(["res.partner", "res.partner"])
        self.assertEqual(len(lines), 1)

    def test_an_archived_row_still_counts_as_present(self):
        """The DB constraint does not know about archiving.

        Reading line_ids would hide the archived row and the insert would then
        fail on the unique index instead of being skipped.
        """
        line = self.scope.add_models(["res.partner"])
        line.active = False
        self.assertFalse(self.scope.add_models(["res.partner"]))

    def test_readable_model_names_are_sorted_and_skip_archived(self):
        """MCP asks for a deterministic tool list, and these names go in it."""
        self.scope.add_models(["res.country", "res.partner", "res.currency"])
        self.assertEqual(self.scope.readable_model_names(),
                         ["res.country", "res.currency", "res.partner"])
        self.scope.line_for_model("res.currency").active = False
        self.assertEqual(self.scope.readable_model_names(),
                         ["res.country", "res.partner"])

    def test_line_for_model_ignores_archived_rows(self):
        """A caller running with active_test=False must not resolve one."""
        line = self.scope.add_models(["res.partner"])
        line.active = False
        scope = self.scope.with_context(active_test=False)
        self.assertFalse(scope.line_for_model("res.partner"))
