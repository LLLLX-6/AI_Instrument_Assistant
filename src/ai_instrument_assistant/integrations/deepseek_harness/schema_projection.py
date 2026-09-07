from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping


CANONICAL_HARDWARE_SCHEMA_ID = (
    "https://aia.local/protocols/hardware/v1/hardware-tool.schema.json"
)

HARNESS_TOOL_OPERATION_MAP: Mapping[str, str] = {
    "hardware_get_status": "hardware.get_status",
    "hardware_measure_frequency": "hardware.measure_frequency",
    "hardware_measure_vpp": "hardware.measure_vpp",
    "hardware_capture_waveform": "hardware.capture_waveform",
    "hardware_measure_pwm": "hardware.measure_pwm",
}

_HARNESS_KEYWORDS = frozenset(
    {
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "oneOf",
        "enum",
        "const",
        "default",
    }
)
_DOCUMENT_KEYWORDS = frozenset({"$schema", "$id", "$defs"})
_CANONICAL_ONLY_CONSTRAINTS = frozenset(
    {
        "format",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "minItems",
        "maxItems",
        "uniqueItems",
        "pattern",
    }
)


class ProjectionError(ValueError):
    """Projection would be ambiguous or silently lose validation semantics."""


@dataclass(frozen=True, slots=True)
class DeferredConstraint:
    json_path: str
    keyword: str
    value: Any
    enforced_by: str = "python-canonical-validator"


@dataclass(frozen=True, slots=True)
class ProjectedSchema:
    schema: dict[str, Any]
    deferred_constraints: tuple[DeferredConstraint, ...]


@dataclass(frozen=True, slots=True)
class ProjectedToolContract:
    harness_name: str
    canonical_operation: str
    parameters_schema: dict[str, Any]
    output_schema: dict[str, Any]
    deferred_constraints: tuple[DeferredConstraint, ...]


def project_schema(
    schema: Mapping[str, Any],
    *,
    allowed_deferred_keywords: frozenset[str] = frozenset(),
) -> ProjectedSchema:
    """Project one self-contained schema into the reviewed Harness subset.

    Strict mode is the default. Callers must explicitly authorize every canonical
    keyword whose validation remains solely at the Python boundary.
    """

    source = deepcopy(dict(schema))
    resolved = _resolve_local_references(source, source, ())
    deferred: list[DeferredConstraint] = []
    projected = _project_node(
        resolved,
        path="$",
        allowed_deferred_keywords=allowed_deferred_keywords,
        deferred=deferred,
    )
    return ProjectedSchema(projected, tuple(deferred))


def project_hardware_tools(
    canonical_schema: Mapping[str, Any],
) -> tuple[ProjectedToolContract, ...]:
    """Generate the five reviewed Harness tool contracts from the canonical SSOT."""

    source = deepcopy(dict(canonical_schema))
    if source.get("$id") != CANONICAL_HARDWARE_SCHEMA_ID:
        raise ProjectionError("unexpected canonical hardware schema identity")
    definitions = source.get("$defs")
    if not isinstance(definitions, dict):
        raise ProjectionError("canonical hardware schema has no $defs object")
    status_operation = (
        definitions.get("statusRequest", {})
        .get("properties", {})
        .get("operation", {})
        .get("const")
    )
    measurement_operations = (
        definitions.get("measurementRequest", {})
        .get("properties", {})
        .get("operation", {})
        .get("enum")
    )
    canonical_operations = {status_operation, *(measurement_operations or [])}
    if canonical_operations != set(HARNESS_TOOL_OPERATION_MAP.values()):
        raise ProjectionError("canonical operation set drifted from the static Harness allowlist")

    tools: list[ProjectedToolContract] = []
    for harness_name, operation in HARNESS_TOOL_OPERATION_MAP.items():
        request_definition = (
            "statusRequest" if operation == "hardware.get_status" else "measurementRequest"
        )
        request = _resolve_local_references(
            deepcopy(definitions[request_definition]), source, ()
        )
        arguments = request.get("properties", {}).get("arguments")
        if not isinstance(arguments, dict):
            raise ProjectionError(f"{operation} has no canonical arguments schema")

        if operation == "hardware.get_status":
            success = _resolve_local_references(
                deepcopy(definitions["runtimeStatusSuccess"]), source, ()
            )
        else:
            unspecialized = _resolve_local_references(
                deepcopy(definitions["runtimeMeasurementSuccess"]), source, ()
            )
            success = _specialize_measurement_success(unspecialized, operation)
        failure = _resolve_local_references(
            deepcopy(definitions["runtimeError"]), source, ()
        )

        parameters = project_schema(
            arguments,
            allowed_deferred_keywords=_CANONICAL_ONLY_CONSTRAINTS,
        )
        output = project_schema(
            {"oneOf": [success, failure]},
            allowed_deferred_keywords=_CANONICAL_ONLY_CONSTRAINTS,
        )
        tools.append(
            ProjectedToolContract(
                harness_name=harness_name,
                canonical_operation=operation,
                parameters_schema=parameters.schema,
                output_schema=output.schema,
                deferred_constraints=(
                    parameters.deferred_constraints + output.deferred_constraints
                ),
            )
        )
    return tuple(tools)


