#!/usr/bin/env python3
"""Reproduce the archived r315 CHR-restore prototype (not release-qualified).

Its receipt retains a historical menu-writer hypothesis. The operator-state
controls below supersede that inference: they establish inherited corruption,
not a directly observed SELECT writer. This is historical reconstruction only.

The first hardened r314 corrupted-walls replay proved that the map/attribute
transaction is clean, but its final physical CHR is not.  With LCDC bit 4
clear, its physical bank-zero tile IDs $10-$1F at VRAM $9100-$91FF are an
inherited alternate ROM art image instead of canonical Stage-1 art.  A second
authenticated state already loaded inside the menu has completely canonical
bank-zero art, disproving the current SELECT path as the writer.  The exact
historical writer is unobserved; the actionable defect is that r314's scene
$0B selfheal republishes maps, attributes, and hazards without owning this
captured bank-zero CHR corruption.

Mirror the exact hash-pinned 256-byte Stage-1 tile image into r314's erased
bank-31 suffix.  One general-purpose 16-block DMA then restores $9100-$91FF
atomically.  The private primitive is reached only from r314's exact stale-
runtime repair point, before transaction arm/display/commit.  Menu entry,
hold, close, current runtime, and gameplay hot paths remain byte exact.

No emulator is invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any
import zlib

import build_stage1_scene0b_publication_commit_r314 as r314
import build_stage1_single_art_upload_r293 as r293


r305 = r314.r305
ROOT = r314.ROOT
TMP = r314.TMP
BASE = r314.DEFAULT_OUTPUT
BASE_RECEIPT = r314.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-scene0b-chr-restore-r315/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-scene0b-chr-restore-r315/build-receipt.json"

BASE_SHA256 = r314.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "730ddfb4acc6a71dadf7404ad0e000378fe62972ff87d3a5dd0f315357819bf1"
)
BASE_SCHEMA = "penta-stage1-scene0b-publication-commit-r314-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "3af4b5bdf352a43622a01093e225e431109c61b1f7e216b8a732d2248f15bd4c"
)

CORRUPTED_OPERATOR_STATE = ROOT / "save_states_for_claude/rc11_corrupted-walls.ss0"
CORRUPTED_OPERATOR_STATE_SHA256 = (
    "052f2a9e7a80fc9073bf3fd452a0985a007c77afd54078274ad6408ea4010f15"
)
CORRUPTED_GBAS_SHA256 = (
    "5f80b932414a73e8c252331a35069a47996508c219c04e9a7b670e8706c20716"
)
CANONICAL_MENU_LOADED_STATE = (
    ROOT / "save_states_for_claude/rc11_low-health-degradation.ss0"
)
CANONICAL_MENU_LOADED_STATE_SHA256 = (
    "1ea1b02625268a64982bcf272177ce89527a5a99c0baa49e6a1e247a9d2c8b67"
)
CANONICAL_MENU_LOADED_GBAS_SHA256 = (
    "6d379c9711c8d2a396523ca50a6da268651e69fc2a8768e30ce4d139d8b4fdd0"
)
GBAS_BYTES = 71680
GBAS_VRAM_OFFSET = 0x0400
GBAS_VRAM_BYTES = 0x4000

REJECTED_LIVE_RECEIPT = TMP / "stage1-scene0b-r314-cache-audit-v1/receipt.json"
REJECTED_LIVE_RECEIPT_SHA256 = (
    "221b1c1a963c97c25f06e385d5dc4854c2d62c2b4fcba16f58180b7a0697adf0"
)
REJECTED_LIVE_SCHEMA = "penta-stage1-scene0b-cache-publication-diagnostic-v4"
REJECTED_CHR_DUMP = (
    TMP / "stage1-scene0b-r314-cache-audit-v1/operator-corrupted-walls/"
    "replay-1/scene0b.chr.bin"
)
REJECTED_CHR_DUMP_SHA256 = (
    "b94c4f700f8b051e9661e7935b75147fe7dedcbc952281afffb390d90505db1c"
)
REJECTED_PLANE_DUMP = REJECTED_CHR_DUMP.with_name("scene0b.planes.bin")
REJECTED_PLANE_DUMP_SHA256 = (
    "0fd2e37356d338f005bedec206264cfff27afbed8de4f1db822abf11346dd4d1"
)
REJECTED_PLANE_METADATA = REJECTED_CHR_DUMP.with_name("scene0b.planes.meta")
REJECTED_PLANE_METADATA_SHA256 = (
    "46912b8591dce1fc689b3a64a28a31fd792f8bb8aedd95b954b96c7326137907"
)

COLD_WRITER_RECEIPT = TMP / "stage1-chr-writer-r314-cold-v1/chr-writer-receipt.json"
COLD_WRITER_RECEIPT_SHA256 = (
    "a6c3c5e2919d00a316a4c6cb60a056ae09b87b85a6f4e18f2e66ef237e35d2f7"
)
COLD_WRITER_SCHEMA = "penta-stage1-chr-writer-cold-route-v1"
COLD_WRITER_TOOL = ROOT / "scripts/diagnostics/verify_stage1_chr_writer.py"
COLD_WRITER_TOOL_SHA256 = (
    "abdad7890b124336ed7b133c61874eaa19f7f9bcaf0f9735ce920ca73e53ac49"
)

BANK = r314.MUX_BANK
REPAIR_HOOK_ADDR = r314.HANDLER_LABELS["repair_effect"]
OLD_REPAIR_HOOK = bytes((
    0xC3,
    r314.HANDLER_LABELS["arm_transaction"] & 0xFF,
    r314.HANDLER_LABELS["arm_transaction"] >> 8,
))

REPAIR_WRAPPER_ADDR = 0x6E50
MENU_WRAPPER_ADDR = 0x6E60
ART_HELPER_ADDR = 0x6E80
ART_PAYLOAD_ADDR = 0x7000
ART_PAYLOAD_END = 0x70FF
ART_SOURCE_OFFSET = 0x1D100
CORRUPT_SOURCE_OFFSET = 0x1C000
CORRUPT_SOURCE_SHA256 = (
    "c58f00b26aa59fc81619322bd3145e71ad9ef72f23a771a19deee48e935746eb"
)
ART_CANONICAL_OFFSET = 0x0100
ART_BYTES = 0x0100
ART_PAYLOAD_SHA256 = (
    "0f2108c1ee36e7211b10f1dac478a6fdf8548ecc2b275407e40a2a4af9116654"
)
VRAM_DESTINATION = 0x9100
GDMA_BLOCKS = ART_BYTES // 16
GDMA_COMMAND = GDMA_BLOCKS - 1

# Unmodified native paths retained as explicit negative controls.
MENU_INVALIDATION_ADDR = 0x6CDA
MENU_INVALIDATION = bytes.fromhex("3E FF EA 53 DF EA 57 DF")
MENU_EXIT_ADDR = 0x6CE2
MENU_EXIT = bytes.fromhex("E1 F1 AF E0 E4 C3 9A 09")
MENU_HOOK_ADDR = MENU_INVALIDATION_ADDR
OLD_MENU_HOOK = MENU_INVALIDATION
NEW_MENU_HOOK = bytes.fromhex("C3 60 6E 00 00 00 00 00")
MENU_WRAPPER = bytes.fromhex(
    "F3F040F5CBEFE0403EFFEA53DFEA57DFCD806E20FB"
    "F1CBAFE040FBC3E26C"
)
NATIVE_MENU_BANK = 20
NATIVE_MENU_ADDR = 0x4000
NATIVE_MENU_END = 0x4084

def _word(address: int) -> bytes:
    return bytes((address & 0xFF, address >> 8))


NEW_REPAIR_HOOK = bytes((0xC3,)) + _word(REPAIR_WRAPPER_ADDR)

# Repair enters through r314's DI-protected stale-gateway path.  A failed
# post-DMA inactive check takes r314's existing fail-closed path and therefore
# can never acknowledge or display an un-restored transaction.
REPAIR_WRAPPER = (
    bytes((0xCD,)) + _word(ART_HELPER_ADDR)
    + bytes((0xC2,)) + _word(r314.HANDLER_LABELS["arm_fail"])
    + bytes((0xC3,)) + _word(r314.HANDLER_LABELS["arm_transaction"])
)

# FF55 bit 7, not an exact $FF value, is the authoritative active flag.  An
# active transfer while the LCD is off cannot advance through HBlanks, so
# terminate that proven-active HBlank transfer and recheck.  With LCD on, wait
# for it to complete normally, then wait through any current VBlank and detect
# the next LY=$90 edge.  LCD-off bypasses frozen LY.  A 16-block GDMA takes
# about 128 us versus about 1087 us of VBlank, so the one exact-width transfer
# is wholly VRAM-safe.  Pan Docs guarantees exactly $FF after completed GDMA,
# so the asymmetric final comparison leaves Z only for that exact completion.
LCD_OFF_CANCEL_ART_HELPER = bytes.fromhex(
    "F0 55 CB 7F 20 0B "        # inactive bit7=1 -> inspect LCDC
    "F0 40 CB 7F 20 F4 "        # active+LCD-on -> wait at FF55
    "AF E0 55 18 EF "           # active+LCD-off -> terminate/recheck
    "F0 40 CB 7F 28 0C "        # inactive+LCD-off -> direct safe GDMA
    "F0 44 FE 90 30 FA "        # if already VBlank, wait for LY<144
    "F0 44 FE 90 38 FA "        # then wait for fresh LY>=144
    "C5 F0 4F 47 "         # preserve BC and exact entry VBK in B
    "AF E0 4F "            # XOR A; LDH [VBK],A
    "3E 70 E0 51 "         # HDMA1 = $70 (source $7000)
    "AF E0 52 "            # HDMA2 = $00
    "3E 11 E0 53 "         # HDMA3 = $11 (destination $9100)
    "AF E0 54 "            # HDMA4 = $00
    "3E 0F E0 55 "         # HDMA5 = $0F (16 blocks, general DMA)
    "F0 55 FE FF "         # completed GDMA must report exact $FF
    "F5 78 E0 4F F1 C1 C9" # restore exact VBK/BC; RET with Z/NZ
)

# Issue #13: retain the archived r315 instruction stream separately from the
# later LCD-off cancellation experiment used by r324/r328/r329. Mixing their
# names had left this builder inconsistent with its own historical contracts.
ART_HELPER = bytes.fromhex(
    "F055E680FE8020F8F040CB7F280C"
    "F044FE9030FAF044FE9038FA"
    "C5F04F47AFE04F3E70E051AFE0523E11E053AFE0543E0FE055"
    "F055FEFFF578E04FF1C1C9"
)

CHECKSUM_OFFSETS = r314.CHECKSUM_OFFSETS


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(address: int) -> int:
    return r314.bank_offset(BANK, address)


def _range(address: int, width: int) -> set[int]:
    start = bank_offset(address)
    return set(range(start, start + width))


def owned_ranges() -> set[int]:
    return (
        _range(REPAIR_HOOK_ADDR, len(NEW_REPAIR_HOOK))
        | _range(MENU_HOOK_ADDR, len(NEW_MENU_HOOK))
        | _range(MENU_WRAPPER_ADDR, len(MENU_WRAPPER))
        | _range(REPAIR_WRAPPER_ADDR, len(REPAIR_WRAPPER))
        | _range(ART_HELPER_ADDR, len(ART_HELPER))
        | _range(ART_PAYLOAD_ADDR, ART_BYTES)
    )


def menu_retry_model(ff55_reads: tuple[int, ...]) -> dict[str, int]:
    """Model r315's pre-DMA bit-7 wait and exact-FF completion retry."""
    cursor = calls = starts = 0
    while True:
        calls += 1
        while cursor < len(ff55_reads) and not ff55_reads[cursor] & 0x80:
            cursor += 1
        r305.r304.require(cursor < len(ff55_reads), "DMA never becomes idle")
        cursor += 1
        starts += 1
        r305.r304.require(cursor < len(ff55_reads), "DMA completion missing")
        completed = ff55_reads[cursor] == 0xFF
        cursor += 1
        if completed:
            r305.r304.require(cursor == len(ff55_reads), "unread DMA statuses")
            return {"helper_calls": calls, "FF55_reads": cursor,
                    "FF55_writes": starts, "GDMA_starts": starts}


