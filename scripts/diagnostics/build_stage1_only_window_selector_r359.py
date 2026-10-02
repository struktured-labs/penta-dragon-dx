#!/usr/bin/env python3
"""Build r359: pair BG/Window selectors in Stage 1 and nowhere else."""

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
    VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT,
    VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT,
    VBLANK_COMMIT_OFFSET,
    inspect_stage_card_palette_handoff,
)


TMP = ROOT / "tmp"
BASE = TMP / "stage1-scoped-window-selector-r358/candidate.gb"
BASE_RECEIPT = TMP / "stage1-scoped-window-selector-r358/build-receipt.json"
BASE_SHA256 = "8a354d3ed408038d6f61302558053f7aef0d9d772c3de4667b544630824160ac"
BASE_RECEIPT_SHA256 = (
    "ed92fdce2e13056d3093abb9a144a959a2983d212911d1ac424d3e051f528bac"
)
DEFAULT_OUTPUT = TMP / "stage1-only-window-selector-r359/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-only-window-selector-r359/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "9b1742c4891dbcf71f1ad16769e6f3aa989c85b59b6e65f6b15c9c48a47eff0c"
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
    require(len(source) == 32 * 0x4000, "r358 base size changed")
    require(digest(source) == BASE_SHA256, f"wrong exact r358 base: {digest(source)}")
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256, "r358 receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    require(
        base_receipt.get("schema")
        == "penta-stage1-scoped-window-selector-r358-build-v1",
        "r358 receipt schema drifted",
    )
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r358 receipt names another candidate")

    before = inspect_stage_card_palette_handoff(source)
    require(
        before["installed"]
        and before["variant"] == "vblank-atomic-stage1-window-v4",
        "r358 scene-scoped selector preimage drifted",
    )
    require(
        source[
            VBLANK_COMMIT_OFFSET:
            VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT)
        ] == VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT,
        "r358 VBlank commit bytes drifted",
    )
    extension = (
        len(VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT)
        - len(VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT)
    )
    require(extension > 0, "Stage-1-only commit must extend r358")
    require(
        source[
            VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT):
            VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT)
        ] == bytes(extension),
        "Stage-1-only extension cave is no longer empty",
    )

    rom = bytearray(source)
    rom[
        VBLANK_COMMIT_OFFSET:
        VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT)
    ] = VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT
    update_checksums(rom)
    candidate = bytes(rom)

    after = inspect_stage_card_palette_handoff(candidate)
    require(
        after["installed"]
        and after["variant"] == "vblank-atomic-stage1-only-window-v5",
        "Stage-1-only handoff post-install inspection failed",
    )
    require(after["vblank_atomic_stage1_only_window_installed"],
            "Stage-1-only selector was not authenticated")

    owned = set(range(
        VBLANK_COMMIT_OFFSET,
        VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT),
    ))
    changed = {
        index
        for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(
        changed <= owned | CHECKSUM_OFFSETS,
        f"r359 escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)}",
    )
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {sha}")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-only-window-selector-r359-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r358_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "scope_correction": {
            "failed_r358_speed_manifest": (
                "tmp/stage1-scoped-window-selector-r358/"
                "speed-main-release95-v1/manifest.json"
            ),
            "failed_stage": 5,
            "stage1_discriminator": "D880=02 and FFBA=00",
            "stage1_behavior": "paired LCDC bits 6/3",
            "other_stage_behavior": "exact r356 LCDC bit-3-only selector",
        },
        "handoff": {
            "variant": after["variant"],
            "vblank_commit": "bank13:$73FC-$7484",
            "stage1_absolute_publication_pc": "7465",
            "selector_invariant": (
                "LCDC.6 is opposite LCDC.3 after Stage-1 map commits"
            ),
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
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "output": str(output),
        "status": receipt["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
