#!/usr/bin/env bash
set -euo pipefail

require_none=0
if [[ "${1:-}" == "--require-none" ]]; then
    require_none=1
elif [[ "$#" -ne 0 ]]; then
    echo "usage: $0 [--require-none]" >&2
    exit 64
fi

found=0
for name in mgba-qt mgba mgba-headless; do
    while IFS= read -r line; do
        if [[ -n "$line" ]]; then
            printf '%s\n' "$line"
            found=1
        fi
    done < <(pgrep -a -x "$name" || true)
done

if [[ "$found" -eq 0 ]]; then
    echo "No mGBA emulator processes are running."
elif [[ "$require_none" -eq 1 ]]; then
    echo "Refusing to start: an mGBA emulator already owns the host slot." >&2
    exit 75
fi
