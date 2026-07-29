#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
git -C "$project_root" config core.hooksPath .githooks
echo "Installed project hooks from .githooks"