def _banked_offset(bank: int, address: int) -> int:
    return r314.bank_offset(bank, address)


def _absolute_transfer_sites(source: bytes, target: int) -> frozenset[int]:
    """Fixed-bank byte-pattern sites; only used for the authenticated r314."""
    return frozenset(
        index for index in range(0x3FFE)
        if source[index] in (0xC3, 0xC2, 0xCA, 0xD2, 0xDA,
                             0xCD, 0xC4, 0xCC, 0xD4, 0xDC)
        and source[index + 1:index + 3] == _word(target)
    )


def menu_entry_ime_contract(source: bytes) -> dict[str, Any]:
    """Revalidate the exact historical byte image behind its reviewed proof.

    This is a retained r314/r315 contract, not a general control-flow analysis
    and not qualification of a newer ROM. Any changed source byte is rejected.
    """
    r305.r304.require(digest(source) == BASE_SHA256, "menu IME source changed")
    offset = _banked_offset(NATIVE_MENU_BANK, NATIVE_MENU_ADDR)
    native = source[offset:offset + NATIVE_MENU_END - NATIVE_MENU_ADDR]
    r305.r304.require(native[-2:] == bytes.fromhex("FB C9")
                      and native[:-2].count(0xC9) == 0,
                      "native menu EI/return owner changed")
    for address in (0x1B69, 0x1DC2):
        r305.r304.require(source[address:address + 9]
                          == bytes.fromhex("F0 40 CB AF E0 40 CD 98 77"),
                          "direct menu-close route changed")
    r305.r304.require(_absolute_transfer_sites(source, 0x1B35) == {0x1B04}
                      and _absolute_transfer_sites(source, 0x1D5D) == {0x0A97},
                      "modal menu entries changed")
    return {
        "all_targeted_menu_completions_IME": "enabled",
        "close_callsites": ["fixed:$1B69", "fixed:$1DC2"],
        "entry_IME": "enabled at both scoped direct close sites",
        "first_post_EI_route": "$1B53-$1B69 exact and IME-neutral",
        "interactive_post_EI_route": "$1D83-$1DC2 exact; retry $1DC0->$1D78 re-executes EI owner",
        "item_use_tail_IME": "same enabled native-menu iteration; 16-entry table and all 17 tail-call exits exact",
        "modal_entries": ["fixed:$1B35 from $1B04", "fixed:$1D5D from $0A97"],
        "native_IME_owner": "bank20:$4000/$4017 -> sole EI $4082; RET $4083",
        "reviewed_mainline_owner": "fixed:$01E8 room driver",
        "shared_tail_transfers": 19,
        "unknown_IME_assumption": False,
    }


