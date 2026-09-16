#!/usr/bin/env python3
"""Build r357: commit opposite BG/Window map selectors atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from stage_card_palette_handoff import (  # noqa: E402
    VBLANK_ATOMIC_COMMIT,
    VBLANK_ATOMIC_WINDOW_COMMIT,
    VBLANK_COMMIT_OFFSET,
    inspect_stage_card_palette_handoff,
)


TMP = ROOT / "tmp"
BASE = TMP / "stage1-vblank-palette-map-atomic-r356/candidate.gb"
BASE_RECEIPT = TMP / "stage1-vblank-palette-map-atomic-r356/build-receipt.json"
BASE_SHA256 = "31a090fd4609ec1d42813abd13b312dbaba8723886a96e3857ee79ec4228852b"
BASE_RECEIPT_SHA256 = (
    "43809ef880fd9b5039aa0971e4b010830eb564cb65f0a491a12e04a299201dba"
)
DEFAULT_OUTPUT = TMP / "stage1-atomic-window-selector-r357/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-atomic-window-selector-r357/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "0d7df618b16e8fb59d56b73b7e3382361bba7dc57d3ea47441f5be8296fd757c"
)
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(
        resolved != scratch and scratch in resolved.parents,
        f"{label} must be below repository tmp/",
    )
    return resolved


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * 0x4000, "r356 base size changed")
    require(digest(source) == BASE_SHA256, f"wrong exact r356 base: {digest(source)}")
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256, "r356 receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    require(
        base_receipt.get("schema")
        == "penta-stage1-vblank-palette-map-atomic-r356-build-v1",
        "r356 receipt schema drifted",
    )
    require(base_receipt.get("candidate_sha256") == BASE_SHA256, "r356 receipt names another candidate")

    before = inspect_stage_card_palette_handoff(source)
    require(
        before["installed"] and before["variant"] == "vblank-atomic-v2",
        "r356 atomic handoff preimage drifted",
    )
    require(
        source[
            VBLANK_COMMIT_OFFSET:
            VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_COMMIT)
        ]
        == VBLANK_ATOMIC_COMMIT,
        "r356 VBlank commit bytes drifted",
    )
    extension = len(VBLANK_ATOMIC_WINDOW_COMMIT) - len(VBLANK_ATOMIC_COMMIT)
    require(extension > 0, "paired-selector commit must extend r356")
    require(
        source[
            VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_COMMIT):
            VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_WINDOW_COMMIT)
        ]
        == bytes(extension),
        "paired-selector extension cave is no longer empty",
    )

    rom = bytearray(source)
    rom[
        VBLANK_COMMIT_OFFSET:
        VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_WINDOW_COMMIT)
    ] = VBLANK_ATOMIC_WINDOW_COMMIT
    update_checksums(rom)
    candidate = bytes(rom)

    after = inspect_stage_card_palette_handoff(candidate)
    require(
        after["installed"] and after["variant"] == "vblank-atomic-window-v3",
        "paired-selector handoff post-install inspection failed",
    )
    require(after["vblank_atomic_window_installed"], "paired selector was not authenticated")

    owned = set(
        range(
            VBLANK_COMMIT_OFFSET,
            VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_WINDOW_COMMIT),
        )
    )
    changed = {
        index
        for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(
        changed <= owned | CHECKSUM_OFFSETS,
        f"r357 escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)}",
    )
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(sha == EXPECTED_CANDIDATE_SHA256, f"candidate identity drift: {sha}")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-atomic-window-selector-r357-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r356_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "incident": {
            "rejected_candidate_sha256": BASE_SHA256,
            "reproduced_route": "SELECT open; alias on close edge; no movement",
            "reproduced_final_lcdc": "83",
            "symptom": "red/green item rows remain in Stage-1 gameplay until movement",
            "cause": "completed-map commit changed LCDC.3 without pairing LCDC.6",
            "reproduction": "tmp/r356-menu-close-alias-repro/report.txt",
        },
        "handoff": {
            "variant": after["variant"],
            "vblank_commit": "bank13:$73FC-$7465",
            "selector_invariant": "LCDC.6 is always opposite LCDC.3 after a map commit",
            "absolute_commit_mask": "paired bits 6/3",
            "relative_commit_xor": "48",
        },
        "required_live_gates": base_receipt["required_live_gates"],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "candidate_sha256": receipt["candidate_sha256"],
                "output": str(output),
                "status": receipt["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
