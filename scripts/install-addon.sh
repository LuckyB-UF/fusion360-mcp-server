#!/bin/bash
# Install/reinstall the Fusion360MCP add-in via symlink (for development)
# Usage: ./scripts/install-addon.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ADDON_SRC="$REPO_DIR/addon"

# Determine Fusion 360 AddIns folder
if [[ "$OSTYPE" == "darwin"* ]]; then
    ADDINS_DIR="$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ADDINS_DIR="$APPDATA/Autodesk/Autodesk Fusion 360/API/AddIns"
else
    echo "Unsupported OS: $OSTYPE"
    exit 1
fi

TARGET="$ADDINS_DIR/Fusion360MCP"

echo "Installing Fusion360MCP add-in..."
echo "  Source: $ADDON_SRC"
echo "  Target: $TARGET"

# Remove existing installation
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
    echo "  Removing existing installation..."
    rm -rf "$TARGET"
fi

# Create symlink for development (changes reflect immediately)
ln -s "$ADDON_SRC" "$TARGET"

# Under Git Bash on Windows, `ln -s` silently falls back to a COPY unless
# developer mode or MSYS winsymlinks is enabled.  Say so loudly: a copy means
# editing the repo changes nothing Fusion runs, and a patch can look applied
# while the old code is still executing.
if [ -L "$TARGET" ]; then
    echo "  ✓ Installed via symlink"
else
    echo "  ! Installed as a COPY, not a symlink."
    echo "    ln -s fell back to copying (no developer mode / MSYS winsymlinks)."
    echo "    Repo edits will NOT reach Fusion until you re-run this script."
    echo "    tests/test_addon_sync.py::test_deployed_addon_matches_repo catches the drift."
fi
echo ""
echo "Next steps:"
echo "  1. Open Fusion 360"
echo "  2. Press Shift+S to open Scripts and Add-Ins"
echo "  3. Find 'Fusion360MCP' in the Add-Ins tab"
echo "  4. Click 'Run' to start the add-in"
echo ""
echo "The add-in will listen on localhost:9876"