def safe_window_model(lcdc: int, ly_reads: tuple[int, ...]) -> dict[str, Any]:
    """Model the LCD-off bypass or exact two-phase fresh-VBlank wait."""
    r305.r304.require(0 <= lcdc <= 0xFF, "LCDC model is not one byte")
    if not lcdc & 0x80:
        r305.r304.require(not ly_reads,
                          "LCD-off GDMA must not sample frozen LY")
        return {
            "LCDC": f"{lcdc:02X}",
            "mode": "LCD-off direct GDMA",
            "LY_reads": 0,
            "VRAM_safe": True,
        }

    cursor = 0
    while cursor < len(ly_reads) and ly_reads[cursor] >= 144:
        cursor += 1
    r305.r304.require(cursor < len(ly_reads),
                      "LY model never observes the visible period")
    visible_sample = ly_reads[cursor]
    cursor += 1
    while cursor < len(ly_reads) and ly_reads[cursor] < 144:
        cursor += 1
    r305.r304.require(cursor < len(ly_reads),
                      "LY model never reaches a fresh VBlank")
    edge = ly_reads[cursor]
    cursor += 1
    r305.r304.require(cursor == len(ly_reads),
                      "LY model has unread values after VBlank edge")
    return {
        "LCDC": f"{lcdc:02X}",
        "mode": "LCD-on fresh-VBlank GDMA",
        "LY_reads": cursor,
        "visible_sample": visible_sample,
        "VBlank_edge_sample": edge,
        "VRAM_safe": True,
    }


def canonical_bg_art(source: bytes) -> bytes:
    """Reconstruct the verifier's exact ID-ordered 256-tile art."""
    payload = b"".join(
        source[offset:offset + 16]
        for tile in range(0x100)
        for offset in ((
            0x1D000 + tile * 16
            if tile < 0x80
            else 0x1F000 + tile * 16
        ),)
    )
    r305.r304.require(len(payload) == 0x1000,
                      "canonical Stage-1 art source is truncated")
    r305.r304.require(
        digest(payload)
        == "975c68459f26cd731c62acfeabf7c94f6284ab35c7dff3e4eca8e56bafcb9a97",
        "canonical Stage-1 art identity changed",
    )
    return payload


def signed_physical_offset(tile: int) -> int:
    r305.r304.require(0 <= tile <= 0xFF, "tile ID is not one byte")
    return tile * 16 + (0x1000 if tile < 0x80 else 0)


def extract_gbas(png: bytes) -> bytes:
    """Extract and authenticate the sole compressed mGBA state PNG chunk."""
    r305.r304.require(png.startswith(b"\x89PNG\r\n\x1a\n"),
                      "operator state is not a PNG savestate")
    cursor = 8
    gbas_chunks: list[bytes] = []
    saw_iend = False
    while cursor < len(png):
        r305.r304.require(cursor + 12 <= len(png),
                          "operator state has a truncated PNG chunk")
        width = struct.unpack(">I", png[cursor:cursor + 4])[0]
        kind = png[cursor + 4:cursor + 8]
        end = cursor + 12 + width
        r305.r304.require(end <= len(png),
                          "operator state PNG chunk escapes the file")
        payload = png[cursor + 8:cursor + 8 + width]
        stored_crc = struct.unpack(">I", png[cursor + 8 + width:end])[0]
        r305.r304.require(zlib.crc32(kind + payload) & 0xFFFFFFFF == stored_crc,
                          "operator state PNG chunk CRC changed")
        if kind == b"gbAs":
            gbas_chunks.append(payload)
        if kind == b"IEND":
            saw_iend = True
            r305.r304.require(end == len(png),
                              "operator state has bytes after IEND")
        cursor = end
    r305.r304.require(saw_iend and len(gbas_chunks) == 1,
                      "operator state must contain one gbAs chunk")
    try:
        state = zlib.decompress(gbas_chunks[0])
    except zlib.error as error:
        raise AssertionError("operator gbAs payload is not valid zlib") from error
    r305.r304.require(len(state) == GBAS_BYTES,
                      "operator gbAs width changed")
    return state


