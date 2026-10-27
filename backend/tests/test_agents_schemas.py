"""Every agent's output schema must be accepted as a strict structured output (Azure OpenAI):
all properties required, no free-form objects. The fake client can't catch this, so it's
checked here (found against the real endpoint)."""

from typing import Any

import pytest

from app.agents import narrator, personalizer, recap, square_writer, strategist_reason, tutor

SPECS = [narrator.SPEC, personalizer.SPEC, square_writer.SPEC, strategist_reason.SPEC,
         tutor.TUTOR, tutor.CONTEXT, recap.SPEC]


def objects(schema: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    defs = schema.get("$defs", {})

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(schema)
    for definition in defs.values():
        walk(definition)
    return found


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_output_schema_is_strict_compatible(spec):
    schema = spec.output.model_json_schema()
    for obj in objects(schema):
        properties = set(obj.get("properties", {}))
        assert properties, f"{spec.name}: free-form object {obj}"
        assert set(obj.get("required", [])) == properties, \
            f"{spec.name}: every property must be required, got {obj.get('required')}"
