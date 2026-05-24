"""Pull response schemas from FSP's swagger.json for the endpoints we care about."""
import json
import requests

spec = requests.get("https://developer.flightschedulepro.com/core/swagger.json", timeout=15).json()
components = spec.get("components", {}).get("schemas", {})

TARGETS = [
    "/operators/{operatorId}/aircraft",
    "/operators/{operatorId}/aircraft/{aircraftId}/squawks",
    "/operators/{operatorId}/aircraft/{aircraftId}/maintenanceReminders",
    "/operators/{operatorId}/instructors",
]


def resolve_ref(schema):
    if isinstance(schema, dict) and "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return name, components.get(name, {})
    return None, schema


def print_props(schema, indent=2):
    props = schema.get("properties", {})
    if not props and schema.get("type") != "object":
        return
    for prop_name, prop in props.items():
        t = prop.get("type", "?")
        fmt = prop.get("format", "")
        if "$ref" in prop:
            t = prop["$ref"].split("/")[-1]
        if prop.get("type") == "array":
            items = prop.get("items", {})
            if "$ref" in items:
                t = f"array<{items['$ref'].split('/')[-1]}>"
            else:
                t = f"array<{items.get('type','?')}>"
        print(" " * indent + f"{prop_name}: {t}{(' ' + fmt) if fmt else ''}")


for path in TARGETS:
    op = spec["paths"].get(path, {}).get("get", {})
    print(f"=== GET {path} ===")
    print(f"  Summary: {op.get('summary')}")
    print("  Parameters:")
    for p in op.get("parameters", []):
        loc = p.get("in")
        req = p.get("required")
        t = p.get("schema", {}).get("type", "?")
        print(f"    - {p.get('name')} (in={loc}, required={req}, type={t})")
    ok = op.get("responses", {}).get("200", {})
    content = ok.get("content", {}).get("application/json", {})
    schema = content.get("schema", {})
    name, resolved = resolve_ref(schema)
    print(f"  Response 200: {name or schema.get('type', '?')}")
    # array?
    if resolved.get("type") == "array":
        item_schema = resolved.get("items", {})
        iname, iresolved = resolve_ref(item_schema)
        print(f"    [array of {iname or item_schema.get('type', '?')}]")
        print("    item properties:")
        print_props(iresolved, indent=6)
    elif resolved.get("type") == "object":
        print("    properties:")
        print_props(resolved, indent=6)
    # If the top-level response is wrapped (e.g., has data/items), drill in
    for envelope in ("data", "items", "results"):
        if envelope in resolved.get("properties", {}):
            ep = resolved["properties"][envelope]
            iname, iresolved = resolve_ref(ep.get("items", {})) if ep.get("type") == "array" else (None, ep)
            print(f"    envelope.{envelope}:")
            print_props(iresolved, indent=6)
    print()
