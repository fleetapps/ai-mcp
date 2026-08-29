# -*- coding: utf-8 -*-
"""The Connect screen's data layer.

The whole screen is rendered from get_state(), so testing that payload tests
the screen's behaviour without touching the browser. The design rule it exists
to enforce: a user must never learn something is wrong by switching to Claude
and watching it fail.
"""
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from ..models.tools_crypto import new_secret


@tagged("post_install", "-at_install")
class TestConnectState(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Connect = cls.env["mcp.connect"]
        cls.admin = cls.env.ref("base.user_admin")
        cls.scope = cls.env.ref("ai_mcp.scope_readonly_default")

    def _checks(self, state):
        return {c["key"]: c for c in state["checks"]}

    # -------------------------------------------------------------- payload
    def test_state_has_everything_the_screen_renders(self):
        state = self.Connect.get_state()
        for key in ("checks", "ready", "urls", "status", "connections",
                    "prompts", "clients", "can_admin", "upgrade", "qr"):
            self.assertIn(key, state)
        self.assertTrue(state["urls"]["mcp"].endswith("/mcp"))

    def test_the_qr_can_be_left_out_of_a_poll(self):
        """It is the most expensive thing here and cannot change between two
        polls of the same page."""
        self.assertNotIn("qr", self.Connect.get_state(with_qr=False))

    def test_get_state_makes_no_outbound_request(self):
        """It is polled every few seconds - a network call here would hang it."""
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_mcp.reachability_state", "")
        self.assertEqual(self._checks(self.Connect.get_state())["reach"]["state"],
                         "unknown")

    # ------------------------------------------------------------ readiness
    def test_localhost_base_url_is_flagged_with_a_fix(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "http://localhost:8069")
        with patch("odoo.http.request", None):
            check = self._checks(self.Connect.get_state())["base_url"]
        self.assertEqual(check["state"], "fail")
        self.assertTrue(check["fix_action"], "a failing check must offer a fix")

    def test_plain_http_base_url_is_flagged(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "http://erp.example.com")
        with patch("odoo.http.request", None):
            self.assertEqual(
                self._checks(self.Connect.get_state())["base_url"]["state"], "fail")

    def test_public_https_base_url_passes(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "https://erp.example.com")
        with patch("odoo.http.request", None):
            self.assertEqual(
                self._checks(self.Connect.get_state())["base_url"]["state"], "ok")

    def test_every_failing_check_explains_itself(self):
        """A blocker the user cannot act on is just noise."""
        self.env["ir.config_parameter"].sudo().set_param("web.base.url", "")
        with patch("odoo.http.request", None):
            checks = self.Connect.get_state()["checks"]
        for check in checks:
            if check["state"] == "fail":
                self.assertTrue(
                    check["detail"],
                    "check '%s' fails without explaining why" % check["key"])

    def test_a_warning_never_blocks_connecting(self):
        """`ready` is what the screen gates on; only real blockers may clear it."""
        state = self.Connect.get_state()
        warns = [c for c in state["checks"] if c["state"] == "warn"]
        fails = [c for c in state["checks"] if c["state"] == "fail"]
        if warns and not fails:
            self.assertTrue(state["ready"])

    # --------------------------------------------------------- live status
    def test_status_waits_before_any_connection(self):
        self.env["mcp.oauth.token"].sudo().search([]).unlink()
        self.assertEqual(self.Connect.get_state()["status"]["state"], "waiting")

    def test_status_flips_to_connected_when_a_token_lands(self):
        self._token()
        state = self.Connect.get_state()
        self.assertEqual(state["status"]["state"], "connected")
        self.assertTrue(state["connections"])

    def test_fresh_token_with_no_last_used_does_not_break_status(self):
        """last_used is empty until the first call; the status must survive it."""
        self._token()
        self.assertEqual(self.Connect.get_state()["status"]["state"], "connected")

    def test_revoke_removes_the_connection_and_says_so(self):
        token = self._token()
        result = self.Connect.revoke(token.id)
        self.assertTrue(result["ok"])
        self.assertFalse([c for c in result["state"]["connections"]
                          if c["id"] == token.id])

    def test_revoking_someone_elses_connection_reports_failure(self):
        """It used to refuse silently while the screen announced success - on a
        security control that is not a cosmetic problem."""
        other = self.env["res.users"].create({
            "name": "MCP Other", "login": "mcp_other_user",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        token = self._token()
        result = self.Connect.with_user(other).revoke(token.id)
        self.assertFalse(result["ok"])
        self.assertTrue(result["message"])

    def test_revoke_all_disconnects_everything(self):
        self._token()
        self._token()
        self.assertFalse(self.Connect.revoke_all()["connections"])

    def _token(self):
        client = self.env["mcp.oauth.client"].search([], limit=1) or \
            self.env["mcp.oauth.client"].create({
                "name": "TEST client", "client_id": "mcpc-connect-test",
                "redirect_uris": "https://x.example/cb"})
        return self.env["mcp.oauth.token"].issue(
            new_secret(prefix="mcpat-"), new_secret(prefix="mcprt-"), {
                "client_id": client.client_id,
                "client_name": client.name,
                "user_id": self.admin.id,
                "scope_id": self.scope.id,
                "resource": "https://host/mcp",
                "scope": "odoo:read",
            })

    # ------------------------------------------------------------- content
    def test_prompts_are_limited_to_models_in_the_matrix(self):
        """A chip that fails in the assistant reads as a broken product."""
        prompts = [p["text"] for p in self.Connect.get_state()["prompts"]]
        readable = set(self.env["mcp.scope.line"].sudo().search(
            [("can_read", "=", True)]).mapped("model_name"))
        if "account.move" not in readable:
            self.assertFalse([p for p in prompts if "invoices" in p])

    def test_prompts_never_offer_a_change(self):
        """Nothing here can write, so nothing here may suggest writing."""
        for prompt in self.Connect.get_state()["prompts"]:
            self.assertFalse(prompt["text"].startswith("Create"))

    def test_prompts_that_need_no_model_are_always_offered(self):
        """However tight the scope, the screen must never show zero prompts."""
        self.env["mcp.scope.line"].sudo().search([]).unlink()
        self.assertTrue(self.Connect.get_state()["prompts"])

    def test_every_client_guide_has_steps(self):
        for guide in self.Connect.get_state()["clients"]:
            self.assertTrue(guide["steps"], guide["key"])
            self.assertTrue(guide["name"])

    # -------------------------------------------------------------- upgrade
    def test_the_upgrade_note_is_shown_to_an_administrator(self):
        upgrade = self.Connect.get_state()["upgrade"]
        self.assertTrue(upgrade["show"])
        self.assertTrue(upgrade["url"])
        self.assertTrue(upgrade["dashboards_url"])

    # ------------------------------------------------------------ self test
    def test_self_test_runs_through_the_real_engine_and_is_audited(self):
        """The only thing on the screen that proves the whole chain answers."""
        before = self.env["mcp.audit.log"].search_count(
            [("transport", "=", "selftest")])
        result = self.Connect.run_self_test()
        self.assertIn("ok", result)
        self.assertEqual(
            self.env["mcp.audit.log"].search_count(
                [("transport", "=", "selftest")]),
            before + 1,
            "a self-test must be logged honestly, not silently")

    # ------------------------------------------------------------ fix guards
    def test_only_a_settings_admin_can_pin_the_public_address(self):
        employee = self.env["res.users"].create({
            "name": "MCP Fixless", "login": "mcp_fixless",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            self.Connect.with_user(employee).fix_base_url()
