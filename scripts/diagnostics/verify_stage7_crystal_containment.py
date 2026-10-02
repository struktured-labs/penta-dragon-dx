#!/usr/bin/env python3
"""Fail-closed Crystal boundary/outcome gate for the frozen Stage-7 r265 ROM.

This verifier normalizes the canonical Crystal fixture onto the exact
candidate, proves that the current candidate-owned C600/DA60 runtime is
resident, runs two sequential read-only boundary/outcome probes, and then
composes the existing duplicate Crystal ghost cadence/material verifier.

The production probe intentionally installs no debugger breakpoints or
watchpoints: the preserved failed r1 receipt demonstrates that either class
can stop this canonical savestate after its first frame.  Containment is thus
stated as a strict recurrent-boundary plus deterministic-machine-outcome gate.
It does not claim transient helper absence or write-site attribution.

No alternate emulator executable is accepted.  All live runs go through the
checked-in project-wide single-flight launcher.  ``--offline-controls-only``
performs only static/state audits and mutation controls; it never launches an
emulator.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable
import zlib

from normalize_mgba_state_pc import normalize


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
R264_CONTROL = ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb"
STATIC_RECEIPT = ROOT / "tmp/stage7-dual-plane-hdma-r264/static-receipt.json"
HELPER_EQUIVALENCE_RECEIPT = (
    ROOT
    / "tmp/stage7-menu-signature-invalidation-r265/"
    "helper-equivalence-static-receipt.json"
)
R265_BUILD_RECEIPT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/static-receipt.json"
)
R265_MENU_RECEIPT = (
    ROOT
    / "tmp/stage7-menu-signature-invalidation-r265/menu-fixed-r1/receipt.json"
)
CRYSTAL_STATE = (
    ROOT
    / "tmp/visual-audit-suite-r31/matrix/artifacts/boss-arenas"
    / "boss2_crystal_dragon.ss0"
)
RIFF_STATE = CRYSTAL_STATE.with_name("boss1_riff.ss0")
STAGE3_STATE = ROOT / "tmp/palette_session/states/stage3.ss0"
PROBE = ROOT / "scripts/diagnostics/probe_stage7_crystal_containment.lua"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
NORMALIZER = ROOT / "scripts/diagnostics/normalize_mgba_state_pc.py"
GHOST_VERIFIER = ROOT / "scripts/diagnostics/verify_crystal_dragon_ghost.py"
GHOST_PROBE = ROOT / "scripts/diagnostics/probe_crystal_flicker.lua"
BUILDER = ROOT / "scripts/build_v302_title_fix.py"
PALETTE = ROOT / "palettes/penta_palettes_v097.yaml"

EXPECTED_CANDIDATE_SHA256 = (
    "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
)
EXPECTED_E048_CANDIDATE_SHA256 = (
    "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
)
EXPECTED_R264_CONTROL_SHA256 = (
    "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
)
EXPECTED_STATIC_RECEIPT_SHA256 = (
    "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272"
)
EXPECTED_HELPER_EQUIVALENCE_RECEIPT_SHA256 = (
    "295ce612d6dc1dead72e776f44dafb3bd22b6bc0e44b101435b27d7ddafe0583"
)
EXPECTED_R265_BUILD_RECEIPT_SHA256 = (
    "9567c8babe7be863ecbd5a7c6ba9a8234cd81aef7508a1f6e3c184773c3a6ab7"
)
EXPECTED_R265_MENU_RECEIPT_SHA256 = (
    "17c2d8a5a6b2d1d36ce5cb9d931db03534b2dbf7cacf5fae06be4cf3dbfdb7e5"
)
EXPECTED_CRYSTAL_STATE_SHA256 = (
    "7d311c87bc6298c91b25535088c4e055c995a9cff916a4934d040d26379473b8"
)
EXPECTED_RIFF_STATE_SHA256 = (
    "29aa0fb3a53491502073df85218efa69f075141b166e7d522918fbcb6f78bf36"
)
EXPECTED_STAGE3_STATE_SHA256 = (
    "49bbde02f6ea1745b99b1c94d9d1399f3161d2e410234d0abb93d36d42e723f3"
)
EXPECTED_NORMALIZED_STATE_SHA256 = (
    "091b1c5adc7048cfc980f0de7f555901a2e4983a54765264f371f84c41deccde"
)
# Filled only after the exact preserve-machine normalization is audited.  The
# base control is an executable input to the live route discriminator, not an
# unbound convenience ROM.
EXPECTED_CONTROL_NORMALIZED_STATE_SHA256 = (
    "2fdece929453c7e2579701041d7dc556c87d4d85f4e7554045287451f742a941"
)
EXPECTED_TOOL_SHA256 = {
    "probe": "67d92ddf4d33ea2594132d3b7dc4db4a98526f645b76b2bb6d28a7515207cf4e",
    "launcher": "46fe5b57771627e9141e359bd93c9d821c2b873d34162e355dfec33896649570",
    "normalizer": "7718f668eeca9b390af84aad1357c9ffd8dc59723b700b536f86ac9a47b32b01",
    "ghost_verifier": "a905cef0297743af7e473c5e260e4da8e3d4e93079cf92838391ef8cca4d2a9a",
    "ghost_probe": "bf52af5d0dbdc4f8200ec4ad9c767e6308680480e893caab3cecd9b019ccebc6",
    "builder": "9b09071b68b37866f455de25bd9f5dccf8a76bdb85afb039a306e664b48288b0",
    "palette": "71e3ae76ac88151173d2113df1592c470ecd0c8a984e60ca0d36f84174a1935a",
}

FRAMES = 720
SCENE = 0x0E
HELPER_BANK = 22
HELPER_FIRST = 0x6C80
HELPER_LAST = 0x7232
FORBIDDEN_HITS = {
    "helper_entry": 0x6C80,
    "phase1_service": 0x7108,
    "phase2_service": 0x714B,
    "attr_dma": 0x713D,
    "tile_dma": 0x7187,
    "fallback_native": 0x71B3,
    "caller_reject": 0x71BD,
    "fallback_atomic": 0x71C1,
}
GHOST_AMBIENT_ENV_PREFIX = "CRYSTAL_FLICKER_"
GHOST_CONTROLLED_ENV_KEYS = (
    "CRYSTAL_FLICKER_OUT",
    "CRYSTAL_FLICKER_FRAMES",
    "CRYSTAL_FLICKER_EXPECTED_SCENE",
    "CRYSTAL_FLICKER_STATE_FILE",
    "CRYSTAL_FLICKER_RELOAD_MATERIAL",
)
GHOST_OPTIONAL_ENV_KEYS = (
    "CRYSTAL_FLICKER_RELOAD_PHASE",
    "CRYSTAL_FLICKER_RELOAD_WRAM",
    "CRYSTAL_FLICKER_RELOAD_OBJ5",
    "CRYSTAL_FLICKER_SCREENSHOTS",
    "CRYSTAL_FLICKER_SCREENSHOT_STEP",
    "CRYSTAL_FLICKER_TRACE_STEP",
    "CRYSTAL_FLICKER_STATE_OUT",
    "CRYSTAL_FLICKER_STATE_TRACE",
    "CRYSTAL_FLICKER_COPY_TRACE",
    "CRYSTAL_FLICKER_AFTERIMAGE",
)
REQUIRED_LIVENESS = {
    "resume_state", "copy_decider", "runtime_entry",
    "runtime_nonstage_gate", "runtime_nonstage_ret", "rst_return",
    "dirty_branch",
}
OPTIONAL_ROUTE_HITS = {
    "main_loop", "runtime_native_restore", "atomic_entry", "copy_continue",
    "exact_exit", "outer_primary", "outer_secondary",
}
EXPECTED_HIT_NAMES = REQUIRED_LIVENESS | OPTIONAL_ROUTE_HITS | set(FORBIDDEN_HITS)
ROUTE_DIAGNOSTIC_FRAMES = 2

GB_STATE_SIZE = 0x11800
GB_STATE_MAGIC = 0x00400003
CPU_PC = 0x002A
VIDEO_CURRENT_VRAM_BANK = 0x00CC
MEMORY_CURRENT_ROM_BANK = 0x0168
MEMORY_CURRENT_WRAM_BANK = 0x016A
MEMORY_FLAGS = 0x0194
IO = 0x0300
HRAM = 0x0380
IE = 0x03FF
WRAM0 = 0x4400
WRAM1 = 0x5400
WRAM2 = 0x6400
WRAM3 = 0x7400
MEMORY_FLAG_IME = 1 << 3
MEMORY_FLAG_HDMA_ACTIVE = 1 << 4

BANK13 = 13 * 0x4000
ARENA_TABLE2_ROM = BANK13 + 0x7400 - 0x4000
ARENA_GEOMETRY_ROM = BANK13 + 0x563A - 0x4000
RUNTIME_A_ROM = BANK13 + 0x7BB2 - 0x4000
RUNTIME_B_ROM = BANK13 + 0x7C4D - 0x4000
RUNTIME_SPLIT = 0x7BE0 - 0x7BB2


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str:
    require(path.is_file(), f"required file is missing: {path}")
    return digest_bytes(path.read_bytes())


def serialized_state(path: Path) -> bytes:
    """Extract one CRC-valid, exact-size mGBA Game Boy machine state."""

    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"not an mGBA PNG savestate: {path}")
    offset = 8
    states: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        require(offset + 12 <= len(data), f"truncated PNG chunk: {path}")
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + 12 + size
        require(end <= len(data), f"truncated PNG payload: {path}")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        observed_crc = struct.unpack(">I", data[offset + 8 + size:end])[0]
        require(
            observed_crc == zlib.crc32(kind + payload) & 0xFFFFFFFF,
            f"PNG chunk CRC mismatch ({kind!r}): {path}",
        )
        if kind == b"gbAs":
            decoder = zlib.decompressobj()
            state = decoder.decompress(payload) + decoder.flush()
            require(decoder.eof and not decoder.unused_data
                    and not decoder.unconsumed_tail,
                    f"malformed compressed gbAs payload: {path}")
            states.append(state)
        if kind == b"IEND":
            require(size == 0, f"non-empty PNG IEND: {path}")
            saw_iend = True
            require(end == len(data), f"trailing bytes after PNG IEND: {path}")
        offset = end
    require(saw_iend, f"PNG savestate lacks IEND: {path}")
    require(len(states) == 1,
            f"expected one gbAs chunk, found {len(states)}: {path}")
    state = states[0]
    require(len(state) == GB_STATE_SIZE,
            f"gbAs state is {len(state):#x}, expected {GB_STATE_SIZE:#x}: {path}")
    require(int.from_bytes(state[0:4], "little") == GB_STATE_MAGIC,
            f"unsupported Game Boy savestate version: {path}")
    require(state[0x0008] & 0x80, f"savestate is not a CGB machine: {path}")
    return state


def io_byte(state: bytes, address: int) -> int:
    require(0xFF00 <= address <= 0xFF7F, f"not I/O: ${address:04X}")
    return state[IO + address - 0xFF00]


def hram_byte(state: bytes, address: int) -> int:
    require(0xFF80 <= address <= 0xFFFE, f"not HRAM: ${address:04X}")
    return state[HRAM + address - 0xFF80]


def wram0(state: bytes, address: int, size: int = 1) -> bytes:
    require(0xC000 <= address <= 0xCFFF, f"not WRAM0: ${address:04X}")
    offset = WRAM0 + address - 0xC000
    require(offset + size <= WRAM1, "WRAM0 read crosses boundary")
    return state[offset:offset + size]


def bank1(state: bytes, address: int, size: int = 1) -> bytes:
    require(0xD000 <= address <= 0xDFFF, f"not banked WRAM: ${address:04X}")
    offset = WRAM1 + address - 0xD000
    require(offset + size <= WRAM2, "bank-1 read crosses boundary")
    return state[offset:offset + size]


def candidate_runtime(rom: bytes) -> dict[str, bytes]:
    table = rom[ARENA_TABLE2_ROM:ARENA_TABLE2_ROM + 0x100]
    geometry = rom[ARENA_GEOMETRY_ROM:ARENA_GEOMETRY_ROM + 36]
    runtime = (
        rom[RUNTIME_A_ROM:RUNTIME_A_ROM + RUNTIME_SPLIT]
        + rom[RUNTIME_B_ROM:RUNTIME_B_ROM + 0xA0 - RUNTIME_SPLIT]
    )
    require(len(table) == 0x100 and all(value <= 7 for value in table),
            "candidate Crystal C600 table is missing or invalid")
    require(len(geometry) == 36, "candidate DB80 helper is truncated")
    require(len(runtime) == 0xA0, "candidate DA60 helper is truncated")
    return {"c600": table, "db80": geometry, "da60": runtime}


def validate_state_boundary(
    state: bytes,
    runtime: dict[str, bytes],
    *,
    label: str,
    require_resume: bool,
    require_candidate_runtime: bool = True,
) -> dict[str, Any]:
    pc = int.from_bytes(state[CPU_PC:CPU_PC + 2], "little")
    current_rom = int.from_bytes(
        state[MEMORY_CURRENT_ROM_BANK:MEMORY_CURRENT_ROM_BANK + 2], "little"
    )
    current_wram = int.from_bytes(
        state[MEMORY_CURRENT_WRAM_BANK:MEMORY_CURRENT_WRAM_BANK + 2], "little"
    )
    ff99 = hram_byte(state, 0xFF99)
    scene = bank1(state, 0xD880)[0]
    require(scene == SCENE, f"{label}: scene is ${scene:02X}, expected $0E")
    if require_candidate_runtime:
        require(wram0(state, 0xC600, 0x100) == runtime["c600"],
                f"{label}: candidate C600 Crystal table is not resident")
        require(bank1(state, 0xDA60, 0xA0) == runtime["da60"],
                f"{label}: candidate DA60 runtime is not resident")
        require(bank1(state, 0xDB80, 36) == runtime["db80"],
                f"{label}: candidate DB80 geometry is not resident")
        require(bank1(state, 0xDF0D)[0] == SCENE,
                f"{label}: scene cache is not $0E")
    require(io_byte(state, 0xFF55) == 0xFF,
            f"{label}: FF55 is not idle")
    require(io_byte(state, 0xFF4F) & 1 == 0,
            f"{label}: VBK is not zero")
    require(state[VIDEO_CURRENT_VRAM_BANK] == 0,
            f"{label}: serialized VRAM bank is not zero")
    require(io_byte(state, 0xFF70) & 7 == 1,
            f"{label}: SVBK is not bank 1")
    require((current_wram & 7) == 1,
            f"{label}: serialized WRAM bank is not 1")
    require(hram_byte(state, 0xFFBA) == 2,
            f"{label}: Crystal dungeon identity FFBA changed")
    require(hram_byte(state, 0xFFC1) == 1,
            f"{label}: gameplay flag FFC1 changed")
    require(state[IE] == 7, f"{label}: IE is not $07")
    require(current_rom != HELPER_BANK and ff99 != HELPER_BANK,
            f"{label}: bank22 is mapped or retained in the mapper shadow")
    memory_flags = int.from_bytes(
        state[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little"
    )
    if require_resume:
        require(pc == 0x43DA and current_rom == 3,
                f"{label}: canonical resume is not bank3:$43DA")
        require(ff99 == 1,
                f"{label}: canonical return-bank shadow FF99 is not 1")
    return {
        "pc": f"{pc:04X}",
        "mapped_rom_bank": current_rom,
        "ff99": ff99,
        "ffba": hram_byte(state, 0xFFBA),
        "ffc1": hram_byte(state, 0xFFC1),
        "ff55": f"{io_byte(state, 0xFF55):02X}",
        "vbk": io_byte(state, 0xFF4F) & 1,
        "svbk": io_byte(state, 0xFF70) & 7,
        "ie": state[IE],
        "ffa5": hram_byte(state, 0xFFA5),
        "ffe0": hram_byte(state, 0xFFE0),
        "ffe4": hram_byte(state, 0xFFE4),
        "ime": bool(memory_flags & MEMORY_FLAG_IME),
        "serialized_hdma_active": bool(
            memory_flags & MEMORY_FLAG_HDMA_ACTIVE
        ),
        "private_bank2_sha256": digest_bytes(state[WRAM2:WRAM2 + 0x180]),
        "private_bank3_sha256": digest_bytes(state[WRAM3:WRAM3 + 0x300]),
    }


def validate_normalization_delta(source: bytes, normalized: bytes) -> None:
    require(len(source) == len(normalized) == GB_STATE_SIZE,
            "normalization state size changed")
    allowed = [
        (0x0004, 0x0008, "ROM CRC"),
        (WRAM0 + 0x600, WRAM0 + 0x700, "C600 table"),
        (WRAM1 + 0xA60, WRAM1 + 0xB00, "DA60 runtime"),
        (WRAM1 + 0xB80, WRAM1 + 0xBA4, "DB80 geometry"),
        (WRAM1 + 0xF0D, WRAM1 + 0xF0E, "DF0D scene cache"),
    ]
    changes = [index for index, pair in enumerate(zip(source, normalized))
               if pair[0] != pair[1]]
    require(changes, "normalization made no candidate-binding change")
    for index in changes:
        require(any(first <= index < last for first, last, _ in allowed),
                f"normalization mutated unexpected state byte {index:#x}")


def input_identity(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    paths = {
        "candidate": args.candidate.resolve(),
        "r264_control": args.r264_control.resolve(),
        "static_receipt": args.static_receipt.resolve(),
        "helper_equivalence_receipt": args.helper_equivalence_receipt.resolve(),
        "r265_build_receipt": args.r265_build_receipt.resolve(),
        "r265_menu_receipt": args.r265_menu_receipt.resolve(),
        "crystal_state": args.crystal_state.resolve(),
        "riff_state": args.riff_state.resolve(),
        "stage3_state": args.stage3_state.resolve(),
        "probe": PROBE.resolve(),
        "launcher": LAUNCHER.resolve(),
        "normalizer": NORMALIZER.resolve(),
        "ghost_verifier": GHOST_VERIFIER.resolve(),
        "ghost_probe": GHOST_PROBE.resolve(),
        "builder": BUILDER.resolve(),
        "palette": PALETTE.resolve(),
        "verifier": Path(__file__).resolve(),
    }
    return {
        name: {"path": str(path.relative_to(ROOT)), "sha256": digest_file(path)}
        for name, path in paths.items()
    }


def validate_identity(identity: dict[str, dict[str, str]]) -> None:
    expected = {
        "candidate": EXPECTED_CANDIDATE_SHA256,
        "r264_control": EXPECTED_R264_CONTROL_SHA256,
        "static_receipt": EXPECTED_STATIC_RECEIPT_SHA256,
        "helper_equivalence_receipt": (
            EXPECTED_HELPER_EQUIVALENCE_RECEIPT_SHA256
        ),
        "r265_build_receipt": EXPECTED_R265_BUILD_RECEIPT_SHA256,
        "r265_menu_receipt": EXPECTED_R265_MENU_RECEIPT_SHA256,
        "crystal_state": EXPECTED_CRYSTAL_STATE_SHA256,
        "riff_state": EXPECTED_RIFF_STATE_SHA256,
        "stage3_state": EXPECTED_STAGE3_STATE_SHA256,
        **EXPECTED_TOOL_SHA256,
    }
    for name, expected_sha in expected.items():
        require(identity[name]["sha256"] == expected_sha,
                f"{name} SHA-256 is not the frozen containment input")


def validate_static_receipt(path: Path) -> dict[str, Any]:
    receipt = json.loads(path.read_text())
    require(receipt.get("schema")
            == "penta-stage7-hidden-dual-plane-hdma-r264-static-v1",
            "wrong Stage-7 static receipt schema")
    require(receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "Stage-7 static receipt is not awaiting live gates")
    require(receipt.get("promotable") is False
            and receipt.get("emulator_run") is False,
            "static receipt overclaims promotion/live execution")
    candidate = receipt.get("in_memory_candidate", {})
    require(candidate.get("sha256") == EXPECTED_E048_CANDIDATE_SHA256,
            "base helper receipt e048 identity mismatch")
    helper = receipt.get("helper", {})
    require(helper.get("bank") == HELPER_BANK
            and helper.get("entry") == "$6C80"
            and helper.get("end") == "$7232"
            and helper.get("length") == 1459,
            "static helper range changed")
    require(helper.get("sha256")
            == "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003",
            "static helper payload changed")
    labels = helper.get("trace_labels", {})
    expected_labels = {
        "entry": "bank22:$6C80",
        "phase1_service": "bank22:$7108",
        "phase2_service": "bank22:$714B",
        "attr_FF55_store": "bank22:$713D",
        "tile_FF55_store": "bank22:$7187",
        "fallback_native": "bank22:$71B3",
        "caller_reject": "bank22:$71BD",
        "fallback_after_atomic": "bank22:$71C1",
    }
    for name, value in expected_labels.items():
        require(labels.get(name) == value,
                f"static trace label {name} is not {value}")
    require(receipt.get("runtime_router", {}).get("stage_gate")
            == "$D880 == $08", "Stage-7 scene gate changed")
    require(receipt.get("memory_ownership", {}).get("stage1_and_arenas")
            == "cannot enter helper because D880 must equal $08",
            "static scene-gate topology changed")
    return {
        "schema": receipt["schema"],
        "status": receipt["status"],
        "helper": "bank22:$6C80-$7232",
        "dma_sites": ["bank22:$713D", "bank22:$7187"],
        "stage_gate": "$D880 == $08",
    }


def validate_r265_equivalence(
    equivalence_path: Path,
    build_path: Path,
    menu_path: Path,
) -> dict[str, Any]:
    """Bind r265's isolated Window delta to e048's helper contract."""

    equivalence = json.loads(equivalence_path.read_text())
    require(
        equivalence.get("schema")
        == "penta-stage7-r265-helper-equivalence-static-v1",
        "wrong r265 helper-equivalence schema",
    )
    require(
        equivalence.get("status") == "STATIC_PASS_REBIND_WRAPPERS_REQUIRED"
        and equivalence.get("decision")
        == "STATIC_GO_TO_BUILD_STRICT_R265_GATE_WRAPPERS"
        and equivalence.get("promotable") is False,
        "r265 helper-equivalence receipt is not the frozen rebind decision",
    )
    identities = equivalence.get("identities", {})
    expected_identities = {
        "e048_rom": EXPECTED_E048_CANDIDATE_SHA256,
        "e048_static_receipt": EXPECTED_STATIC_RECEIPT_SHA256,
        "r265_rom": EXPECTED_CANDIDATE_SHA256,
        "r265_build_receipt": EXPECTED_R265_BUILD_RECEIPT_SHA256,
        "r265_menu_live_receipt": EXPECTED_R265_MENU_RECEIPT_SHA256,
    }
    for name, expected in expected_identities.items():
        require(identities.get(name) == expected,
                f"r265 equivalence identity {name} changed")
    consumer = equivalence.get("consumer_requirements", {})
    require(consumer.get("candidate_identity") == EXPECTED_CANDIDATE_SHA256,
            "r265 equivalence consumer candidate changed")
    require(consumer.get("nonmenu_ABI_visual_speed")
            == "require FFE4==$00 throughout",
            "historical r265 equivalence condition changed")
    protected = equivalence.get("equivalence", {}).get("protected_spans", {})
    require(protected.get("bank22_helper", {}).get("sha256")
            == "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003",
            "r265 bank22 helper is not e048-identical")
    require(protected.get("bank22_immutable_LUT", {}).get("sha256")
            == "cfb5fe66cecfb2887abd8f8e828d311265217831888713ddeb50d8b0f4a6a84a",
            "r265 Stage7 LUT is not e048-identical")
    require(protected.get("runtime_DA60_source_part1", {}).get("sha256")
            == "cf20fc43bbab456a503f5fa589149b7a876316a236252cfe469413bb5c3f4cb7",
            "r265 DA60 runtime part 1 changed")
    require(protected.get("runtime_DA60_source_part2", {}).get("sha256")
            == "74f218cab519f21561454427cf0974fc33bf2e465689d5fa15def0f548bfa720",
            "r265 DA60 runtime part 2 changed")

    build = json.loads(build_path.read_text())
    require(build.get("schema")
            == "penta-stage7-menu-signature-invalidation-r265-static-v1"
            and build.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED"
            and build.get("candidate_sha256") == EXPECTED_CANDIDATE_SHA256,
            "r265 build receipt is not the frozen static PASS")
    menu = json.loads(menu_path.read_text())
    require(menu.get("schema")
            == "penta-stage7-menu-signature-control-fix-live-v1"
            and menu.get("status") == "PASS"
            and menu.get("rom_sha256") == EXPECTED_CANDIDATE_SHA256,
            "r265 menu receipt is not the frozen live PASS")
    require(menu.get("determinism", {}).get("passed") is True,
            "r265 menu live receipt is not deterministic")
    return {
        "schema": equivalence["schema"],
        "status": equivalence["status"],
        "r265_candidate": EXPECTED_CANDIDATE_SHA256,
        "e048_helper_base": EXPECTED_E048_CANDIDATE_SHA256,
        "window_only_changed_region": "bank13:$6A40-$6A56",
        "historical_transfer_condition": "FFE4==$00 throughout",
        "boundary_gate_claim": (
            "not dynamically transferred: this zero-debugger Crystal gate "
            "does not observe transient Window-helper execution"
        ),
        "menu_live_receipt": EXPECTED_R265_MENU_RECEIPT_SHA256,
    }


def validate_probe_source() -> dict[str, Any]:
    source = PROBE.read_text()
    verifier_source = Path(__file__).read_text()
    ghost_source = GHOST_PROBE.read_text()
    required = (
        'local PROBE_SCHEMA = "penta-stage7-crystal-containment-probe-v2"',
        "local HELPER_BANK = 22",
        "local HELPER_FIRST, HELPER_LAST = 0x6C80, 0x7232",
        'add_breakpoint(0xDA60, "runtime_entry")',
        'add_breakpoint(0xDAA3, "runtime_native_restore")',
        'add_breakpoint(0xDAE9, "runtime_nonstage_gate")',
        'add_breakpoint(0xDAF5, "runtime_nonstage_ret")',
        'add_breakpoint(0x3493, "rst_return")',
        'add_breakpoint(0x42B1, "dirty_branch", 1)',
        "return emu:saveStateFile(STATE_OUT)",
        "emu:setKeys(0)",
        'startup:write("instrumentation-armed\\n")',
        'startup:write("state-loaded-zero-debugger\\n")',
        'ROUTE_DIAGNOSTIC and 9 or 0',
    )
    for text in required:
        require(text in source, f"containment probe lacks exact contract: {text}")
    require("emu:write" not in source,
            "containment probe must not write emulated game memory")
    require("setWatchpoint" not in source
            and "setRangeWatchpoint" not in source,
            "production Crystal probe must install zero write watchpoints")
    for text in (
        'GHOST_AMBIENT_ENV_PREFIX = "CRYSTAL_FLICKER_"',
        "name.startswith(GHOST_AMBIENT_ENV_PREFIX)",
        "environment.pop(name, None)",
        "env=ghost_subprocess_environment()",
    ):
        require(text in verifier_source,
                f"composed ghost gate lacks environment scrub: {text}")
    ghost_keys = set(re.findall(r'CRYSTAL_FLICKER_[A-Z0-9_]+', ghost_source))
    require(
        ghost_keys
        == set(GHOST_CONTROLLED_ENV_KEYS) | set(GHOST_OPTIONAL_ENV_KEYS),
        "ghost probe environment namespace changed without an allowlist update",
    )
    diagnostic_begin = source.index(
        'if ROUTE_DIAGNOSTIC then\n    add_breakpoint(RESUME_PC'
    )
    diagnostic_end = source.index(
        "\nend\n\nfinish = function", diagnostic_begin
    )
    call_needle = "\n    add_breakpoint("
    for offset in (
        index + 5 for index in range(len(source))
        if source.startswith(call_needle, index)
    ):
        require(diagnostic_begin < offset < diagnostic_end,
                "production containment installs an execution breakpoint")
    return {
        "read_only_game_memory": True,
        "production_execution_breakpoints": 0,
        "production_write_watchpoints": 0,
        "production_debugger_hooks": 0,
        "helper_range": "bank22:$6C80-$7232",
        "static_stage7_sites_not_instrumented_in_production": [
            f"bank22:${address:04X}" for address in FORBIDDEN_HITS.values()
        ],
        "current_runtime_sites": [
            "$DA60", "$DAA3", "$DAE9", "$DAF5", "$3493", "$42B1",
        ],
        "forensic_route_diagnostic": (
            "retained but non-promotable: the exact aa4c control itself failed "
            "to advance under breakpoint instrumentation. Production uses no "
            "execution breakpoints and only candidate-native normalized state."
        ),
        "boundary_outcome_semantics": (
            "The frozen scene gate admits Stage-7 ownership only for D880=$08. "
            "Production samples Crystal D880=$0E plus restored FF55/VBK/SVBK/"
            "IE/FFE4 at every one of 720 callbacks and compares duplicate full-"
            "machine outcomes. It deliberately makes no transient write-site "
            "or helper-execution claim because debugger hooks stall this "
            "canonical savestate."
        ),
        "ghost_ambient_environment_policy": {
            "removed_prefix": GHOST_AMBIENT_ENV_PREFIX,
            "controlled_keys": list(GHOST_CONTROLLED_ENV_KEYS),
            "known_optional_keys": list(GHOST_OPTIONAL_ENV_KEYS),
            "controlled_values_are_set_only_by_composed_ghost_verifier": True,
        },
    }


def prepare_normalized_state(
    args: argparse.Namespace,
    destination: Path,
) -> tuple[bytes, bytes, dict[str, bytes], dict[str, Any]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists(),
            f"refusing stale normalized state: {destination}")
    normalize(
        args.crystal_state.resolve(), destination,
        pc=0, writes=[], rom=args.candidate.resolve(),
        preserve_machine=True, arena_table=2,
    )
    require(digest_file(destination) == EXPECTED_NORMALIZED_STATE_SHA256,
            "normalized Crystal state is not the frozen candidate fixture")
    source = serialized_state(args.crystal_state.resolve())
    normalized = serialized_state(destination)
    validate_normalization_delta(source, normalized)
    rom = args.candidate.resolve().read_bytes()
    runtime = candidate_runtime(rom)
    require(normalized[4:8]
            == (zlib.crc32(rom) & 0xFFFFFFFF).to_bytes(4, "little"),
            "normalized state ROM CRC does not bind the candidate")
    source_boundary = validate_state_boundary(
        source, runtime, label="canonical Crystal source", require_resume=True,
        require_candidate_runtime=False,
    )
    normalized_boundary = validate_state_boundary(
        normalized, runtime, label="normalized Crystal input", require_resume=True,
    )
    require(source[:4] == normalized[:4], "state format changed")
    return source, normalized, runtime, {
        "path": str(destination.relative_to(ROOT)),
        "sha256": digest_file(destination),
        "source_boundary": source_boundary,
        "normalized_boundary": normalized_boundary,
        "normalization": (
            "ROM CRC + candidate-owned C600/DA60/DB80/DF0D only; CPU $43DA, "
            "bank3 resume, stack, mapper, video, and native game state preserved"
        ),
        "resume_explanation": (
            "The fixture resumes bank3:$43DA with FF99=1 by design: it is "
            "inside current bank-3 work and retains bank 1 as the native return "
            "shadow. Candidate-owned C600/DA60/DB80/DF0D bytes are installed "
            "before 720 advancing zero-debugger frame callbacks; final-state "
            "validation requires those exact bytes still resident."
        ),
    }


def prepare_control_state(
    args: argparse.Namespace,
    destination: Path,
) -> tuple[bytes, dict[str, bytes], dict[str, Any]]:
    """Bind the same preserved Crystal machine to exact pre-Stage7 r264."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists(),
            f"refusing stale r264 control state: {destination}")
    normalize(
        args.crystal_state.resolve(), destination,
        pc=0, writes=[], rom=args.r264_control.resolve(),
        preserve_machine=True, arena_table=2,
    )
    require(
        digest_file(destination) == EXPECTED_CONTROL_NORMALIZED_STATE_SHA256,
        "normalized Crystal r264 control is not the frozen fixture",
    )
    source = serialized_state(args.crystal_state.resolve())
    normalized = serialized_state(destination)
    validate_normalization_delta(source, normalized)
    rom = args.r264_control.resolve().read_bytes()
    runtime = candidate_runtime(rom)
    require(
        normalized[4:8]
        == (zlib.crc32(rom) & 0xFFFFFFFF).to_bytes(4, "little"),
        "normalized control state ROM CRC does not bind exact r264",
    )
    boundary = validate_state_boundary(
        normalized, runtime, label="normalized r264 Crystal control",
        require_resume=True,
    )
    return normalized, runtime, {
        "path": str(destination.relative_to(ROOT)),
        "sha256": digest_file(destination),
        "boundary": boundary,
        "rom_sha256": digest_file(args.r264_control.resolve()),
        "normalization": (
            "same canonical machine/stack/video state; exact aa4c r264 ROM "
            "CRC plus its C600/DA60/DB80/DF0D payloads only"
        ),
    }


