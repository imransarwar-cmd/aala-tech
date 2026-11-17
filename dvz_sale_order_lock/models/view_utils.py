"""Apply read-only conditions after all inherited views have been combined.

The returned XML never depends on the currently logged-in user's groups.
Per-user helper fields drive the conditions, avoiding shared-view-cache leaks.
Only sale.order / sale.order.line scopes are changed; linked master records
and unrelated embedded models retain their own permissions.
"""
import ast
from lxml import etree

PROTECTED_MODELS = frozenset({"sale.order", "sale.order.line"})
HELPER_FIELDS = frozenset({
    "dvz_lock_readonly", "dvz_can_manage_lock", "dvz_lock_status", "locked",
})
VIEW_ROOTS = frozenset({"form", "list", "tree", "kanban"})
MUTATING_ORDER_BUTTONS = frozenset({
    "action_confirm", "action_cancel", "action_draft", "action_update_prices",
    "action_update_taxes", "action_open_discount_wizard",
})


class _LockNameRewriter(ast.NodeTransformer):
    def __init__(self, model_name, parent_model):
        self.model_name = model_name
        self.parent_model = parent_model
        self.changed = False

    def visit_Name(self, node):
        if self.model_name == "sale.order" and node.id == "locked":
            self.changed = True
            return ast.copy_location(ast.Name(id="dvz_lock_readonly", ctx=node.ctx), node)
        return node

    def visit_Attribute(self, node):
        if (
            self.parent_model == "sale.order"
            and isinstance(node.value, ast.Name)
            and node.value.id == "parent"
            and node.attr == "locked"
        ):
            self.changed = True
            return ast.copy_location(
                ast.Attribute(value=node.value, attr="dvz_lock_readonly", ctx=node.ctx),
                node,
            )
        return self.generic_visit(node)


def replace_lock_condition(expression, model_name, parent_model=None):
    """Replace only AST names, never substrings inside quoted text."""
    if not expression:
        return expression
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        # Preserve an unfamiliar vendor expression instead of damaging it.
        return expression
    rewriter = _LockNameRewriter(model_name, parent_model)
    result = rewriter.visit(parsed)
    return ast.unparse(ast.fix_missing_locations(result)) if rewriter.changed else expression


def _or_condition(existing, condition):
    if not existing:
        return condition
    if existing.strip() in {"1", "True"}:
        return existing
    # Idempotence when another parent model has already processed a subview.
    try:
        parsed = ast.parse(existing, mode="eval").body
        if isinstance(parsed, ast.BoolOp) and isinstance(parsed.op, ast.Or):
            if any(isinstance(x, ast.Name) and x.id == condition for x in parsed.values):
                return existing
        elif isinstance(parsed, ast.Name) and parsed.id == condition:
            return existing
    except SyntaxError:
        pass
    return f"({existing}) or {condition}"


def protect_view(arch, model_name, resolve_relation, parent_model=None):
    """Mutate one combined XML architecture; resolve_relation(model, field).

    Nested view boundaries are traversed with their actual comodel, so an
    unrelated child field named 'locked' is never treated as the SO flag.
    """
    protected = model_name in PROTECTED_MODELS
    local_fields = []

    def walk(node):
        for child in list(node):
            if not isinstance(child.tag, str):
                continue
            if child.tag == "field":
                field_name = child.get("name", "")
                local_fields.append(child)
                if protected:
                    if field_name in HELPER_FIELDS:
                        child.set("readonly", "1")
                    else:
                        readonly = replace_lock_condition(
                            child.get("readonly", ""), model_name, parent_model,
                        )
                        child.set("readonly", _or_condition(readonly, "dvz_lock_readonly"))
                relation = resolve_relation(model_name, field_name)
                if relation:
                    for subview in child:
                        if isinstance(subview.tag, str) and subview.tag in VIEW_ROOTS:
                            protect_view(subview, relation, resolve_relation, model_name)
                # Field descendants belong to their comodel, not the parent.
                continue
            if protected and child.tag == "button" and model_name == "sale.order":
                name = child.get("name")
                if name in {"action_lock", "action_unlock"}:
                    # New DVZ buttons replace the native manager-only buttons.
                    child.set("invisible", "1")
                elif name in MUTATING_ORDER_BUTTONS:
                    child.set("invisible", _or_condition(child.get("invisible", ""), "dvz_lock_readonly"))
            walk(child)

    walk(arch)
    if protected:
        for helper in ("dvz_lock_readonly", "dvz_can_manage_lock"):
            occurrences = [node for node in local_fields if node.get("name") == helper]
            # Do not trust a groups-restricted occurrence to exist for every user.
            if not any(not node.get("groups") for node in occurrences):
                attrib = {"name": helper, "invisible": "1", "readonly": "1"}
                if arch.tag in {"list", "tree"}:
                    attrib["column_invisible"] = "1"
                arch.insert(0, etree.Element("field", **attrib))
    return arch
