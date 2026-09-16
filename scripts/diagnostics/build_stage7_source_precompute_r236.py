#!/usr/bin/env python3
"""Build a Stage-7 source-generation attribute-plane speed experiment.

The stock $139A expander is the sole observed writer of Stage 7's completed
$C1A0-$C3DF packed source.  Relocate that routine into expansion bank 21 and
compile the matching 24x32 attribute plane once at the end of source
generation.  Dirty map publications reuse the plane only when its two-byte
source signature and room still match; every miss and every non-Stage-7 scene
falls back to the byte-exact existing compiler.

This is diagnostic-only until strict speed, four-room semantic soak, audio,
and hardware receipts pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyze_later_attr_signature import desired_plane, semantic_lut
from build_later_hdma_overlap import Asm


BASE_SHA256 = "bb042bd850277e1130a2bde2c2cb86019c4e5f0ba21e4c856699f75aedc3e5af"
BANK = 21
BANK_SIZE = 0x4000
EXPANDER_START = 0x1399
EXPANDER_END = 0x13E5
COMPILER_START = 0x42FC
COMPILER_END = 0x4354

FALLBACK_ADDR = 0x4200
EXPANDER_ADDR = 0x4300
PRECOMPUTE_ADDR = 0x4400
POSTCOPY_ADDR = 0x4500
ROW_COMPILER_ADDR = 0x5000
LUT_ADDR = 0x5F00

KEY_ADDR = 0xD3F8
KEY_VALID_ADDR = 0xD3FB
KEY_VALID = 0xA7
SIGNATURE_A = (444, 149, 19, 251)
SIGNATURE_B = (0, 59, 333, 201)
EXPECTED_WRITER_PCS = {"01:13BE", "01:13C1", "01:13C9", "01:13CB"}


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def emit_key(a: Asm, *, store: bool) -> None:
    for opcode, samples in ((0x47, SIGNATURE_A), (0x4F, SIGNATURE_B)):
        first = 0xC1A0 + samples[0]
        a.db(0xFA, first & 0xFF, first >> 8)
        for offset in samples[1:]:
            source = 0xC1A0 + offset
            a.db(0x21, source & 0xFF, source >> 8, 0xAE)
        a.db(opcode)
    a.db(0xF0, 0xBD, 0x5F)                 # E = exact room
    if store:
        a.db(
            0x78, 0xEA, KEY_ADDR & 0xFF, KEY_ADDR >> 8,
            0x79, 0xEA, (KEY_ADDR + 1) & 0xFF, KEY_ADDR >> 8,
            0x7B, 0xEA, (KEY_ADDR + 2) & 0xFF, KEY_ADDR >> 8,
            0x3E, KEY_VALID,
            0xEA, KEY_VALID_ADDR & 0xFF, KEY_VALID_ADDR >> 8,
        )


def build_row_compiler() -> bytes:
    """Compile all 576 source cells and explicitly zero row padding.

    The caller has selected SVBK3.  The routine's CALL/RET pair therefore
    lives wholly in bank 3; its outer bank-1 frame is not touched until the
    caller restores SVBK1.
    """
    a = Asm(ROW_COMPILER_ADDR)
    a.db(
        0x11, 0xA0, 0xC1,                  # DE = packed 24x24 source
        0x21, 0x00, 0xD0,                  # HL = padded 24x32 plane
        0x06, LUT_ADDR >> 8,                # B = immutable LUT page
    )
    for _row in range(24):
        for _column in range(24):
            a.db(0x1A, 0x13, 0x4F, 0x0A, 0x22)
        a.db(0xAF, *([0x22] * 8))           # deterministic zero padding
    a.db(0xC9)
    return a.finish()


def build_precompute() -> bytes:
    a = Asm(PRECOMPUTE_ADDR)
    # The fixed-bank trampoline masks IE before mapping expansion bank 21 and
    # restores it only after RST $28 maps bank 1 again.  Do not restore IE in
    # this banked helper: a pending IRQ could fire before its RET and enter a
    # bank-1 handler through the wrong switchable ROM page.
    a.db(0xF5, 0xC5, 0xD5, 0xE5)          # preserve native expander ABI
    a.db(0x3E, 0x03, 0xE0, 0x70)           # select persistent plane bank
    a.db(0xCD, ROW_COMPILER_ADDR & 0xFF, ROW_COMPILER_ADDR >> 8)
    emit_key(a, store=True)
    a.db(
        0x3E, 0x01, 0xE0, 0x70,            # restore stack's bank
        0xE1, 0xD1, 0xC1, 0xF1,
        0xC9,
    )
    return a.finish()


def build_relocated_expander(original: bytes, *, precompute: bool = True) -> bytes:
    if len(original) != EXPANDER_END - EXPANDER_START:
        raise AssertionError("expander width changed")
    if not original.endswith(bytes.fromhex("CD D6 09 EF C9")):
        raise AssertionError("expander restore tail changed")
    # Keep the original external-RAM reset CALL, but let the fixed trampoline
    # own the displaced RST $28 / RET after this helper returns.
    prefix = original[:-2]
    if not precompute:
        return prefix + bytes((0xC9,))
    a = Asm(EXPANDER_ADDR + len(prefix))
    a.db(0xF0, 0xBA, 0xFE, 0x06)           # exact Stage-7 selector
    a.jr(0x20, "done")
    a.db(0xCD, PRECOMPUTE_ADDR & 0xFF, PRECOMPUTE_ADDR >> 8)
    a.label("done")
    a.db(0xC9)
    return prefix + a.finish()


def build_postcopy(
    *, fallback_only: bool = False, cache_enabled: bool = True
) -> bytes:
    a = Asm(POSTCOPY_ADDR)
    if fallback_only:
        a.db(0xCD, FALLBACK_ADDR & 0xFF, FALLBACK_ADDR >> 8, 0xC9)
        return a.finish()
    a.db(0xF0, 0xBA, 0xFE, 0x06)
    a.jr(0x20, "fallback")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x08)    # exact Stage-7 gameplay scene
    a.jr(0x20, "fallback")
    a.db(0xFA, 0x4E, 0xDF, 0xFE, 0x12)    # render services initialized
    a.jr(0x28, "stage7")
    a.label("fallback")
    a.db(0xCD, FALLBACK_ADDR & 0xFF, FALLBACK_ADDR >> 8, 0xC9)

    a.label("stage7")
    # This replaces the original Stage-7 dirty compiler beginning at $42FC.
    # Enter its banked work inside the same interrupt-atomic window as the
    # displaced compiler.  Do not DI before the scene check: title/loading
    # fallback routes can legitimately return without the later atomic tail.
    a.db(0xF3)
    if not cache_enabled:
        a.db(0x3E, 0x03, 0xE0, 0x70)
        a.db(0xCD, ROW_COMPILER_ADDR & 0xFF, ROW_COMPILER_ADDR >> 8)
        a.jp(0xC3, "publish")
    else:
        emit_key(a, store=False)
        a.db(0x3E, 0x03, 0xE0, 0x70)       # select persistent plane
        a.db(
            0xFA, KEY_VALID_ADDR & 0xFF, KEY_VALID_ADDR >> 8,
            0xFE, KEY_VALID,
        )
        a.jr(0x20, "compile")
        a.db(0xFA, KEY_ADDR & 0xFF, KEY_ADDR >> 8, 0xB8)
        a.jr(0x20, "compile")
        a.db(0xFA, (KEY_ADDR + 1) & 0xFF, KEY_ADDR >> 8, 0xB9)
        a.jr(0x20, "compile")
        a.db(0xFA, (KEY_ADDR + 2) & 0xFF, KEY_ADDR >> 8, 0xBB)
        a.jr(0x28, "publish")

        a.label("compile")
        a.db(0xCD, ROW_COMPILER_ADDR & 0xFF, ROW_COMPILER_ADDR >> 8)
        emit_key(a, store=True)

    a.label("publish")
    # Byte-equivalent full-plane publication contract from r232: exact odd
    # destination tag, LCD-off GDMA / LCD-on HBlank DMA, bounded completion,
    # then restore VBK0 and SVBK1 before returning through the bank-1 tail.
    a.db(
        0xF0, 0xA5, 0x3D, 0x67, 0xE0, 0x53,
        0xAF, 0xE0, 0x54,
        0x3E, 0x01, 0xE0, 0x4F,
        0x3E, 0xD0, 0xE0, 0x51,
        0xAF, 0xE0, 0x52,
        0xF0, 0x40, 0xCB, 0x7F,
        0x3E, 0x2F,
    )
    a.jr(0x28, "dma_ready")
    a.db(0x3E, 0xAF)
    a.label("dma_ready")
    a.db(0xE0, 0x55)
    a.label("dma_wait")
    a.db(0xF0, 0x55, 0xCB, 0x7F)
    a.jr(0x28, "dma_wait")
    a.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70, 0xC9)
    return a.finish()


def parse_writer_trace(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    in_writers = False
    for line in path.read_text().splitlines():
        if line == "writers":
            in_writers = True
            continue
        if line == "events":
            break
        if in_writers and line:
            key, count = line.split("\t")
            counts[key] = int(count)
    if set(counts) != EXPECTED_WRITER_PCS or not all(counts.values()):
        raise ValueError(f"Stage-7 writer ownership changed: {counts}")
    return counts


def verify_attr_trace(path: Path) -> dict[str, int]:
    by_key: dict[tuple[int, int, int], set[bytes]] = {}
    events = changes = 0
    previous: dict[int, bytes] = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 30:
            raise ValueError(f"{path}:{number}: expected 30 fields")
        room = int(fields[3], 16)
        raw = bytes.fromhex(fields[29])
        if len(raw) != 576:
            raise ValueError(f"{path}:{number}: raw plane width changed")
        desired = desired_plane(7, raw)
        key = (
            room,
            __import__("functools").reduce(
                int.__xor__, (raw[i] for i in SIGNATURE_A), 0
            ),
            __import__("functools").reduce(
                int.__xor__, (raw[i] for i in SIGNATURE_B), 0
            ),
        )
        by_key.setdefault(key, set()).add(desired)
        destination = int(fields[2], 16)
        if destination in previous and previous[destination] != desired:
            changes += 1
        previous[destination] = desired
        # The immutable page installed below must remain the exact YAML-slot
        # function used by every replayed desired plane.
        if bytes(semantic_lut(7)[tile] for tile in raw) != desired:
            raise ValueError("Stage-7 LUT model diverged")
        events += 1
    collisions = sum(len(values) - 1 for values in by_key.values())
    if events < 800 or changes < 100 or collisions:
        raise ValueError(
            f"attr corpus insufficient/colliding: events={events} "
            f"changes={changes} collisions={collisions}"
        )
    return {"events": events, "semantic_changes": changes, "key_collisions": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--writer-trace", type=Path, required=True)
    parser.add_argument("--attr-trace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--control",
        choices=("full", "expander", "postcopy", "expander-map", "postcopy-map"),
        default="full",
        help=(
            "full experiment; expander/precompute or postcopy isolation; "
            "or mapping-only controls with the new semantic work disabled"
        ),
    )
    args = parser.parse_args()

    source = args.base.read_bytes()
    if sha256(source) != BASE_SHA256:
        raise SystemExit(f"wrong exact r232 base: {sha256(source)}")
    original_expander = source[EXPANDER_START:EXPANDER_END]
    original_compiler = source[COMPILER_START:COMPILER_END]
    if len(original_compiler) != 88 or not original_compiler.startswith(
        bytes.fromhex("F0 E0 FE 03")
    ) or not original_compiler.endswith(bytes.fromhex("AF E0 4F 3C E0 70")):
        raise SystemExit("r232 compiler/publication preimage moved")

    writers = parse_writer_trace(args.writer_trace)
    corpus = verify_attr_trace(args.attr_trace)
    fallback = original_compiler + bytes((0xC9,))
    relocated_expander = build_relocated_expander(
        original_expander, precompute=args.control != "expander-map"
    )
    precompute = build_precompute()
    postcopy = build_postcopy(
        fallback_only=args.control == "postcopy-map",
        cache_enabled=args.control == "full",
    )
    row_compiler = build_row_compiler()
    lut = semantic_lut(7)

    regions = (
        (FALLBACK_ADDR, fallback),
        (EXPANDER_ADDR, relocated_expander),
        (PRECOMPUTE_ADDR, precompute),
        (POSTCOPY_ADDR, postcopy),
        (ROW_COMPILER_ADDR, row_compiler),
        (LUT_ADDR, lut),
    )
    ordered = sorted((addr, addr + len(payload)) for addr, payload in regions)
    for left, right in zip(ordered, ordered[1:]):
        if left[1] > right[0]:
            raise SystemExit(f"bank21 helper overlap: {left} / {right}")
    bank_base = BANK * BANK_SIZE
    rom = bytearray(source)
    for address, payload in regions:
        offset = bank_base + address - 0x4000
        if source[offset:offset + len(payload)] != bytes([0xFF]) * len(payload):
            raise SystemExit(f"bank21 cave not erased at ${address:04X}")
        rom[offset:offset + len(payload)] = payload

    expander_trampoline = bytes.fromhex(
        # Preserve the exact IE mask and caller IME state.  With IE=0, no
        # interrupt can enter while bank21 or SVBK3 is selected.  RST $28
        # restores ROM bank1 before IE becomes live again.  The final stack
        # shuffle also restores the exact AF produced by RST $28 and the
        # caller's BC; loader control flow consumes that return state.
        f"C5 F0 FF F5 AF E0 FF 3E {BANK:02X} CD 61 00 "
        f"CD {EXPANDER_ADDR & 0xFF:02X} {EXPANDER_ADDR >> 8:02X} "
        f"EF F5 C1 F1 E0 FF C5 F1 C1 C9"
    )
    compiler_trampoline = bytes.fromhex(
        f"3E {BANK:02X} CD 61 00 CD {POSTCOPY_ADDR & 0xFF:02X} "
        f"{POSTCOPY_ADDR >> 8:02X} 3E 01 CD 61 00 C3 54 43"
    )
    if args.control in ("full", "expander", "expander-map"):
        rom[EXPANDER_START:EXPANDER_END] = expander_trampoline + bytes(
            EXPANDER_END - EXPANDER_START - len(expander_trampoline)
        )
    if args.control in ("full", "postcopy", "postcopy-map"):
        rom[COMPILER_START:COMPILER_END] = compiler_trampoline + bytes(
            COMPILER_END - COMPILER_START - len(compiler_trampoline)
        )
    update_checksums(rom)
    candidate = bytes(rom)
    receipt = {
        "schema": "penta-stage7-source-precompute-r236-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "control": args.control,
        "source_precompute_enabled": args.control in ("full", "expander"),
        "postcopy_cache_enabled": args.control == "full",
        "base_sha256": sha256(source),
        "candidate_sha256": sha256(candidate),
        "writer_trace_sha256": sha256(args.writer_trace.read_bytes()),
        "attr_trace_sha256": sha256(args.attr_trace.read_bytes()),
        "writer_counts": writers,
        "corpus": corpus,
        "bank": BANK,
        "helpers": {
            f"${address:04X}": len(payload) for address, payload in regions
        },
        "contracts": {
            "source_expander_relocated_byte_exact_before_tail": True,
            "non_stage7_fallback_compiler_byte_exact": True,
            "stage7_plane_key_fail_closed": args.control == "full",
            "stage7_gameplay_render_ready_gate": args.control in (
                "full", "postcopy"
            ),
            "stage7_immutable_yaml_slot_lut": True,
            "exact_tagged_destination": True,
            "lcd_off_gdma_lcd_on_hblank": True,
            "vbk_svbk_restored_before_outer_return": True,
        },
        "required_next_gate": (
            "Stage7 patrol strict speed with exact scroll parity, then "
            "four-room semantic soak"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
