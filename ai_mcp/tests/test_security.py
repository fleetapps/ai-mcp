# -*- coding: utf-8 -*-
"""Who can see and use the app at all.

An earlier build shipped with nothing implying group_mcp_user, so the menu was
invisible to every internal user and the product's whole promise was
unreachable for anyone an administrator had not hand-picked. These tests pin
the fix down, and pin down that it granted navigation only.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEmployeeAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["res.users"].create({
            "name": "MCP Plain Employee",
            "login": "mcp_plain_employee",
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def test_every_employee_holds_the_mcp_user_role(self):
        """Nobody has to find a group they were never told about."""
        self.assertTrue(self.employee.has_group("ai_mcp.group_mcp_user"))

    def test_an_employee_is_not_made_an_administrator(self):
        self.assertFalse(
            self.employee.has_group("ai_mcp.group_mcp_admin"),
            "the admin role must stay something an administrator grants")

    def test_an_employee_can_open_the_connect_screen(self):
        state = self.env["mcp.connect"].with_user(self.employee).get_state()
        self.assertIn("urls", state)
        self.assertFalse(state["can_admin"])

    def test_an_employee_cannot_widen_the_matrix(self):
        """Navigation, not authority."""
        connect = self.env["mcp.connect"].with_user(self.employee)
        with self.assertRaises(AccessError):
            connect.add_suggested_models()

    def test_an_employee_cannot_edit_the_permission_matrix(self):
        with self.assertRaises(AccessError):
            self.env["mcp.scope.line"].with_user(self.employee).create({
                "scope_id": self.env.ref("ai_mcp.scope_readonly_default").id,
                "model_id": self.env["ir.model"]._get("res.users").id,
            })

    def test_the_upgrade_note_is_not_shown_to_someone_who_cannot_act_on_it(self):
        connect = self.env["mcp.connect"].with_user(self.employee)
        self.assertFalse(connect.get_state()["upgrade"]["show"])
