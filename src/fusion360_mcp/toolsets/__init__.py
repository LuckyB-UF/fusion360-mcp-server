"""One module per toolset; each owns its tool schemas and mocks.

A module exports ``TOOLSET`` (its name), ``SUMMARY`` (one line for
``fusion_toolsets``), ``TOOLS`` (schema dicts with annotation flags inline)
and ``MOCKS`` (tool name -> ``--mode mock`` handler).  ``DOMAINS`` fixes the
order tools are listed in.
"""

from . import (
    assembly,
    cam,
    core,
    drawing,
    electronics,
    inspection,
    modeling,
    modeling_advanced,
    surface_sheetmetal,
)

DOMAINS = (
    core,
    modeling,
    inspection,
    modeling_advanced,
    assembly,
    surface_sheetmetal,
    cam,
    electronics,
    drawing,
)