def parse_int(value: str, base: int = 10) -> int:
    try:
        return int(value, base)
    except ValueError as error:
        raise AssertionError(f"invalid probe integer {value!r}") from error


def parse_probe_report(path: Path) -> dict[str, Any]:
    lines = path.read_text().splitlines()
    require(lines, f"empty containment report: {path}")
    header: dict[str, str] = {}
    for token in lines[0].split():
        require("=" in token, f"malformed containment header token {token!r}")
        key, value = token.split("=", 1)
        require(key not in header, f"duplicate containment header key {key}")
        header[key] = value
    hits: dict[str, int] = {}
    frames: list[dict[str, int]] = []
    events: list[str] = []
    for line in lines[1:]:
        fields = line.split("\t")
        if fields[0] == "hit":
            require(len(fields) == 3, f"malformed hit row: {line}")
            require(fields[1] not in hits, f"duplicate hit row: {fields[1]}")
            hits[fields[1]] = parse_int(fields[2])
        elif fields[0] == "frame":
            require(len(fields) == 15, f"malformed frame row: {line}")
            require(fields[2] != "--", "scene was unreadable at a frame boundary")
            frames.append({
                "frame": parse_int(fields[1]),
                "scene": parse_int(fields[2], 16),
                "pc": parse_int(fields[3], 16),
                "ff99": parse_int(fields[4], 16),
                "svbk": parse_int(fields[5]),
                "vbk": parse_int(fields[6]),
                "ff55": parse_int(fields[7], 16),
                "ffa5": parse_int(fields[8], 16),
                "ffe0": parse_int(fields[9], 16),
                "ie": parse_int(fields[10], 16),
                "lcdc": parse_int(fields[11], 16),
                "ffba": parse_int(fields[12], 16),
                "ffc1": parse_int(fields[13], 16),
                "ffe4": parse_int(fields[14], 16),
            })
        elif fields[0] == "event":
            events.append(line)
        else:
            raise AssertionError(f"unknown containment report row: {line}")
    return {
        "header": header,
        "hits": hits,
        "frames": frames,
        "events": events,
        "text": path.read_text(),
    }


