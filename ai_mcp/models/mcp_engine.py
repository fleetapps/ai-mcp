# -*- coding: utf-8 -*-
"""Tool execution engine - every call is scope-checked, ACL-checked, audited.

The controller has already switched ``self.env`` to the acting user, so native
Odoo security (ir.model.access + ir.rule + field groups + multi-company record
rules) is enforced *underneath* everything here. The engine adds the governance
layer on top: capability gating, per-model read scope, row caps, rate limiting
and the audit trail.

Handlers are generic verbs selected by data (see mcp.tool.handler), so partners
extend the connector with new tool *records*, or override/add a `_handler_*`
method by inheriting this model - no controller changes, upgrade-safe.

Every verb here reads. A module that adds a mutating verb has two things to do:
declare it in ``mcp.tool._write_handlers()`` and override
``_check_write_permitted`` below, which refuses outright by default. Failing to
do either is a fail-closed, not a silent grant.

ORM reference (search_read / _read_group / name_search / fields_get / domains):
https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html
"""
import ast
import datetime
import json
import logging
import time

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .mcp_scope import MAX_RECORDS, RATE_LIMIT_PER_HOUR

_logger = logging.getLogger(__name__)
MAX_ARGS_LOG = 4000

# Read verbs whose usefulness depends on *which* models this connection can
# reach, so their descriptions name them (see _tool_description).
MODEL_AWARE_HANDLERS = {
    "search_records", "count_records", "name_search", "read_group",
}
# How many model names to spell out before summarising the rest. Long enough to
# cover a normal scope, short enough not to bloat every tool description.
MODELS_IN_DESCRIPTION = 12

# OAuth scope name, duplicated from the controller to keep the model layer
# import-free of controllers.
SCOPE_READ = "odoo:read"


