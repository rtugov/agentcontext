#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="AgentContext"
EXECUTABLE_NAME="AgentContext"
DIST_DIR="$PROJECT_DIR/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"

cd "$PROJECT_DIR"
"$PROJECT_DIR/Scripts/sync-resources.sh"
swift build -c release
BIN_DIR="$(swift build -c release --show-bin-path)"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

cp "$BIN_DIR/$EXECUTABLE_NAME" "$APP_DIR/Contents/MacOS/$EXECUTABLE_NAME"
cp "$PROJECT_DIR/Packaging/Info.plist" "$APP_DIR/Contents/Info.plist"

RESOURCE_BUNDLE="$BIN_DIR/AgentContext_AgentContext.bundle"
if [[ ! -d "$RESOURCE_BUNDLE" ]]; then
    echo "Swift resource bundle was not found at: $RESOURCE_BUNDLE" >&2
    exit 1
fi
cp -R "$RESOURCE_BUNDLE" "$APP_DIR/Contents/Resources/"

codesign --force --deep --sign - "$APP_DIR"
echo "$APP_DIR"