def validate_probe_result(result: dict[str, Any]) -> dict[str, Any]:
    header = result["header"]
    require(header.get("schema")
            == "penta-stage7-crystal-containment-probe-v2",
            "wrong containment probe schema")
    require(header.get("status") == "ok", "containment probe reported violation")
    for key, expected in {
        "frames": FRAMES,
        "scene_samples": FRAMES,
        "scene_unreadable": 0,
        "wrong_scene": 0,
        "ff55_nonidle": 0,
        "boundary_bank22": 0,
        "ffe4_nonzero": 0,
        "final_saved": 1,
        "drain_frames": 0,
        "safe_finish": 0,
        "max_drain_frames": 120,
        "route_diagnostic": 0,
        "production_debugger_instrumentation": 0,
    }.items():
        require(key in header, f"containment header lacks {key}")
        require(parse_int(header[key]) == expected,
                f"containment {key} is {header[key]}, expected {expected}")
    require(header.get("route_mode") == "candidate",
            "containment route mode changed")
    for key in ("state_save_wait_frames", "state_save_stable_frames"):
        require(key in header, f"containment header lacks {key}")
    save_wait = parse_int(header["state_save_wait_frames"])
    save_stable = parse_int(header["state_save_stable_frames"])
    require(2 <= save_wait <= 120 and save_stable >= 2,
            "final frame-boundary state did not become stably complete")
    hits = result["hits"]
    require(set(hits) == EXPECTED_HIT_NAMES,
            "containment hit-site census is incomplete or has unknown sites")
    require(all(value == 0 for value in hits.values()),
            "zero-instrumentation placeholder hit table is not zero")
    frames = result["frames"]
    require(len(frames) == FRAMES, "containment frame count is not 720")
    require([row["frame"] for row in frames] == list(range(1, FRAMES + 1)),
            "containment frame sequence is not exact 1..720")
    for row in frames:
        require(row["scene"] == SCENE,
                f"frame {row['frame']}: scene is not $0E")
        require(row["ff99"] != HELPER_BANK,
                f"frame {row['frame']}: bank22 is mapped")
        require(row["ff55"] == 0xFF,
                f"frame {row['frame']}: FF55 is not idle")
        require(row["svbk"] == 1 and row["vbk"] == 0,
                f"frame {row['frame']}: VRAM/WRAM mapper is not restored")
        require(row["ie"] == 7,
                f"frame {row['frame']}: IE is not restored")
        require(row["ffba"] == 2 and row["ffc1"] == 1,
                f"frame {row['frame']}: Crystal/gameplay identity changed")
        require(row["ffe4"] == 0,
                f"frame {row['frame']}: menu ownership FFE4 is not zero")
    require(not result["events"], "containment probe emitted violation events")
    return {
        "frames": FRAMES,
        "scene": "0E",
        "production_execution_breakpoints": 0,
        "production_write_watchpoints": 0,
        "production_debugger_instrumentation": 0,
        "execution_site_measurement": (
            "not installed; zero hit rows are schema placeholders and do not "
            "prove transient helper absence"
        ),
        "frame_boundary": {
            "FF55": "FF", "VBK": 0, "SVBK": 1, "IE": 7,
            "FFBA": 2, "FFC1": 1, "FFE4": 0, "bank22_frames": 0,
        },
        "native_ff99_banks": sorted({row["ff99"] for row in frames}),
        "state_save_wait_frames": save_wait,
        "state_save_stable_frames": save_stable,
        "ffa5_values": sorted({row["ffa5"] for row in frames}),
        "ffe0_values": sorted({row["ffe0"] for row in frames}),
    }


