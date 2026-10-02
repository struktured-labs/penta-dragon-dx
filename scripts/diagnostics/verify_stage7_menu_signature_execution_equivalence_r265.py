#!/usr/bin/env python3
"""Refine r265's non-menu transfer to an execution-path equivalence rule.

The historical 295ce/3bf receipts conservatively asked for FFE4 to remain
zero "throughout" a non-menu gate.  mGBA's safe instrumentation can prove the
condition that actually controls equivalence more directly: the only changed
payload is bank13:$6A40-$6A56, and either that helper never executes or every
exact helper entry observes FFE4=0 and takes the common four-byte, 36T RET-Z
path before any changed byte.  Frame-boundary FFE4=0 remains required context
telemetry; debugger write-watchpoints are deliberately avoided because they
have stalled savestate-backed routes in this environment.

This offline receipt binds the first r265 short ABI PASS.  It does not promote
the ROM; visual and safe-boundary runs must independently satisfy the same
entry-qualified rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
BASE = ROOT / "tmp/stage7-dual-plane-hdma-r264/candidate.gb"
CANDIDATE = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
EQUIVALENCE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "helper-equivalence-static-receipt.json"
)
TRANSFER = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "transferred-stage7-static-receipt.json"
)
MENU = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "menu-fixed-r1/receipt.json"
)
WINDOW = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "generic-menu-natural-receipt.json"
)
DEFAULT_ABI = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "abi-r265-r2/receipt.json"
)
DEFAULT_OUTPUT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "execution-equivalence-short-abi-r1.json"
)

BASE_SHA = "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
CANDIDATE_SHA = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
EQUIVALENCE_SHA = "295ce612d6dc1dead72e776f44dafb3bd22b6bc0e44b101435b27d7ddafe0583"
TRANSFER_SHA = "3bf962c18274ba8c5efe1e1ee9673ba19401dbebfc970782efed5e9e96673661"
MENU_SHA = "17c2d8a5a6b2d1d36ce5cb9d931db03534b2dbf7cacf5fae06be4cf3dbfdb7e5"
WINDOW_SHA = "f32977eb72a3030b21015b089db00d93420dd1c7c58613b78a6a234b59415019"
ABI_SHA = "49561196551f825cb3f235b2081320ea59c133b7acb20e7cce0633f8a0859f90"
SPEED_PROBE_SHA = "3b3643da1a42ba4d6d23ee161fc6914b3b655e308d39ec22042ce359ec68cdc6"
ABI_VERIFIER_SHA = "f4815c5717a92a32eb47c898fa6aa56579acc8e75c66a9dd64c62babeebcf804"
LAUNCHER_SHA = "46fe5b57771627e9141e359bd93c9d821c2b873d34162e355dfec33896649570"
HELPER_OFFSET = 13 * 0x4000 + 0x6A40 - 0x4000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return digest(path.read_bytes())


def scratch(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(resolved != root and resolved.is_relative_to(root)
                for root in roots),
            "output must be a child of repo tmp/ or /mnt/data/tmp/")
    return resolved


def dynamic_rule(helper_hits: object, nonzero_hits: object) -> dict[str, Any]:
    integer = (
        isinstance(helper_hits, int) and not isinstance(helper_hits, bool)
        and isinstance(nonzero_hits, int) and not isinstance(nonzero_hits, bool)
    )
    no_execution = integer and helper_hits == 0 and nonzero_hits == 0
    zero_at_every_entry = (
        integer and helper_hits > 0 and nonzero_hits == 0
    )
    consistent = (
        integer and 0 <= nonzero_hits <= helper_hits
    )
    return {
        "passed": bool(consistent and (no_execution or zero_at_every_entry)),
        "integer_counts": integer,
        "consistent_counts": consistent,
        "changed_helper_not_executed": no_execution,
        "FFE4_zero_at_every_changed_helper_entry": zero_at_every_entry,
    }


def mutation_controls() -> dict[str, bool]:
    no_execution = dynamic_rule(0, 0)
    zero_entries = dynamic_rule(8, 0)
    return {
        "zero_execution_passes": no_execution["passed"],
        "zero_at_each_entry_passes": zero_entries["passed"],
        "nonzero_entry_rejected": not dynamic_rule(8, 1)["passed"],
        "negative_count_rejected": not dynamic_rule(-1, 0)["passed"],
        "overcount_rejected": not dynamic_rule(1, 2)["passed"],
        "boolean_count_rejected": not dynamic_rule(True, 0)["passed"],
    }


def audit(abi_path: Path) -> dict[str, Any]:
    identities = {
        "e048_rom": sha256(BASE),
        "r265_rom": sha256(CANDIDATE),
        "historical_equivalence": sha256(EQUIVALENCE),
        "transferred_static": sha256(TRANSFER),
        "stage7_menu_live": sha256(MENU),
        "generic_window_live": sha256(WINDOW),
        "short_ABI_live": sha256(abi_path),
        "verifier": sha256(SELF),
    }
    require(identities == {
        "e048_rom": BASE_SHA,
        "r265_rom": CANDIDATE_SHA,
        "historical_equivalence": EQUIVALENCE_SHA,
        "transferred_static": TRANSFER_SHA,
        "stage7_menu_live": MENU_SHA,
        "generic_window_live": WINDOW_SHA,
        "short_ABI_live": ABI_SHA,
        "verifier": identities["verifier"],
    }, "execution-equivalence identity changed")

    base, candidate = BASE.read_bytes(), CANDIDATE.read_bytes()
    old = bytes.fromhex(
        "F0 E4 B7 C8 FA 80 D8 D6 02 C0 AF EA 53 DF EA 57 DF 3C C9 00 00 00 00"
    )
    new = bytes.fromhex(
        "F0 E4 B7 C8 FA 80 D8 FE 02 28 03 FE 08 C0 AF EA 53 DF EA 57 DF 3C C9"
    )
    require(base[HELPER_OFFSET:HELPER_OFFSET + 23] == old
            and candidate[HELPER_OFFSET:HELPER_OFFSET + 23] == new,
            "Window helper exact old/new payload changed")
    require(old[:4] == new[:4] == bytes.fromhex("F0 E4 B7 C8"),
            "FFE4-zero RET-Z prefix changed")
    differences = [
        index for index, pair in enumerate(zip(base, candidate))
        if pair[0] != pair[1]
    ]
    require(len(differences) == 17
            and set(differences) <= set(range(HELPER_OFFSET, HELPER_OFFSET + 23))
            | {0x014E, 0x014F},
            "r265 differs outside helper/global checksum")

    abi = json.loads(abi_path.read_text())
    require(abi.get("schema") == "penta-stage7-dual-plane-abi-smoke-v1"
            and abi.get("status") == "PASS",
            "short ABI receipt did not pass")
    require(abi.get("expected_candidate_sha256") == CANDIDATE_SHA
            and abi.get("expected_static_receipt_sha256") == TRANSFER_SHA,
            "short ABI receipt is not r265/3bf bound")
    before, after = abi.get("identity_before", {}), abi.get("identity_after", {})
    require(before == after and before == {
        "candidate_sha256": CANDIDATE_SHA,
        "probe_sha256": SPEED_PROBE_SHA,
        "verifier_sha256": ABI_VERIFIER_SHA,
        "launcher_sha256": LAUNCHER_SHA,
        "static_receipt_sha256": TRANSFER_SHA,
    }, "short ABI tool/input identity changed")
    observed = abi.get("observed", {})
    ffe4 = observed.get("FFE4_transfer", {})
    require(ffe4.get("passed") is True
            and all(ffe4.get("checks", {}).values()),
            "short ABI FFE4 telemetry did not pass")
    raw_path = Path(abi.get("raw_result", ""))
    if not raw_path.is_absolute():
        raw_path = (abi_path.parent / raw_path).resolve()
    require(raw_path.is_file()
            and sha256(raw_path) == abi.get("raw_result_sha256"),
            "short ABI raw result identity changed")
    raw = json.loads(raw_path.read_text())
    require(raw.get("frames") == 300
            and raw.get("ffe4_zero_play_frames") == 300
            and raw.get("ffe4_nonzero_play_frames") == 0
            and raw.get("first_ffe4_nonzero_play_frame") == -1
            and raw.get("first_ffe4_nonzero_value") == -1,
            "short ABI non-menu FFE4 boundary telemetry changed")
    dynamic = dynamic_rule(
        raw.get("window_helper_hits"),
        raw.get("window_helper_ffe4_nonzero_hits"),
    )
    require(dynamic["passed"],
            "short ABI entered a changed helper with FFE4 nonzero")
    controls = mutation_controls()
    require(all(controls.values()), "dynamic equivalence mutation escaped")

    return {
        "schema": "penta-stage7-r265-execution-equivalence-v1",
        "status": "PASS_SHORT_ABI_ONLY_MORE_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_run_by_this_verifier": False,
        "identities": identities,
        "historical_requirement": "295ce requested FFE4==$00 throughout",
        "superseding_execution_rule": {
            "rule": (
                "zero executions of changed bank13:$6A40 helper OR FFE4==$00 "
                "at every exact helper entry"
            ),
            "proof": dynamic,
            "common_prefix": "F0 E4 B7 C8 (LDH FFE4; OR A; RET Z)",
            "common_prefix_t_cycles": 36,
            "first_changed_byte_offset": "bank13:$6A47",
            "frame_context": "FFE4 zero at all 300/300 measured callbacks",
            "rationale": (
                "no changed byte can execute when helper_hits=0; if it does "
                "execute, entry FFE4=0 returns before the first changed byte"
            ),
        },
        "short_ABI": {
            "receipt": str(abi_path.relative_to(ROOT)),
            "receipt_sha256": sha256(abi_path),
            "raw_result": str(raw_path.relative_to(ROOT)),
            "raw_result_sha256": sha256(raw_path),
            "frames": raw["frames"],
            "helper_entries": raw["abi_entry_hits"],
            "window_helper_entries": raw["window_helper_hits"],
            "window_helper_nonzero_entries": raw[
                "window_helper_ffe4_nonzero_hits"
            ],
        },
        "changed_payload": {
            "difference_count": len(differences),
            "only_window_helper_and_global_checksum": True,
            "first_changed_helper_byte": "bank13:$6A47",
        },
        "separate_changed_route_nonvacuity": {
            "stage7_menu_live_receipt": MENU_SHA,
            "generic_window_live_receipt": WINDOW_SHA,
        },
        "mutation_controls": controls,
        "remaining": [
            "duplicate r265 Stage7 exact visual with the same entry rule",
            "duplicate r265 safe-boundary speed with the same entry rule",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abi-receipt", type=Path, default=DEFAULT_ABI)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = scratch(args.output)
    receipt = audit(args.abi_receipt.resolve())
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
    print("PASS: r265 short-ABI execution equivalence")
    print(f"Receipt: {output.relative_to(ROOT)}")
    print(f"Receipt SHA-256: {digest(payload.encode())}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