def operator_state_contract(
    source: bytes, corrupted_state: bytes, menu_loaded_state: bytes,
) -> dict[str, Any]:
    """Bind inherited corruption and the menu-loaded negative control."""
    r305.r304.require(
        digest(corrupted_state) == CORRUPTED_OPERATOR_STATE_SHA256,
        "corrupted-walls operator state identity changed",
    )
    r305.r304.require(
        digest(menu_loaded_state) == CANONICAL_MENU_LOADED_STATE_SHA256,
        "menu-loaded operator state identity changed",
    )
    corrupted_gbas = extract_gbas(corrupted_state)
    menu_gbas = extract_gbas(menu_loaded_state)
    r305.r304.require(digest(corrupted_gbas) == CORRUPTED_GBAS_SHA256,
                      "corrupted-walls gbAs identity changed")
    r305.r304.require(
        digest(menu_gbas) == CANONICAL_MENU_LOADED_GBAS_SHA256,
        "menu-loaded gbAs identity changed",
    )
    r305.r304.require(
        corrupted_gbas[:4] == menu_gbas[:4] == bytes.fromhex("03 00 40 00"),
        "mGBA serialized-state layout/version changed",
    )
    corrupted_vram = corrupted_gbas[
        GBAS_VRAM_OFFSET:GBAS_VRAM_OFFSET + GBAS_VRAM_BYTES
    ]
    menu_vram = menu_gbas[
        GBAS_VRAM_OFFSET:GBAS_VRAM_OFFSET + GBAS_VRAM_BYTES
    ]
    r305.r304.require(len(corrupted_vram) == len(menu_vram) == 0x4000,
                      "serialized VRAM extraction changed width")
    canonical = canonical_bg_art(source)

    def mismatches(vram: bytes) -> tuple[list[int], int]:
        bad: list[int] = []
        byte_count = 0
        for tile in range(0x100):
            physical = signed_physical_offset(tile)
            actual = vram[physical:physical + 16]
            expected = canonical[tile * 16:(tile + 1) * 16]
            differences = sum(
                left != right
                for left, right in zip(actual, expected, strict=True)
            )
            if differences:
                bad.append(tile)
                byte_count += differences
        return bad, byte_count

    corrupted_tiles, corrupted_bytes = mismatches(corrupted_vram)
    menu_tiles, menu_bytes = mismatches(menu_vram)
    r305.r304.require(corrupted_tiles == list(range(0x10, 0x20))
                      and corrupted_bytes == 248,
                      "corrupted operator state CHR domain changed")
    r305.r304.require(not menu_tiles and menu_bytes == 0,
                      "menu-loaded negative control is no longer canonical")

    physical = VRAM_DESTINATION - 0x8000
    alternate = source[
        CORRUPT_SOURCE_OFFSET:CORRUPT_SOURCE_OFFSET + ART_BYTES
    ]
    desired = source[ART_SOURCE_OFFSET:ART_SOURCE_OFFSET + ART_BYTES]
    r305.r304.require(digest(alternate) == CORRUPT_SOURCE_SHA256,
                      "alternate captured-art source identity changed")
    r305.r304.require(
        corrupted_vram[physical:physical + ART_BYTES] == alternate,
        "corrupted state is no longer exact ROM file $1C000-$1C0FF art",
    )
    r305.r304.require(desired == canonical[0x100:0x200]
                      and digest(desired) == ART_PAYLOAD_SHA256
                      and alternate != desired,
                      "canonical bank7:$5100 replacement identity changed")
    return {
        "corrupted_state_sha256": CORRUPTED_OPERATOR_STATE_SHA256,
        "corrupted_gbAs_sha256": CORRUPTED_GBAS_SHA256,
        "menu_loaded_state_sha256": CANONICAL_MENU_LOADED_STATE_SHA256,
        "menu_loaded_gbAs_sha256": CANONICAL_MENU_LOADED_GBAS_SHA256,
        "serialized_VRAM": "$0400-$43FF within exact 71680-byte gbAs",
        "corrupted_state_mismatch_tiles": "$10-$1F",
        "corrupted_state_mismatch_bytes": corrupted_bytes,
        "corrupted_bytes_equal_ROM_source": (
            "file:$1C000-$1C0FF = bank7:$4000-$40FF"
        ),
        "canonical_replacement_source": (
            "file:$1D100-$1D1FF = bank7:$5100-$51FF"
        ),
        "menu_loaded_bank0_mismatch_tiles": len(menu_tiles),
        "menu_loaded_bank0_mismatch_bytes": menu_bytes,
        "current_menu_writer_causality": "disproved by canonical menu-loaded state",
        "historical_runtime_writer": "unobserved; do not attribute",
    }


