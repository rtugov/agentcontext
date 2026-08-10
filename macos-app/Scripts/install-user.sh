#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="AgentContext"
SOURCE_APP="$PROJECT_DIR/dist/$APP_NAME.app"
INSTALL_DIR="$HOME/Applications"
INSTALLED_APP="$INSTALL_DIR/$APP_NAME.app"

if [[ ! -d "$SOURCE_APP" ]]; then
    "$PROJECT_DIR/Scripts/build-app.sh"
fi

mkdir -p "$INSTALL_DIR"
rm -rf "$INSTALLED_APP"
cp -R "$SOURCE_APP" "$INSTALLED_APP"
echo "$INSTALLED_APP"