def _resolve_local_references(
    node: Any,
    root: Mapping[str, Any],
    stack: tuple[str, ...],
) -> Any:
    if isinstance(node, list):
        return [_resolve_local_references(item, root, stack) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        reference = node["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ProjectionError(f"only local JSON Pointer references are projectable: {reference!r}")
        if len(node) != 1:
            raise ProjectionError("$ref siblings require semantics not approved for projection")
        if reference in stack:
            raise ProjectionError(f"cyclic local reference: {reference}")
        target: Any = root
        for raw_part in reference[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                raise ProjectionError(f"unresolvable local reference: {reference}")
            target = target[part]
        return _resolve_local_references(deepcopy(target), root, stack + (reference,))
    return {
        key: _resolve_local_references(value, root, stack)
        for key, value in node.items()
    }


def _project_node(
    node: Any,
    *,
    path: str,
    allowed_deferred_keywords: frozenset[str],
    deferred: list[DeferredConstraint],
) -> Any:
    if isinstance(node, list):
        return [
            _project_node(
                item,
                path=f"{path}/{index}",
                allowed_deferred_keywords=allowed_deferred_keywords,
                deferred=deferred,
            )
            for index, item in enumerate(node)
        ]
    if not isinstance(node, dict):
        return node

    projected: dict[str, Any] = {}
    for keyword, value in node.items():
        keyword_path = f"{path}/{keyword}"
        if keyword in _DOCUMENT_KEYWORDS:
            continue
        if keyword in allowed_deferred_keywords:
            deferred.append(DeferredConstraint(keyword_path, keyword, deepcopy(value)))
            continue
        if keyword not in _HARNESS_KEYWORDS:
            raise ProjectionError(
                f"unsupported keyword {keyword!r} at {path}; semantic loss is not allowed"
            )
        if keyword == "type" and isinstance(value, list):
            if len(value) != 2 or "null" not in value:
                raise ProjectionError(f"only nullable two-type unions are approved at {path}")
            projected["oneOf"] = [{"type": item} for item in value]
        elif keyword == "additionalProperties":
            if not isinstance(value, bool):
                raise ProjectionError(
                    f"Harness projection only supports boolean additionalProperties at {path}"
                )
            projected[keyword] = value
        elif keyword == "properties":
            if not isinstance(value, dict):
                raise ProjectionError(f"properties must be an object at {path}")
            projected[keyword] = {
                name: _project_node(
                    child,
                    path=f"{keyword_path}/{name}",
                    allowed_deferred_keywords=allowed_deferred_keywords,
                    deferred=deferred,
                )
                for name, child in value.items()
            }
        elif keyword in {"items", "oneOf"}:
            projected[keyword] = _project_node(
                value,
                path=keyword_path,
                allowed_deferred_keywords=allowed_deferred_keywords,
                deferred=deferred,
            )
        else:
            projected[keyword] = deepcopy(value)

    if "type" not in node and "oneOf" not in node:
        if "const" in node:
            projected["type"] = _infer_scalar_type(node["const"], path=f"{path}/const")
        elif "enum" in node:
            enum_values = node["enum"]
            if not isinstance(enum_values, list) or not enum_values:
                raise ProjectionError(f"enum must be a non-empty array at {path}")
            inferred = {
                _infer_scalar_type(value, path=f"{path}/enum/{index}")
                for index, value in enumerate(enum_values)
            }
            if len(inferred) != 1:
                raise ProjectionError(
                    f"enum members do not have one safely inferable scalar type at {path}"
                )
            projected["type"] = inferred.pop()
    return projected


def _infer_scalar_type(value: Any, *, path: str) -> str:
    """Infer only the scalar types accepted by the frozen Harness validator."""

    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float) and isfinite(value):
        return "number"
    if value is None:
        raise ProjectionError(
            f"null cannot be inferred without an explicit nullable type or oneOf at {path}"
        )
    raise ProjectionError(f"non-scalar or non-finite value cannot be inferred at {path}")


def _specialize_measurement_success(
    schema: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    all_of = schema.pop("allOf", None)
    if not isinstance(all_of, list) or len(all_of) != 1:
        raise ProjectionError("measurement success discriminator shape changed")
    discriminator = all_of[0]
    branches = discriminator.get("oneOf") if isinstance(discriminator, dict) else None
    if not isinstance(branches, list):
        raise ProjectionError("measurement success discriminator has no oneOf")
    matching = [
        branch
        for branch in branches
        if isinstance(branch, dict)
        and branch.get("properties", {}).get("operation", {}).get("const") == operation
    ]
    if len(matching) != 1:
        raise ProjectionError(f"cannot uniquely specialize output for {operation}")
    return _merge_schema(schema, matching[0])


def _merge_schema(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(left))
    for key, right_value in right.items():
        if key == "properties" and key in result:
            merged_properties = deepcopy(result[key])
            for name, child in right_value.items():
                merged_properties[name] = (
                    _merge_schema(merged_properties[name], child)
                    if name in merged_properties
                    else deepcopy(child)
                )
            result[key] = merged_properties
        elif key == "required" and key in result:
            result[key] = list(dict.fromkeys([*result[key], *right_value]))
        elif key in result and result[key] != right_value:
            if key in {"enum", "const"}:
                result[key] = deepcopy(right_value) if key == "const" else deepcopy(result[key])
            else:
                raise ProjectionError(f"cannot safely merge schema keyword {key!r}")
        else:
            result[key] = deepcopy(right_value)
    return result