def rejected_chr_contract(
    source: bytes, dump: bytes, planes: bytes, metadata: bytes,
) -> dict[str, Any]:
    """Bind ID order to the captured physical dump through exact LCDC."""
    r305.r304.require(len(dump) == 0x4000,
                      "r314 final physical CHR dump width changed")
    r305.r304.require(len(planes) == 0x1340,
                      "r314 final physical-plane dump width changed")
    try:
        fields = dict(
            line.split("=", 1)
            for line in metadata.decode("ascii").splitlines()
            if line
        )
        lcdc = int(fields["lcdc"], 16)
    except (UnicodeDecodeError, KeyError, ValueError) as error:
        raise AssertionError("r314 final plane metadata is malformed") from error
    r305.r304.require(lcdc == 0x83 and not (lcdc & 0x10),
                      "r314 final LCDC no longer selects signed BG tiles")

    canonical = canonical_bg_art(source)

    mismatch_tiles: list[int] = []
    mismatch_bytes = 0
    for tile in range(0x100):
        address = signed_physical_offset(tile)
        actual_tile = dump[address:address + 16]
        expected_tile = canonical[tile * 16:(tile + 1) * 16]
        differences = sum(
            left != right
            for left, right in zip(actual_tile, expected_tile, strict=True)
        )
        if differences:
            mismatch_tiles.append(tile)
            mismatch_bytes += differences
    r305.r304.require(mismatch_tiles == list(range(0x10, 0x20)),
                      "r314 physical CHR corruption domain changed")
    r305.r304.require(mismatch_bytes == 248,
                      "r314 physical CHR mismatch count changed")
    destination_offset = VRAM_DESTINATION - 0x8000
    alternate = source[
        CORRUPT_SOURCE_OFFSET:CORRUPT_SOURCE_OFFSET + ART_BYTES
    ]
    r305.r304.require(
        dump[destination_offset:destination_offset + ART_BYTES] == alternate
        and digest(alternate) == CORRUPT_SOURCE_SHA256,
        "r314 rejected page is no longer exact bank7:$4000 alternate art",
    )

    tiles_blob = planes[:0x800]
    attrs_blob = planes[0x800:0x1000]
    references: set[tuple[int, int]] = set()
    for map_index in range(2):
        tiles = tiles_blob[map_index * 0x400:(map_index + 1) * 0x400]
        attrs = attrs_blob[map_index * 0x400:(map_index + 1) * 0x400]
        for row in range(24):
            for column in range(24):
                offset = row * 32 + column
                references.add(((attrs[offset] >> 3) & 1, tiles[offset]))
    referenced_mismatch_tiles: list[int] = []
    referenced_mismatch_bytes = 0
    for bank, tile in sorted(references):
        if bank != 0:
            continue
        address = signed_physical_offset(tile)
        actual_tile = dump[address:address + 16]
        expected_tile = canonical[tile * 16:(tile + 1) * 16]
        differences = sum(
            left != right
            for left, right in zip(actual_tile, expected_tile, strict=True)
        )
        if differences:
            referenced_mismatch_tiles.append(tile)
            referenced_mismatch_bytes += differences
    expected_referenced = [
        0x10, 0x11, 0x13, 0x14, 0x15, 0x16, 0x17, 0x1D, 0x1E,
    ]
    r305.r304.require(referenced_mismatch_tiles == expected_referenced,
                      "r314 referenced CHR mismatch population changed")
    r305.r304.require(referenced_mismatch_bytes == 138,
                      "r314 referenced CHR mismatch count changed")

    r305.r304.require(
        dump[signed_physical_offset(0x0F):signed_physical_offset(0x0F) + 16]
        == canonical[0x0F0:0x100],
        "tile $0F is no longer the exact lower boundary control",
    )
    r305.r304.require(
        dump[signed_physical_offset(0x20):signed_physical_offset(0x20) + 16]
        == canonical[0x200:0x210],
        "tile $20 is no longer the exact upper boundary control",
    )
    repaired = bytearray(dump[:0x2000])
    repaired[destination_offset:destination_offset + ART_BYTES] = (
        canonical[0x100:0x200]
    )
    for tile in range(0x100):
        address = signed_physical_offset(tile)
        r305.r304.require(
            repaired[address:address + 16]
            == canonical[tile * 16:(tile + 1) * 16],
            f"corrected physical tile ${tile:02X} is not canonical",
        )
    return {
        "dump_sha256": REJECTED_CHR_DUMP_SHA256,
        "plane_dump_sha256": REJECTED_PLANE_DUMP_SHA256,
        "metadata_sha256": REJECTED_PLANE_METADATA_SHA256,
        "dump_layout": "first $2000 bytes = physical VBK0 $8000-$9FFF",
        "LCDC": f"{lcdc:02X}",
        "tile_addressing": "signed; IDs 00-7F add $1000",
        "mismatch_tile_range": "$10-$1F",
        "mismatch_tiles": len(mismatch_tiles),
        "mismatch_bytes": mismatch_bytes,
        "referenced_mismatch_tiles": [
            f"{tile:02X}" for tile in referenced_mismatch_tiles
        ],
        "referenced_mismatch_bytes": referenced_mismatch_bytes,
        "physical_corrupt_range": "$9100-$91FF",
        "physical_corrupt_page_sha256": CORRUPT_SOURCE_SHA256,
        "physical_corrupt_page_source": (
            "file:$1C000-$1C0FF = bank7:$4000-$40FF"
        ),
        "tile_0F_boundary_exact": True,
        "tile_20_boundary_exact": True,
        "minimal_complete_restore": "$9100-$91FF (IDs $10-$1F)",
    }


def lineage_contract(source: bytes) -> dict[str, Any]:
    """Prove why r293/r305/r314 cannot repair bank-zero CHR."""
    # r303 deliberately evolved only the fixed admission predicate.  The
    # private upload chain (increment, VBK selection, sources, destinations,
    # commands, and return) remains the exact r293 implementation.
    for bank, address, payload in r293.LOADER_BLOBS[1:]:
        offset = r314.bank_offset(bank, address)
        r305.r304.require(source[offset:offset + len(payload)] == payload,
                          f"r293 loader lineage changed at bank{bank}:${address:04X}")
    r305.r304.require(
        source[bank_offset(MENU_HOOK_ADDR):
               bank_offset(MENU_HOOK_ADDR) + len(OLD_MENU_HOOK)]
        == OLD_MENU_HOOK,
        "r305 menu invalidator preimage changed",
    )
    r305.r304.require(
        source[bank_offset(REPAIR_HOOK_ADDR):
               bank_offset(REPAIR_HOOK_ADDR) + len(OLD_REPAIR_HOOK)]
        == OLD_REPAIR_HOOK,
        "r314 repair-to-arm jump changed",
    )
    # The r293 chain explicitly selects VBK1 and targets only $9010/$9640/
    # $9740.  Its total 256-byte image is independent of bank-zero $9100.
    r305.r304.require(bytes.fromhex("3E 01 E0 4F")
                      in r293.LOADER_BLOBS[1][2],
                      "r293 no longer selects VBK1")
    r305.r304.require(sum((value + 1) * 16 for value in (3, 5, 5)) == 256,
                      "r293 loader transfer width changed")
    return {
        "r293_private_bank_one_loader_chain_byte_exact": True,
        "r303_admission_gate_evolution_acknowledged": True,
        "r293_targets": ["VBK1:$9010-$904F", "VBK1:$9640-$969F",
                         "VBK1:$9740-$979F"],
        "r293_total_bytes": 256,
        "r305_menu_close_effect": "DF53=DF57=FF only",
        "r314_transaction_effect": "tilemap+attributes+hazards only",
        "missing_owner": "bank-zero CHR $9100-$91FF after menu completion",
    }