def validate_route_diagnostic(
    result: dict[str, Any], *, mode: str,
) -> dict[str, Any]:
    """Validate the two-frame exact-r264 versus redirected-tail discriminator."""

    require(mode in {"candidate", "control"}, "invalid route diagnostic mode")
    header = result["header"]
    require(
        header.get("schema") == "penta-stage7-crystal-containment-probe-v2",
        "wrong route diagnostic probe schema",
    )
    require(header.get("status") == "ok",
            f"{mode} route diagnostic reported violation")
    expected_header = {
        "frames": ROUTE_DIAGNOSTIC_FRAMES,
        "scene_samples": ROUTE_DIAGNOSTIC_FRAMES,
        "scene_unreadable": 0,
        "wrong_scene": 0,
        "ff55_nonidle": 0,
        "boundary_bank22": 0,
        "final_saved": 1,
        "drain_frames": 0,
        "safe_finish": 0,
        "route_diagnostic": 1,
        "production_debugger_instrumentation": 9,
    }
    for key, expected in expected_header.items():
        require(key in header, f"route diagnostic header lacks {key}")
        require(parse_int(header[key]) == expected,
                f"{mode} route {key} is {header[key]}, expected {expected}")
    require(header.get("route_mode") == mode,
            f"route report mode is not {mode}")
    hits = result["hits"]
    require(set(hits) == EXPECTED_HIT_NAMES,
            "route diagnostic hit-site census is incomplete")
    for name in FORBIDDEN_HITS:
        require(hits[name] == 0,
                f"unexpected Stage-7 helper hit in {mode} route diagnostic")
    for name in (
        "resume_state", "runtime_entry", "rst_return", "dirty_branch",
        "atomic_entry", "copy_continue",
    ):
        require(hits[name] > 0,
                f"{mode} route did not reach {name}")
    if mode == "candidate":
        require(hits["runtime_nonstage_gate"] > 0
                and hits["runtime_nonstage_ret"] > 0,
                "candidate did not traverse DAE9 -> DAF5")
    else:
        require(hits["runtime_native_restore"] > 0,
                "r264 control did not traverse native DAA3 restore")
        require(hits["runtime_nonstage_gate"] == 0
                and hits["runtime_nonstage_ret"] == 0,
                "r264 control unexpectedly traversed candidate DAE9 tail")
    frames = result["frames"]
    require(len(frames) == ROUTE_DIAGNOSTIC_FRAMES,
            f"{mode} route did not advance two exact frames")
    require([row["frame"] for row in frames] == [1, 2],
            f"{mode} route frame sequence changed")
    for row in frames:
        require(row["scene"] == SCENE, f"{mode} route left Crystal scene")
        require(row["ff55"] == 0xFF and row["ff99"] != HELPER_BANK,
                f"{mode} route exposed Stage-7 DMA/bank state")
        require(row["svbk"] == 1 and row["vbk"] == 0 and row["ie"] == 7,
                f"{mode} route did not restore mapper/interrupt state")
        require(row["ffba"] == 2 and row["ffc1"] == 1,
                f"{mode} route changed Crystal/gameplay identity")
    require(not result["events"], f"{mode} route emitted violation events")
    return {
        "mode": mode,
        "frames": ROUTE_DIAGNOSTIC_FRAMES,
        "route_hits": {
            name: hits[name]
            for name in (
                "resume_state", "runtime_entry", "runtime_native_restore",
                "runtime_nonstage_gate", "runtime_nonstage_ret", "rst_return",
                "dirty_branch", "atomic_entry", "copy_continue",
            )
        },
        "frame_pcs": [f"{row['ff99']:02X}:{row['pc']:04X}" for row in frames],
    }


