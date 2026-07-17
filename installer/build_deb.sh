#!/bin/sh
# Builds subtitleburner_<version>_amd64.deb from this repo's app source plus
# the packaging metadata in installer/debian/.
#
# Must be run on a real Linux machine (or a working WSL/Docker Linux
# environment) with dpkg-deb available - it cannot run on plain Windows.
# This script has not been executed/tested anywhere yet (see README.md in
# this directory for why) - review it before relying on it.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAGE="$SCRIPT_DIR/debian"
APP_DIR="$STAGE/opt/subtitleburner"

echo "Copying app source into $APP_DIR ..."
mkdir -p "$APP_DIR"
cp "$REPO_ROOT/app.py" "$REPO_ROOT/config.py" "$REPO_ROOT/launcher.py" \
   "$REPO_ROOT/gui.py" "$REPO_ROOT/tui.py" "$REPO_ROOT/tui_launcher.py" \
   "$REPO_ROOT/bootstrap.py" "$REPO_ROOT/requirements.txt" "$APP_DIR/"

# subburn/ is a growing package (engines, routes, etc.) - copied as a whole
# tree (minus dev-time __pycache__ dirs) so new files under it never need a
# packaging-script edit, same idea as the web/ copy below.
rsync -a --exclude '__pycache__' "$REPO_ROOT/subburn/" "$APP_DIR/subburn/"

mkdir -p "$APP_DIR/web"
# node_modules and .next are excluded - reinstalled/rebuilt on first launch
# by bootstrap.py, same as the Windows installer's approach.
rsync -a --exclude node_modules --exclude .next --exclude '*.log' \
    "$REPO_ROOT/web/" "$APP_DIR/web/"

chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"
chmod 0755 "$STAGE/usr/bin/subtitleburner"

VERSION=$(grep '^Version:' "$STAGE/DEBIAN/control" | awk '{print $2}')
OUTPUT="$SCRIPT_DIR/output/subtitleburner_${VERSION}_amd64.deb"
mkdir -p "$SCRIPT_DIR/output"

echo "Building $OUTPUT ..."
dpkg-deb --build --root-owner-group "$STAGE" "$OUTPUT"

echo "Done: $OUTPUT"
echo "Test with: sudo apt install ./$(basename "$OUTPUT")"
