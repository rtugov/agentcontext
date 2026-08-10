#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPOSITORY_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
RESOURCE_DIR="$PROJECT_DIR/Sources/AgentContext/Resources"

mkdir -p "$RESOURCE_DIR"
cp "$REPOSITORY_DIR/proxy-server/proxy.py" "$RESOURCE_DIR/proxy.py"
cp "$REPOSITORY_DIR/proxy-server/requirements.txt" "$RESOURCE_DIR/requirements.txt"