def require_deterministic(
    first: dict[str, Any], second: dict[str, Any]
) -> None:
    require(first["text"] == second["text"],
            "duplicate containment reports are not byte-deterministic")


def stop_owned_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_containment_probe(
    candidate: Path,
    state: Path,
    output_dir: Path,
    name: str,
    timeout: float,
    *,
    frames: int = FRAMES,
    route_diagnostic: bool = False,
    route_mode: str = "candidate",
) -> tuple[dict[str, Any], Path, Path]:
    require(route_mode in {"candidate", "control"}, "invalid route mode")
    prefix = output_dir / name
    report = Path(str(prefix) + ".report")
    done = Path(str(prefix) + ".done")
    startup = Path(str(prefix) + ".startup")
    final_state = output_dir / f"{name}-final.ss0"
    runtime = output_dir / f"{name}-runtime"
    log = output_dir / f"{name}.log"
    runtime.mkdir()
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE7_CRYSTAL_OUT": str(prefix),
        "STAGE7_CRYSTAL_STATE_FILE": str(state.resolve()),
        "STAGE7_CRYSTAL_STATE_OUT": str(final_state.resolve()),
        "STAGE7_CRYSTAL_FRAMES": str(frames),
        "STAGE7_CRYSTAL_EXPECTED_SCENE": str(SCENE),
        "STAGE7_CRYSTAL_RESUME_PC": "43DA",
        "STAGE7_CRYSTAL_RESUME_BANK": "3",
        "STAGE7_CRYSTAL_ROUTE_DIAGNOSTIC": (
            "1" if route_diagnostic else "0"
        ),
        "STAGE7_CRYSTAL_ROUTE_MODE": route_mode,
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    command = [
        str(LAUNCHER), "--fastforward",
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        str(candidate), "--script", str(PROBE), "-l", "0",
    ]
    with log.open("wb") as stream:
        process = subprocess.Popen(
            command, cwd=output_dir, env=environment,
            stdout=stream, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if report.is_file() and done.is_file():
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            stop_owned_process(process)
    if not report.is_file() or not done.is_file():
        startup_evidence = (
            startup.read_text() if startup.is_file()
            else "<startup marker missing: Lua source did not enter>"
        )
        raise AssertionError(
            f"containment probe did not finish; see {log}; "
            f"startup evidence:\n{startup_evidence}"
        )
    require(done.read_text() == "ok\n",
            f"containment completion marker is not ok; see {report}")
    startup_text = startup.read_text()
    if route_diagnostic:
        require("instrumentation-armed\n" in startup_text
                and "state-loaded-route-debugger\n" in startup_text,
                "route diagnostic lifecycle evidence is incomplete")
    else:
        require("instrumentation-armed\n" not in startup_text
                and "breakpoint " not in startup_text
                and "watchpoint " not in startup_text
                and "state-loaded-zero-debugger\n" in startup_text,
                "production containment installed debugger instrumentation")
    require(startup_text.endswith("finished ok\n"),
            "containment startup lifecycle did not finish cleanly")
    require(final_state.is_file(), "containment probe did not save final state")
    return parse_probe_report(report), final_state, log


def validate_crystal_final_state(
    state: bytes,
    runtime: dict[str, bytes],
    *,
    label: str,
    expected_scratch: tuple[int, int, int],
) -> tuple[bytes, dict[str, Any]]:
    """Validate the stable state serialized after Crystal frame 720."""

    boundary = validate_state_boundary(
        state, runtime, label=label, require_resume=False,
    )
    memory_flags = int.from_bytes(
        state[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little"
    )
    require(not memory_flags & MEMORY_FLAG_HDMA_ACTIVE,
            f"{label}: serialized HDMA-active flag is set")
    observed = (
        hram_byte(state, 0xFFA5), hram_byte(state, 0xFFE0),
        hram_byte(state, 0xFFE4),
    )
    require(observed == expected_scratch,
            f"{label}: FFA5/FFE0/FFE4 changed from normalized input")
    boundary["boundary"] = (
        "stable serialization requested at the 720th Crystal frame callback; "
        "CPU PC/current native ROM bank and IME phase are observational"
    )
    boundary["interrupt_contract"] = (
        "serialized HDMA-active is clear; IME may legitimately be clear or "
        "set because mGBA frame callbacks are not a fixed CPU-PC rendezvous"
    )
    return state, boundary


def validate_crystal_final_state_path(
    path: Path,
    runtime: dict[str, bytes],
    *,
    label: str,
    expected_scratch: tuple[int, int, int],
) -> tuple[bytes, dict[str, Any]]:
    return validate_crystal_final_state(
        serialized_state(path), runtime, label=label,
        expected_scratch=expected_scratch,
    )


MGBA_NONDETERMINISTIC_STATE_RANGES = (
    (0x00AC, 0x00B0, "audio capRight"),
    (0x01E0, 0x0260, "rendered audio samples"),
)


def machine_state_projection(state: bytes) -> bytes:
    """Mask only the documented host-audio serialization variability."""

    require(len(state) == GB_STATE_SIZE, "machine projection state size changed")
    projection = bytearray(state)
    for first, last, _label in MGBA_NONDETERMINISTIC_STATE_RANGES:
        projection[first:last] = bytes(last - first)
    return bytes(projection)


def require_machine_projection_equal(first: bytes, second: bytes) -> list[int]:
    differences = [
        index for index, values in enumerate(zip(first, second))
        if values[0] != values[1]
    ]
    allowed = {
        index
        for first_index, last_index, _label
        in MGBA_NONDETERMINISTIC_STATE_RANGES
        for index in range(first_index, last_index)
    }
    require(set(differences) <= allowed,
            "duplicate final states differ outside documented mGBA audio fields")
    require(machine_state_projection(first) == machine_state_projection(second),
            "duplicate full-machine projections are not deterministic")
    return differences


def require_machine_advanced(initial: bytes, final: bytes) -> None:
    """Reject a no-op/stalled containment outcome."""

    require(machine_state_projection(initial) != machine_state_projection(final),
            "Crystal machine state did not advance beyond normalized input")


def ghost_subprocess_environment(
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    """Remove the entire inherited ghost-probe namespace before composition."""

    environment = dict(os.environ if source is None else source)
    for name in tuple(environment):
        if name.startswith(GHOST_AMBIENT_ENV_PREFIX):
            environment.pop(name, None)
    return environment


def run_ghost_gate(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    receipt = output_dir / "crystal-ghost-receipt.json"
    debug = output_dir / "crystal-ghost-debug"
    log = output_dir / "crystal-ghost.log"
    debug.mkdir()
    command = [
        sys.executable, str(GHOST_VERIFIER), str(args.candidate.resolve()),
        "--states", str(args.crystal_state.resolve().parent),
        "--stage3-state", str(args.stage3_state.resolve()),
        "--frames", str(FRAMES), "--timeout", str(args.timeout),
        "--output", str(receipt), "--debug-dir", str(debug),
    ]
    with log.open("wb") as stream:
        result = subprocess.run(
            command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
            timeout=max(args.timeout * 8, 120), check=False,
            env=ghost_subprocess_environment(),
        )
    require(result.returncode == 0,
            f"Crystal ghost gate failed with {result.returncode}; see {log}")
    require(receipt.is_file(), "Crystal ghost gate emitted no receipt")
    data = json.loads(receipt.read_text())
    require(data.get("schema") == "penta-crystal-ghost-v1"
            and data.get("status") == "pass", "Crystal ghost receipt is not PASS")
    require(data.get("rom_sha256") == EXPECTED_CANDIDATE_SHA256,
            "Crystal ghost receipt is bound to the wrong ROM")
    require(data.get("crystal_state_sha256") == EXPECTED_CRYSTAL_STATE_SHA256,
            "Crystal ghost receipt is bound to the wrong source state")
    require(data.get("frames") == FRAMES
            and data.get("deterministic_replay") is True,
            "Crystal ghost duplicate cadence gate is incomplete")
    require(data.get("scene") == "0E", "Crystal ghost scene is not $0E")
    visibility = data.get("body_sprite_visibility", {})
    require(visibility.get("minimum") == 0
            and visibility.get("maximum", 0) >= 12
            and visibility.get("longest_settled_blank_frames", 99) <= 1,
            "Crystal ghost material/cadence contract failed")
    require(data.get("riff_isolation") == "pass"
            and data.get("stage3_isolation") == "pass",
            "Crystal ghost isolation controls failed")
    attempts = data.get("determinism_attempts", [])
    require(attempts and attempts[-1].get("semantic_match") is True,
            "Crystal ghost replay did not reach semantic determinism")
    return {
        "path": str(receipt.relative_to(ROOT)),
        "sha256": digest_file(receipt),
        "scene": data["scene"],
        "frames": data["frames"],
        "obj_slots": data.get("obj_slots"),
        "material_bytes": data.get("material_bytes"),
        "body_sprite_visibility": visibility,
        "determinism_attempts": attempts,
        "riff_isolation": data["riff_isolation"],
        "stage3_isolation": data["stage3_isolation"],
        "inherited_ghost_environment": {
            "removed_prefix": GHOST_AMBIENT_ENV_PREFIX,
            "controlled_keys": list(GHOST_CONTROLLED_ENV_KEYS),
            "known_optional_keys": list(GHOST_OPTIONAL_ENV_KEYS),
        },
    }


def synthetic_probe_result() -> dict[str, Any]:
    header = {
        "schema": "penta-stage7-crystal-containment-probe-v2",
        "status": "ok",
        "frames": str(FRAMES),
        "scene_samples": str(FRAMES),
        "scene_unreadable": "0",
        "wrong_scene": "0",
        "ff55_nonidle": "0",
        "boundary_bank22": "0",
        "ffe4_nonzero": "0",
        "final_saved": "1",
        "drain_frames": "0",
        "safe_finish": "0",
        "max_drain_frames": "120",
        "route_diagnostic": "0",
        "route_mode": "candidate",
        "production_debugger_instrumentation": "0",
        "state_save_wait_frames": "2",
        "state_save_stable_frames": "2",
    }
    hits = {name: 0 for name in EXPECTED_HIT_NAMES}
    frames = [
        {
            "frame": frame, "scene": SCENE, "pc": 0x43DA,
            "ff99": 1, "svbk": 1, "vbk": 0, "ff55": 0xFF,
            "ffa5": 0x9C, "ffe0": 0, "ie": 7, "lcdc": 0x8B,
            "ffba": 2, "ffc1": 1, "ffe4": 0,
        }
        for frame in range(1, FRAMES + 1)
    ]
    return {"header": header, "hits": hits, "frames": frames,
            "events": [], "text": "synthetic-exact"}


def synthetic_route_result(mode: str) -> dict[str, Any]:
    require(mode in {"candidate", "control"}, "invalid synthetic route mode")
    header = {
        "schema": "penta-stage7-crystal-containment-probe-v2",
        "status": "ok",
        "frames": str(ROUTE_DIAGNOSTIC_FRAMES),
        "scene_samples": str(ROUTE_DIAGNOSTIC_FRAMES),
        "scene_unreadable": "0",
        "wrong_scene": "0",
        "ff55_nonidle": "0",
        "boundary_bank22": "0",
        "final_saved": "1",
        "drain_frames": "0",
        "safe_finish": "0",
        "max_drain_frames": "120",
        "route_diagnostic": "1",
        "route_mode": mode,
        "production_debugger_instrumentation": "9",
    }
    hits = {name: 0 for name in EXPECTED_HIT_NAMES}
    for name in (
        "resume_state", "runtime_entry", "rst_return", "dirty_branch",
        "atomic_entry", "copy_continue",
    ):
        hits[name] = 1
    if mode == "candidate":
        hits["runtime_nonstage_gate"] = 1
        hits["runtime_nonstage_ret"] = 1
    else:
        hits["runtime_native_restore"] = 1
    frames = [
        {
            "frame": frame, "scene": SCENE, "pc": 0x43DA,
            "ff99": 1, "svbk": 1, "vbk": 0, "ff55": 0xFF,
            "ffa5": 0x9C, "ffe0": 0, "ie": 7, "lcdc": 0x8B,
            "ffba": 2, "ffc1": 1, "ffe4": 0,
        }
        for frame in range(1, ROUTE_DIAGNOSTIC_FRAMES + 1)
    ]
    return {
        "header": header, "hits": hits, "frames": frames,
        "events": [], "text": f"synthetic-route-{mode}",
    }


def mutation_controls(
    source_state: bytes,
    normalized_state: bytes,
    runtime: dict[str, bytes],
    identity: dict[str, dict[str, str]],
    static_receipt: Path,
    equivalence_receipt: Path,
) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    ambient = {
        name: "1"
        for name in GHOST_CONTROLLED_ENV_KEYS + GHOST_OPTIONAL_ENV_KEYS
    }
    ambient.update({
        "KEEP_ME": "1",
        "CRYSTAL_FLICKER_FUTURE_OPT_IN": "1",
    })
    scrubbed_environment = ghost_subprocess_environment(ambient)
    require(scrubbed_environment == {"KEEP_ME": "1"},
            "composed ghost environment namespace was not scrubbed exactly")
    controls["ghost_ambient_namespace_scrubbed"] = True
    baseline = synthetic_probe_result()
    validate_probe_result(baseline)
    controls["exact_control_passes"] = True

    route_candidate = synthetic_route_result("candidate")
    route_control = synthetic_route_result("control")
    validate_route_diagnostic(route_candidate, mode="candidate")
    validate_route_diagnostic(route_control, mode="control")
    controls["route_discriminator_controls_pass"] = True

    def route_rejected(
        name: str, mode: str, mutate: Callable[[dict[str, Any]], None]
    ) -> None:
        source = route_candidate if mode == "candidate" else route_control
        mutant = copy.deepcopy(source)
        mutate(mutant)
        try:
            validate_route_diagnostic(mutant, mode=mode)
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(f"route negative control escaped: {name}")

    route_rejected(
        "candidate_tail_return_missing_rejected", "candidate",
        lambda row: row["hits"].__setitem__("runtime_nonstage_ret", 0),
    )
    route_rejected(
        "candidate_post_tail_missing_rejected", "candidate",
        lambda row: row["hits"].__setitem__("rst_return", 0),
    )
    route_rejected(
        "control_candidate_tail_hit_rejected", "control",
        lambda row: row["hits"].__setitem__("runtime_nonstage_gate", 1),
    )
    route_rejected(
        "route_one_frame_stall_rejected", "candidate",
        lambda row: row["frames"].pop(),
    )

    def rejected(name: str, mutate: Callable[[dict[str, Any]], None]) -> None:
        mutant = copy.deepcopy(baseline)
        mutate(mutant)
        try:
            validate_probe_result(mutant)
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(f"negative control escaped: {name}")

    rejected("uninstrumented_hit_placeholder_rejected",
             lambda row: row["hits"].__setitem__("helper_entry", 1))
    rejected("wrong_scene_rejected",
             lambda row: row["frames"][119].__setitem__("scene", 0x08))
    rejected("nonidle_ff55_rejected",
             lambda row: row["frames"][233].__setitem__("ff55", 0x80))
    rejected("bank22_boundary_rejected",
             lambda row: row["frames"][311].__setitem__("ff99", HELPER_BANK))
    rejected("unrestored_svbk_rejected",
             lambda row: row["frames"][401].__setitem__("svbk", 3))
    rejected("production_debugger_hook_rejected",
             lambda row: row["header"].__setitem__(
                 "production_debugger_instrumentation", "1"))
    rejected("ffe4_boundary_rejected",
             lambda row: row["frames"][515].__setitem__("ffe4", 1))
    rejected("missing_frame_rejected", lambda row: row["frames"].pop())
    rejected("out_of_order_frame_rejected",
             lambda row: row["frames"][10].__setitem__("frame", 12))
    rejected("unsafe_finish_rejected",
             lambda row: row["header"].__setitem__(
                 "state_save_stable_frames", "1"))
    rejected("unexpected_postframe_drain_rejected",
             lambda row: row["header"].__setitem__("drain_frames", "121"))

    final_scratch = (
        hram_byte(normalized_state, 0xFFA5),
        hram_byte(normalized_state, 0xFFE0),
        hram_byte(normalized_state, 0xFFE4),
    )
    validate_crystal_final_state(
        normalized_state, runtime, label="synthetic Crystal final",
        expected_scratch=final_scratch,
    )
    controls["crystal_final_control_passes"] = True

    def final_state_rejected(
        name: str, mutate: Callable[[bytearray], None]
    ) -> None:
        mutant = bytearray(normalized_state)
        mutate(mutant)
        try:
            validate_crystal_final_state(
                bytes(mutant), runtime, label=f"mutant {name}",
                expected_scratch=final_scratch,
            )
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(
                f"final-state negative control escaped: {name}"
            )

    final_state_rejected(
        "final_crystal_ffe4_mutation_rejected",
        lambda state: state.__setitem__(
            HRAM + 0xFFE4 - 0xFF80, final_scratch[2] ^ 1
        ),
    )
    final_state_rejected(
        "final_crystal_ffa5_mutation_rejected",
        lambda state: state.__setitem__(
            HRAM + 0xFFA5 - 0xFF80, final_scratch[0] ^ 1
        ),
    )
    final_state_rejected(
        "final_crystal_ffe0_mutation_rejected",
        lambda state: state.__setitem__(
            HRAM + 0xFFE0 - 0xFF80, final_scratch[1] ^ 1
        ),
    )
    final_state_rejected(
        "final_crystal_hdma_state_flip_rejected",
        lambda state: state.__setitem__(
            MEMORY_FLAGS, state[MEMORY_FLAGS] ^ MEMORY_FLAG_HDMA_ACTIVE
        ),
    )
    final_state_rejected(
        "final_crystal_bank22_shadow_rejected",
        lambda state: state.__setitem__(
            HRAM + 0xFF99 - 0xFF80, HELPER_BANK
        ),
    )
    final_state_rejected(
        "final_crystal_bank22_mapper_rejected",
        lambda state: state.__setitem__(
            MEMORY_CURRENT_ROM_BANK, HELPER_BANK
        ),
    )
    final_state_rejected(
        "final_crystal_scene_rejected",
        lambda state: state.__setitem__(WRAM1 + 0x880, SCENE ^ 1),
    )
    final_state_rejected(
        "final_crystal_ff55_rejected",
        lambda state: state.__setitem__(IO + 0x55, 0x80),
    )
    final_state_rejected(
        "final_crystal_vbk_rejected",
        lambda state: state.__setitem__(IO + 0x4F, 1),
    )
    final_state_rejected(
        "final_crystal_svbk_rejected",
        lambda state: state.__setitem__(IO + 0x70, 3),
    )
    final_state_rejected(
        "final_crystal_ie_rejected",
        lambda state: state.__setitem__(IE, 0),
    )
    final_state_rejected(
        "final_crystal_runtime_rejected",
        lambda state: state.__setitem__(
            WRAM1 + 0xA60, state[WRAM1 + 0xA60] ^ 1
        ),
    )

    pc_phase = bytearray(normalized_state)
    pc_phase[CPU_PC] ^= 1
    validate_crystal_final_state(
        bytes(pc_phase), runtime, label="allowed final PC phase",
        expected_scratch=final_scratch,
    )
    controls["final_pc_phase_is_observational"] = True
    ime_phase = bytearray(normalized_state)
    ime_phase[MEMORY_FLAGS] ^= MEMORY_FLAG_IME
    validate_crystal_final_state(
        bytes(ime_phase), runtime, label="allowed final IME phase",
        expected_scratch=final_scratch,
    )
    controls["final_ime_phase_is_observational"] = True

    require_machine_projection_equal(normalized_state, normalized_state)
    controls["machine_projection_exact_control_passes"] = True
    advanced_control = bytearray(normalized_state)
    advanced_control[0x0300] ^= 1
    require_machine_advanced(normalized_state, bytes(advanced_control))
    controls["machine_advance_control_passes"] = True
    try:
        require_machine_advanced(normalized_state, normalized_state)
    except AssertionError:
        controls["stalled_machine_outcome_rejected"] = True
    else:
        raise AssertionError("stalled machine outcome escaped")
    audio_mutant = bytearray(normalized_state)
    audio_mutant[MGBA_NONDETERMINISTIC_STATE_RANGES[0][0]] ^= 1
    require_machine_projection_equal(normalized_state, bytes(audio_mutant))
    controls["documented_audio_difference_allowed"] = True
    samples_mutant = bytearray(normalized_state)
    samples_mutant[MGBA_NONDETERMINISTIC_STATE_RANGES[1][0]] ^= 1
    require_machine_projection_equal(normalized_state, bytes(samples_mutant))
    controls["documented_rendered_samples_difference_allowed"] = True
    machine_mutant = bytearray(normalized_state)
    machine_mutant[0x0300] ^= 1
    try:
        require_machine_projection_equal(normalized_state, bytes(machine_mutant))
    except AssertionError:
        controls["machine_difference_outside_audio_rejected"] = True
    else:
        raise AssertionError("out-of-envelope machine mutation escaped")

    unexpected = bytearray(normalized_state)
    unexpected[0x200] ^= 1
    try:
        validate_normalization_delta(source_state, bytes(unexpected))
    except AssertionError:
        controls["unexpected_normalization_mutation_rejected"] = True
    else:
        raise AssertionError("unexpected normalization mutation escaped")

    identity_mutant = copy.deepcopy(identity)
    identity_mutant["candidate"]["sha256"] = "00" * 32
    try:
        validate_identity(identity_mutant)
    except AssertionError:
        controls["candidate_identity_mutation_rejected"] = True
    else:
        raise AssertionError("candidate identity mutation escaped")

    receipt_mutant = json.loads(static_receipt.read_text())
    receipt_mutant["helper"]["trace_labels"]["attr_FF55_store"] = "bank22:$713E"
    # Exercise the same exact semantic check without writing a mutant file.
    try:
        require(receipt_mutant["helper"]["trace_labels"]["attr_FF55_store"]
                == "bank22:$713D", "mutated static DMA site")
    except AssertionError:
        controls["static_dma_site_mutation_rejected"] = True
    else:
        raise AssertionError("static receipt mutation escaped")

    equivalence_mutant = json.loads(equivalence_receipt.read_text())
    equivalence_mutant["equivalence"]["protected_spans"]["bank22_helper"][
        "sha256"
    ] = "00" * 32
    try:
        require(
            equivalence_mutant["equivalence"]["protected_spans"][
                "bank22_helper"
            ]["sha256"]
            == "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003",
            "mutated r265 helper equivalence",
        )
    except AssertionError:
        controls["r265_helper_equivalence_mutation_rejected"] = True
    else:
        raise AssertionError("r265 helper-equivalence mutation escaped")

    replay_mutant = copy.deepcopy(baseline)
    replay_mutant["text"] = "synthetic-mutant"
    try:
        require_deterministic(baseline, replay_mutant)
    except AssertionError:
        controls["duplicate_report_mutation_rejected"] = True
    else:
        raise AssertionError("duplicate report mutation escaped")
    require(all(controls.values()), "one or more mutation controls failed")
    return controls


def offline_audit(
    args: argparse.Namespace,
    normalized_path: Path,
) -> tuple[dict[str, Any], bytes, dict[str, bytes]]:
    require(
        args.riff_state.resolve()
        == args.crystal_state.resolve().with_name("boss1_riff.ss0"),
        "--riff-state must be the sibling consumed by the ghost verifier",
    )
    identity = input_identity(args)
    validate_identity(identity)
    static = validate_static_receipt(args.static_receipt.resolve())
    equivalence = validate_r265_equivalence(
        args.helper_equivalence_receipt.resolve(),
        args.r265_build_receipt.resolve(),
        args.r265_menu_receipt.resolve(),
    )
    probe = validate_probe_source()
    source, normalized, runtime, normalization = prepare_normalized_state(
        args, normalized_path,
    )
    _control_state, _control_runtime, control_normalization = (
        prepare_control_state(
            args, normalized_path.with_name("normalized-r264-control.ss0")
        )
    )
    controls = mutation_controls(
        source, normalized, runtime, identity, args.static_receipt.resolve(),
        args.helper_equivalence_receipt.resolve(),
    )
    return {
        "identity": identity,
        "static_contract": static,
        "r265_helper_equivalence_static_context": equivalence,
        "probe_contract": probe,
        "normalized_state": normalization,
        "normalized_r264_control": control_normalization,
        "mutation_controls": controls,
    }, normalized, runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    parser.add_argument("--r264-control", type=Path, default=R264_CONTROL)
    parser.add_argument("--static-receipt", type=Path, default=STATIC_RECEIPT)
    parser.add_argument(
        "--helper-equivalence-receipt", type=Path,
        default=HELPER_EQUIVALENCE_RECEIPT,
    )
    parser.add_argument(
        "--r265-build-receipt", type=Path, default=R265_BUILD_RECEIPT,
    )
    parser.add_argument(
        "--r265-menu-receipt", type=Path, default=R265_MENU_RECEIPT,
    )
    parser.add_argument("--crystal-state", type=Path, default=CRYSTAL_STATE)
    parser.add_argument("--riff-state", type=Path, default=RIFF_STATE)
    parser.add_argument("--stage3-state", type=Path, default=STAGE3_STATE)
    parser.add_argument(
        "--output-dir", type=Path,
        help="fresh child directory under repository tmp/ or /mnt/data/tmp/",
    )
    parser.add_argument("--timeout", type=float, default=90.0,
                        help="timeout in seconds for each emulator probe")
    parser.add_argument(
        "--offline-controls-only", action="store_true",
        help="run static/state/mutation controls only; never launch an emulator",
    )
    parser.add_argument(
        "--route-discriminator-only", action="store_true",
        help=(
            "forensic/non-promotable only: run the breakpoint-based exact "
            "r264-control versus candidate DAA3/DAE9 route diagnostic"
        ),
    )
    args = parser.parse_args()
    require(args.timeout > 0, "--timeout must be positive")
    require(not (args.offline_controls_only and args.route_discriminator_only),
            "choose only one diagnostic mode")
    if args.offline_controls_only:
        require(args.output_dir is None,
                "--offline-controls-only does not accept --output-dir")
    else:
        require(args.output_dir is not None,
                "live containment requires --output-dir")
    return args


def run_route_discriminator(
    args: argparse.Namespace,
    output: Path,
    audit: dict[str, Any],
) -> int:
    """Run the retired aa4/r265 breakpoint routes and retain evidence."""

    identity_before = audit["identity"]
    attempts: dict[str, dict[str, Any]] = {}
    controls = (
        (
            "control", args.r264_control.resolve(),
            output / "normalized-r264-control.ss0",
        ),
        (
            "candidate", args.candidate.resolve(),
            output / "normalized-crystal.ss0",
        ),
    )
    for mode, rom, state in controls:
        try:
            result, final_state, log = run_containment_probe(
                rom, state, output, f"route-{mode}", args.timeout,
                frames=ROUTE_DIAGNOSTIC_FRAMES,
                route_diagnostic=True, route_mode=mode,
            )
            summary = validate_route_diagnostic(result, mode=mode)
            attempts[mode] = {
                "status": "PASS",
                "rom": str(rom.relative_to(ROOT)),
                "rom_sha256": digest_file(rom),
                "normalized_state": str(state.relative_to(ROOT)),
                "normalized_state_sha256": digest_file(state),
                "summary": summary,
                "report": str(
                    (output / f"route-{mode}.report").relative_to(ROOT)
                ),
                "report_sha256": digest_file(
                    output / f"route-{mode}.report"
                ),
                "startup_sha256": digest_file(
                    output / f"route-{mode}.startup"
                ),
                "final_state_sha256": digest_file(final_state),
                "log": str(log.relative_to(ROOT)),
            }
        except Exception as error:  # fail closed, but preserve discriminator data
            startup = output / f"route-{mode}.startup"
            attempts[mode] = {
                "status": "FAIL",
                "rom": str(rom.relative_to(ROOT)),
                "rom_sha256": digest_file(rom),
                "normalized_state": str(state.relative_to(ROOT)),
                "normalized_state_sha256": digest_file(state),
                "error_type": type(error).__name__,
                "error": str(error),
                "startup": (
                    startup.read_text() if startup.is_file() else "missing"
                ),
                "startup_sha256": (
                    digest_file(startup) if startup.is_file() else None
                ),
            }
            # A failed base control already proves this breakpoint diagnostic
            # is not a valid candidate discriminator. Do not spend a second
            # emulator launch or mislabel the candidate from an invalid test.
            break

    if attempts["control"]["status"] != "PASS":
        status = "BLOCKED_CONTROL_ROUTE_DID_NOT_ADVANCE"
        decision = (
            "The exact pre-Stage7 r264 control failed under the same minimal "
            "instrumentation, so prior candidate timeouts are not admissible "
            "ROM-fault evidence. Replace breakpoint-based containment."
        )
        exit_status = 1
    elif attempts.get("candidate", {}).get("status") != "PASS":
        status = "FAIL_CANDIDATE_ROUTE_DID_NOT_ADVANCE"
        decision = (
            "Exact r264 advanced through DAA3/$3493/$42B1/$DA13/$42B8, but "
            "the candidate did not advance through DAE9/DAF5 and the same "
            "post-tail chain. The redirected router fails Crystal containment."
        )
        exit_status = 1
    else:
        status = "PASS_ROUTES_ADVANCE"
        decision = (
            "Both exact-ROM routes advance two frames through their expected "
            "restore tail and the same post-tail chain. The old 720-frame "
            "failure was caused by its invalid fixed:$016C completion contract "
            "or excessive instrumentation, not a demonstrated DAE9 stall."
        )
        exit_status = 0

    identity_after = input_identity(args)
    require(identity_before == identity_after,
            "route discriminator inputs/tools changed during execution")
    receipt = {
        "schema": "penta-stage7-crystal-route-discriminator-v1",
        "status": status,
        "emulator_run": True,
        "promotable": False,
        "frames_per_route": ROUTE_DIAGNOSTIC_FRAMES,
        "execution_order": ["r264_control", "stage7_candidate"],
        "identity_before": identity_before,
        "identity_after": identity_after,
        "normalized_candidate": audit["normalized_state"],
        "normalized_r264_control": audit["normalized_r264_control"],
        "attempts": attempts,
        "decision": decision,
    }
    receipt_path = output / "route-discriminator-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"{status}: {decision}")
    print(f"receipt: {receipt_path}")
    return exit_status


def main() -> int:
    args = parse_args()
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    if args.offline_controls_only:
        with tempfile.TemporaryDirectory(
            prefix="stage7-crystal-containment-offline-", dir=scratch,
        ) as temporary:
            audit, _, _ = offline_audit(
                args, Path(temporary) / "normalized-crystal.ss0",
            )
        print(json.dumps({
            "schema": "penta-stage7-crystal-containment-offline-v2",
            "status": "PASS",
            "emulator_run": False,
            **audit,
        }, indent=2))
        return 0

    output = args.output_dir.resolve()
    allowed = [ROOT / "tmp", Path("/mnt/data/tmp")]
    require(any(
        root.exists() and output != root.resolve()
        and output.is_relative_to(root.resolve()) for root in allowed
    ), "--output-dir must be below repository tmp/ or /mnt/data/tmp/")
    require(not output.exists(), "--output-dir must be fresh/nonexistent")
    output.mkdir(parents=True)
    audit, normalized_input, runtime = offline_audit(
        args, output / "normalized-crystal.ss0",
    )
    if args.route_discriminator_only:
        return run_route_discriminator(args, output, audit)
    identity_before = audit["identity"]

    first, first_state_path, _ = run_containment_probe(
        args.candidate.resolve(), output / "normalized-crystal.ss0",
        output, "containment-a", args.timeout,
    )
    second, second_state_path, _ = run_containment_probe(
        args.candidate.resolve(), output / "normalized-crystal.ss0",
        output, "containment-b", args.timeout,
    )
    first_summary = validate_probe_result(first)
    second_summary = validate_probe_result(second)
    require_deterministic(first, second)
    final_scratch = (
        hram_byte(normalized_input, 0xFFA5),
        hram_byte(normalized_input, 0xFFE0),
        hram_byte(normalized_input, 0xFFE4),
    )
    first_state, first_boundary = validate_crystal_final_state_path(
        first_state_path, runtime, label="containment A final",
        expected_scratch=final_scratch,
    )
    second_state, second_boundary = validate_crystal_final_state_path(
        second_state_path, runtime, label="containment B final",
        expected_scratch=final_scratch,
    )
    raw_machine_differences = require_machine_projection_equal(
        first_state, second_state,
    )
    first_projection = machine_state_projection(first_state)
    second_projection = machine_state_projection(second_state)
    require(first_projection == second_projection,
            "duplicate full-machine projections are not deterministic")
    require_machine_advanced(normalized_input, first_state)
    private_bank_observation = {
        "bank2_D000_D17F_equal_input": (
            first_state[WRAM2:WRAM2 + 0x180]
            == normalized_input[WRAM2:WRAM2 + 0x180]
            and second_state[WRAM2:WRAM2 + 0x180]
            == normalized_input[WRAM2:WRAM2 + 0x180]
        ),
        "bank3_D000_D2FF_equal_input": (
            first_state[WRAM3:WRAM3 + 0x300]
            == normalized_input[WRAM3:WRAM3 + 0x300]
            and second_state[WRAM3:WRAM3 + 0x300]
            == normalized_input[WRAM3:WRAM3 + 0x300]
        ),
        "policy": (
            "observational only: these physical banks are shared by native "
            "boss scenes. This zero-debugger gate checks recurrent and final "
            "mapper boundaries only; it does not attribute transient writes. "
            "The frozen static topology is recorded as context, not promoted "
            "to dynamic helper-execution evidence."
        ),
    }

    ghost = run_ghost_gate(args, output)
    identity_after = input_identity(args)
    require(identity_before == identity_after,
            "candidate, fixtures, or verification tools changed during gate")
    receipt = {
        "schema": "penta-stage7-crystal-containment-v2",
        "status": "PASS",
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "frames_per_containment_run": FRAMES,
        "scene": "0E",
        "identity_before": identity_before,
        "identity_after": identity_after,
        "static_contract": audit["static_contract"],
        "r265_helper_equivalence_static_context": (
            audit["r265_helper_equivalence_static_context"]
        ),
        "probe_contract": audit["probe_contract"],
        "normalized_state": audit["normalized_state"],
        "normalized_r264_control": audit["normalized_r264_control"],
        "mutation_controls": audit["mutation_controls"],
        "containment": {
            "duplicate_reports_byte_exact": True,
            "duplicate_full_machine_projection_exact": True,
            "run_a": first_summary,
            "run_b": second_summary,
            "final_a": first_boundary,
            "final_b": second_boundary,
            "final_state_sha256": [
                digest_file(first_state_path), digest_file(second_state_path),
            ],
            "full_machine_projection_sha256": digest_bytes(first_projection),
            "raw_machine_state_differences": {
                "count": len(raw_machine_differences),
                "offsets": [f"0x{index:04X}" for index in raw_machine_differences],
                "allowed_ranges": [
                    {
                        "first": f"0x{first_index:04X}",
                        "last_exclusive": f"0x{last_index:04X}",
                        "reason": label,
                    }
                    for first_index, last_index, label
                    in MGBA_NONDETERMINISTIC_STATE_RANGES
                ],
            },
            "private_bank_input_parity": private_bank_observation,
            "stage7_ownership": (
                "The frozen b724 topology requires D880=$08 before any bank22 "
                "Stage-7 ownership path. As static context only, that does not "
                "prove transient helper absence here. All 720 recurrent "
                "boundaries remain "
                "Crystal D880=$0E with FF55 idle and restored mapper state, and "
                "duplicate full-machine outcomes are exact outside documented "
                "host-audio fields. This is boundary/outcome containment, not "
                "a transient write-site trace: debugger hooks demonstrably "
                "stall the canonical Crystal fixture."
            ),
        },
        "crystal_ghost_gate": ghost,
        "covered": [
            "candidate-owned C600/DA60/DB80/DF0D resident before and after play",
            "720 exact frame-boundary samples in scene $0E per duplicate run",
            "zero production debugger breakpoints and write watchpoints",
            "static scene-gate topology plus deterministic full-machine outcome",
            "FF55 idle and restored VBK/SVBK/IE/FFE4 at every boundary",
            "stable final Crystal state with HDMA inactive and input-exact FFA5/FFE0/FFE4",
            "duplicate serialized machine equality outside documented mGBA audio fields",
            "Crystal material slots, native ghost cadence, Riff isolation, Stage3 isolation",
        ],
        "not_covered": [
            "Stage-7 gameplay visual correctness or patrol speed",
            "menu round trips",
            "generic shared SVBK2/3 writes by native non-bank22 boss code",
            "transient Stage-7 helper execution or FFE4 values between callbacks",
            "transient between-callback write-site attribution",
            "per-callback/final IME phase (mGBA frame callbacks are not a fixed CPU-PC rendezvous)",
        ],
        "promotable_by_itself": False,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS: frozen Stage-7 r265 is contained from Crystal scene $0E")
    print("  duplicate 720-frame containment reports: byte exact")
    print("  production debugger hooks: zero; 720 scene/hardware boundaries clean")
    print("  candidate runtime bytes: resident before and after deterministic play")
    print("  existing duplicate Crystal ghost cadence/material gate: PASS")
    print(f"  receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
