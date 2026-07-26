"""Static contract check: does app.js only call API methods that exist,
and does every block type / field kind line up end to end?"""
import ast
import inspect
import re
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

fails = []


def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + ((" -- " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


# ---- what Python exposes -------------------------------------------------
src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
tree = ast.parse(src)
api_cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Api")
api_methods = {n.name for n in api_cls.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and not n.name.startswith("_")}

# ---- what JS calls -------------------------------------------------------
js = open(os.path.join(ROOT, "ui", "app.js"), encoding="utf-8").read()
called = set(re.findall(r"pywebview\.api\.([A-Za-z_][A-Za-z0-9_]*)", js))
called |= set(re.findall(r"api\[[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\]", js))
# app.js routes everything through api()/apiQ() wrappers taking the name.
called |= set(re.findall(r"""\bapiQ?\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""", js))
called |= set(re.findall(r"""\bcallApi\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""", js))

print("== API surface ==")
print("  python exposes %d, js calls %d" % (len(api_methods), len(called)))
unknown = sorted(called - api_methods)
check("no calls to nonexistent methods", not unknown, unknown)
unused = sorted(api_methods - called)
print("  unused by UI: %s" % (unused or "none"))

# ---- push events ---------------------------------------------------------
print("== push events ==")
pushed = set(re.findall(r"push_ui\([\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\)", src))
pushed |= set(re.findall(r"window\.(\w+)\s*&&\s*window\.\1\(", src))
defined = set(re.findall(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)", js, re.M))
defined |= set(re.findall(r"window\.([A-Za-z_][A-Za-z0-9_]*)\s*=", js))
for name in sorted(pushed):
    check("push target %s defined in js" % name, name in defined)

# ---- block contract ------------------------------------------------------
print("== block contract ==")
from core import blocks as blockmod
from core import runner as runnermod

catalog_types = [b["type"] for b in blockmod.catalog()]
check("no duplicate block types", len(catalog_types) == len(set(catalog_types)))

handlers = {n[4:] for n in dir(runnermod.MacroRunner) if n.startswith("_do_")}
flow_only = {"loop_start", "loop_end"}
missing = [t for t in catalog_types if t not in handlers and t not in flow_only]
check("every block type has a runner handler", not missing, missing)
orphan = [h for h in handlers if h not in catalog_types]
check("no orphan handlers", not orphan, orphan)

# The kinds the frontend ACTUALLY renders, read out of renderField's switch
# rather than kept as a second hand-written list here that can drift.
KINDS_UI_RENDERS = set(re.findall(r'case\s+"([a-z_]+)"\s*:', js))
check("renderField's switch was found in app.js", len(KINDS_UI_RENDERS) > 5,
      sorted(KINDS_UI_RENDERS))
declared = set(blockmod.FIELD_KINDS)
used = {f["kind"] for spec in blockmod.catalog() for f in spec["fields"]}
check("every kind used by the catalog is declared in FIELD_KINDS",
      used <= declared, used - declared)
bad_kinds = set()
for spec in blockmod.catalog():
    for f in spec["fields"]:
        if f["kind"] not in KINDS_UI_RENDERS:
            bad_kinds.add((spec["type"], f["key"], f["kind"]))
check("all field kinds renderable", not bad_kinds, bad_kinds)

# Every param a handler reads must be declared in the catalog.
runner_src = open(os.path.join(ROOT, "core", "runner.py"), encoding="utf-8").read()
for spec in blockmod.catalog():
    if spec["type"] in flow_only:
        continue
    fn = getattr(runnermod.MacroRunner, "_do_" + spec["type"], None)
    if fn is None:
        continue
    body = inspect.getsource(fn)
    reads = set(re.findall(r"params\.get\([\"'](\w+)[\"']", body))
    declared = {f["key"] for f in spec["fields"]}
    # on_fail is injected by _fail() for blocks that declare it
    extra = reads - declared
    check("%s reads only declared params" % spec["type"], not extra, extra)

# on_fail policy: any block whose catalog declares on_fail must reach _fail
for spec in blockmod.catalog():
    declared = {f["key"] for f in spec["fields"]}
    if "on_fail" not in declared:
        continue
    fn = getattr(runnermod.MacroRunner, "_do_" + spec["type"], None)
    body = inspect.getsource(fn) if fn else ""
    check("%s honours on_fail" % spec["type"], "_fail(" in body)

# ---- html ids referenced by js ------------------------------------------
print("== dom ids ==")
html = open(os.path.join(ROOT, "ui", "index.html"), encoding="utf-8").read()
html_ids = set(re.findall(r'id="([^"]+)"', html))
js_ids = set(re.findall(r"""\$\(\s*["']#([A-Za-z0-9_\-]+)["']\s*\)""", js))
js_ids |= set(re.findall(r"""getElementById\(\s*["']([A-Za-z0-9_\-]+)["']""", js))
missing_ids = sorted(js_ids - html_ids)
check("no js reference to a missing dom id", not missing_ids, missing_ids)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