def helper_contract(source: bytes) -> dict[str, Any]:
    r305.r304.require(ART_BYTES == 16 * 16 and GDMA_COMMAND == 0x0F,
                      "signed menu-art transfer is not one exact GDMA")
    r305.r304.require(
        ART_HELPER == bytes.fromhex(
            "F055E680FE8020F8F040CB7F280C"
            "F044FE9030FAF044FE9038FA"
            "C5F04F47AFE04F3E70E051AFE0523E11E053AFE0543E0FE055"
            "F055FEFFF578E04FF1C1C9"
        ),
        "art helper instruction stream changed",
    )
    r305.r304.require(REPAIR_WRAPPER.startswith(bytes.fromhex("CD806E")),
                      "repair wrapper no longer calls the art helper")
    r305.r304.require(REPAIR_WRAPPER.endswith(bytes.fromhex("C36D6D")),
                      "repair wrapper no longer arms r314 after art")
    lcd_branch = ART_HELPER.index(bytes.fromhex("28 0C"))
    dma_setup = ART_HELPER.index(bytes.fromhex("C5 F0 4F 47 AF E0 4F"))
    r305.r304.require(
        ART_HELPER_ADDR + lcd_branch + 2 + 0x0C
        == ART_HELPER_ADDR + dma_setup,
        "LCD-off branch no longer bypasses both LY loops into DMA setup",
    )
    r305.r304.require(ART_BYTES <= 2280 and GDMA_BLOCKS * 8 == 128,
                      "GDMA no longer fits one complete CGB VBlank")
    r305.r304.require(
        MENU_WRAPPER
        == bytes.fromhex(
            "F3F040F5CBEFE0403EFFEA53DFEA57DFCD806E20FB"
            "F1CBAFE040FBC3E26C"
        ),
        "menu restore/retry wrapper instruction stream changed",
    )
    retry_call = MENU_WRAPPER.index(bytes.fromhex("CD 80 6E"))
    retry_branch = MENU_WRAPPER.index(bytes.fromhex("20 FB"))
    retry_target = MENU_WRAPPER_ADDR + retry_branch + 2 - 5
    r305.r304.require(retry_target == MENU_WRAPPER_ADDR + retry_call
                      == 0x6E70,
                      "menu helper NZ retry no longer targets its exact CALL")
    busy_model = menu_retry_model((0x00, 0x03, 0x85, 0xFF))
    r305.r304.require(busy_model == {
        "helper_calls": 1,
        "FF55_reads": 4,
        "FF55_writes": 1,
        "GDMA_starts": 1,
    }, "busy-to-idle menu retry no longer starts exactly one GDMA")
    terminated_model = menu_retry_model((0x85, 0xFF))
    r305.r304.require(terminated_model["GDMA_starts"] == 1
                      and terminated_model["helper_calls"] == 1,
                      "terminated HDMA status is not accepted as inactive")
    stopped_post_retry_model = menu_retry_model((0x85, 0x85, 0x85, 0xFF))
    r305.r304.require(
        stopped_post_retry_model["helper_calls"] == 2
        and stopped_post_retry_model["GDMA_starts"] == 2,
        "stopped-HDMA-shaped post status can incorrectly acknowledge GDMA",
    )
    lcd_off = safe_window_model(0x03, ())
    visible_vblank = safe_window_model(0x83, (80, 143, 144))
    current_vblank = safe_window_model(0x83, (150, 153, 0, 80, 143, 144))
    r305.r304.require(lcd_off["LY_reads"] == 0 and lcd_off["VRAM_safe"],
                      "LCD-off repair path no longer bypasses frozen LY")
    r305.r304.require(visible_vblank["VBlank_edge_sample"] == 144
                      and current_vblank["VBlank_edge_sample"] == 144,
                      "two-phase LY wait does not reach a fresh VBlank")
    entry_ime = menu_entry_ime_contract(source)

    # $12E0 publishes only $83/$8B, both LCD-on.  The exact native menu
    # uploader and both close sites only RES/SET other LCDC bits, preserving
    # bit 7.  The rejected live artifact independently observed LCDC=$83.
    r305.r304.require(
        source[0x12E0:0x12EE]
        == bytes.fromhex("FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40"),
        "Stage-1 LCDC publisher no longer chooses exact LCD-on values",
    )
    r305.r304.require(
        MENU_WRAPPER.index(bytes.fromhex("CB EF E0 40"))
        < MENU_WRAPPER.index(bytes.fromhex("CD 80 6E"))
        < MENU_WRAPPER.index(bytes.fromhex("F1 CB AF E0 40")),
        "Window cover no longer brackets the wait/GDMA",
    )
    r305.r304.require(source[bank_offset(0x6CE2):bank_offset(0x6CE2) + 8]
                      == bytes.fromhex("E1 F1 AF E0 E4 C3 9A 09"),
                      "native close exit no longer retains menu ownership "
                      "until after the Window-covered wait")
    return {
        "source": "bank31:$7000-$70FF",
        "destination": "VBK0:$9100-$91FF",
        "blocks": GDMA_BLOCKS,
        "HDMA5_command": f"{GDMA_COMMAND:02X}",
        "mode": "general-purpose DMA (bit7 clear)",
        "single_transfer": True,
        "FF55_inactive_bit7_required_before": True,
        "FF55_exact_FF_required_after_GDMA": True,
        "exact_FF_precondition_comparison_forbidden": True,
        "busy_retry": {
            "instruction": "bank31:$6E73 JR NZ $6E70",
            "model_busy_busy_idle": busy_model,
            "model_terminated_85_is_inactive": terminated_model,
            "model_post_85_retries_until_exact_FF": stopped_post_retry_model,
            "cache_invalidation_runs_once": True,
            "EI_only_after_helper_Z": True,
        },
        "HBlank_busy_liveness": {
            "precondition": "LCDC.7=1 at both scoped close routes",
            "static_owner": "fixed:$12E0 chooses $83/$8B",
            "native_menu_and_close": "preserve LCDC.7; only bits 3/5/6 change",
            "captured_control": "rejected live metadata LCDC=$83",
            "bounded_without_IME": True,
        },
        "VRAM_safe_window": {
            "instruction_order": (
                "poll FF55 bit7 -> branch on LCDC.7; LCD-off direct GDMA, "
                "LCD-on wait LY<144 -> wait fresh LY>=144 -> GDMA"
            ),
            "LCD_off_repair_model": lcd_off,
            "visible_period_model": visible_vblank,
            "already_in_vblank_model": current_vblank,
            "transfer_time_us": 16 * 8,
            "nominal_VBlank_time_us": 1087,
            "VBlank_capacity_bytes": 2280,
            "payload_bytes": ART_BYTES,
            "source": (
                "Pan Docs CGB Registers: FF55 active bit, GDMA restrictions, "
                "8 us/block and 2280 bytes/VBlank"
            ),
            "source_url": (
                "https://github.com/gbdev/pandocs/blob/master/"
                "src/CGB_Registers.md"
            ),
        },
        "visual_boundary": {
            "entry_precondition": (
                "direct native close has LCDC.5=0; other shared menu "
                "completions remain Window-owned"
            ),
            "direct_close_proof": (
                "fixed:$1B69/$1DC2 exact F040CBAFE040CD9877"
            ),
            "cover": "save LCDC; SET LCDC.5 before any wait",
            "ownership": "FFE4 remains 1 until native $6CE4 after restore",
            "release": "POP saved LCDC; RES LCDC.5 after GDMA Z",
            "other_LCDC_bits": "restored exactly from saved entry value",
            "corrupted_gameplay_CHR_visible_during_wait": False,
        },
        "repair_IME": "already disabled by r314:$6D35 DI",
        "menu_IME": "DI before invalidation/DMA; EI before native exit",
        "menu_entry_IME_contract": entry_ime,
        "register_abi": "BC/DE/HL/SP and entry VBK preserved; A/F scratch only",
    }


