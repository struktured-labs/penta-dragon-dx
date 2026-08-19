#!/usr/bin/env python3
"""Emit the static address receipt for the packed Ted <=1% fit draft."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_v302_title_fix as build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    fragments = build.build_ted_incremental_packed_exact_fit_draft()
    rows = []
    for address, payload in sorted(fragments.items()):
        rows.append({
            "start": f"{address:04X}",
            "end": f"{address + len(payload) - 1:04X}",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "hex": payload.hex(),
        })

    packed_next = (
        build.TED_INWINDOW_BODY_MASK_ADDR
        + build.TED_INWINDOW_BODY_MASK_SIZE
    )
    assert packed_next == 0xD8AB
    assert packed_next + build.TED_INWINDOW_BODY_MASK_SIZE == 0xD8F3
    assert build.TED_INWINDOW_NEXT_MASK_ADDR == 0xD579
    report = {
        "schema": "penta-ted-packed-exact-fit-v1",
        "status": "pass",
        "runtime_candidate": False,
        "packed_lut": "D579-D5FF",
        "packed_key": "D578",
        "next_mask": "D8AB-D8F2",
        "resident_mask": "D863-D8AA",
        "fragments": rows,
        "remaining_gates": [
            "accumulator writer integration",
            "SVBK4/5 ownership receipt",
            "ready sentinel written last after both banks",
            "emulator semantic/cadence receipts",
        ],
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
