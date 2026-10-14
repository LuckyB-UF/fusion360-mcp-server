"""One module per toolset; each owns its tool schemas.

A module exports ``TOOLSET`` (its name), ``SUMMARY`` (one line for
``fusion_toolsets``) and ``TOOLS`` (schema dicts with annotation flags
inline).  ``DOMAINS`` fixes the order tools are listed in.
"""

from . import (
    assembly,
    cam,
    core,
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
)