def validate_preimages(
    source: bytes, base_receipt_bytes: bytes,
    rejected_receipt_bytes: bytes, rejected_chr: bytes,
    rejected_planes: bytes, rejected_metadata: bytes,
) -> dict[str, Any]:
    r305.r304.require(len(source) == r305.r304.ROM_SIZE,
                      "r314 base is not exactly 512 KiB")
    r305.r304.require(digest(source) == BASE_SHA256,
                      "r315 requires exact r314 candidate")
    r305.r304.require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
                      "r314 receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("schema") == BASE_SCHEMA,
                      "r314 receipt schema changed")
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r314 receipt names another candidate")

    r305.r304.require(
        digest(rejected_receipt_bytes) == REJECTED_LIVE_RECEIPT_SHA256,
        "r314 rejected live receipt identity changed",
    )
    rejected = json.loads(rejected_receipt_bytes)
    r305.r304.require(rejected.get("schema") == REJECTED_LIVE_SCHEMA,
                      "r314 rejected live receipt schema changed")
    r305.r304.require(rejected.get("status") == "FAIL",
                      "r314 diagnostic is no longer rejected")
    r305.r304.require(rejected.get("candidate_sha256") == BASE_SHA256,
                      "r314 rejection names another candidate")
    r305.r304.require(any(
        "final referenced physical BG CHR differs from canonical art" in item
        for item in rejected.get("failures", [])
    ), "r314 rejection no longer binds the CHR failure")
    r305.r304.require(digest(rejected_chr) == REJECTED_CHR_DUMP_SHA256,
                      "r314 rejected CHR dump identity changed")
    r305.r304.require(
        digest(rejected_planes) == REJECTED_PLANE_DUMP_SHA256,
        "r314 rejected physical-plane dump identity changed",
    )
    r305.r304.require(
        digest(rejected_metadata) == REJECTED_PLANE_METADATA_SHA256,
        "r314 rejected physical-plane metadata identity changed",
    )

    lineage = lineage_contract(source)
    failure = rejected_chr_contract(
        source, rejected_chr, rejected_planes, rejected_metadata
    )
    canonical = canonical_bg_art(source)
    payload = canonical[
        ART_CANONICAL_OFFSET:ART_CANONICAL_OFFSET + ART_BYTES
    ]
    r305.r304.require(digest(payload) == ART_PAYLOAD_SHA256,
                      "canonical signed menu-art identity changed")

    cave_start = bank_offset(r314.HANDLER_ADDR + len(r314.HANDLER))
    cave_end = bank_offset(0x7FFF) + 1
    r305.r304.require(source[cave_start:cave_end]
                      == bytes([0xFF]) * (cave_end - cave_start),
                      "r314 bank31 suffix is no longer wholly erased")
    for address, width, label in (
        (REPAIR_WRAPPER_ADDR, len(REPAIR_WRAPPER), "repair wrapper"),
        (MENU_WRAPPER_ADDR, len(MENU_WRAPPER), "menu wrapper"),
        (ART_HELPER_ADDR, len(ART_HELPER), "art helper"),
        (ART_PAYLOAD_ADDR, ART_BYTES, "art payload"),
    ):
        offset = bank_offset(address)
        r305.r304.require(source[offset:offset + width]
                          == bytes([0xFF]) * width,
                          f"{label} cave preimage changed")
    r305.r304.require(ART_HELPER_ADDR + len(ART_HELPER) <= ART_PAYLOAD_ADDR,
                      "r315 helper overlaps its payload")
    r305.r304.require(ART_PAYLOAD_ADDR + ART_BYTES - 1 == ART_PAYLOAD_END,
                      "r315 payload range changed")
    return {
        "r314_build_receipt_sha256": BASE_RECEIPT_SHA256,
        "r314_rejected_live_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
        "r314_rejected_chr_dump_sha256": REJECTED_CHR_DUMP_SHA256,
        "r314_rejected_plane_dump_sha256": REJECTED_PLANE_DUMP_SHA256,
        "r314_rejected_plane_metadata_sha256": (
            REJECTED_PLANE_METADATA_SHA256
        ),
        "lineage": lineage,
        "captured_failure": failure,
        "bank31_suffix_preimage": "$6E4B-$7FFF exact FF",
        "canonical_signed_menu_art_sha256": ART_PAYLOAD_SHA256,
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(len(candidate) == len(source) == r305.r304.ROM_SIZE,
                      "candidate/source size changed")
    expected_blobs = (
        (REPAIR_HOOK_ADDR, NEW_REPAIR_HOOK, "repair hook"),
        (MENU_HOOK_ADDR, NEW_MENU_HOOK, "menu hook"),
        (REPAIR_WRAPPER_ADDR, REPAIR_WRAPPER, "repair wrapper"),
        (MENU_WRAPPER_ADDR, MENU_WRAPPER, "menu wrapper"),
        (ART_HELPER_ADDR, ART_HELPER, "art helper"),
    )
    for address, payload, label in expected_blobs:
        offset = bank_offset(address)
        r305.r304.require(candidate[offset:offset + len(payload)] == payload,
                          f"r315 {label} changed")
    payload_offset = bank_offset(ART_PAYLOAD_ADDR)
    art_payload = candidate[payload_offset:payload_offset + ART_BYTES]
    r305.r304.require(digest(art_payload) == ART_PAYLOAD_SHA256,
                      "r315 mirrored art payload changed")
    r305.r304.require(
        art_payload == source[ART_SOURCE_OFFSET:ART_SOURCE_OFFSET + ART_BYTES],
        "r315 mirror differs from canonical signed Stage-1 menu art",
    )

    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    allowed = owned_ranges()
    expected = {offset for offset in allowed if source[offset] != candidate[offset]}
    r305.r304.require(functional == expected,
                      "r315 functional delta differs from exact ownership")
    r305.r304.require(changed <= allowed | CHECKSUM_OFFSETS,
                      "r315 escaped exact hooks/helpers/payload/checksums")
    for offset, (before, after) in enumerate(zip(source, candidate, strict=True)):
        if offset in allowed or offset in CHECKSUM_OFFSETS:
            continue
        r305.r304.require(before == after,
                          f"r315 changed unowned byte {offset:#x}")

    # All r314 transaction observation addresses stay fixed; only the exact
    # start instruction now detours through the private art helper.
    r305.r304.require(r314.HANDLER_LABELS["repair_effect"] == 0x6D4D
                      and r314.HANDLER_LABELS["transaction_armed_effect"] == 0x6DCB
                      and r314.HANDLER_LABELS["display_flip_effect"] == 0x6E25
                      and r314.HANDLER_LABELS["commit_effect"] == 0x6E2A,
                      "r314 transaction observation addresses moved")
    return {
        "functional_changed_bytes": len(functional),
        "escaped_bytes": 0,
        "owned_ranges": [
            "bank31:$6CDA-$6CE1 menu hook",
            "bank31:$6D4D-$6D4F repair hook",
            f"bank31:${REPAIR_WRAPPER_ADDR:04X}-"
            f"${REPAIR_WRAPPER_ADDR + len(REPAIR_WRAPPER) - 1:04X} repair wrapper",
            f"bank31:${MENU_WRAPPER_ADDR:04X}-"
            f"${MENU_WRAPPER_ADDR + len(MENU_WRAPPER) - 1:04X} menu wrapper",
            f"bank31:${ART_HELPER_ADDR:04X}-"
            f"${ART_HELPER_ADDR + len(ART_HELPER) - 1:04X} GDMA helper",
            "bank31:$7000-$70FF canonical signed menu-art mirror",
        ],
        "r314_observation_addresses_preserved": {
            "start": "$6D4D", "armed": "$6DCB",
            "display": "$6E25", "commit": "$6E2A",
        },
    }


def build(
    source: bytes, base_receipt_bytes: bytes,
    rejected_receipt_bytes: bytes, rejected_chr: bytes,
    rejected_planes: bytes, rejected_metadata: bytes,
) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(
        source, base_receipt_bytes, rejected_receipt_bytes, rejected_chr,
        rejected_planes, rejected_metadata,
    )
    helper = helper_contract(source)
    canonical = canonical_bg_art(source)

    rom = bytearray(source)
    for address, old, new, label in (
        (REPAIR_HOOK_ADDR, OLD_REPAIR_HOOK, NEW_REPAIR_HOOK, "repair hook"),
        (MENU_HOOK_ADDR, OLD_MENU_HOOK, NEW_MENU_HOOK, "menu hook"),
    ):
        offset = bank_offset(address)
        r305.r304.require(source[offset:offset + len(old)] == old,
                          f"{label} preimage changed")
        r305.r304.require(len(old) == len(new), f"{label} changes width")
        rom[offset:offset + len(new)] = new
    for address, payload in (
        (REPAIR_WRAPPER_ADDR, REPAIR_WRAPPER),
        (MENU_WRAPPER_ADDR, MENU_WRAPPER),
        (ART_HELPER_ADDR, ART_HELPER),
    ):
        offset = bank_offset(address)
        rom[offset:offset + len(payload)] = payload
    payload_offset = bank_offset(ART_PAYLOAD_ADDR)
    rom[payload_offset:payload_offset + ART_BYTES] = canonical[
        ART_CANONICAL_OFFSET:ART_CANONICAL_OFFSET + ART_BYTES
    ]
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"r315 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-scene0b-chr-restore-r315-build-v1",
        "status": "STATIC_PASS_R315_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r314-transactional-map-publication",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
            "rejected_live_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
            "rejected_chr_dump_sha256": REJECTED_CHR_DUMP_SHA256,
            "rejected_plane_dump_sha256": REJECTED_PLANE_DUMP_SHA256,
            "rejected_plane_metadata_sha256": (
                REJECTED_PLANE_METADATA_SHA256
            ),
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "with LCDC.4=0 the native SELECT menu owns signed bank-zero "
            "IDs 10-1F at physical $9100-$91FF; "
            "r293 reloads only bank-one hazard art, r305 invalidates only "
            "semantic-map keys, and r314 republishes maps/attributes/hazards "
            "without restoring the menu-overwritten bank-zero CHR"
        ),
        "patch": {
            "repair_order": (
                "$6D4D start -> $6E50 wrapper -> $6E80 FF55-bit7 idle -> "
                "LCD-off direct or LCD-on fresh-VBlank atomic CHR GDMA -> "
                "$6D6D arm -> $6DCB armed -> native publication -> "
                "$6E25 display -> $6E2A commit"
            ),
            "menu_order": (
                "$6CDA exact scoped menu completion -> $6E60 DI/save LCDC/"
                "show Window/cache invalidation once -> $6E80 FF55-bit7 "
                "inactive + fresh VBlank + atomic CHR GDMA -> retry helper "
                "only while NZ -> restore LCDC with Window hidden -> EI -> "
                "native $6CE2 exit"
            ),
            "menu_entry_hold_untouched": True,
            "art_mirror": "bank31:$7000-$70FF",
            "vram_restore": "VBK0:$9100-$91FF, signed IDs $10-$1F",
        },
        "preimage_contract": preimages,
        "offline_contract": {"atomic_art_helper": helper},
        "ownership": ownership,
        "timing": {
            "current_scene0B_handler_path": "byte-exact r314; 0T delta",
            "current_scene02_handler_path": "byte-exact r314; 0T delta",
            "renderer_inner_loop_delta": 0,
            "ordinary_map_publication_delta": 0,
            "menu_entry_and_hold_delta": 0,
            "one_time_repair_or_menu_close": (
                "LCD-off direct or LCD-on wait to fresh VBlank, then one "
                "128-us 256-byte general DMA"
            ),
            "release_speed_gate_required": True,
        },
        "required_live_gates": [
            "both operator captures restore exact referenced CHR before acknowledgment",
            "menu entry/hold retains native Window glyph art",
            "menu-close wait remains Window-covered until canonical CHR is restored",
            "first post-close gameplay sample and final CHR dump are canonical",
            "r314 transaction ordering and full physical-plane oracles remain exact",
            "no wall-edge, flash, trail, pickup, or hazard visual regressions",
            "Stage1 release speed >=95%; later-stage strict policy unchanged",
        ],
        "decision": "STATIC_CHR_RESTORE_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument(
        "--rejected-live-receipt", type=Path, default=REJECTED_LIVE_RECEIPT
    )
    parser.add_argument("--rejected-chr", type=Path, default=REJECTED_CHR_DUMP)
    parser.add_argument(
        "--rejected-planes", type=Path, default=REJECTED_PLANE_DUMP
    )
    parser.add_argument(
        "--rejected-metadata", type=Path, default=REJECTED_PLANE_METADATA
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes(),
        args.rejected_live_receipt.read_bytes(), args.rejected_chr.read_bytes(),
        args.rejected_planes.read_bytes(), args.rejected_metadata.read_bytes(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
