#!/usr/bin/env python3
"""Build an exact-r208 Stage-1 split phase/content key candidate.

r208 XORs the native packed-source phase into the semantic layout signature.
That permits a phase delta to cancel a content delta and suppress a required
attribute publication.  This diagnostic keeps two independent per-map bytes:

* cache byte 0: ``SCY ^ DC02 ^ raw[123] ^ raw[280]``;
* cache byte 1: the exact native source phase ``DC00``.

The semantic signature is collision-free in the established Stage-1 corpus,
while the separate phase byte makes phase/content cancellation impossible.
The larger decider executes from erased expansion bank 21 and restores bank 1
through the stock mapper without disturbing the caller's comparison flags.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums
from build_stage1_phase_content_key_r208 import collect_traces


BASE_SHA256 = "cc5baaaddd063f5c943b65d9a09f05afb40c71982405de81fc5e5d4a9cff5840"
BANK_SIZE = 0x4000
PRIVATE_BANK = 21
PRIVATE_ADDR = 0x4100
PRIVATE_OFFSET = PRIVATE_BANK * BANK_SIZE + PRIVATE_ADDR - 0x4000
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
OLD_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FA00"
    "DCA847FA97C2A8B9C812C9C3B9DA"
)
DEFAULT_CORPORA = (
    Path("tmp/stage1-semantic-key-r74/transition-key-rerun"),
    Path("tmp/stage1-key-box-copy-corpus-r199"),
)


class Asm:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.rel8: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return self.origin + len(self.code)

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise AssertionError(f"duplicate label: {name}")
        self.labels[name] = self.pc

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.rel8.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for operand, label in self.rel8:
            source_after = self.origin + operand + 1
            delta = self.labels[label] - source_after
            if not -128 <= delta <= 127:
                raise AssertionError((label, delta))
            self.code[operand] = delta & 0xFF
        return bytes(self.code)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_gateway() -> bytes:
    code = bytes.fromhex(
        # Normalize Stage-1 live/Gargoyle scenes; every other scene retains
        # the existing later-stage WRAM dispatcher at $DAB9.
        "FA 80 D8 E6 F7 FE 02 C2 B9 DA "
        # Map expansion bank 21 and tail-enter its larger split-key decider.
        "3E 15 CD 61 00 C3 00 41"
    )
    if len(code) > RUNTIME_LENGTH:
        raise AssertionError("split-key gateway exceeds the WRAM runtime slot")
    return code + bytes(RUNTIME_LENGTH - len(code))


def emit_semantic_signature(a: Asm) -> None:
    # A = SCY ^ DC02 ^ raw[123] ^ raw[280].  The two raw offsets are
    # collision-free across the exact archived transition corpus.
    a.db(
        0xF0, 0x42, 0x47,                  # B = SCY
        0xFA, 0x02, 0xDC, 0xA8, 0x47,      # B ^= DC02
        0xFA, 0x1B, 0xC2, 0xA8, 0x47,      # B ^= C1A0 + 123
        0xFA, 0xB8, 0xC2, 0xA8,            # A = B ^ C1A0 + 280
    )


def build_private_decider() -> bytes:
    a = Asm(PRIVATE_ADDR)
    # Select DF53/DF57 from the exact physical destination H.  DF54/DF58 are
    # the second bytes of those existing three-byte metadata records; DF55/
    # DF59 remain owned by the Stage-1 hazard scanner.
    a.db(0x16, 0xDF, 0x7C, 0xEE, 0xCB, 0x5F, 0x1A, 0x4F)
    emit_semantic_signature(a)
    a.db(0xB9)                              # semantic signature == cache A?
    a.jr(0x20, "changed_a")
    # Cache A=$FF is the entry sentinel.  Even if the real signature is also
    # $FF, fail closed and initialize both bytes rather than trusting cache B.
    a.db(0x3C)
    a.jr(0x28, "sentinel_changed")
    a.db(
        0x13, 0x1A, 0x4F,                  # C = cached native phase
        0xFA, 0x00, 0xDC,                  # A = exact DC00 phase
        0xB9,                              # phase == cache B?
    )
    a.jr(0x20, "changed_b")
    a.label("unchanged")
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)     # preserve Z; restore bank 1

    a.label("sentinel_changed")
    a.db(0x3D)                              # restore semantic signature $FF
    a.jr(0x18, "changed_a")

    a.label("changed_b")
    a.db(0x12)                              # publish phase only
    a.jr(0x18, "dirty_return")

    a.label("changed_a")
    a.db(0x12, 0x13)                        # publish semantic signature
    a.db(0xFA, 0x00, 0xDC, 0x12)           # publish independent phase

    a.label("dirty_return")
    a.db(0x3E, 0x01, 0xB7, 0xC3, 0x61, 0x00)  # NZ; restore bank 1
    return a.finish()


def transition_metrics(roots: tuple[Path, ...], traces: dict[Path, bytes] | None = None
                       ) -> dict[str, object]:
    profiles: dict[str, object] = {}
    total_events = total_semantic = total_false_negative = 0
    for root, trace, payload in collect_traces(roots, traces):
        previous: dict[str, tuple[int, int, bytes]] = {}
        events = semantic = false_negative = 0
        with io.StringIO(payload.decode(), newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                destination = row["destination"]
                raw = bytes.fromhex(row["raw"])
                plane = bytes.fromhex(row["plane"])
                if len(raw) != 576 or len(plane) != 576:
                    raise SystemExit(f"invalid transition plane in {trace}")
                semantic_key = (
                    int(row["scy"], 16)
                    ^ int(row["dc02"], 16)
                    ^ raw[123]
                    ^ raw[280]
                )
                phase_key = int(row["dc00"], 16)
                prior = previous.get(destination)
                previous[destination] = (semantic_key, phase_key, plane)
                events += 1
                if prior is None or prior[2] == plane:
                    continue
                semantic += 1
                if prior[0] == semantic_key and prior[1] == phase_key:
                    false_negative += 1
        name = f"{root.name}/{trace.parent.name}"
        profiles[name] = {
            "events": events,
            "semantic_transitions": semantic,
            "false_negatives": false_negative,
        }
        total_events += events
        total_semantic += semantic
        total_false_negative += false_negative
    if total_false_negative:
        raise SystemExit(
            f"split key misses {total_false_negative} established transitions"
        )
    return {
        "profiles": profiles,
        "events": total_events,
        "semantic_transitions": total_semantic,
        "false_negatives": total_false_negative,
    }


def construct(source: bytes) -> bytes:
    """Emit fixed split-key code without claiming historical corpus checks."""
    if sha256(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r208 base: {sha256(source)}")
    gateway = build_gateway()
    private = build_private_decider()

    rom = bytearray(source)
    for offset in RUNTIME_OFFSETS:
        if rom[offset:offset + RUNTIME_LENGTH] != OLD_RUNTIME:
            raise SystemExit(f"Stage-1 runtime preimage moved at ${offset:06X}")
        rom[offset:offset + RUNTIME_LENGTH] = gateway
    if rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(private)] != bytes([0xFF]) * len(private):
        raise SystemExit("expansion-bank split-key cave is no longer erased")
    rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(private)] = private
    update_checksums(rom)
    return bytes(rom)


def build(source: bytes, *, corpora: tuple[Path, ...] = DEFAULT_CORPORA,
          traces: dict[Path, bytes] | None = None) -> tuple[bytes, dict[str, object]]:
    candidate = construct(source)
    private = build_private_decider()
    metrics = transition_metrics(corpora, traces)
    receipt = {
        "schema": "penta-stage1-split-phase-key-r209-v1",
        "status": "STATIC_PASS_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": sha256(source),
        "candidate_sha256": sha256(candidate),
        "gateway_offsets": [f"0x{offset:X}" for offset in RUNTIME_OFFSETS],
        "private_helper": f"bank{PRIVATE_BANK}:${PRIVATE_ADDR:04X}",
        "private_helper_size": len(private),
        "semantic_key": "SCY ^ DC02 ^ raw123 ^ raw280",
        "phase_key": "DC00",
        "phase_content_cancellation_possible": False,
        "hazard_cache_bytes_preserved": ["DF55", "DF59"],
        "corpus": metrics,
        "required_first_gates": [
            "3600-frame native no-bleed",
            "current-ROM menu/item/low-health hazard",
            "Stage-1 wall/tile publication integrity",
            "strict Stage-1 speed",
            "Pocket/SameBoy physical confirmation",
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