class MCPEngine(models.AbstractModel):
    _name = "mcp.engine"
    _description = "MCP Engine"

    # ================================================================ tools/list
    @api.model
    def list_tools(self, scope):
        """Advertise every tool this governance scope permits."""
        # Governance config is read with elevated rights (it is not sensitive
        # business data); actual record access below always runs as the user.
        scope = scope.sudo()
        hint = self._model_hint(scope)
        model_aware = self._model_aware_handlers()
        tools = []
        for cap in scope.allowed_capabilities():
            for tool in cap.tool_ids.filtered("active"):
                tools.append({
                    "name": tool.name,
                    "title": tool.title or tool.name.replace("_", " ").title(),
                    "description": self._tool_description(tool, hint, model_aware),
                    "inputSchema": self._input_schema(tool),
                    "annotations": self._annotations(tool),
                })
        return tools

    # ------------------------------------------------- per-scope descriptions
    def _model_hint(self, scope):
        """Name the models this scope can read, for the read tools to carry.

        Without it every connection is advertised the same generic description
        and the assistant has to spend a ``list_capabilities`` (then usually a
        ``list_models``) round trip before it can answer the first question -
        which the user experiences as the connector being slow to wake up.

        Varying *tool* output by the presented authorization is explicitly
        permitted (MCP 2026-07-28 tools/list: "The set MAY vary by the
        authorization presented on the request"), and the same section asks for
        a deterministic order, which the sort below provides. Note this must
        never move into ``server/discover``: that result is returned with
        ``cacheScope: "public"`` and would be shared across users.
        """
        names = scope.readable_model_names()
        if not names:
            return ""
        shown = names[:MODELS_IN_DESCRIPTION]
        listed = ", ".join(shown)
        if len(names) > len(shown):
            return str(_(
                " Models readable on this connection include %(models)s and "
                "%(more)s more — call list_models for the full set.",
                models=listed, more=len(names) - len(shown)))
        return str(_(" Models readable on this connection: %s.") % listed)

    @api.model
    def _model_aware_handlers(self):
        """Verbs whose usefulness depends on which models are in scope.

        Overridable so a downstream module's read verbs can carry the same
        per-scope model hint instead of shipping a generic description.
        """
        return set(MODEL_AWARE_HANDLERS)

    def _tool_description(self, tool, hint, model_aware=None):
        """The description as the client sees it: generic text plus this scope."""
        if model_aware is None:
            model_aware = self._model_aware_handlers()
        if hint and tool.handler in model_aware:
            return "%s%s" % (tool.description, hint)
        return tool.description

    def _annotations(self, tool):
        """MCP tool behaviour hints (2026-07-28 ToolAnnotations).

        Clients use these to decide when to put a human in the loop.
        ``destructiveHint`` and ``idempotentHint`` are defined as meaningful
        only when ``readOnlyHint`` is false, so they are omitted for read tools
        rather than sent as noise. ``openWorldHint`` is false throughout: every
        tool here acts on this one Odoo database and nothing outside it.
        """
        read_only = not tool.writes
        annotations = {"readOnlyHint": read_only, "openWorldHint": False}
        if not read_only:
            annotations["destructiveHint"] = True
            annotations["idempotentHint"] = False
        return annotations

    def _input_schema(self, tool):
        try:
            schema = json.loads(tool.input_schema or "")
        except (ValueError, TypeError):
            schema = None
        if not isinstance(schema, dict) or not schema:
            return {"type": "object", "properties": {}}
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        return schema

    # ================================================================ tools/call
    @api.model
    def call_tool(self, scope, name, args, audit_ctx=None):
        audit_ctx = audit_ctx or {}
        args = args or {}
        scope = scope.sudo()  # config reads only; data ops stay as the user
        start = time.time()
        status, payload = "ok", None
        model_used = args.get("model") if isinstance(args, dict) else None
        try:
            tool = self._resolve_tool(scope, name)
            self._check_write_permitted(tool, audit_ctx)
            self._check_rate_limit(scope, audit_ctx)
            # Carry the granted OAuth scopes so a handler can explain what a
            # connection is and is not allowed to do.
            engine = self.with_context(
                mcp_granted_scopes=audit_ctx.get("granted_scopes"))
            payload = getattr(engine, f"_handler_{tool.handler}")(scope, args)
        except (AccessError, UserError) as exc:
            status, payload = "error", {"error": type(exc).__name__, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 - audited, then surfaced generically
            _logger.exception("MCP tool %s crashed", name)
            status, payload = "error", {"error": "InternalError", "message": str(exc)}
        self._audit(scope, name, model_used, args, status, start, payload, audit_ctx)
        result = {
            "content": [{"type": "text", "text": json.dumps(payload, default=str)}],
            "isError": status == "error",
        }
        if status == "ok" and isinstance(payload, dict):
            result["structuredContent"] = payload  # MCP structured output
        return result

    def _resolve_tool(self, scope, name):
        tool = self.env["mcp.tool"].sudo().search(
            [("name", "=", name), ("active", "=", True)], limit=1)
        if not tool or tool.capability_id not in scope.allowed_capabilities():
            raise AccessError(_("Tool '%s' is not available in this scope.") % name)
        return tool

    def _check_write_permitted(self, tool, audit_ctx):
        """Refuse anything that changes data. The extension point for writes.

        This edition implements only reading verbs, so a tool flagged as
        writing can only have arrived from a module that added the verb without
        adding the governance to go with it. Refusing is the fail-closed
        answer: the alternative is executing an unaudited, ungated write
        because a registry row said so.

        AI MCP Governance overrides this with the real gate - the scope's Read
        Only switch, the per-operation matrix bits, the granted ``odoo:write``
        OAuth scope, and the human approval queue.
        """
        if tool.writes:
            raise AccessError(_(
                "'%s' changes records. This edition of AI MCP is read-only; "
                "governed writes, with a per-model permission matrix and a "
                "human approval queue, are provided by AI MCP Governance."
            ) % tool.name)

    # =============================================================== rate limit
    def _check_rate_limit(self, scope, audit_ctx):
        """A fixed ceiling per connection per rolling hour.

        Counted off the audit log rather than a counter, so it survives a
        restart and cannot drift from what was actually executed.
        """
        limit = self._rate_limit(scope)
        if not limit:
            return
        since = fields.Datetime.now() - datetime.timedelta(hours=1)
        domain = [("create_date", ">=", since)]
        if audit_ctx.get("oauth_token_id"):
            domain.append(("oauth_token_id", "=", audit_ctx["oauth_token_id"]))
        else:
            domain.append(("user_id", "=", self.env.uid))
        used = self.env["mcp.audit.log"].sudo().search_count(domain)
        if used >= limit:
            raise UserError(_(
                "Rate limit reached (%s calls/hour). Try again shortly."
            ) % limit)

    def _rate_limit(self, scope):
        """The ceiling in calls/hour. Overridden to read a per-scope field."""
        return RATE_LIMIT_PER_HOUR

    # =============================================================== enforcement
    # Human labels for the matrix columns, so a refusal names the switch the
    # admin actually has to flip rather than an internal field name.
    _OP_LABELS = {"read": "Read"}

    def _require_line(self, scope, model, op):
        """Resolve the matrix row for this model, or refuse with a fix.

        The error text is deliberately specific: the most common complaint
        about ERP MCP servers is an opaque "access denied" that tells neither
        the model nor the assistant what to do about it.
        """
        if model not in self.env:
            raise AccessError(_(
                "There is no model named '%s' in this database.") % model)
        line = scope.line_for_model(model)
        label = self._OP_LABELS.get(op, op)
        if not line:
            raise AccessError(_(
                "'%(model)s' is not in the '%(scope)s' permission matrix, so "
                "no AI access to it is configured. An administrator can add it "
                "under AI MCP → Permissions → Model Permissions.",
                model=model, scope=scope.name))
        if not line["can_%s" % op]:
            raise AccessError(_(
                "The '%(scope)s' matrix does not allow %(op)s on '%(model)s'. "
                "An administrator can enable the '%(op)s' switch for that model "
                "under AI MCP → Permissions → Model Permissions.",
                scope=scope.name, op=label, model=model))
        return line

    def _scope_domain(self, line):
        """Extra domain ANDed onto every read of this model.

        Always empty here; AI MCP Governance returns the row's record domain.
        """
        return []

    def _blacklisted_fields(self, line):
        """Fields never returned for this model.

        Delegates to the matrix row so there is one answer to this question,
        whichever layer asks it - the engine here, or a module validating a
        query against the same row.
        """
        return line.blacklisted_fields()

    @staticmethod
    def _parse_domain(raw):
        if not raw:
            return []
        if isinstance(raw, (list, tuple)):
            return list(raw)
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            raise UserError(_("Invalid domain: %s") % raw)
        return list(parsed) if isinstance(parsed, (list, tuple)) else []

    def _clamp_limit(self, scope, requested):
        cap = self._max_records(scope)
        try:
            requested = int(requested) if requested else cap
        except (ValueError, TypeError):
            requested = cap
        return max(1, min(requested, cap))

    def _max_records(self, scope):
        """The row cap for one call. Overridden to read a per-scope field."""
        return MAX_RECORDS

    @staticmethod
    def _jsonify(value):
        if isinstance(value, models.BaseModel):
            if len(value) == 1:
                return {"id": value.id, "name": value.display_name}
            return [{"id": r.id, "name": r.display_name} for r in value]
        if isinstance(value, datetime.datetime):
            return fields.Datetime.to_string(value)
        if isinstance(value, datetime.date):
            return fields.Date.to_string(value)
        return value

    def _company_ctx(self, args):
        """Honour multi-company: default to all the user's companies, or a
        client-requested subset (never wider than what the user is allowed)."""
        allowed = self.env.user.company_ids.ids
        requested = args.get("company_ids")
        if requested:
            requested = [c for c in requested if c in allowed]
        return {"allowed_company_ids": requested or allowed}

    # ================================================================= handlers
    def _handler_list_capabilities(self, scope, args):
        """Describe what this connection can do.

        A capability that comes back with an empty tool list and no explanation
        reads exactly like a broken connector, so anything unusable says which
        switch would restore it and who can flip it.
        """
        # The second place tool descriptions are emitted; it has to say the
        # same thing tools/list does or the two drift apart.
        hint = self._model_hint(scope)
        model_aware = self._model_aware_handlers()
        caps = []
        for cap in scope.allowed_capabilities():
            active = cap.tool_ids.filtered("active")
            caps.append({
                "name": cap.name,
                "technical_name": cap.technical_name,
                "description": cap.description,
                "tools": [{"name": t.name,
                           "description": self._tool_description(t, hint, model_aware)}
                          for t in active],
            })
        return {
            "scope": scope.name,
            "read_only": True,
            "granted_scopes": self.env.context.get("mcp_granted_scopes"),
            "capabilities": caps,
            # str() on purpose: this travels in structuredContent, where a lazy
            # translation object would only resolve via a serializer fallback.
            "note": str(_(
                "This connection can read the models listed by list_models and "
                "cannot change anything. If you are asked to create or update "
                "a record, say that this Odoo connector is read-only rather "
                "than attempting it.")),
        }

    def _handler_list_models(self, scope, args):
        """What the matrix currently permits, per model.

        Archived rows are excluded: ``line_for_model`` already ignores them at
        call time, so advertising one here would promise the AI access that
        every subsequent call refuses.
        """
        return {"models": [{
            "model": line.model_name,
            "name": line.model_id.name,
            "read": line.can_read,
        } for line in scope.line_ids.filtered("active")]}

    def _handler_get_schema(self, scope, args):
        model = args["model"]
        line = self._require_line(scope, model, "read")
        blacklist = self._blacklisted_fields(line)
        raw = self.env[model].fields_get(attributes=[
            "string", "type", "help", "relation", "required", "readonly", "selection"])
        out = {}
        for fname, meta in raw.items():
            if fname in blacklist:
                continue
            entry = {k: meta[k] for k in ("string", "type", "help", "relation",
                                          "required", "readonly")
                     if meta.get(k) not in (None, "")}
            if meta.get("selection"):
                entry["selection"] = [list(opt) for opt in meta["selection"]]
            out[fname] = entry
        return {"model": model, "fields": out}

    def _handler_search_records(self, scope, args):
        """Read records, and say plainly when there are more of them.

        The row cap is a real protection - it is what stops an AI query on a
        100k-record model from taking the database with it - but a silent cap
        is worse than no cap: the assistant receives a full page, has nothing
        to tell it the page was full, and reports partial data to the user as
        if it were the whole answer. So fetch one row past the cap, return the
        cap's worth, and hand back `has_more` so the assistant knows to
        paginate, narrow the domain, or aggregate with read_group instead.
        """
        model = args["model"]
        line = self._require_line(scope, model, "read")
        blacklist = self._blacklisted_fields(line)
        domain = self._parse_domain(args.get("domain")) + self._scope_domain(line)
        requested = args.get("fields") or ["display_name"]
        field_list = [f for f in requested if f not in blacklist]
        limit = self._clamp_limit(scope, args.get("limit"))
        offset = max(0, int(args.get("offset") or 0))
        records = self.env[model].with_context(**self._company_ctx(args)).search_read(
            domain, field_list, limit=limit + 1, offset=offset,
            order=args.get("order"))
        has_more = len(records) > limit
        records = records[:limit]
        return {"model": model, "count": len(records), "limit": limit,
                "offset": offset, "has_more": has_more, "records": records}

    def _handler_count_records(self, scope, args):
        model = args["model"]
        line = self._require_line(scope, model, "read")
        domain = self._parse_domain(args.get("domain")) + self._scope_domain(line)
        count = self.env[model].with_context(**self._company_ctx(args)).search_count(domain)
        return {"model": model, "count": count}

    def _handler_name_search(self, scope, args):
        model = args["model"]
        line = self._require_line(scope, model, "read")
        domain = self._parse_domain(args.get("domain")) + self._scope_domain(line)
        limit = self._clamp_limit(scope, args.get("limit"))
        # `domain=`, not the pre-19 `args=`: Odoo 19 renamed the parameter and
        # kept no alias, so the old spelling raised TypeError and this tool -
        # the one the business context tells the AI to use before every
        # filter-by-name - failed with an opaque internal error every time.
        res = self.env[model].with_context(**self._company_ctx(args)).name_search(
            name=args.get("name", ""), domain=domain, limit=limit + 1)
        has_more = len(res) > limit
        res = res[:limit]
        # has_more matters here too: a truncated match list is how an assistant
        # picks "the wrong Acme" and reports on it with complete confidence.
        return {"model": model, "count": len(res), "limit": limit,
                "has_more": has_more,
                "results": [{"id": i, "name": n} for i, n in res]}

    def _handler_read_group(self, scope, args):
        model = args["model"]
        line = self._require_line(scope, model, "read")
        blacklist = self._blacklisted_fields(line)
        domain = self._parse_domain(args.get("domain")) + self._scope_domain(line)
        groupby = args.get("group_by") or args.get("groupby") or []
        if isinstance(groupby, str):
            groupby = [groupby]
        groupby = [g for g in groupby if g.split(":")[0] not in blacklist]
        measures = args.get("measures") or ["__count"]
        if isinstance(measures, str):
            measures = [measures]
        aggregates = []
        for measure in measures:
            if measure == "__count":
                aggregates.append("__count")
            elif measure.split(":")[0] not in blacklist:
                aggregates.append(measure if ":" in measure else "%s:sum" % measure)
        limit = self._clamp_limit(scope, args.get("limit"))
        rows = self.env[model].with_context(**self._company_ctx(args))._read_group(
            domain, groupby=groupby, aggregates=aggregates,
            order=args.get("order"), limit=limit + 1)
        # Same trap as search_records, and worse here: a report silently missing
        # its last groups still totals up and still looks complete.
        has_more = len(rows) > limit
        rows = rows[:limit]
        groups = []
        for row in rows:
            entry, idx = {}, 0
            for key in groupby:
                entry[key] = self._jsonify(row[idx]); idx += 1
            for key in aggregates:
                entry[key] = self._jsonify(row[idx]); idx += 1
            groups.append(entry)
        return {"model": model, "group_by": groupby, "measures": aggregates,
                "count": len(groups), "limit": limit, "has_more": has_more,
                "groups": groups}

    # ================================================== prompts & resources (MCP)
    # Declared but empty here, so the transport can answer prompts/list and
    # resources/list truthfully rather than 'method not found'. AI MCP
    # Governance fills both: a curated, role-based prompt library and the
    # Business Context Engine that teaches the AI what your data means.
    @api.model
    def list_prompts(self, scope):
        return []

    @api.model
    def get_prompt(self, scope, name, arguments):
        raise UserError(_("Unknown prompt '%s'.") % name)

    @api.model
    def list_resources(self, scope):
        return []

    @api.model
    def read_resource(self, scope, uri):
        raise UserError(_("Unknown resource '%s'.") % uri)

    # ==================================================================== audit
    def _audit(self, scope, name, model_used, args, status, start, payload, audit_ctx):
        self.env["mcp.audit.log"].sudo().create({
            "oauth_token_id": audit_ctx.get("oauth_token_id"),
            "user_id": self.env.uid,
            "scope_id": scope.id,
            "tool": name,
            "model_name": model_used,
            "transport": audit_ctx.get("transport", "http"),
            "remote_addr": audit_ctx.get("remote_addr"),
            "args_json": json.dumps(args, default=str)[:MAX_ARGS_LOG],
            "status": status,
            "duration_ms": int((time.time() - start) * 1000),
            "tokens_est": max(1, len(json.dumps(payload or {}, default=str)) // 4),
        })
