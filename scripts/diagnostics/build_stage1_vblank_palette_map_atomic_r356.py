#!/usr/bin/env python3
"""Build r356: commit Stage-1 BG0 and its completed map in one VBlank."""

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
    RUNTIME_SOURCE_B_OFFSET,
    RUNTIME_SOURCE_C_OFFSET,
    VBLANK_ATOMIC_COMMIT,
    VBLANK_ATOMIC_RUNTIME,
    VBLANK_COMMIT_OFFSET,
    _runtime_payloads,
    _source_runtime_image,
    inspect_stage_card_palette_handoff,
)


TMP = ROOT / "tmp"
BASE = TMP / "stage1-postcommit-hram-target-r354/candidate.gb"
BASE_RECEIPT = TMP / "stage1-postcommit-hram-target-r354/build-receipt.json"
BASE_SHA256 = "3759f8ad10e6841f7705d13ee76f4b45478460b1bf782acb8507b4f70414e71f"
BASE_RECEIPT_SHA256 = "0cc07e1a3fe2b56f7f348fc254e4b361b7d7bbed1d63e547eb6c46cdf699d3d0"
DEFAULT_OUTPUT = TMP / "stage1-vblank-palette-map-atomic-r356/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-vblank-palette-map-atomic-r356/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "31a090fd4609ec1d42813abd13b312dbaba8723886a96e3857ee79ec4228852b"
)

OLD_COMMIT = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F AF EA 5C DF "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 "
    "F0 C4 B7 28 10 E6 04 07 47 AF E0 C4 "
    "F0 40 E6 F7 B0 E0 40 18 06 F0 40 EE 08 E0 40 "
    "C3 1D 6F"
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
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be below repository tmp/")
    return resolved


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * 0x4000, "r354 base size changed")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r354 base: {digest(source)}")
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256,
            "r354 receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    require(base_receipt.get("schema")
            == "penta-stage1-postcommit-hram-target-r354-build-v1",
            "r354 receipt schema drifted")
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r354 receipt names another candidate")

    before = inspect_stage_card_palette_handoff(source)
    require(before["installed"] and before["variant"] == "dirty-return-v1",
            "r354 legacy dirty-return Stage-card handoff drifted")
    fast, continuation = _runtime_payloads()
    runtime = bytearray(_source_runtime_image(source))
    require(runtime[23:41] == fast + continuation,
            "r354 WRAM Stage-card dispatcher preimage drifted")
    require(source[VBLANK_COMMIT_OFFSET:
                   VBLANK_COMMIT_OFFSET + len(OLD_COMMIT)] == OLD_COMMIT,
            "r354 VBlank commit preimage drifted")
    require(source[VBLANK_COMMIT_OFFSET + len(OLD_COMMIT):
                   VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_COMMIT)]
            == bytes(len(VBLANK_ATOMIC_COMMIT) - len(OLD_COMMIT)),
            "expanded VBlank commit cave is no longer empty")

    rom = bytearray(source)
    runtime[23:41] = VBLANK_ATOMIC_RUNTIME
    rom[RUNTIME_SOURCE_B_OFFSET:RUNTIME_SOURCE_B_OFFSET + 36] = runtime[:36]
    rom[RUNTIME_SOURCE_C_OFFSET:RUNTIME_SOURCE_C_OFFSET + 5] = runtime[36:]
    rom[VBLANK_COMMIT_OFFSET:
        VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_COMMIT)] = VBLANK_ATOMIC_COMMIT
    update_checksums(rom)
    candidate = bytes(rom)

    after = inspect_stage_card_palette_handoff(candidate)
    require(after["installed"] and after["variant"] == "vblank-atomic-v2",
            "atomic Stage-card handoff post-install inspection failed")
    require(after["vblank_atomic_installed"],
            "VBlank atomic handoff was not authenticated")
    require(candidate[VBLANK_COMMIT_OFFSET:
                      VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_COMMIT)]
            == VBLANK_ATOMIC_COMMIT, "VBlank commit did not round-trip")

    owned = set(range(RUNTIME_SOURCE_B_OFFSET,
                      RUNTIME_SOURCE_B_OFFSET + 36))
    owned.update(range(RUNTIME_SOURCE_C_OFFSET,
                       RUNTIME_SOURCE_C_OFFSET + 5))
    owned.update(range(VBLANK_COMMIT_OFFSET,
                       VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_COMMIT)))
    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(changed <= owned | CHECKSUM_OFFSETS,
            f"r356 escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)}")
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-vblank-palette-map-atomic-r356-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r354_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "incident": {
            "rejected_candidate_sha256": BASE_SHA256,
            "reproduced_frame": 508,
            "symptom": "Stage-1 BG0 over the outgoing STAGE-card tilemap",
            "cause": "dirty-return palette load preceded deferred VBlank map flip",
        },
        "handoff": {
            "variant": after["variant"],
            "dirty_return": "direct atomic-wrapper pass-through",
            "vblank_commit": "bank13:$73FC-$745E",
            "order": ["BG0", "SCX", "SCY", "LCDC"],
            "sentinel": "FFE1 consumed only inside pending VBlank commit",
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
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "output": str(output), "status": receipt["status"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
