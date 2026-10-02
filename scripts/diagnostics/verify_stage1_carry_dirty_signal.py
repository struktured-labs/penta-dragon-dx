#!/usr/bin/env python3
"""Fail closed on the Stage-1 saved-Carry dirty signal trace contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MAP_DONE = "0x42EC"
DIRTY_POSTCOPY = "0x4353"
COMMON_EXIT = "0x6C50"
EXPECTED_ROM_SHA256 = (
    "53b52ac2c15d5069c822185867a72f9468112ecbc9fcb20db2bb834d08dc0de6"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_sample(sample: str) -> dict[str, int]:
    fields = sample.split(":")
    if len(fields) != 8:
        raise ValueError(f"expected 8 trace fields, got {sample!r}")
    frame = int(fields[0])
    values = [int(value, 16) for value in fields[1:]]
    return dict(zip(
        ("frame", "a", "b", "f", "ffba", "scene", "bank", "ffa5"),
        (frame, *values),
    ))


def validate_map_done(rows: list[dict[str, int]]) -> dict[str, int]:
    if not rows:
        raise AssertionError("map_done trace is empty")
    pure = dirty = 0
    for row in rows:
        carry = 1 if row["f"] & 0x10 else 0
        latch = row["ffa5"]
        if latch == 0:
            pure += 1
            if carry:
                raise AssertionError(
                    f"frame {row['frame']}: pure FFA5=00 arrived C=1"
                )
        else:
            dirty += 1
            if latch not in (0x98, 0x9C):
                raise AssertionError(
                    f"frame {row['frame']}: dirty FFA5=${latch:02X}"
                )
            if not carry:
                raise AssertionError(
                    f"frame {row['frame']}: dirty FFA5=${latch:02X} arrived C=0"
                )
    if not pure or not dirty:
        raise AssertionError(f"need both pure and dirty samples, got {pure}/{dirty}")
    return {"pure": pure, "dirty": dirty}


def require_latches(
    samples: dict[str, list[str]], address: str, allowed: set[int]
) -> dict[str, int]:
    rows = [parse_sample(sample) for sample in samples.get(address, [])]
    if not rows:
        raise AssertionError(f"trace {address} is empty")
    counts: dict[str, int] = {}
    for row in rows:
        latch = row["ffa5"]
        if latch not in allowed:
            raise AssertionError(
                f"{address} frame {row['frame']}: FFA5=${latch:02X}, "
                f"allowed={sorted(allowed)}"
            )
        key = f"0x{latch:02X}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    if len(manifest.get("rows", [])) != 1:
        raise AssertionError("expected one Stage-1 speed row")
    row = manifest["rows"][0]
    dx = row["dx"]
    samples = dx.get("trace_addr_samples", {})
    hits = dx.get("trace_addr_hits", {})

    map_done_rows = [parse_sample(sample) for sample in samples.get(MAP_DONE, [])]
    contract = validate_map_done(map_done_rows)
    path_latches = {
        # $4353 has no same-address false positives in this trace: all six
        # hits are the fixed bank-1 dirty completion call.
        "dirty_postcopy": require_latches(
            samples, DIRTY_POSTCOPY, {0x98, 0x9C}
        ),
        # $6C50 is the common bank-19 return before XOR/LDH clears the latch.
        # Pure and dirty/direct room03 exits must both reach it.
        "common_exit_before_clear": require_latches(
            samples, COMMON_EXIT, {0x00, 0x98, 0x9C}
        ),
    }
    if not {"0x00", "0x98", "0x9C"}.issubset(
        path_latches["common_exit_before_clear"]
    ):
        raise AssertionError(
            "common exit did not sample pure plus both exact destinations"
        )

    rom_path = Path(dx["rom"])
    rom_sha = digest(rom_path)
    if rom_sha != EXPECTED_ROM_SHA256:
        raise AssertionError(f"candidate ROM changed: {rom_sha}")
    rom = rom_path.read_bytes()
    # Static half of the live receipt: Carry selects the unchanged compiler
    # address, C=0 falls through the exact B=$05/pure DBF1 block, both postcopy
    # routes retain the common FFA5 clear at bank19:$6C50.
    if rom[0x42EC:0x42FB] != bytes.fromhex(
        "38 0D 78 FE 05 28 03 CD F1 DB FB C9 00 00 00"
    ):
        raise AssertionError("map_done carry route changed")
    common_return = 19 * 0x4000 + (0x6C50 - 0x4000)
    if rom[common_return:common_return + 8] != bytes.fromhex(
        "AF E0 A5 3E 01 C3 61 00"
    ):
        raise AssertionError("common FFA5 clear changed")

    # Deterministic negative controls must fail the same validator.
    pure_mutant = [dict(map_done_rows[0])]
    pure_mutant[0]["ffa5"] = 0
    pure_mutant[0]["f"] |= 0x10
    dirty_mutant = [dict(map_done_rows[0])]
    dirty_mutant[0]["ffa5"] = 0x98
    dirty_mutant[0]["f"] &= ~0x10
    negative_controls = {}
    for name, mutant in (("pure_carry_set", pure_mutant),
                         ("dirty_carry_clear", dirty_mutant)):
        try:
            validate_map_done(mutant)
        except AssertionError as error:
            negative_controls[name] = str(error)
        else:
            raise AssertionError(f"negative control {name} was accepted")

    status = (
        "PASS" if manifest.get("status") == "pass"
        and row.get("ratio", 0) >= 0.98
        and row.get("dx", {}).get("scroll_changes")
        == row.get("original", {}).get("scroll_changes")
        else "FAIL"
    )
    receipt = {
        "status": status,
        "manifest": str(args.manifest),
        "manifest_sha256": digest(args.manifest),
        "rom": str(rom_path),
        "rom_sha256": rom_sha,
        "ratio": row.get("ratio"),
        "scroll": {
            "original": row.get("original", {}).get("scroll_changes"),
            "dx": row.get("dx", {}).get("scroll_changes"),
        },
        "map_done_latch_carry": contract,
        "path_latches": path_latches,
        "trace_hits": {address: hits.get(address, 0) for address in (
            MAP_DONE, DIRTY_POSTCOPY, COMMON_EXIT
        )},
        "trace_sample_limit_note": (
            "map_done/common samples are capped at 64; static exact-byte "
            "routing binds the sampled invariant to all hits"
        ),
        "negative_controls": negative_controls,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
