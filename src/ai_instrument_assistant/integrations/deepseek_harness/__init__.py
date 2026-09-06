"""Pure compatibility logic for the DeepSeek Harness adapter boundary."""

from .schema_projection import (
    HARNESS_TOOL_OPERATION_MAP,
    DeferredConstraint,
    ProjectedSchema,
    ProjectedToolContract,
    ProjectionError,
    project_hardware_tools,
    project_schema,
)

__all__ = [
    "HARNESS_TOOL_OPERATION_MAP",
    "DeferredConstraint",
    "ProjectedSchema",
    "ProjectedToolContract",
    "ProjectionError",
    "project_hardware_tools",
    "project_schema",
]
