#!/usr/bin/env python3
"""Install the deterministic Stage 1 phase/content key on exact r199.

The postcomputed attribute publisher must be armed before the native physical
map flip: C1A0 can advance while the multi-HBlank tile copier is in flight.
DC00 is the native packed-source phase and anticipates that advance without
sampling timing-sensitive SCX.  Raw cell 247 closes the remaining semantic
collisions across the exact six-profile copier corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums
from verify_stage1_transition_key import STAGE1_LUT_OFFSET, assess


BASE_SHA256 = "0ebae52b5c74ecb5e0cd2bbee11c4ee4fa6aca118aeb0515333722e0273518e8"
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
FEATURES = ("dc00", "scy", "dc02", "raw247")
OLD_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FABB"
    "C1A847FA9FC2A8B9C812C9C3B9DA"
)
NEW_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FA00"
    "DCA847FA97C2A8B9C812C9C3B9DA"
)
DEFAULT_CORPORA = (
    Path("tmp/stage1-semantic-key-r74/transition-key-rerun"),
    Path("tmp/stage1-key-box-copy-corpus-r199"),
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def collect_traces(roots: tuple[Path, ...], explicit: dict[Path, bytes] | None = None
                   ) -> list[tuple[Path, Path, bytes]]:
    """Load standalone corpora or require explicit bytes without file fallback."""
    collected = []
    used = set()
    for root in roots:
        traces = sorted(root.glob("*/events.tsv") if explicit is None else (
            path for path in explicit if path.name == "events.tsv" and path.parent.parent == root))
        if not traces:
            raise SystemExit(f"no transition traces below {root}")
        for trace in traces:
            payload = trace.read_bytes() if explicit is None else explicit[trace]
            collected.append((root, trace, payload))
            used.add(trace)
    if explicit is not None and used != set(explicit):
        raise ValueError("unused explicit transition trace")
    return collected


def construct(source: bytes) -> bytes:
    """Emit the fixed recipe; this performs no corpus or live qualification."""
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r199 base: {digest(source)}")
    if len(OLD_RUNTIME) != RUNTIME_LENGTH or len(NEW_RUNTIME) != RUNTIME_LENGTH:
        raise SystemExit("internal runtime length error")
    rom = bytearray(source)
    for offset in RUNTIME_OFFSETS:
        if rom[offset : offset + RUNTIME_LENGTH] != OLD_RUNTIME:
            raise SystemExit(f"Stage 1 runtime preimage moved at ${offset:06X}")
        rom[offset : offset + RUNTIME_LENGTH] = NEW_RUNTIME
    update_checksums(rom)
    return bytes(rom)


def build(source: bytes, *, corpora: tuple[Path, ...] = DEFAULT_CORPORA,
          traces: dict[Path, bytes] | None = None) -> tuple[bytes, dict[str, object]]:
    candidate = construct(source)
    canonical_lut = source[STAGE1_LUT_OFFSET : STAGE1_LUT_OFFSET + 256]
    if len(canonical_lut) != 256:
        raise SystemExit("missing canonical Stage 1 LUT")

    profiles: dict[str, object] = {}
    for root, trace, payload in collect_traces(corpora, traces):
        name = f"{root.name}/{trace.parent.name}"
        profile = assess(trace, FEATURES, canonical_lut, trace_text=payload.decode())
        if profile["false_negatives"]:
            raise SystemExit(f"phase/content key misses transitions in {name}: {profile}")
        profiles[name] = profile

    receipt = {
        "schema": "penta-stage1-phase-content-key-r208-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "candidate_sha256": digest(candidate),
        "runtime_offsets": [f"0x{offset:X}" for offset in RUNTIME_OFFSETS],
        "old_features": ["SCY", "DC02", "raw27", "raw255"],
        "new_features": list(FEATURES),
        "runtime_length_unchanged": True,
        "runtime_instruction_timing_unchanged": True,
        "timing_sensitive_scx_used": False,
        "profiles": profiles,
        "required_first_gates": [
            "3600-frame native no-bleed",
            "low-health deterministic replay",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, action="append")
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes(), corpora=tuple(args.corpus or DEFAULT_CORPORA))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
