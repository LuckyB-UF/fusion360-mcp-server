"""Annotation flags a tool schema sets inline as ``"annotations": FLAG``.

A tool without an ``annotations`` entry is neither read-only, destructive
nor idempotent.  The registry (``tools.py``) expands every entry into the
full ``readOnlyHint`` / ``destructiveHint`` / ``idempotentHint`` triple.
"""

# Reads only, so repeating it is harmless too.
READ_ONLY = {"readOnlyHint": True, "idempotentHint": True}
# Changes the design, but repeating it with the same arguments changes nothing.
IDEMPOTENT = {"idempotentHint": True}
# Deletes or rewrites things that cannot simply be redone.
DESTRUCTIVE = {"destructiveHint": True}
