#!/usr/bin/env python3
"""Replay both safe authenticated scene-$0B captures through native SELECT.

The offline binder authenticates the compatible operator capture, its
SELECT-only candidate-native closed derivative, and the separately archived
incompatible wall capture. This producer changes only mGBA's serialized ROM
identity metadata, runs two sequential replays of each safe capture through
the checked single-flight launcher, and emits rendered and state-trace
evidence. It exposes no emulator override and never writes gameplay, fixture,
or VRAM state.
"""

# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: LAUNCHER is the checked-in guarded
# wrapper. This verifier accepts no caller-supplied emulator executable.

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence
import zlib

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS = Path(__file__).resolve().parent
if str(DIAGNOSTICS) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS))

from normalize_mgba_state_pc import retarget_rom_identity  # noqa: E402
from verify_stage1_spike_palettes import publication_boundary  # noqa: E402
from verify_stage1_scene0b_captured_menu_receipt import (  # noqa: E402
    ContractError,
    LIVE_CHECKS,
    LIVE_SCHEMA,
    archived_incompatible_evidence,
    capture_evidence,
    expected_live_tool_identity,
    gbas_payload,
    load_capture_contract,
    validate_native_capture_provenance,
    validate_live_receipt,
)
from stage1_scene0b_hazard_tile_oracle import (  # noqa: E402
    evaluate_scene0b_hazard_tiles,
    load_contract as load_hazard_tile_contract,
)


SCHEMA = LIVE_SCHEMA
IMPLEMENTATION_STATUS = "IMPLEMENTED_REVIEWED"
LAUNCHER = ROOT / "scripts" / "mgba-qt-singleflight"
SINGLEFLIGHT_IMPLEMENTATION = ROOT / "scripts" / "mgba_singleflight.py"
PROCESS_CHECK = ROOT / "scripts" / "check_emulator_processes.sh"
PROBE = DIAGNOSTICS / "probe_stage1_scene0b_live_menu_roundtrip.lua"
VISUAL_ORACLE_FIXTURE = (
    DIAGNOSTICS / "fixtures" / "stage1_scene0b_visual_oracle.json"
)
RUNTIME_OBSERVATION_FIXTURE = (
    DIAGNOSTICS / "fixtures"
    / "stage1_scene0b_runtime_observation_sites.json"
)
FRAME_LIMIT = 900
CAPTURE_FRAMES = 1
REPAIR_SETTLE_FRAMES = 24
MENU_HOLD_FRAMES = 60
POST_CLOSE_FRAMES = 60
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
STAGE1_BG_PALETTE_OFFSET = 13 * 0x4000 + (0x6800 - 0x4000)
STAGE1_HAZARD_BG7_OFFSET = 13 * 0x4000 + (0x68C8 - 0x4000)
STAGE1_LOW_TILE_GFX_OFFSET = 0x1D000
STAGE1_HIGH_TILE_GFX_OFFSET = 0x1F000
GBAS_WRAM_OFFSET = 0x4400
GBAS_SIZE = 0x11800
GBAS_MAGIC = 0x00400003
GBAS_MODEL_OFFSET = 0x0008
GBAS_TITLE_OFFSET = 0x0010
GBAS_TITLE_SIZE = 16
GBAS_BOOT_REGISTER_OFFSET = 0x0350
GB_MODEL_CGB = 0x80
ROM_TITLE_OFFSET = 0x0134
CGB_COMPATIBLE_FLAG = 0x80
CGB_ONLY_FLAG = 0xC0
STAGE1_LUT_SHA256 = (
    "487c1443ddec16171cc0f2744b3fbbd013cdcac5e1d7fd8145fe46f277805734"
)
STAGE1_RELEASE_LUT_SHA256 = (
    "3b2d1224bb47c68263ff862f1a1c68d8b20f055fe2fcae0fa1028659d492961a"
)
# r438 changes only the twelve reviewed tooth-tile VRAM-bank bits.  The low
# palette bits remain byte-identical to the release semantic table, while the
# live replay independently verifies the selected bank's CHR payload.
STAGE1_COMPILED_TOOTH_LUT_SHA256 = (
    "22de0c9f11d8b8f4f050c4e62928e7ea300b1d7483fb9df1d65bb6eec6a0527f"
)
# Exact r343 Stage-1 art contract. Only free-tip tiles 6B/7B differ from the
# inherited r292 image: pixels outside their reviewed diagonal are neutralized
# so BG5 cannot paint detached yellow spill. The digest prevents a candidate
# from teaching the verifier an arbitrary expected glyph through its own ROM.
STAGE1_BG_ART_SHA256 = (
    "aaf4f2596e74abc19f75cf094b432c5f1c504a6e34f7cf2622403f86fe562d95"
)
STAGE1_HAZARD_BANK1_ART_SHA256 = (
    "1fe86832f5508392a809a58e8d10e566f2fcafff553b07df914e614713dc7e4f"
)
STAGE1_HAZARD_PHASE_PAYLOAD_SHA256 = (
    "ca0e91b5df9c9ceceabd1a53d845efcc6562f8b4dc88fd3d705be53d1975e2b2"
)
STAGE1_BG_CRAM_SHA256 = (
    "2df58b72d35dbcd9de2a0144ae721ce248db1f73b0baa6f5eb29a755bb8c4952"
)
RUNTIME_ORACLE_BYTES = 0x1E40
FINAL_BG_CHR_BYTES = 0x4000
PLANE_DUMP_SIZE = 0x1340
STARTUP_TIMEOUT_SECONDS = 8.0
READY_TIMEOUT_SECONDS = 5.0
CORE_TIMEOUT_SECONDS = 8.0
TEARDOWN_POLICY = {
    "probe_action": "stop-core-after-token-bound-receipts",
    "launcher_action": "terminate-exact-child-after-done-marker",
    "acceptance": (
        "natural-zero-or-verifier-owned-signal-after-token-bound-"
        "trace-report-done-validation"
    ),
}
SCREEN_WIDTH = 160
SCREEN_HEIGHT = 144
PLAYFIELD_HEIGHT = 112
MENU_WINDOW_TOP = 96
SCREENSHOT_RE = re.compile(
    r"\.frame(?P<sample>\d{4})\.(?P<phase>[a-z_]+)\.png\Z"
)
TRACE_FIELDS = (
    "sample", "frame", "phase", "scene", "room", "active", "menu",
    "lcdc", "scx", "scy", "attr_mismatches", "semantic_attr_mismatches",
    "immutable_tile_mismatches", "tile_publication_mismatches",
    "tile_phase_mismatches", "tile_plane_mismatches",
    "tile_source_mismatches", "tile_art_mismatches",
    "bg_cram_mismatches", "lut_mismatches",
    "startup_token",
)
CACHE_AUDIT_FIELDS = (
    "event", "kind", "sample", "frame", "phase", "svbk", "ffb7",
    "ffba", "scene", "room", "active", "menu", "ff01", "scy", "dc0b",
    "dc00", "dc02", "c21b", "c2b8", "df02", "df0d", "df4f",
    "df51", "df53", "df54", "df55", "df56", "df57", "df58", "df59",
    "dad7_7", "dad7_8", "dad7_9",
    "c624", "c627", "c630", "c633", "ff99", "lcdc",
    "write_address", "old_value", "new_value", "pc",
)
CACHE_AUDIT_KINDS = frozenset({
    "observers-ready", "frame", "epochGate13", "epochGate16",
    "installer13", "installer16", "epochPublish13", "epochPublish16",
    "runtimeDAD7", "menuMux6CC5", "menuEffect6CE2",
    "rst18Route001A", "selfhealEntry6CEA", "selfhealRepair6D35",
    "selfhealStart6D4D", "transactionArmed6DCB", "displayFlip6E25",
    "commitEffect6E2A",
    "consumer4100", "compiler4302", "publication4354",
    "postcopy10E2", "hazardDispatch6CCE", "hazardHelper6BA7",
    "hazardFront61B7", "hazardWrite4300", "hazardWrite4500",
    *(f"write{address:04X}" for address in (
        0xDF53, 0xDF54, 0xDF55, 0xDF57, 0xDF58, 0xDF59,
    )),
})
HAZARD_CAPTURE_LABELS = frozenset({
    "candidate-native-closed-after-operator-low-health",
    "operator-low-health-menu-loaded",
})


class LiveError(RuntimeError):
    """Live evidence is missing, malformed, or not release-clean."""


class SingleFlightBusy(LiveError):
    """Another guarded emulator command owns the project slot."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveError(message)


def sha256(path: Path) -> str:
    require(path.is_file(), f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def timed_launch_artifact(
    path: Path, started_at_ns: int, completed_at_ns: int,
) -> dict[str, Any]:
    """Bind a launch-owned artifact to both its bytes and launch window."""
    require(path.is_file(), f"launch artifact is missing: {path}")
    modified_at_ns = path.stat().st_mtime_ns
    require(
        started_at_ns <= modified_at_ns <= completed_at_ns,
        f"launch artifact timestamp is outside this replay: {path}",
    )
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "modified_at_ns": modified_at_ns,
    }


def canonical_stage1_bg_art(rom: bytes) -> bytes:
    """Return the hash-pinned 256-tile Stage-1 bank-zero art preimage."""
    payload = b"".join(
        rom[offset:offset + 16]
        for tile in range(0x100)
        for offset in ((
            STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
            if tile < 0x80
            else STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
        ),)
    )
    require(len(payload) == 0x1000,
            "isolated runtime ROM Stage-1 art source is truncated")
    require(sha256_bytes(payload) == STAGE1_BG_ART_SHA256,
            "isolated runtime ROM lacks the reviewed canonical Stage-1 art")
    return payload


def canonical_stage1_hazard_bank1_art(rom: bytes) -> bytes:
    """Return exact r292 bank-one tooth patterns for IDs 64-69/74-79."""
    payload = rom[0x1D640:0x1D6A0] + rom[0x1D740:0x1D7A0]
    require(len(payload) == 192,
            "isolated runtime ROM bank-one hazard art is truncated")
    require(sha256_bytes(payload) == STAGE1_HAZARD_BANK1_ART_SHA256,
            "isolated runtime ROM lacks canonical bank-one hazard art")
    return payload


def canonical_scene0b_hazard_phase_payload() -> bytes:
    """Serialize four independent objects x four whole 4x12 phases."""
    contract = load_hazard_tile_contract()
    payload = b"".join(
        phase.tiles
        for hazard_object in contract.objects
        for phase in contract.family(hazard_object.family).phases
    )
    require(len(contract.objects) == 4 and len(payload) == 4 * 4 * 4 * 12,
            "exact Scene-$0B hazard phase payload geometry changed")
    require(sha256_bytes(payload) == STAGE1_HAZARD_PHASE_PAYLOAD_SHA256,
            "exact Scene-$0B hazard phase payload identity changed")
    return payload


def runtime_observation_contract(candidate: Path) -> dict[str, Any]:
    """Pin current runtime/publication breakpoints to exact candidate bytes."""
    fixture = json.loads(RUNTIME_OBSERVATION_FIXTURE.read_text())
    require(
        fixture.get("schema")
        == "penta-stage1-scene0b-runtime-observation-sites-v7",
        "wrong scene-$0B runtime-observation fixture schema",
    )
    require(fixture.get("rom_size") == 512 * 1024,
            "scene-$0B observation fixture ROM size changed")
    require(fixture.get("candidate_sha256") == sha256(candidate),
            "scene-$0B observation fixture names another candidate")
    require(fixture.get("runtime_epoch") == {
        "address": 0xDF51,
        "legacy_value": 0xA8,
        "candidate_value": 0xA9,
    }, "scene-$0B runtime epoch contract changed")
    require(fixture.get("resident_runtime") == {
        "address": 0xDAD7,
        "length": 41,
        "captured_legacy_sha256": (
            "9d6f623a4797317c30eb649bbb32ebc5f6bec303239cfd623e99257f187e2d81"
        ),
        "candidate_sha256": (
            "04cdd8d7432477821a21098acfb95b322aef0dff3562e812ac365f0130159aef"
        ),
    }, "scene-$0B resident runtime contract changed")
    require(fixture.get("semantic_key") == "SCY ^ DC02 ^ C21B ^ C2B8",
            "scene-$0B cache semantic key changed")
    require(fixture.get("publication_tags") == {"99": "9800", "9D": "9C00"},
            "scene-$0B physical publication tags changed")
    require(fixture.get("cache_records") == {
        "DF53": ["semantic_key", "phase_key_DC00", "hazard_key"],
        "DF57": ["semantic_key", "phase_key_DC00", "hazard_key"],
    }, "scene-$0B cache record ownership changed")
    expected_names = {
        *(f"runtime_epoch_gate{bank}_{suffix}"
          for bank in (13, 16) for suffix in ("a", "b", "c")),
        "runtime_installer13_entry", "runtime_installer16_entry",
        "runtime_epoch13_publication", "runtime_epoch16_publication",
        "runtime_gateway_DAD7", "current_menu_mux_entry",
        "fixed_rst18_route", "runtime_selfheal_entry",
        "runtime_selfheal_repair", "runtime_selfheal_start",
        "runtime_transaction_armed", "runtime_display_flip_effect",
        "runtime_commit_effect",
        "current_menu_cache_effect", "stage1_split_key_consumer",
        "native_attr_compiler_entry", "native_attr_publication_effect",
        "fixed_postcopy_handoff", "hazard_dispatcher",
        "hazard_geometry_helper", "hazard_geometry_front",
        "hazard_semantic_writer", "hazard_room01_semantic_writer",
    }
    sites = fixture.get("sites")
    require(isinstance(sites, dict) and set(sites) == expected_names,
            "scene-$0B runtime-observation sites changed")
    payload = candidate.read_bytes()
    require(len(payload) == fixture["rom_size"],
            "cache-audit candidate is not exactly 512 KiB")
    require(payload[0x4328:0x432E] == bytes.fromhex("F0 01 3D 67 E0 53"),
            "relocated dirty tag to physical destination decode changed")
    validated: dict[str, Any] = {}
    for name in sorted(expected_names):
        site = sites[name]
        require(set(site) == {
            "bank", "address", "offset", "bytes", "breakpoint",
            "breakpoint_bank", "software_bank_mirror", "kind",
        }, f"runtime-observation site {name} fields changed")
        bank, address, offset = (
            site["bank"], site["address"], site["offset"]
        )
        require(isinstance(bank, int) and 0 <= bank < 32
                and isinstance(address, int)
                and (0 <= address < 0x4000 if bank == 0
                     else 0x4000 <= address < 0x8000),
                f"runtime-observation site {name} location is invalid")
        expected_offset = address if bank == 0 else (
            bank * 0x4000 + address - 0x4000
        )
        require(offset == expected_offset,
                f"runtime-observation site {name} offset is invalid")
        try:
            expected = bytes.fromhex(site["bytes"])
        except (TypeError, ValueError) as error:
            raise LiveError(
                f"runtime-observation site {name} bytes are invalid"
            ) from error
        require(expected and payload[offset:offset + len(expected)] == expected,
                f"candidate does not contain reviewed {name} bytes")
        breakpoint = site["breakpoint"]
        breakpoint_bank = site["breakpoint_bank"]
        if breakpoint_bank is None:
            require(
                (name == "runtime_gateway_DAD7"
                 and breakpoint == fixture["resident_runtime"]["address"])
                or (name == "fixed_rst18_route" and breakpoint == 0x001A),
                    f"runtime-observation site {name} unbanked target changed")
        else:
            require(breakpoint_bank == bank
                    and address <= breakpoint < address + len(expected),
                    f"runtime-observation site {name} breakpoint escapes bytes")
        require(site["kind"] in CACHE_AUDIT_KINDS,
                f"runtime-observation site {name} kind changed")
        mirror = site["software_bank_mirror"]
        require(mirror is None or isinstance(mirror, int) and 0 < mirror < 32,
                f"runtime-observation site {name} mirror is invalid")
        validated[name] = {
            "bank": bank,
            "address": f"{address:04X}",
            "breakpoint": f"{breakpoint:04X}",
            "breakpoint_bank": (
                None if breakpoint_bank is None else f"{breakpoint_bank:02X}"
            ),
            "software_bank_mirror": (
                None if mirror is None else f"{mirror:02X}"
            ),
            "kind": site["kind"],
            "bytes_sha256": sha256_bytes(expected),
        }
    return {
        "fixture": str(RUNTIME_OBSERVATION_FIXTURE.resolve()),
        "fixture_sha256": sha256(RUNTIME_OBSERVATION_FIXTURE),
        "sites": validated,
    }


def scratch_output(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(
        root.exists() and resolved != root and resolved.is_relative_to(root)
        for root in roots
    ), "output must be below repo tmp/ or /mnt/data/tmp/")
    require(not resolved.exists(), f"refusing to reuse output: {resolved}")
    resolved.mkdir(parents=True)
    return resolved


def audit_probe_source(source: str) -> dict[str, Any]:
    """Fail closed if Lua gains state injection or loses route coverage."""
    required = (
        "emu:loadStateFile(STATE_FILE)",
        "The stock edge-input poll is not guaranteed to run every host frame",
        "keys = KEY_SELECT",
        'write_token_marker(".startup")',
        'write_token_marker(".ready")',
        'write_token_marker(".core-ready")',
        'write_token_marker(".config-ready")',
        'write_token_marker(".trace-ready")',
        "local raw_vram = nil",
        "local trace = nil",
        "return emu.memory and emu.memory.vram",
        'boot_fail("vram-domain-unavailable", domain)',
        'boot_fail("runtime-env-invalid", config_error)',
        'boot_fail("trace-open-failed", trace_value)',
        "local KEY_SELECT = 0x04",
        "emu:setKeys(keys)",
        "emu:screenshot(path)",
        "emu:read8(0xD880)",
        "emu:read8(0xFFE4)",
        "emu:read8(0xC600 + index)",
        "capture_baseline()",
        "capture_immutable_source()",
        "reconstruct_current_world_source()",
        "arm_tile_publication_oracle()",
        "publish_tile_publication_oracle()",
        "published_tile_planes[0x8000 + base]",
        'os.getenv("PENTA_SCENE0B_IMMUTABLE_SOURCE")',
        'os.getenv("PENTA_SCENE0B_STAGE1_TABLES")',
        'os.getenv("PENTA_SCENE0B_CANONICAL_BG_ART")',
        'os.getenv("PENTA_SCENE0B_CANONICAL_HAZARD_BANK1_ART")',
        'os.getenv("PENTA_SCENE0B_HAZARD_PHASES")',
        "immutable_source_packed",
        "immutable_source_packed, immutable_stage1_tables,",
        "canonical_bg_art, canonical_hazard_bank1_art, hazard_phase_tiles,",
        "expected_bg_cram,",
        "exact_hazard_tile_mismatches(tiles)",
        'OUT .. ".runtime-oracles.bin"',
        'OUT .. ".chr.bin"',
        "local function read_vbk1(offsets)",
        "values[index] = emu:read8(0x8000 + offset)",
        "local attrs = read_vbk1(offsets)",
        "local bank1_chr = read_vbk1(chr_offsets)",
        "observed_bank1 = read_vbk1(pattern_offsets)",
        "for offset = 0, 0x1FFF do",
        "chr_handle:write(byte_blob(bank0_chr))",
        "chr_handle:write(byte_blob(bank1_chr))",
        "visible_attr_mismatches()",
        "semantic_attr_mismatches()",
        "immutable_tile_mismatches()",
        "bg_cram_mismatches()",
        "emu.memory and emu.memory.cgbBgPalette",
        "dump_physical_planes()",
        'if not dump_physical_planes() then',
        'finish("fail", "final-physical-planes-unreadable")',
        'elseif phase == "repair_settle" then\n    -- This is candidate-rendered output',
        'set_phase("menu_entry")',
        'set_phase("menu_hold")',
        'set_phase("menu_exit")',
        'set_phase("post_close")',
        'finish("ok", "complete")',
        'handle:write("startup_token=" .. STARTUP_TOKEN .. "\\n")',
        'marker:write("startup_token=" .. STARTUP_TOKEN .. "\\n")',
        "lut_mismatches(), STARTUP_TOKEN)",
        'write_completion_marker(status)',
        "emu:stop()",
        "for _, address in ipairs({0x6B10, 0x6B19, 0x6B80}) do",
        'install(address, 13, "epochGate13")',
        'install(address, 16, "epochGate16")',
        'install(0x7CBF, 13, "installer13")',
        'install(0x7CBF, 16, "installer16")',
        'install(0x5559, 13, "epochPublish13")',
        'install(0x5559, 16, "epochPublish16")',
        'install(0xDAD7, nil, "runtimeDAD7")',
        'install(0x001A, nil, "rst18Route001A")',
        'install(0x6CEA, 31, "selfhealEntry6CEA")',
        'install(0x6D35, 31, "selfhealRepair6D35")',
        'install(0x6D4D, 31, "selfhealStart6D4D")',
        'install(0x6DCB, 31, "transactionArmed6DCB")',
        'install(0x6E25, 31, "displayFlip6E25")',
        'install(0x6E2A, 31, "commitEffect6E2A")',
        'install(0x6CC5, 31, "menuMux6CC5")',
        'install(0x6CE2, 31, "menuEffect6CE2")',
        'install(0x4100, 21, "consumer4100")',
        'install(0x4302, 1, "compiler4302")',
        'install(0x4354, 1, "publication4354")',
        'install(0x10E2, 0, "postcopy10E2")',
        'install(0x6CCE, 19, "hazardDispatch6CCE")',
        'install(0x6BA7, 19, "hazardHelper6BA7")',
        'install(0x61B7, 19, "hazardFront61B7")',
        'install(0x4300, 20, "hazardWrite4300")',
        'install(0x4500, 20, "hazardWrite4500")',
        "deferred_wram_frames = deferred_wram_frames + 1",
        "if (emu:read8(0xFF70) % 0x08) ~= 1 then",
        "PENTA_SCENE0B_OAM_DMA_UNREADABLE_FRAMES",
        "PENTA_SCENE0B_READ_PC()",
        "current_pc >= 0xFF80 and current_pc <= 0xFFFE",
        "and emu:read8(0xD880) == 0xFF then",
        '"oam_dma_unreadable_frames=%d\\n"',
        'finish("fail", "initial-wram-bank-not-1")',
        "C.WATCHPOINT_TYPE.WRITE",
        'write_token_marker(".cache-audit-ready")',
    )
    for snippet in required:
        require(snippet in source, f"scene-$0B probe lacks contract: {snippet}")
    forbidden = (
        "saveStateFile", "writeRange", "memory:write", "C600,",
        "D880,", "FFE4,", "FFC1,",
    )
    for snippet in forbidden:
        require(snippet not in source,
                f"scene-$0B probe contains forbidden state write: {snippet}")
    # mGBA's raw VRAM domain is bank zero only.  Pin all three raw reads to
    # bank-zero offsets and require every bank-one consumer to share the one
    # VBK-selecting CPU-window helper.  This prevents a bank-zero alias from
    # producing a plausible 16-KiB artifact when both banks happen to contain
    # the same reviewed tooth pattern.
    raw_reads = re.findall(r"raw_vram:read8\(([^)\n]+)\)", source)
    require(raw_reads == ["offset", "offset", "address + byte"],
            "scene-$0B raw VRAM reads are not bank-zero-only")
    require(source.count("read_vbk1(") == 4,
            "scene-$0B bank-one consumers bypass the shared VBK helper")
    require(source.count("emu:read8(0x8000 + offset)") == 1,
            "scene-$0B bank-one CPU-window read is not unique")
    bank_dispatch = (
        "if bank == 0 then\n"
        "              observed = raw_vram:read8(address + byte)\n"
        "            else\n"
        "              observed = observed_bank1[byte + 1]\n"
        "            end"
    )
    require(bank_dispatch in source,
            "scene-$0B CHR grader does not dispatch bank one to VBK data")
    vbk1_start = source.index("local function read_vbk1(offsets)")
    vbk1_end = source.index("\nlocal function read_planes(offsets)", vbk1_start)
    vbk1 = source[vbk1_start:vbk1_end]
    require(
        "raw_vram" not in vbk1
        and "if not vram_cpu_readable() then return nil end" in vbk1
        and "local old_vbk = emu:read8(0xFF4F)" in vbk1
        and "values[index] = emu:read8(0x8000 + offset)" in vbk1
        and "if emu:read8(0xFF4F) ~= old_vbk then" in vbk1,
        "scene-$0B bank-one reads do not use the guarded VBK CPU window",
    )
    require(
        source.index("chr_handle:write(byte_blob(bank0_chr))")
        < source.index("chr_handle:write(byte_blob(bank1_chr))"),
        "scene-$0B final CHR artifact does not serialize bank zero then bank one",
    )
    writes = re.findall(r"emu:write8\(([^\n]+)\)", source)
    require(len(writes) == 4,
            "scene-$0B probe must have exactly four observation-only writes")
    require(writes[0].startswith("0xFF4F, 1")
            and writes[1].startswith("0xFF4F, old_vbk")
            and writes[2].startswith("0xFF68, index")
            and writes[3].startswith("0xFF68, old_index"),
            "scene-$0B probe writes outside observation-only selector pairs")
    require(source.count("emu:setKeys(") >= 2,
            "scene-$0B probe does not explicitly release input")
    deferred = source.index("deferred_wram_frames = deferred_wram_frames + 1")
    require(
        source.index("apply_keys(0)", deferred) < source.index("return", deferred),
        "SVBK3 frame deferral does not release input before returning",
    )
    require(
        source.index("phase_frame = phase_frame + 1") > deferred,
        "SVBK3 frame deferral advances the logical phase",
    )
    dma_deferred = source.index(
        "PENTA_SCENE0B_OAM_DMA_UNREADABLE_FRAMES =\n"
        "      PENTA_SCENE0B_OAM_DMA_UNREADABLE_FRAMES + 1"
    )
    require(
        source.index("apply_keys(0)", dma_deferred)
        < source.index("return", dma_deferred),
        "OAM-DMA frame deferral does not release input before returning",
    )
    require(
        source.index("phase_frame = phase_frame + 1") > dma_deferred,
        "OAM-DMA frame deferral advances the logical phase",
    )
    repair_start = source.index('elseif phase == "repair_settle" then')
    repair_end = source.index('elseif phase == "menu_entry" then', repair_start)
    repair_block = source[repair_start:repair_end]
    require(
        "sample_phase()" in repair_block
        and repair_block.index("sample_phase()")
        < repair_block.index("if phase_frame >= REPAIR_SETTLE then"),
        "repair-settle does not sample every frame before advancing",
    )
    first_close_contract = (
        'set_phase("repair_settle")\n'
        "        -- Capture the exact acknowledged-close frame"
    )
    require(first_close_contract in source
            and "sample_phase()" in source[
                source.index(first_close_contract):
                source.index(first_close_contract) + 420
            ], "initial menu close is not sampled at acknowledgement")
    require(
        source.index("return emu.memory and emu.memory.vram")
        > source.index('callbacks:add("frame"'),
        "scene-$0B probe acquires its core VRAM accessor before first frame",
    )
    require("local raw_vram = assert" not in source,
            "scene-$0B probe has a core-dependent top-level VRAM assertion")
    frame_registration = source.index('callbacks:add("frame"')
    pre_frame = source[:frame_registration]
    for variable in (
        "PENTA_SCENE0B_STATE", "PENTA_SCENE0B_CAPTURE_LABEL",
        "PENTA_SCENE0B_INITIAL_MENU", "PENTA_SCENE0B_FRAME_LIMIT",
        "PENTA_SCENE0B_CAPTURE_FRAMES", "PENTA_SCENE0B_REPAIR_SETTLE",
        "PENTA_SCENE0B_MENU_HOLD", "PENTA_SCENE0B_POST_CLOSE",
        "PENTA_SCENE0B_IMMUTABLE_SOURCE",
        "PENTA_SCENE0B_STAGE1_TABLES",
        "PENTA_SCENE0B_CANONICAL_BG_ART",
        "PENTA_SCENE0B_CANONICAL_HAZARD_BANK1_ART",
        "PENTA_SCENE0B_HAZARD_PHASES",
        "PENTA_SCENE0B_EXPECTED_BG_CRAM",
        "PENTA_SCENE0B_CACHE_AUDIT_OUT",
    ):
        require(f'os.getenv("{variable}")' not in pre_frame,
                f"scene-$0B probe reads {variable} before first frame")
    require('io.open(OUT .. ".trace.tsv"' not in pre_frame,
            "scene-$0B probe opens its trace before first frame")
    require("tonumber(assert(" not in source,
            "scene-$0B probe passes assert's message as tonumber's base")
    require("os.exit(" not in source,
            "scene-$0B probe must not tear Qt down from its frame callback")
    require(source.count("emu:stop()") == 2,
            "scene-$0B probe must stop its core on success and boot failure")
    require(source.count(
        'handle:write("startup_token=" .. STARTUP_TOKEN .. "\\n")'
    ) == 2, "scene-$0B success/failure reports must both bind the token")
    require(source.count(
        'marker:write("startup_token=" .. STARTUP_TOKEN .. "\\n")'
    ) == 1, "scene-$0B completion marker must bind the token exactly once")
    require(source.count("assert(os.rename(temporary, path))") == 2,
            "scene-$0B startup/completion markers must both be atomic")
    require(source.count("emu:setBreakpoint(") == 1,
            "cache audit must install breakpoints through one guarded helper")
    require(source.count("emu:setRangeWatchpoint(") == 1,
            "cache audit must own one guarded cache-writer watchpoint")
    require(source.count("emu:read8(0xFF01)") == 2,
            "scene-$0B probe does not observe both relocated FF01 owners")
    require("emu:read8(0xFFA5)" not in source,
            "scene-$0B probe still grades the obsolete FFA5 latch")
    require("emu:write8" not in source[source.index(
        "local function cache_audit_sample"
    ):source.index("local function window_visible")],
        "cache audit contains a memory write")
    return {
        "probe_sha256": sha256_bytes(source.encode()),
        "gameplay_writes": 0,
        "fixture_writes": 0,
        "vram_injection_bytes": 0,
        "observation_only_vbk_write_sites": 2,
        "raw_vram_bank0_only": True,
        "bank1_cpu_window_only": True,
        "final_chr_bank_order": [0, 1],
        "native_select_only": True,
        "select_input_policy": "hold-until-native-menu-acknowledgement",
        "publication_latch": "FF01",
        "deferred_core_accessor": True,
        "deferred_runtime_environment": True,
        "deferred_trace_open": True,
        "token_bound_controlled_teardown": True,
        "optional_cache_audit_is_read_only": True,
        "svbk1_deferred_frame_sampling": True,
        "cache_audit_breakpoint_sites": 29,
        "cache_audit_watchpoint_sites": 1,
        "cache_audit_wram_writes": 0,
    }


def check_known_source_resume(source_state: bytes, rom_bytes: bytes) -> None:
    """Fail closed on the archived IRQ return into the relocated source loop.

    This is a narrow incompatibility check, not a general savestate ABI proof.
    Do not normalize the CPU or stack here: that would change the exact replay.
    """
    if sha256_bytes(source_state) != (
        "5f80b932414a73e8c252331a35069a47996508c219c04e9a7b670e8706c20716"
    ):
        return
    # The pinned wall capture's nested IRQ stack returns to native $13C2.
    # r387's fast-finish shim instead has the operand of LDH A,($BA) there.
    if rom_bytes[0x13C0:0x13C5] == bytes.fromhex("F5 F0 BA B7 20"):
        require(False,
                "archived wall state is incompatible with relocated source code: "
                "saved IRQ return $13C2 now enters the fast-finish shim mid-instruction; "
                "exact replay remains unqualified (no CPU/stack normalization applied)")


def retarget_capture(source: Path, destination: Path, rom: Path) -> dict[str, Any]:
    """Retarget only CRC and saved ROM identity for the $80->$C0 ROM."""
    source_state = gbas_payload(source)
    require(len(source_state) == GBAS_SIZE,
            "identity retarget source has the wrong gbAs size")
    require(int.from_bytes(source_state[:4], "little") == GBAS_MAGIC,
            "identity retarget source is not an exact mGBA v3 state")
    require(source_state[GBAS_MODEL_OFFSET] == GB_MODEL_CGB,
            "identity retarget source is not serialized in CGB mode")
    require(source_state[GBAS_BOOT_REGISTER_OFFSET] != 0xFF,
            "identity retarget source is still inside the BIOS")

    rom_bytes = rom.read_bytes()
    check_known_source_resume(source_state, rom_bytes)
    target_identity = rom_bytes[
        ROM_TITLE_OFFSET:ROM_TITLE_OFFSET + GBAS_TITLE_SIZE
    ]
    require(len(target_identity) == GBAS_TITLE_SIZE,
            "identity-retarget candidate is too small for its ROM header")
    source_identity = source_state[
        GBAS_TITLE_OFFSET:GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE
    ]
    require(source_identity[:15] == target_identity[:15],
            "source and target ROM title bytes 0..14 differ")
    require(source_identity[15] == CGB_COMPATIBLE_FLAG
            and target_identity[15] == CGB_ONLY_FLAG,
            "identity retarget is not the exact $80->$C0 CGB transition")

    candidate_crc = zlib.crc32(rom_bytes) & 0xFFFFFFFF
    candidate_crc_bytes = candidate_crc.to_bytes(4, "little")
    expected_differences = [
        4 + index for index, values in enumerate(zip(
            source_state[4:8], candidate_crc_bytes, strict=True
        )) if values[0] != values[1]
    ] + [GBAS_TITLE_OFFSET + 15]
    retarget_rom_identity(source, destination, rom)
    retargeted = gbas_payload(destination)
    differences = [
        index
        for index, pair in enumerate(zip(source_state, retargeted, strict=True))
        if pair[0] != pair[1]
    ]
    require(differences == expected_differences,
            "ROM-identity retarget changed unexpected gbAs offsets")
    require(int.from_bytes(retargeted[4:8], "little") == candidate_crc,
            "retargeted state does not contain the candidate ROM CRC32")
    require(retargeted[
        GBAS_TITLE_OFFSET:GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE
    ] == target_identity,
            "retargeted state does not contain the target ROM identity")
    require(source_state[:4] == retargeted[:4]
            and source_state[8:GBAS_TITLE_OFFSET + 15]
            == retargeted[8:GBAS_TITLE_OFFSET + 15]
            and source_state[GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE:]
            == retargeted[GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE:],
            "ROM-identity retarget changed CPU, mapper, memory, or video state")
    return {
        "path": str(destination.resolve()),
        "sha256": sha256(destination),
        "rom_crc32": f"{candidate_crc:08x}",
        "rom_identity": target_identity.hex(),
        "changed_gbAs_offsets": differences,
        "normalization_writes": 0,
        "fixture_writes": 0,
        "vram_injection_bytes": 0,
    }


def launcher_command(runtime_rom: Path, runtime: Path) -> list[str]:
    """Put every option before the ROM positional for deterministic parsing."""
    return [
        str(LAUNCHER), "--fastforward",
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        "--script", str(PROBE), str(runtime_rom),
    ]


def default_qt_emulator() -> Path:
    """Resolve the guard's default Qt binary after overrides are stripped."""
    for candidate in (
        Path("/home/struktured/bin/mgba-qt"),
        Path("/usr/bin/mgba-qt"),
        Path("/usr/local/bin/mgba-qt"),
    ):
        if candidate.is_file():
            return candidate.resolve()
    raise LiveError("default checked Qt emulator executable is missing")


def stop_owned_process(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    """Stop only this exact child and return an auditable teardown outcome."""
    existing = process.poll()
    if existing is not None:
        return {
            "exact_child_terminated": False,
            "termination_method": "already-exited",
            "return_code": existing,
        }
    process.terminate()
    method = "SIGTERM"
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
        method = "SIGKILL-after-SIGTERM-timeout"
    return {
        "exact_child_terminated": True,
        "termination_method": method,
        "return_code": int(process.returncode),
    }


def validate_process_teardown(
    outcome: dict[str, Any], *, completion_authenticated: bool,
) -> dict[str, Any]:
    """Accept no nonzero exit unless we ended this exact authenticated child."""
    return_code = outcome.get("return_code")
    terminated = outcome.get("exact_child_terminated") is True
    method = outcome.get("termination_method")
    if terminated:
        require(completion_authenticated,
                "exact-child termination precedes authenticated completion")
        require(method in {"SIGTERM", "SIGKILL-after-SIGTERM-timeout"},
                "exact-child termination method is not allowed")
        allowed = {0, -signal.SIGTERM, -signal.SIGKILL}
        require(return_code in allowed,
                f"controlled exact child exited unexpectedly: {return_code}")
        policy = "authenticated-exact-child-termination"
    else:
        require(method == "already-exited" and return_code == 0,
                f"scene-$0B launcher exited unexpectedly: {return_code}")
        policy = "natural-zero-exit"
    return {
        "policy": policy,
        "completion_authenticated": completion_authenticated,
        "exact_child_terminated": terminated,
        "termination_method": method,
        "return_code": return_code,
    }


def read_only_process_check(path: Path) -> None:
    try:
        completed = subprocess.run(
            [str(PROCESS_CHECK)], cwd=ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=10, check=False,
        )
        path.write_bytes(completed.stdout)
    except BaseException as error:
        path.write_text(f"process check failed: {error}\n")


def parse_key_values(path: Path) -> dict[str, str]:
    require(path.is_file(), f"probe report is missing: {path}")
    result: dict[str, str] = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        require(line and "=" in line, f"probe report line {number} is malformed")
        key, value = line.split("=", 1)
        require(key and key not in result,
                f"probe report repeats or omits a key on line {number}")
        result[key] = value
    return result


def parse_completion_marker(path: Path, startup_token: str) -> str:
    marker = parse_key_values(path)
    require(set(marker) == {"status", "startup_token"},
            "probe completion marker has the wrong keys")
    require(marker["startup_token"] == startup_token,
            "probe completion token differs")
    require(marker["status"] in {"ok", "fail"},
            "probe completion status is invalid")
    return marker["status"]


def parse_trace(path: Path, startup_token: str) -> list[dict[str, Any]]:
    require(path.is_file(), f"probe state trace is missing: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        values = line.split("\t")
        require(len(values) == len(TRACE_FIELDS),
                f"probe trace line {number} has the wrong field count")
        row: dict[str, Any] = dict(zip(TRACE_FIELDS, values, strict=True))
        for name in TRACE_FIELDS:
            if name in {"phase", "startup_token"}:
                continue
            base = 16 if name in {
                "scene", "room", "active", "menu", "lcdc", "scx", "scy"
            } else 10
            try:
                row[name] = int(row[name], base)
            except ValueError as error:
                raise LiveError(
                    f"probe trace line {number} has invalid {name}"
                ) from error
        require(row["sample"] == number,
                f"probe trace sample sequence breaks at line {number}")
        require(row.pop("startup_token") == startup_token,
                f"probe trace token differs on line {number}")
        rows.append(row)
    require(rows, "probe state trace is empty")
    return rows


def parse_cache_audit(path: Path) -> list[dict[str, Any]]:
    """Parse the optional diagnostic-only cache/entry sidecar."""
    require(path.is_file(), f"cache-audit sidecar is missing: {path}")
    lines = path.read_text().splitlines()
    require(lines, "cache-audit sidecar is empty")
    require(tuple(lines[0].split("\t")) == CACHE_AUDIT_FIELDS,
            "cache-audit header changed")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines[1:], 2):
        values = line.split("\t")
        require(len(values) == len(CACHE_AUDIT_FIELDS),
                f"cache-audit line {number} has the wrong field count")
        row: dict[str, Any] = dict(zip(CACHE_AUDIT_FIELDS, values, strict=True))
        require(row["kind"] in CACHE_AUDIT_KINDS,
                f"cache-audit line {number} has unknown kind")
        for name in CACHE_AUDIT_FIELDS:
            if name in {"kind", "phase"}:
                continue
            base = 10 if name in {"event", "sample", "frame"} else 16
            try:
                row[name] = int(row[name], base)
            except ValueError as error:
                raise LiveError(
                    f"cache-audit line {number} has invalid {name}"
                ) from error
        require(row["event"] == number - 1,
                f"cache-audit event sequence breaks on line {number}")
        write_kind = row["kind"].startswith("write")
        if write_kind:
            require(row["write_address"] == int(row["kind"][5:], 16),
                    f"cache-audit writer address differs on line {number}")
        else:
            require(row["write_address"] == 0xFFFF,
                    f"non-writer cache row has a write address on line {number}")
        rows.append(row)
    require(rows, "cache-audit sidecar has no observations")
    return rows


def selfheal_publication_contract(
    rows: Sequence[dict[str, Any]],
    *,
    require_semantic_write: bool = False,
) -> dict[str, Any]:
    """Require r314's pending -> complete-map -> acknowledged transaction."""
    all_helper_rows = [
        row for row in rows if row["kind"] == "hazardHelper6BA7"
    ]
    require(
        all_helper_rows
        and all(row["ffb7"] == 0x02 for row in all_helper_rows),
        "bank19:$6BA7 executed outside the Stage-1 FFB7=$02 owner",
    )
    entries = [row for row in rows if row["kind"] == "selfhealEntry6CEA"]
    repairs = [row for row in rows if row["kind"] == "selfhealRepair6D35"]
    starts = [row for row in rows if row["kind"] == "selfhealStart6D4D"]
    armed_rows = [
        row for row in rows if row["kind"] == "transactionArmed6DCB"
    ]
    displays = [row for row in rows if row["kind"] == "displayFlip6E25"]
    commits = [row for row in rows if row["kind"] == "commitEffect6E2A"]
    require(entries, "self-heal entry is absent")
    require(
        all(len(group) == 1 for group in (
            repairs, starts, armed_rows, displays, commits,
        )),
        "self-heal transaction sites are not each exact-once",
    )
    repair, start, armed, display, commit = (
        repairs[0], starts[0], armed_rows[0], displays[0], commits[0]
    )
    first_entry = min(row["event"] for row in entries)
    routes = [
        row["event"] for row in rows
        if row["kind"] == "rst18Route001A" and row["event"] < first_entry
    ]
    require(routes and max(routes) < first_entry <= repair["event"]
            < start["event"] < armed["event"] < display["event"]
            < commit["event"],
            "self-heal chronology is not RST->repair->arm->display->commit")
    require(
        repair["scene"] == 0x0B and repair["ffb7"] == 0x02
        and repair["svbk"] == 1
        and (repair["dad7_7"], repair["dad7_8"], repair["dad7_9"])
        == (0xC2, 0xB9, 0xDA),
        "self-heal repair does not observe the exact stale preimage",
    )
    for transaction_row, label in ((start, "start"), (armed, "armed")):
        require(
            transaction_row["scene"] == 0x0B
            and transaction_row["ffb7"] == 0x02
            and transaction_row["svbk"] == 1
            and (
                transaction_row["dad7_7"], transaction_row["dad7_8"],
                transaction_row["dad7_9"],
            ) == (0xCD, 0x13, 0x00)
            and transaction_row["df53"] == transaction_row["df57"] == 0xFF,
            f"self-heal {label} is not pending with both caches dirty",
        )

    transaction_kinds = {
        kind: [
            row for row in rows
            if row["kind"] == kind
            and armed["event"] < row["event"] < display["event"]
        ]
        for kind in (
            "runtimeDAD7", "consumer4100", "compiler4302",
            "publication4354", "postcopy10E2", "hazardDispatch6CCE",
            "hazardHelper6BA7", "hazardFront61B7",
        )
    }
    require(all(len(group) == 1 for group in transaction_kinds.values()),
            "repair transaction does not have one complete native pipeline")
    transaction_order = [armed["event"]] + [
        transaction_kinds[kind][0]["event"] for kind in (
            "runtimeDAD7", "consumer4100", "compiler4302",
            "publication4354", "postcopy10E2", "hazardDispatch6CCE",
            "hazardHelper6BA7", "hazardFront61B7",
        )
    ] + [display["event"], commit["event"]]
    require(transaction_order == sorted(transaction_order)
            and len(set(transaction_order)) == len(transaction_order),
            "repair transaction native publication order changed")
    require(
        all(
            (row["dad7_7"], row["dad7_8"], row["dad7_9"])
            == (0xCD, 0x13, 0x00)
            for row in rows
            if armed["event"] < row["event"] < commit["event"]
            and row["kind"] == "runtimeDAD7"
        ),
        "pre-commit DAD7 observation is not pending",
    )
    transaction_writers = [
        row for row in rows
        if row["kind"] in {"hazardWrite4300", "hazardWrite4500"}
        and armed["event"] < row["event"] < display["event"]
    ]
    require(all(
        transaction_kinds["hazardFront61B7"][0]["event"] < row["event"]
        for row in transaction_writers
    ), "a semantic hazard write escaped the native transaction tail")
    if require_semantic_write:
        require(transaction_writers,
                "hazard-bearing repair transaction reached no semantic writer")

    key = display["scy"] ^ display["dc02"] ^ display["c21b"] ^ display["c2b8"]
    selector = display["dc0b"]
    publication = transaction_kinds["publication4354"][0]
    require(
        publication["ff01"] == (0x9D if selector else 0x99),
        "repair transaction published to the wrong physical map",
    )
    selected_display = (
        display["lcdc"] == (0x8B if selector else 0x83)
        and display["df57" if selector else "df53"] == key
        and display["df53" if selector else "df57"] == 0xFF
    )
    require(
        display["scene"] == 0x0B and display["ffb7"] == 0x02
        and display["svbk"] == 1
        and (display["dad7_7"], display["dad7_8"], display["dad7_9"])
        == (0xCD, 0x13, 0x00)
        and selected_display,
        "display effect did not select the completed pending map",
    )
    require(
        commit["event"] == display["event"] + 1
        and (commit["dad7_7"], commit["dad7_8"], commit["dad7_9"])
        == (0xC4, 0x13, 0x00)
        and all(commit[field] == display[field] for field in (
            "scene", "ffb7", "svbk", "dc0b", "lcdc", "ff01",
            "df53", "df57", "scy", "dc02", "c21b", "c2b8",
        )),
        "repair acknowledgment is not immediately after the clean map flip",
    )

    after = start["event"]
    current_runtime = [
        row for row in rows
        if row["kind"] == "runtimeDAD7" and row["event"] > commit["event"]
    ]
    require(current_runtime and all(
        (row["dad7_7"], row["dad7_8"], row["dad7_9"])
        == (0xC4, 0x13, 0x00) for row in current_runtime
    ), "post-commit DAD7 observation regressed")
    kinds = {
        kind: [row for row in rows if row["kind"] == kind
               and row["event"] > after]
        for kind in ("publication4354",)
    }
    writes = [row for row in rows if row["kind"].startswith("write")]
    repopulation = {
        f"{address:04X}": sum(
            row["event"] > after and row["write_address"] == address
            and row["old_value"] == 0xFF and row["new_value"] != 0xFF
            and row["new_value"]
            == (row["scy"] ^ row["dc02"] ^ row["c21b"] ^ row["c2b8"])
            for row in writes
        ) for address in (0xDF53, 0xDF57)
    }
    require(all(repopulation.values()),
            "both physical cache sentinels were not repopulated")
    publications = {
        "9800": sum(row["ff01"] == 0x99 for row in kinds["publication4354"]),
        "9C00": sum(row["ff01"] == 0x9D for row in kinds["publication4354"]),
    }
    require(all(publications.values()),
            "both physical attribute maps were not published")
    owner_kinds = (
        "postcopy10E2", "hazardDispatch6CCE", "hazardHelper6BA7",
        "hazardFront61B7",
    )
    owner_rows = {
        kind: [row for row in rows if row["kind"] == kind
               and row["event"] > after]
        for kind in owner_kinds
    }
    writer_rows = [
        row for row in rows
        if row["kind"] in {"hazardWrite4300", "hazardWrite4500"}
        and row["event"] > after
    ]
    owner_counts = {
        "postcopy": len(owner_rows["postcopy10E2"]),
        "dispatcher": len(owner_rows["hazardDispatch6CCE"]),
        "helper": len(owner_rows["hazardHelper6BA7"]),
        "geometry_front": len(owner_rows["hazardFront61B7"]),
        "writer_4300": sum(
            row["kind"] == "hazardWrite4300" for row in writer_rows
        ),
        "writer_4500": sum(
            row["kind"] == "hazardWrite4500" for row in writer_rows
        ),
    }
    require(
        owner_counts["postcopy"] > 0
        and owner_counts["dispatcher"] == owner_counts["postcopy"]
        and owner_counts["helper"] == owner_counts["dispatcher"]
        and owner_counts["geometry_front"] == owner_counts["dispatcher"],
        "scene-$0B publications did not all reach the semantic hazard owner",
    )
    require(
        all(row["ffb7"] == 0x02
            for row in owner_rows["hazardHelper6BA7"]),
        "bank19:$6BA7 executed outside the Stage-1 FFB7=$02 owner",
    )
    if require_semantic_write:
        require(writer_rows and transaction_writers,
                "hazard-bearing scene-$0B fixture reached no semantic writer")
    return {
        "repair_event": repair["event"],
        "start_event": start["event"],
        "armed_event": armed["event"],
        "display_event": display["event"],
        "commit_event": commit["event"],
        "effect_event": commit["event"],
        "ordered_first_events": transaction_order,
        "repopulation_by_address": repopulation,
        "physical_publication_targets": publications,
        "hazard_semantic_owner": owner_counts,
    }


def _stage1_tooth(tile: int) -> bool:
    return 0x64 <= (tile & 0xEF) < 0x6A


def _stage1_hazard_positions(tiles: bytes) -> set[int]:
    """Reproduce the reviewed geometry scanner without consulting live attrs."""
    require(len(tiles) == 0x400, "physical BG tile map has wrong size")
    positions: set[int] = set()
    for row in range(32):
        start = row * 32
        values = tiles[start:start + 32]
        columns: Iterable[int] = ()
        if _stage1_tooth(values[0]) or _stage1_tooth(values[1]):
            width = 11 if _stage1_tooth(values[10]) else (
                10 if _stage1_tooth(values[9]) else 9
            )
            columns = range(width)
        elif values[4] == 0x6A:
            columns = range(5, 15)
        elif _stage1_tooth(values[4]) or _stage1_tooth(values[5]):
            columns = range(4, 13)
        elif _stage1_tooth(values[6]):
            columns = tuple(
                column for column in range(4, 14)
                if _stage1_tooth(values[column])
            )
        positions.update(start + column for column in columns)
    return positions


def _stage1_semantic_attrs(
    tiles: bytes, canonical_lut: bytes, room: int,
    hazard_positions: set[int] | None = None,
) -> tuple[bytes, set[int]]:
    require(len(canonical_lut) == 0x100,
            "canonical Stage-1 LUT has wrong size")
    expected = bytearray(canonical_lut[tile] & 0x07 for tile in tiles)
    if room == 0x01:
        for offset, tile in enumerate(tiles):
            if tile in {0x24, 0x27, 0x30, 0x33}:
                expected[offset] = 0x06
    positions = (
        _stage1_hazard_positions(tiles)
        if hazard_positions is None else set(hazard_positions)
    )
    for offset in positions:
        if _stage1_tooth(tiles[offset]):
            expected[offset] = 0x0F
    return bytes(expected), positions


def capture_sram(path: Path) -> bytes:
    """Extract the one mGBA savedata extension, checking every PNG CRC."""
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"operator capture is not an mGBA PNG state: {path}")
    offset = 8
    savedata: list[bytes] = []
    while offset < len(data):
        require(offset + 12 <= len(data),
                f"truncated PNG extension chunk: {path}")
        length = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc = data[offset + 8 + length:offset + 12 + length]
        require(len(payload) == length and len(crc) == 4
                and int.from_bytes(crc, "big")
                == (zlib.crc32(kind + payload) & 0xFFFFFFFF),
                f"bad PNG extension chunk: {path}")
        if kind == b"gbAx" and len(payload) >= 8:
            extension = int.from_bytes(payload[:4], "little")
            size = int.from_bytes(payload[4:8], "little")
            if extension == 2:
                try:
                    raw = zlib.decompress(payload[8:])
                except zlib.error as error:
                    raise LiveError(
                        f"malformed savedata extension: {path}"
                    ) from error
                require(len(raw) == size == 0x2000,
                        "operator capture savedata size changed")
                savedata.append(raw)
        offset += 12 + length
    require(offset == len(data) and len(savedata) == 1,
            "operator capture must contain one savedata extension")
    return savedata[0]


def capture_immutable_source(capture: Mapping[str, Any]) -> bytes:
    """Rebuild C1A0 from independent world/SRAM tables in the exact state."""
    path = Path(capture["path"])
    state = gbas_payload(path)
    sram = capture_sram(path)

    def wram(address: int) -> int:
        require(0xC000 <= address <= 0xDFFF,
                "operator world lookup escaped serialized WRAM")
        return state[GBAS_WRAM_OFFSET + address - 0xC000]

    camera_x = (wram(0xDC00) | (wram(0xDC01) << 8)) >> 5
    camera_y = (wram(0xDC02) | (wram(0xDC03) << 8)) >> 5
    rebuilt = bytearray(24 * 24)
    for world_row in range(6):
        for world_column in range(6):
            world_address = (
                0xC780 + (camera_y + world_row) * 0x40
                + camera_x + world_column
            )
            world_id = wram(world_address)
            metatile_base = 0x400 + world_id * 4
            require(metatile_base + 4 <= len(sram),
                    "operator world ID escaped its metatile table")
            for metatile_row in range(2):
                for metatile_column in range(2):
                    metatile = sram[
                        metatile_base + metatile_row * 2 + metatile_column
                    ]
                    tile_base = metatile * 4
                    require(tile_base + 4 <= 0x400,
                            "operator metatile escaped its tile table")
                    for tile_row in range(2):
                        for tile_column in range(2):
                            output_row = (
                                world_row * 4 + metatile_row * 2 + tile_row
                            )
                            output_column = (
                                world_column * 4
                                + metatile_column * 2 + tile_column
                            )
                            rebuilt[output_row * 24 + output_column] = sram[
                                tile_base + tile_row * 2 + tile_column
                            ]
    # The native packed compiler owns a 22x20 world rectangle; its remaining
    # two columns and four rows are deterministic zero padding.
    for row in range(24):
        for column in range(24):
            if row >= 20 or column >= 22:
                rebuilt[row * 24 + column] = 0

    c1a0_start = GBAS_WRAM_OFFSET + (0xC1A0 - 0xC000)
    captured_c1a0 = state[c1a0_start:c1a0_start + 24 * 24]
    require(bytes(rebuilt) == captured_c1a0,
            "operator C1A0 differs from independent world/SRAM expansion")
    return bytes(rebuilt)


def expected_stage1_bg_cram(rom: bytes) -> bytes:
    """Return the static Stage-1 CRAM contract, including hazard BG7."""
    require(len(rom) >= STAGE1_HAZARD_BG7_OFFSET + 8,
            "candidate is too small for the Stage-1 CRAM contract")
    expected = bytearray(rom[
        STAGE1_BG_PALETTE_OFFSET:STAGE1_BG_PALETTE_OFFSET + 64
    ])
    require(len(expected) == 64,
            "candidate Stage-1 background palette table is incomplete")
    expected[7 * 8:8 * 8] = rom[
        STAGE1_HAZARD_BG7_OFFSET:STAGE1_HAZARD_BG7_OFFSET + 8
    ]
    payload = bytes(expected)
    require(sha256_bytes(payload) == STAGE1_BG_CRAM_SHA256,
            "candidate lacks the reviewed canonical Stage-1 BG CRAM")
    return payload


def physical_plane_receipt(
    dump_path: Path, metadata_path: Path, canonical_lut: bytes,
    immutable_source: bytes, capture_label: str = "",
) -> dict[str, Any]:
    """Grade both final physical maps without a candidate-output baseline."""
    payload = dump_path.read_bytes()
    require(len(payload) == PLANE_DUMP_SIZE,
            f"physical-plane dump size changed: {len(payload)}")
    metadata = parse_key_values(metadata_path)
    require(metadata.get("schema") == "maps-v1"
            and int(metadata.get("bytes", "0")) == PLANE_DUMP_SIZE,
            "physical-plane dump metadata changed")
    try:
        frame = int(metadata["frame"])
        sample = int(metadata["sample"])
        lcdc = int(metadata["lcdc"], 16)
        scx = int(metadata["scx"], 16)
        scy = int(metadata["scy"], 16)
        scene = int(metadata["scene"], 16)
        room = int(metadata["room"], 16)
        menu = int(metadata["menu"], 16)
    except (KeyError, ValueError) as error:
        raise LiveError("physical-plane metadata is malformed") from error
    require(metadata.get("phase") == "post_close" and scene == 0x0B
            and menu == 0,
            "physical-plane dump is not a scene-$0B post-close sample")

    tiles_blob = payload[:0x800]
    attrs_blob = payload[0x800:0x1000]
    source = payload[0x1000:0x1240]
    runtime_lut = payload[0x1240:0x1340]
    require(len(source) == 24 * 24 and len(runtime_lut) == 0x100
            and len(immutable_source) == 24 * 24,
            "physical-plane source/LUT payload is incomplete")
    # Both safe replay states descend from the exact pre-compiled-tooth
    # operator runtime, whose C600 table is the reviewed release LUT. The
    # candidate's private compiler nevertheless publishes the current bank-1
    # tooth attributes; grade those physical maps below and reject any other
    # inherited C600 payload here.
    if capture_label in HAZARD_CAPTURE_LABELS:
        require(sha256_bytes(runtime_lut) == STAGE1_RELEASE_LUT_SHA256,
                "scene-$0B capture carries an unknown inherited runtime LUT")
    else:
        require(runtime_lut == canonical_lut,
                "scene-$0B capture runtime LUT differs from canonical")
    # The native terrain/attribute compiler publishes 24 rows of 24 bytes.
    # Grade that complete owned rectangle, including all canonical padding,
    # rather than only the current 160x144 viewport.  The legacy receipt key
    # names retain "visible" for schema compatibility, but their counters are
    # deliberately full-owner counters now.
    owned = [
        row * 32 + column
        for row in range(24)
        for column in range(24)
    ]
    maps: dict[str, Any] = {}
    source_map = bytearray(0x400)
    immutable_source_map = bytearray(0x400)
    for row in range(24):
        source_map[row * 32:row * 32 + 24] = source[
            row * 24:(row + 1) * 24
        ]
        immutable_source_map[row * 32:row * 32 + 24] = immutable_source[
            row * 24:(row + 1) * 24
        ]
    immutable_hazard_positions = _stage1_hazard_positions(
        bytes(immutable_source_map)
    )
    hazard_envelope: set[int] = set()
    for position in immutable_hazard_positions:
        hazard_row, hazard_column = divmod(position, 32)
        for envelope_row in range(max(0, hazard_row - 1),
                                  min(32, hazard_row + 2)):
            for envelope_column in range(max(0, hazard_column - 1),
                                         min(32, hazard_column + 2)):
                hazard_envelope.add(envelope_row * 32 + envelope_column)
    exact_source_hazard = None
    hazard_contract = None
    if capture_label in HAZARD_CAPTURE_LABELS:
        hazard_contract = load_hazard_tile_contract()
        exact_source_hazard = evaluate_scene0b_hazard_tiles(
            source, source=immutable_source, contract=hazard_contract
        )
        hazard_envelope = {
            (offset // 24) * 32 + offset % 24
            for offset in hazard_contract.coverage.exact_object_cells
        }
    source_immutable_diffs = [
        offset for offset in owned
        if source_map[offset] != immutable_source_map[offset]
    ]
    source_immutable_outside = [
        offset for offset in source_immutable_diffs
        if offset not in hazard_envelope
    ]
    source_immutable_right_edge = [
        offset for offset in source_immutable_outside
        if offset % 32 >= 17
    ]
    for index, name in enumerate(("9800", "9C00")):
        tiles = tiles_blob[index * 0x400:(index + 1) * 0x400]
        attrs = attrs_blob[index * 0x400:(index + 1) * 0x400]
        exact_map_hazard = None
        semantic_hazard_positions = immutable_hazard_positions
        if hazard_contract is not None:
            exact_map_hazard = evaluate_scene0b_hazard_tiles(
                tiles, source=immutable_source, contract=hazard_contract
            )
            semantic_hazard_positions = _stage1_hazard_positions(tiles)
        expected, hazard_positions = _stage1_semantic_attrs(
            tiles, canonical_lut, room, semantic_hazard_positions
        )
        semantic_diffs = [
            offset for offset in range(0x400)
            if attrs[offset] != expected[offset]
        ]
        visible_semantic_diffs = [
            offset for offset in owned if attrs[offset] != expected[offset]
        ]
        source_diffs: list[int] = []
        immutable_diffs: list[int] = []
        for offset in owned:
            row, column = divmod(offset, 32)
            if row < 24 and column < 24:
                if tiles[offset] != source[row * 24 + column]:
                    source_diffs.append(offset)
                if tiles[offset] != immutable_source[row * 24 + column]:
                    immutable_diffs.append(offset)
        hazard_owned_source_diffs = [
            offset for offset in source_diffs
            if offset in hazard_envelope
        ]
        outside_hazard_source_diffs = [
            offset for offset in source_diffs
            if offset not in hazard_envelope
        ]
        right_edge_source_diffs = [
            offset for offset in source_diffs if offset % 32 >= 17
        ]
        immutable_outside_hazard_diffs = [
            offset for offset in immutable_diffs
            if offset not in hazard_envelope
        ]
        immutable_right_edge_diffs = [
            offset for offset in immutable_outside_hazard_diffs
            if offset % 32 >= 17
        ]
        maps[name] = {
            "active": (name == "9C00") == bool(lcdc & 0x08),
            "tiles_sha256": sha256_bytes(tiles),
            "attrs_sha256": sha256_bytes(attrs),
            "exact_hazard_oracle": (
                None if exact_map_hazard is None
                else exact_map_hazard.to_receipt()
            ),
            "hazard_positions": len(hazard_positions),
            "hazard_animation_envelope": len(hazard_envelope),
            "semantic_mismatches_full_map": len(semantic_diffs),
            "semantic_mismatches_visible": len(visible_semantic_diffs),
            "tile_source_mismatches_visible": len(source_diffs),
            "tile_source_mismatches_hazard_owned_visible": len(
                hazard_owned_source_diffs
            ),
            "tile_source_mismatches_outside_hazard_visible": len(
                outside_hazard_source_diffs
            ),
            "tile_source_mismatches_right_edge_visible": len(
                right_edge_source_diffs
            ),
            "tile_immutable_mismatches_visible": len(immutable_diffs),
            "tile_immutable_mismatches_outside_hazard_visible": len(
                immutable_outside_hazard_diffs
            ),
            "tile_immutable_mismatches_right_edge_visible": len(
                immutable_right_edge_diffs
            ),
            "first_visible_semantic_mismatches": [
                {
                    "offset": f"{offset:03X}",
                    "tile": f"{tiles[offset]:02X}",
                    "actual": f"{attrs[offset]:02X}",
                    "expected": f"{expected[offset]:02X}",
                    "hazard_position": offset in hazard_positions,
                }
                for offset in visible_semantic_diffs[:32]
            ],
            "first_visible_tile_source_mismatches": [
                {
                    "offset": f"{offset:03X}",
                    "actual": f"{tiles[offset]:02X}",
                    "source": f"{source[(offset // 32) * 24 + offset % 32]:02X}",
                }
                for offset in source_diffs[:32]
            ],
        }
    return {
        "path": str(dump_path.resolve()),
        "sha256": sha256(dump_path),
        "metadata_path": str(metadata_path.resolve()),
        "metadata_sha256": sha256(metadata_path),
        "frame": frame,
        "sample": sample,
        "lcdc": f"{lcdc:02X}",
        "scx": f"{scx:02X}",
        "scy": f"{scy:02X}",
        "scene": f"{scene:02X}",
        "room": f"{room:02X}",
        "runtime_lut_sha256": sha256_bytes(runtime_lut),
        "runtime_lut_matches_canonical": runtime_lut == canonical_lut,
        "source_sha256": sha256_bytes(source),
        "immutable_source_sha256": sha256_bytes(immutable_source),
        "exact_hazard_oracle": (
            None if exact_source_hazard is None
            else exact_source_hazard.to_receipt()
        ),
        "source_immutable_mismatches_outside_hazard_visible": len(
            source_immutable_outside
        ),
        "source_immutable_mismatches_right_edge_visible": len(
            source_immutable_right_edge
        ),
        "maps": maps,
    }


def _stage1_chr_address(tile: int, lcdc: int) -> int:
    """Map a tile ID to its physical VRAM address under LCDC bit 4."""
    address = tile * 16
    if not (lcdc & 0x10) and tile < 0x80:
        address += 0x1000
    return address


def final_bg_chr_receipt(
    chr_path: Path,
    plane_dump_path: Path,
    metadata_path: Path,
    canonical_bg_art: bytes,
    canonical_hazard_bank1_art: bytes,
    capture_label: str,
) -> dict[str, Any]:
    """Grade actual final physical CHR for every compiler-owned map cell."""
    actual = chr_path.read_bytes()
    require(len(actual) == FINAL_BG_CHR_BYTES,
            f"final physical CHR size changed: {len(actual)}")
    planes = plane_dump_path.read_bytes()
    require(len(planes) == PLANE_DUMP_SIZE,
            "final CHR grading lacks the exact physical-plane dump")
    metadata = parse_key_values(metadata_path)
    try:
        lcdc = int(metadata["lcdc"], 16)
    except (KeyError, ValueError) as error:
        raise LiveError("final CHR metadata is malformed") from error
    require(len(canonical_bg_art) == 0x1000
            and len(canonical_hazard_bank1_art) == 192,
            "canonical final CHR oracle is incomplete")

    tiles_blob = planes[:0x800]
    attrs_blob = planes[0x800:0x1000]
    owned = tuple(
        row * 32 + column
        for row in range(24)
        for column in range(24)
    )
    references: dict[tuple[int, int], tuple[str, int]] = {}
    for map_index, map_name in enumerate(("9800", "9C00")):
        tiles = tiles_blob[map_index * 0x400:(map_index + 1) * 0x400]
        attrs = attrs_blob[map_index * 0x400:(map_index + 1) * 0x400]
        for offset in owned:
            key = ((attrs[offset] >> 3) & 1, tiles[offset])
            references.setdefault(key, (map_name, offset))

    illegal: list[tuple[int, int]] = []
    mismatches: list[dict[str, Any]] = []
    byte_mismatches = 0
    for bank, tile in sorted(references):
        expected: bytes | None = None
        if bank == 0:
            expected = canonical_bg_art[tile * 16:(tile + 1) * 16]
        elif capture_label in HAZARD_CAPTURE_LABELS:
            if 0x64 <= tile <= 0x69:
                base = (tile - 0x64) * 16
                expected = canonical_hazard_bank1_art[base:base + 16]
            elif 0x74 <= tile <= 0x79:
                base = 96 + (tile - 0x74) * 16
                expected = canonical_hazard_bank1_art[base:base + 16]
        if expected is None:
            illegal.append((bank, tile))
            continue
        address = bank * 0x2000 + _stage1_chr_address(tile, lcdc)
        observed = actual[address:address + 16]
        differences = sum(
            left != right for left, right in zip(
                observed, expected, strict=True
            )
        )
        if differences:
            byte_mismatches += differences
            map_name, offset = references[(bank, tile)]
            mismatches.append({
                "bank": bank,
                "tile": f"{tile:02X}",
                "address": f"{address:04X}",
                "map": map_name,
                "offset": f"{offset:03X}",
                "actual_sha256": sha256_bytes(observed),
                "expected_sha256": sha256_bytes(expected),
                "byte_mismatches": differences,
            })
    return {
        "path": str(chr_path.resolve()),
        "sha256": sha256(chr_path),
        "bytes": len(actual),
        "referenced_patterns": len(references),
        "bank0_patterns": sum(bank == 0 for bank, _tile in references),
        "bank1_patterns": sum(bank == 1 for bank, _tile in references),
        "illegal_bank1_patterns": len(illegal),
        "pattern_mismatches": len(mismatches),
        "byte_mismatches": byte_mismatches,
        "first_mismatches": mismatches[:32],
    }


def is_yellow(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return red >= 220 and green >= 180 and blue <= 100


def is_red_or_orange(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return red >= 180 and red >= green + 50 and red >= blue + 40


def is_magenta(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return red >= 120 and green <= 80 and blue >= 100


def is_red_or_green(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return (
        red >= 150 and red >= green + 60 and red >= blue + 50
    ) or (
        green >= 120 and green >= red + 35 and green >= blue + 20
    )


def is_achromatic_dark(color: tuple[int, int, int]) -> bool:
    return max(color) <= 200 and max(color) - min(color) <= 8


def is_gray(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return 45 <= red <= 200 and abs(red - green) <= 8 and (
        max(color) - min(color) <= 8 or 15 <= blue - red <= 80
    )


def is_floor_light(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return (red >= 145 and green >= 145 and blue >= 180) or min(color) >= 235


def longest_yellow_run(pixels: Sequence[tuple[int, int, int]]) -> int:
    longest = 0
    for y in range(PLAYFIELD_HEIGHT):
        run = 0
        for x in range(SCREEN_WIDTH):
            if is_yellow(pixels[y * SCREEN_WIDTH + x]):
                run += 1
                longest = max(longest, run)
            else:
                run = 0
    return longest


def magenta_outside_actor(pixels: Sequence[tuple[int, int, int]]) -> int:
    return sum(
        is_magenta(color) and not (64 <= x < 96 and 32 <= y < 104)
        for y in range(PLAYFIELD_HEIGHT)
        for x, color in enumerate(
            pixels[y * SCREEN_WIDTH:(y + 1) * SCREEN_WIDTH]
        )
    )


def edge_component(pixels: Sequence[tuple[int, int, int]]) -> set[int]:
    usable = [
        is_achromatic_dark(color)
        for color in pixels[:SCREEN_WIDTH * PLAYFIELD_HEIGHT]
    ]
    seen: set[int] = set()
    queue: deque[int] = deque()
    for y in range(PLAYFIELD_HEIGHT):
        for x in (0, SCREEN_WIDTH - 1):
            index = y * SCREEN_WIDTH + x
            if usable[index] and index not in seen:
                seen.add(index)
                queue.append(index)
    while queue:
        index = queue.popleft()
        x, y = index % SCREEN_WIDTH, index // SCREEN_WIDTH
        for next_x, next_y in (
            (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1),
        ):
            if not (0 <= next_x < SCREEN_WIDTH
                    and 0 <= next_y < PLAYFIELD_HEIGHT):
                continue
            next_index = next_y * SCREEN_WIDTH + next_x
            if usable[next_index] and next_index not in seen:
                seen.add(next_index)
                queue.append(next_index)
    return seen


def mask_sha256(indices: Iterable[int]) -> str:
    packed = bytearray((SCREEN_WIDTH * PLAYFIELD_HEIGHT + 7) // 8)
    for index in indices:
        require(0 <= index < SCREEN_WIDTH * PLAYFIELD_HEIGHT,
                "operator visual mask index is outside the playfield")
        packed[index // 8] |= 1 << (index % 8)
    return sha256_bytes(bytes(packed))


def operator_visual_oracle(capture_label: str) -> dict[str, Any]:
    """Rebuild and verify masks from a hash-pinned operator screenshot."""
    fixture = json.loads(VISUAL_ORACLE_FIXTURE.read_text())
    require(
        fixture.get("schema")
        == "penta-stage1-scene0b-operator-visual-oracle-v1",
        "wrong scene-$0B operator visual-oracle schema",
    )
    require(
        fixture.get("mask_encoding")
        == "sha256-lsb0-bitset-over-160x112-playfield",
        "scene-$0B operator visual mask encoding changed",
    )
    require(fixture.get("reviewed_wall_artifact_x_ranges") == [
        [0, 24], [136, 160],
    ], "scene-$0B reviewed wall-artifact regions changed")
    thresholds = fixture.get("thresholds")
    require(thresholds == {
        "wall_chromatic_pixels": 2,
        "wall_cleared_pixels": 8,
        "fixture_forbidden_chromatic_pixels": 2,
        "post_close_persistence_percent": 50,
    }, "scene-$0B reviewed visual thresholds changed")

    specifications = fixture.get("captures")
    require(isinstance(specifications, list) and len(specifications) == 2,
            "scene-$0B visual oracle must bind both operator captures")
    by_label = {item.get("label"): item for item in specifications}
    require(set(by_label) == {
        "operator-corrupted-walls", "operator-low-health-menu-loaded",
    }, "scene-$0B visual oracle capture labels changed")
    require(capture_label in by_label,
            f"scene-$0B visual oracle has no capture {capture_label}")

    capture_contract = load_capture_contract()
    captures = {
        item["label"]: item for item in capture_evidence(capture_contract)
    }
    archived = capture_contract["archived_incompatible_capture"]
    archived_path = (ROOT / archived["path"]).resolve()
    require(sha256(archived_path) == archived["sha256"],
            "archived incompatible wall capture hash changed")
    captures[archived["label"]] = {
        "label": archived["label"],
        "path": str(archived_path),
        "sha256": archived["sha256"],
    }
    spec = by_label[capture_label]
    capture = captures[capture_label]
    require(spec.get("capture_sha256") == capture["sha256"],
            "scene-$0B visual oracle binds another operator capture")
    with Image.open(Path(capture["path"])) as source:
        image = source.convert("RGB")
        require(image.size == (SCREEN_WIDTH, SCREEN_HEIGHT),
                "scene-$0B operator visual-oracle geometry changed")
        pixels = tuple(image.getdata())
    rgb = bytes(channel for color in pixels for channel in color)
    require(sha256_bytes(rgb) == spec.get("rgb_sha256"),
            "scene-$0B operator screenshot RGB hash changed")

    wall = frozenset(edge_component(pixels))
    forbidden_chromatic = frozenset(
        index for index, color in enumerate(
            pixels[:SCREEN_WIDTH * PLAYFIELD_HEIGHT]
        )
        if (is_red_or_green(color) or is_magenta(color))
        and (
            index % SCREEN_WIDTH < 24
            or index % SCREEN_WIDTH >= 136
        )
    )
    require(len(wall) == spec.get("wall_mask_pixels")
            and mask_sha256(wall) == spec.get("wall_mask_sha256"),
            "scene-$0B reviewed fixture wall mask changed")
    require(
        len(forbidden_chromatic)
        == spec.get("forbidden_chromatic_pixels")
        and mask_sha256(forbidden_chromatic)
        == spec.get("forbidden_chromatic_mask_sha256"),
        "scene-$0B reviewed fixture chromatic mask changed",
    )
    require(spec.get("wall_height") in {96, PLAYFIELD_HEIGHT},
            "scene-$0B reviewed wall height changed")
    require(isinstance(spec.get("forbidden_chromatic_active"), bool),
            "scene-$0B forbidden-chromatic policy is invalid")
    return {
        "capture_sha256": capture["sha256"],
        "rgb_sha256": spec["rgb_sha256"],
        "pixels": pixels,
        "wall_mask": wall,
        "wall_mask_sha256": spec["wall_mask_sha256"],
        "wall_height": spec["wall_height"],
        "forbidden_chromatic_mask": forbidden_chromatic,
        "forbidden_chromatic_active": spec["forbidden_chromatic_active"],
        "thresholds": thresholds,
    }


def expanded(indices: Iterable[int], radius: int) -> set[int]:
    result: set[int] = set()
    for index in indices:
        x, y = index % SCREEN_WIDTH, index // SCREEN_WIDTH
        for next_y in range(max(0, y - radius),
                            min(PLAYFIELD_HEIGHT, y + radius + 1)):
            result.update(range(
                next_y * SCREEN_WIDTH + max(0, x - radius),
                next_y * SCREEN_WIDTH + min(SCREEN_WIDTH, x + radius + 1),
            ))
    return result


def gray_near_hazard(
    pixels: Sequence[tuple[int, int, int]], excluded: set[int] | None = None,
) -> int:
    material = {
        index for index, color in enumerate(
            pixels[:SCREEN_WIDTH * PLAYFIELD_HEIGHT]
        ) if is_red_or_orange(color) or is_yellow(color)
    }
    neighborhood = expanded(material, 5)
    ignored = excluded or set()
    return sum(
        index in neighborhood and index not in ignored and is_gray(color)
        for index, color in enumerate(
            pixels[:SCREEN_WIDTH * PLAYFIELD_HEIGHT]
        )
    )


def load_rendered_frames(prefix: Path) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for path in prefix.parent.glob(prefix.name + ".frame*.png"):
        match = SCREENSHOT_RE.search(path.name)
        if match is None:
            continue
        with Image.open(path) as source:
            image = source.convert("RGB")
            require(image.size == (SCREEN_WIDTH, SCREEN_HEIGHT),
                    f"wrong screenshot geometry {image.size}: {path}")
            pixels = tuple(image.getdata())
        frames.append({
            "sample": int(match.group("sample")),
            "phase": match.group("phase"),
            "path": path.resolve(),
            "sha256": sha256(path),
            "rgb_sha256": sha256_bytes(
                bytes(channel for color in pixels for channel in color)
            ),
            "pixels": pixels,
        })
    frames.sort(key=lambda row: row["sample"])
    require(frames and [row["sample"] for row in frames]
            == list(range(1, len(frames) + 1)),
            "rendered screenshot sequence is incomplete")
    return frames


def visual_metrics(
    frames: Sequence[dict[str, Any]], capture_label: str,
) -> dict[str, int]:
    post_close = [row for row in frames if row["phase"] == "post_close"]
    require(len(post_close) >= 24,
            "fewer than 24 final post-close visual-oracle frames")
    oracle_label = (
        "operator-low-health-menu-loaded"
        if capture_label
        == "candidate-native-closed-after-operator-low-health"
        else capture_label
    )
    oracle = operator_visual_oracle(oracle_label)
    wall = oracle["wall_mask"]
    excluded_wall = set(wall)
    fixture_pixels = oracle["pixels"]
    thresholds = oracle["thresholds"]
    chromatic = lambda color: is_red_or_green(color) or is_magenta(color)
    baseline_white: dict[tuple[int, int], int] = {}
    for y in range(0, PLAYFIELD_HEIGHT - 7, 8):
        for x in range(0, SCREEN_WIDTH, 8):
            baseline_white[(x, y)] = sum(
                color == (255, 255, 255)
                for scanline in range(y, y + 8)
                for color in fixture_pixels[
                    scanline * SCREEN_WIDTH + x:
                    scanline * SCREEN_WIDTH + x + 8
                ]
            )

    counts = {
        "wall_edge_artifact_frames": 0,
        "red_green_artifact_frames": 0,
        "clear_tile_frames": 0,
        "weird_edge_tile_frames": 0,
        "postsettle_wall_edge_artifact_frames": 0,
        "postsettle_red_green_artifact_frames": 0,
        "postsettle_weird_edge_tile_frames": 0,
        "yellow_trail_frames": 0,
        "gray_spike_frames": 0,
    }
    candidate_static = {
        index for index in range(SCREEN_WIDTH * PLAYFIELD_HEIGHT)
        if all(
            is_achromatic_dark(item["pixels"][index])
            or is_gray(item["pixels"][index])
            for item in post_close[-24:]
        )
    }
    for frame in frames:
        if frame["phase"] == "captured":
            continue
        pixels = frame["pixels"]
        height = (
            MENU_WINDOW_TOP
            if frame["phase"] in {"menu_entry", "menu_hold", "menu_exit"}
            else PLAYFIELD_HEIGHT
        )
        wall_height = min(height, oracle["wall_height"])
        # Every rendered frame is graded against immutable operator-authored
        # regions.  Never derive a mask from candidate post-close output: that
        # suppresses short flashes and moving corruption by construction.
        # The complete connected wall/edge masks intersect legitimate moving
        # sprites, so screenshot chroma authority is the exact hash-pinned
        # operator signature below. Background corruption at every other wall
        # pixel is covered independently by all-frame map, attr, CRAM, and
        # immutable tile-pattern checks in the Lua state trace.
        chromatic_indices: Iterable[int] = ()
        cleared_indices = wall
        fixture_indices = oracle["forbidden_chromatic_mask"]
        chromatic_wall = sum(
            index // SCREEN_WIDTH < wall_height
            and chromatic(pixels[index])
            for index in chromatic_indices
        )
        cleared_wall = sum(
            index // SCREEN_WIDTH < wall_height
            and is_floor_light(pixels[index])
            for index in cleared_indices
        )
        fixture_chromatic = (
            oracle["forbidden_chromatic_active"]
            and sum(
                index // SCREEN_WIDTH < wall_height
                and chromatic(pixels[index])
                for index in fixture_indices
            ) >= thresholds["fixture_forbidden_chromatic_pixels"]
        )
        chromatic_failure = (
            chromatic_wall >= thresholds["wall_chromatic_pixels"]
            or fixture_chromatic
        )
        cleared_failure = (
            cleared_wall >= thresholds["wall_cleared_pixels"]
        )
        if chromatic_failure or cleared_failure:
            counts["wall_edge_artifact_frames"] += 1
            if frame["phase"] != "repair_settle":
                counts["postsettle_wall_edge_artifact_frames"] += 1
        if chromatic_failure:
            counts["red_green_artifact_frames"] += 1
            if frame["phase"] != "repair_settle":
                counts["postsettle_red_green_artifact_frames"] += 1
        if (
            chromatic_wall >= thresholds["wall_chromatic_pixels"]
            or fixture_chromatic or cleared_failure
        ):
            counts["weird_edge_tile_frames"] += 1
            if frame["phase"] != "repair_settle":
                counts["postsettle_weird_edge_tile_frames"] += 1

        clear = False
        for y in range(0, height - 7, 8):
            for x in range(8, SCREEN_WIDTH - 8, 8):
                white = sum(
                    color == (255, 255, 255)
                    for scanline in range(y, y + 8)
                    for color in pixels[
                        scanline * SCREEN_WIDTH + x:
                        scanline * SCREEN_WIDTH + x + 8
                    ]
                )
                if white >= 62 and baseline_white[(x, y)] < 40:
                    clear = True
                    break
            if clear:
                break
        if clear:
            counts["clear_tile_frames"] += 1
        if longest_yellow_run(pixels) >= 12:
            counts["yellow_trail_frames"] += 1

        gray_suspects = gray_near_hazard(
            pixels, excluded_wall | candidate_static
        )
        if gray_suspects >= 3:
            counts["gray_spike_frames"] += 1
    return counts


def archived_negative_controls() -> dict[str, bool]:
    oracles = {
        label: operator_visual_oracle(label)
        for label in (
            "operator-corrupted-walls", "operator-low-health-menu-loaded",
        )
    }
    pixels = {label: row["pixels"] for label, row in oracles.items()}
    clean = tuple((165, 165, 255) for _ in range(SCREEN_WIDTH * SCREEN_HEIGHT))
    return {
        "operator_capture_rgb_and_wall_masks_are_fixture_pinned": all(
            len(row["wall_mask"]) > 0 and len(row["rgb_sha256"]) == 64
            for row in oracles.values()
        ),
        "candidate_frames_do_not_define_wall_masks": all(
            row["wall_mask_sha256"] == mask_sha256(row["wall_mask"])
            for row in oracles.values()
        ),
        "archived_corrupted_wall_red_green_edge_detected": (
            sum(
                is_red_or_green(
                    pixels["operator-corrupted-walls"][index]
                ) or is_magenta(
                    pixels["operator-corrupted-walls"][index]
                )
                for index in oracles[
                    "operator-corrupted-walls"
                ]["forbidden_chromatic_mask"]
            ) >= 2
        ),
        "archived_low_health_yellow_trail_detected": (
            longest_yellow_run(pixels["operator-low-health-menu-loaded"]) >= 12
        ),
        "archived_low_health_gray_spikes_detected": (
            gray_near_hazard(
                pixels["operator-low-health-menu-loaded"]
            ) >= 3
        ),
        "neutral_control_has_no_magenta_classifier_signature": (
            magenta_outside_actor(clean) == 0
        ),
        "neutral_control_has_no_yellow_trail_signature": (
            longest_yellow_run(clean) == 0
        ),
        "neutral_control_has_no_gray_spike_signature": (
            gray_near_hazard(clean) == 0
        ),
    }


def write_state_trace(rows: Sequence[dict[str, Any]], path: Path) -> None:
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(
                {"schema": "penta-stage1-scene0b-state-sample-v1", **row},
                sort_keys=True, separators=(",", ":"),
            ) + "\n")


def write_rendered_manifest(
    frames: Sequence[dict[str, Any]], path: Path,
    capture_label: str, replay_index: int,
) -> str:
    rows = [
        {
            "sample": frame["sample"], "phase": frame["phase"],
            "path": str(frame["path"]), "sha256": frame["sha256"],
            "rgb_sha256": frame["rgb_sha256"],
        }
        for frame in frames
    ]
    semantic = sha256_bytes(json.dumps(
        [{key: row[key] for key in ("sample", "phase", "rgb_sha256")}
         for row in rows],
        sort_keys=True, separators=(",", ":"),
    ).encode())
    path.write_text(json.dumps({
        "schema": "penta-stage1-scene0b-rendered-manifest-v1",
        "capture_label": capture_label,
        "replay_index": replay_index,
        "semantic_sha256": semantic,
        "frames": rows,
    }, indent=2, sort_keys=True) + "\n")
    return semantic


def semantic_fingerprint(
    rows: Sequence[dict[str, Any]], frames: Sequence[dict[str, Any]],
) -> str:
    payload = {
        "trace": list(rows),
        "rendered": [
            (frame["sample"], frame["phase"], frame["rgb_sha256"])
            for frame in frames
        ],
    }
    return sha256_bytes(json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode())


def run_process(
    command: Sequence[str], environment: dict[str, str], cwd: Path,
    log: Path, marker: Path, timeout: float, *, startup: Path,
    startup_token: str, ready: Path,
    core_ready: Path,
    startup_timeout: float = STARTUP_TIMEOUT_SECONDS,
    ready_timeout: float = READY_TIMEOUT_SECONDS,
    core_timeout: float = CORE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    timed_out = False
    startup_failure: str | None = None
    startup_seen = False
    ready_seen = False
    core_seen = False
    completion_status: str | None = None
    with log.open("wb") as stream:
        process = subprocess.Popen(
            list(command), cwd=cwd, env=environment,
            stdout=stream, stderr=subprocess.STDOUT,
        )
        launched_at = time.monotonic()
        deadline = launched_at + timeout
        startup_deadline = launched_at + startup_timeout
        ready_deadline: float | None = None
        core_deadline: float | None = None
        try:
            while time.monotonic() < deadline:
                now = time.monotonic()
                if not startup_seen and startup.is_file():
                    observed = startup.read_text().strip()
                    if observed != startup_token:
                        startup_failure = "probe startup token differs"
                        break
                    startup_seen = True
                    ready_deadline = now + ready_timeout
                if startup_seen and not ready_seen and ready.is_file():
                    observed = ready.read_text().strip()
                    if observed != startup_token:
                        startup_failure = "probe ready token differs"
                        break
                    ready_seen = True
                    core_deadline = now + core_timeout
                if ready_seen and not core_seen and core_ready.is_file():
                    observed = core_ready.read_text().strip()
                    if observed != startup_token:
                        startup_failure = "probe core-ready token differs"
                        break
                    core_seen = True
                if ready_seen and marker.is_file():
                    try:
                        completion_status = parse_completion_marker(
                            marker, startup_token
                        )
                    except LiveError as error:
                        startup_failure = str(error)
                    break
                if not startup_seen and now >= startup_deadline:
                    startup_failure = "probe startup handshake is missing"
                    break
                if (startup_seen and not ready_seen
                        and ready_deadline is not None
                        and now >= ready_deadline):
                    startup_failure = (
                        "probe started but did not create its ready trace"
                    )
                    break
                if (ready_seen and not core_seen
                        and core_deadline is not None
                        and now >= core_deadline):
                    startup_failure = (
                        "probe registered callbacks but did not acquire its "
                        "core VRAM accessor"
                    )
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            else:
                timed_out = True
        finally:
            teardown_outcome = stop_owned_process(process)
    if timed_out:
        process_log = log.with_name("timeout-process-check.log")
        read_only_process_check(process_log)
        raise LiveError(
            f"guarded scene-$0B replay timed out after {timeout:.1f}s; "
            f"process check: {process_log}"
        )
    if process.returncode == 75:
        raise SingleFlightBusy("single-flight slot is already owned (exit 75)")
    if (startup_failure is not None or not startup_seen or not ready_seen
            or (not core_seen and completion_status != "fail")):
        process_log = log.with_name("startup-process-check.log")
        read_only_process_check(process_log)
        detail = startup_failure or (
            "launcher exited before the probe startup handshake"
            if not startup_seen
            else (
                "launcher exited before the probe ready trace"
                if not ready_seen
                else "launcher exited before the core VRAM accessor was ready"
            )
        )
        raise LiveError(
            f"scene-$0B {detail}; launcher status={process.returncode}; "
            f"log={log}; process check={process_log}"
        )
    return {
        **teardown_outcome,
        "completion_status": completion_status,
    }


def run_replay(
    *, candidate: Path, candidate_sha256: str,
    capture: dict[str, Any], replay_index: int, output: Path,
    timeout: float, cache_audit: bool = False,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    runtime = output / "runtime"
    runtime.mkdir()
    runtime_rom = runtime / "candidate.gb"
    runtime_state = runtime / "capture.ss0"
    shutil.copy2(candidate, runtime_rom)
    require(sha256(runtime_rom) == candidate_sha256,
            "isolated runtime candidate hash changed")
    runtime_rom_bytes = runtime_rom.read_bytes()
    presentation_publication = publication_boundary(runtime_rom_bytes)
    presentation_pc = int(presentation_publication["pc"])
    presentation_segment = 0x0D if presentation_pc >= 0x4000 else 0
    canonical_lut = runtime_rom_bytes[
        STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 0x100
    ]
    require(len(canonical_lut) == 0x100
            and sha256_bytes(canonical_lut) in {
                STAGE1_RELEASE_LUT_SHA256,
                STAGE1_COMPILED_TOOTH_LUT_SHA256,
            },
            "isolated runtime ROM lacks the reviewed canonical Stage-1 LUT")
    immutable_source = capture_immutable_source(capture)
    immutable_stage1_tables = capture_sram(Path(capture["path"]))[:0x800]
    require(len(immutable_stage1_tables) == 0x800,
            "operator Stage-1 SRAM tables are incomplete")
    canonical_bg_art = canonical_stage1_bg_art(runtime_rom_bytes)
    canonical_hazard_bank1_art = canonical_stage1_hazard_bank1_art(
        runtime_rom_bytes
    )
    hazard_contract = load_hazard_tile_contract()
    hazard_phase_payload = canonical_scene0b_hazard_phase_payload()
    if capture["label"] in HAZARD_CAPTURE_LABELS:
        require(immutable_source == hazard_contract.immutable_source,
                "low-health capture differs from exact hazard oracle source")
    expected_bg_cram = expected_stage1_bg_cram(runtime_rom_bytes)
    runtime_oracles = (
        immutable_source + immutable_stage1_tables + canonical_bg_art
        + canonical_hazard_bank1_art + hazard_phase_payload
        + expected_bg_cram
    )
    require(len(runtime_oracles) == RUNTIME_ORACLE_BYTES,
            "runtime oracle bundle size changed")
    retarget = retarget_capture(Path(capture["path"]), runtime_state, runtime_rom)

    prefix = output / "scene0b"
    report_path = Path(str(prefix) + ".report")
    raw_trace = Path(str(prefix) + ".trace.tsv")
    plane_dump_path = Path(str(prefix) + ".planes.bin")
    plane_metadata_path = Path(str(prefix) + ".planes.meta")
    chr_dump_path = Path(str(prefix) + ".chr.bin")
    runtime_oracles_path = Path(str(prefix) + ".runtime-oracles.bin")
    cache_audit_path = output / "cache-audit.tsv"
    startup = Path(str(prefix) + ".startup")
    ready = Path(str(prefix) + ".ready")
    core_ready = Path(str(prefix) + ".core-ready")
    config_ready = Path(str(prefix) + ".config-ready")
    trace_ready = Path(str(prefix) + ".trace-ready")
    cache_audit_ready = Path(str(prefix) + ".cache-audit-ready")
    marker = Path(str(prefix) + ".done")
    emulator_log = output / "emulator.log"
    initial_menu = int(capture["captured_state"]["FFE4"], 16)
    environment = os.environ.copy()
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        environment.pop(key, None)
    startup_token = secrets.token_hex(32)
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "PENTA_SCENE0B_OUT": str(prefix),
        "PENTA_SCENE0B_STATE": str(runtime_state),
        "PENTA_SCENE0B_STARTUP_TOKEN": startup_token,
        "PENTA_SCENE0B_CAPTURE_LABEL": capture["label"],
        "PENTA_SCENE0B_INITIAL_MENU": str(initial_menu),
        "PENTA_SCENE0B_FRAME_LIMIT": str(FRAME_LIMIT),
        "PENTA_SCENE0B_CAPTURE_FRAMES": str(CAPTURE_FRAMES),
        "PENTA_SCENE0B_REPAIR_SETTLE": str(REPAIR_SETTLE_FRAMES),
        "PENTA_SCENE0B_MENU_HOLD": str(MENU_HOLD_FRAMES),
        "PENTA_SCENE0B_POST_CLOSE": str(POST_CLOSE_FRAMES),
        "PENTA_SCENE0B_IMMUTABLE_SOURCE": immutable_source.hex().upper(),
        "PENTA_SCENE0B_STAGE1_TABLES": (
            immutable_stage1_tables.hex().upper()
        ),
        "PENTA_SCENE0B_CANONICAL_BG_ART": (
            canonical_bg_art.hex().upper()
        ),
        "PENTA_SCENE0B_CANONICAL_HAZARD_BANK1_ART": (
            canonical_hazard_bank1_art.hex().upper()
        ),
        "PENTA_SCENE0B_HAZARD_PHASES": (
            hazard_phase_payload.hex().upper()
        ),
        "PENTA_SCENE0B_EXPECTED_BG_CRAM": expected_bg_cram.hex().upper(),
        "PENTA_SCENE0B_PRESENTATION_PC": f"{presentation_pc:04X}",
        "PENTA_SCENE0B_PRESENTATION_FALLBACK_PC": (
            f"{presentation_pc + 8:04X}"
        ),
        "PENTA_SCENE0B_PRESENTATION_SEGMENT": (
            f"{presentation_segment:02X}"
        ),
    })
    if cache_audit:
        environment["PENTA_SCENE0B_CACHE_AUDIT_OUT"] = str(cache_audit_path)
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    emulator_binary = default_qt_emulator()
    command = launcher_command(runtime_rom, runtime)
    launch_contract_path = output / "launch-contract.json"
    launch_started_at_ns = time.time_ns()
    launch_contract = {
        "schema": "penta-stage1-scene0b-launch-contract-v6",
        "command": command,
        "cwd": str(output),
        "output_prefix": str(prefix),
        "capture_label": capture["label"],
        "replay_index": replay_index,
        "startup_token_sha256": sha256_bytes(startup_token.encode()),
        "launch_started_at_ns": launch_started_at_ns,
        "initial_menu": initial_menu,
        "frame_limit": FRAME_LIMIT,
        "capture_frames": CAPTURE_FRAMES,
        "repair_settle_frames": REPAIR_SETTLE_FRAMES,
        "menu_hold_frames": MENU_HOLD_FRAMES,
        "post_close_frames": POST_CLOSE_FRAMES,
        "launcher_sha256": sha256(LAUNCHER),
        "singleflight_implementation_sha256": sha256(
            SINGLEFLIGHT_IMPLEMENTATION
        ),
        "emulator_path": str(emulator_binary),
        "emulator_sha256": sha256(emulator_binary),
        "probe_sha256": sha256(PROBE),
        "runtime_rom_path": str(runtime_rom),
        "runtime_rom_sha256": sha256(runtime_rom),
        "runtime_state_path": str(runtime_state),
        "runtime_state_sha256": sha256(runtime_state),
        "immutable_source_sha256": sha256_bytes(immutable_source),
        "immutable_stage1_tables_sha256": sha256_bytes(
            immutable_stage1_tables
        ),
        "canonical_bg_art_sha256": sha256_bytes(canonical_bg_art),
        "canonical_hazard_bank1_art_sha256": sha256_bytes(
            canonical_hazard_bank1_art
        ),
        "hazard_oracle_fixture_sha256": hazard_contract.fixture_sha256,
        "hazard_phase_payload_sha256": sha256_bytes(
            hazard_phase_payload
        ),
        "expected_bg_cram_sha256": sha256_bytes(expected_bg_cram),
        "runtime_oracle_bundle_sha256": sha256_bytes(runtime_oracles),
        # Final byte/time-bound claims are added only after the exact child
        # has stopped and every token-bearing sidecar has been parsed.
        "cache_audit": str(cache_audit_path) if cache_audit else None,
        "cache_audit_ready": (
            str(cache_audit_ready) if cache_audit else None
        ),
        "startup_timeout_seconds": STARTUP_TIMEOUT_SECONDS,
        "ready_timeout_seconds": READY_TIMEOUT_SECONDS,
        "core_timeout_seconds": CORE_TIMEOUT_SECONDS,
        "teardown_policy": TEARDOWN_POLICY,
    }
    launch_contract_path.write_text(
        json.dumps(launch_contract, indent=2, sort_keys=True) + "\n"
    )
    process_outcome = run_process(
        command, environment, output, emulator_log, marker, timeout,
        startup=startup, startup_token=startup_token, ready=ready,
        core_ready=core_ready,
    )
    launch_contract["provisional_process_outcome"] = process_outcome
    launch_contract_path.write_text(
        json.dumps(launch_contract, indent=2, sort_keys=True) + "\n"
    )
    marker_status = (
        parse_completion_marker(marker, startup_token)
        if marker.is_file() else ""
    )
    if marker_status != "ok":
        reason = "missing-completion-marker"
        if report_path.is_file():
            reason = parse_key_values(report_path).get("reason", reason)
        raise LiveError(
            f"scene-$0B probe failed before replay: {reason}; "
            f"see {emulator_log}"
        )
    require(core_ready.is_file()
            and core_ready.read_text().strip() == startup_token,
            "scene-$0B probe lacks its token-bound core-ready marker")
    require(config_ready.is_file()
            and config_ready.read_text().strip() == startup_token,
            "scene-$0B probe lacks its token-bound config-ready marker")
    require(runtime_oracles_path.is_file()
            and runtime_oracles_path.read_bytes() == runtime_oracles,
            "scene-$0B child parsed different runtime oracle bytes")
    require(trace_ready.is_file()
            and trace_ready.read_text().strip() == startup_token,
            "scene-$0B probe lacks its token-bound trace-ready marker")
    if cache_audit:
        require(cache_audit_ready.is_file()
                and cache_audit_ready.read_text().strip() == startup_token,
                "scene-$0B cache audit lacks its token-bound ready marker")
    require(process_outcome.get("completion_status") == "ok",
            "scene-$0B launcher did not observe authenticated completion")
    report = parse_key_values(report_path)
    require(report.get("status") == "ok" and report.get("reason") == "complete",
            f"scene-$0B probe failed: {report.get('reason', 'unknown')}")
    require(report.get("startup_token") == startup_token,
            "scene-$0B report token differs")
    require(report.get("capture_label") == capture["label"],
            "scene-$0B probe reports another capture label")
    require(int(report.get("state_loaded", "0")) == 1,
            "scene-$0B probe did not load its exact state")
    require(int(report.get("initial_menu", "-1")) == initial_menu,
            "scene-$0B probe initial menu state changed")
    require(int(report.get("initial_scene", "-1"), 16) == 0x0B,
            "scene-$0B probe did not start in scene $0B")
    require(int(report.get("scene_violation_frames", "-1")) == 0,
            "scene-$0B replay left the captured scene")
    require(int(report.get("active_violation_frames", "-1")) == 0,
            "scene-$0B replay left the captured active state")
    require(int(report.get("observation_restore_failures", "-1")) == 0,
            "scene-$0B probe did not restore VBK after observation")
    require(int(report.get("oam_dma_unreadable_frames", "-1")) >= 0,
            "scene-$0B probe lacks its OAM-DMA deferral count")
    require(int(report.get("baseline_ready", "0")) == 1,
            "scene-$0B probe never captured a native post-repair baseline")
    require(int(report.get("attr_checked_samples", "0")) >= 24,
            "scene-$0B probe has fewer than 24 readable attribute samples")
    require(int(report.get("semantic_checked_samples", "0")) >= 24,
            "scene-$0B probe has fewer than 24 immutable semantic samples")
    require(int(report.get("attr_unreadable_samples", "-1")) == 0,
            "scene-$0B probe has unreadable post-baseline attribute samples")
    require(int(report.get("semantic_unreadable_samples", "-1")) == 0,
            "scene-$0B probe has unreadable immutable semantic samples")
    require(int(report.get("immutable_tile_checked_samples", "0")) >= 24,
            "scene-$0B probe has fewer than 24 immutable tile samples")
    require(int(report.get("immutable_tile_unreadable_samples", "-1")) == 0,
            "scene-$0B probe has unreadable immutable tile samples")
    require(int(report.get("cram_checked_samples", "0")) >= 24,
            "scene-$0B probe has fewer than 24 Stage-1 CRAM samples")
    require(int(report.get("cram_unreadable_samples", "-1")) == 0,
            "scene-$0B probe has unreadable Stage-1 CRAM samples")
    require(int(report.get("plane_dump_written", "0")) == 1,
            "scene-$0B probe did not dump both final physical maps")
    require(plane_dump_path.is_file() and plane_metadata_path.is_file(),
            "scene-$0B final physical-plane artifacts are missing")
    physical_planes = physical_plane_receipt(
        plane_dump_path, plane_metadata_path, canonical_lut,
        immutable_source, capture["label"],
    )
    final_bg_chr = final_bg_chr_receipt(
        chr_dump_path, plane_dump_path, plane_metadata_path,
        canonical_bg_art, canonical_hazard_bank1_art, capture["label"],
    )
    require(
        final_bg_chr["referenced_patterns"] > 0
        and final_bg_chr["illegal_bank1_patterns"] == 0
        and final_bg_chr["pattern_mismatches"] == 0
        and final_bg_chr["byte_mismatches"] == 0,
        "final referenced physical BG CHR differs from canonical art",
    )
    if capture["label"] in HAZARD_CAPTURE_LABELS:
        require(final_bg_chr["bank1_patterns"] > 0,
                "hazard replay did not exercise bank-one CHR")
    require(physical_planes["sample"]
            == int(report.get("plane_dump_sample", "-1"))
            and physical_planes["frame"]
            == int(report.get("plane_dump_frame", "-1")),
            "physical-plane artifact/report identity differs")

    rows = parse_trace(raw_trace, startup_token)
    require(all((row["lcdc"] & 0x97) == 0x83 for row in rows),
            "scene-$0B changed required display/BG/OBJ LCDC bits")
    cache_rows = parse_cache_audit(cache_audit_path) if cache_audit else []
    frames = load_rendered_frames(prefix)
    require(int(report["semantic_checked_samples"]) == len(rows)
            and int(report["immutable_tile_checked_samples"]) == len(rows)
            and int(report["cram_checked_samples"]) == len(rows),
            "scene-$0B all-frame immutable observation counts differ")
    require(int(report.get("samples", "-1")) == len(rows),
            "scene-$0B probe report/state sample counts differ")
    require(len(rows) == len(frames),
            "scene-$0B rendered/state sample counts differ")
    require(all(
        row["sample"] == frame["sample"] and row["phase"] == frame["phase"]
        for row, frame in zip(rows, frames, strict=True)
    ), "scene-$0B rendered/state sample ordering differs")
    require(
        rows[-1]["phase"] == "post_close"
        and physical_planes["sample"] == rows[-1]["sample"]
        and physical_planes["frame"] == rows[-1]["frame"],
        "scene-$0B final physical planes do not bind the final post-close "
        "sample",
    )
    process_teardown = validate_process_teardown(
        process_outcome, completion_authenticated=True
    )
    launch_completed_at_ns = time.time_ns()
    require(launch_completed_at_ns >= launch_started_at_ns,
            "scene-$0B launch wall clock moved backwards")
    launch_contract.update({
        "launch_completed_at_ns": launch_completed_at_ns,
        "startup": timed_launch_artifact(
            startup, launch_started_at_ns, launch_completed_at_ns
        ),
        "ready": timed_launch_artifact(
            ready, launch_started_at_ns, launch_completed_at_ns
        ),
        "core_ready": timed_launch_artifact(
            core_ready, launch_started_at_ns, launch_completed_at_ns
        ),
        "config_ready": timed_launch_artifact(
            config_ready, launch_started_at_ns, launch_completed_at_ns
        ),
        "trace_ready": timed_launch_artifact(
            trace_ready, launch_started_at_ns, launch_completed_at_ns
        ),
        "done": timed_launch_artifact(
            marker, launch_started_at_ns, launch_completed_at_ns
        ),
        "report": timed_launch_artifact(
            report_path, launch_started_at_ns, launch_completed_at_ns
        ),
        "raw_trace": timed_launch_artifact(
            raw_trace, launch_started_at_ns, launch_completed_at_ns
        ),
        "emulator_log": timed_launch_artifact(
            emulator_log, launch_started_at_ns, launch_completed_at_ns
        ),
    })
    launch_contract["validated_process_teardown"] = process_teardown
    launch_contract_path.write_text(
        json.dumps(launch_contract, indent=2, sort_keys=True) + "\n"
    )
    phase_counts = {
        phase: sum(row["phase"] == phase for row in rows)
        for phase in (
            "captured", "repair_settle", "menu_entry", "menu_hold",
            "menu_exit", "post_close"
        )
    }
    require(phase_counts["captured"] >= CAPTURE_FRAMES,
            "captured-state frame coverage is incomplete")
    require(phase_counts["repair_settle"] >= REPAIR_SETTLE_FRAMES,
            "native repair-settle frame coverage is incomplete")
    require(phase_counts["menu_entry"] >= 1,
            "native menu-entry frame coverage is incomplete")
    require(phase_counts["menu_hold"] >= MENU_HOLD_FRAMES,
            "native menu-hold frame coverage is incomplete")
    require(phase_counts["menu_exit"] >= 1,
            "native menu-exit frame coverage is incomplete")
    require(phase_counts["post_close"] >= POST_CLOSE_FRAMES,
            "post-close frame coverage is incomplete")
    expected_opens = 1
    expected_closes = 1 if initial_menu == 0 else 2
    open_events = int(report.get("menu_open_events", "-1"))
    close_events = int(report.get("menu_close_events", "-1"))
    require(open_events == expected_opens and close_events == expected_closes,
            "native menu transition event counts changed")
    require({row["scene"] for row in rows} == {0x0B},
            "rendered evidence contains a non-$0B scene")

    trace_path = output / "state-trace.jsonl"
    manifest_path = output / "rendered-manifest.json"
    write_state_trace(rows, trace_path)
    write_rendered_manifest(frames, manifest_path, capture["label"], replay_index)
    metrics = visual_metrics(frames, capture["label"])
    visible_attr_mismatch_frames = sum(
        row["attr_mismatches"] > 0 for row in rows
    )
    postrepair_semantic_attr_mismatch_frames = sum(
        row["phase"] != "captured"
        and row["semantic_attr_mismatches"] > 0
        for row in rows
    )
    postsettle_semantic_attr_mismatch_frames = sum(
        row["phase"] not in {"captured", "repair_settle"}
        and row["semantic_attr_mismatches"] > 0
        for row in rows
    )
    postrepair_immutable_tile_mismatch_frames = sum(
        row["phase"] != "captured"
        and row["immutable_tile_mismatches"] > 0
        for row in rows
    )
    postsettle_immutable_tile_mismatch_frames = sum(
        row["phase"] not in {"captured", "repair_settle"}
        and row["immutable_tile_mismatches"] > 0
        for row in rows
    )
    repair_rows = [row for row in rows if row["phase"] == "repair_settle"]
    late_tile_art_mismatch_frames = sum(
        row["tile_art_mismatches"] > 0
        for row in repair_rows[6:]
    ) + sum(
        row["tile_art_mismatches"] > 0
        for row in rows if row["phase"] not in {"captured", "repair_settle"}
    )
    postrepair_bg_cram_mismatch_frames = sum(
        row["phase"] != "captured"
        and row["bg_cram_mismatches"] > 0
        for row in rows
    )
    runtime_lut_mutation_frames = sum(
        row["lut_mismatches"] > 0 for row in rows
    )
    cache_audit_receipt = None
    if cache_audit:
        def reported(name: str) -> int:
            try:
                value = int(report[f"cache_audit_{name}"])
            except (KeyError, ValueError) as error:
                raise LiveError(
                    f"cache-audit report lacks integer {name}"
                ) from error
            require(value >= 0, f"cache-audit {name} is negative")
            return value

        breakpoint_failures = reported("breakpoint_failures")
        watchpoint_failures = reported("watchpoint_failures")
        deferred_wram_frames = reported("deferred_wram_frames")
        require(breakpoint_failures == watchpoint_failures == 0,
                "cache-audit observer installation failed")
        kind_to_report = {
            "epochGate13": "epoch_gate13_hits",
            "epochGate16": "epoch_gate16_hits",
            "installer13": "installer13_hits",
            "installer16": "installer16_hits",
            "epochPublish13": "epoch_publish13_hits",
            "epochPublish16": "epoch_publish16_hits",
            "runtimeDAD7": "runtime_gateway_hits",
            "rst18Route001A": "rst18_route_hits",
            "selfhealEntry6CEA": "selfheal_entry_hits",
            "selfhealRepair6D35": "selfheal_repair_hits",
            "selfhealStart6D4D": "selfheal_start_hits",
            "transactionArmed6DCB": "transaction_armed_hits",
            "displayFlip6E25": "display_flip_hits",
            "commitEffect6E2A": "commit_effect_hits",
            "menuMux6CC5": "menu_mux_hits",
            "menuEffect6CE2": "menu_effect_hits",
            "consumer4100": "consumer_hits",
            "compiler4302": "compiler_hits",
            "publication4354": "publication_hits",
            "postcopy10E2": "postcopy_hits",
            "hazardDispatch6CCE": "hazard_dispatch_hits",
            "hazardHelper6BA7": "hazard_helper_hits",
            "hazardFront61B7": "hazard_front_hits",
            "hazardWrite4300": "hazard_write4300_hits",
            "hazardWrite4500": "hazard_write4500_hits",
        }
        hits = {
            kind: reported(report_name)
            for kind, report_name in kind_to_report.items()
        }
        for kind, count in hits.items():
            require(sum(row["kind"] == kind for row in cache_rows) == count,
                    f"cache-audit {kind} rows do not match report")
        expected_mirrors = {
            "selfhealEntry6CEA": 0x1F,
            "selfhealRepair6D35": 0x1F,
            "selfhealStart6D4D": 0x1F,
            "transactionArmed6DCB": 0x1F,
            "displayFlip6E25": 0x1F,
            "commitEffect6E2A": 0x1F,
            "menuMux6CC5": 0x1F, "menuEffect6CE2": 0x1F,
            "consumer4100": 0x15,
            "compiler4302": 0x01, "publication4354": 0x01,
            "postcopy10E2": 0x01,
            "hazardDispatch6CCE": 0x13,
            "hazardHelper6BA7": 0x13,
            "hazardFront61B7": 0x13,
            "hazardWrite4300": 0x14,
            "hazardWrite4500": 0x14,
        }
        require(all(
            row["ff99"] == expected_mirrors[row["kind"]]
            for row in cache_rows if row["kind"] in expected_mirrors
        ), "cache-audit breakpoint software-bank mirror changed")
        helper_rows = [
            row for row in cache_rows
            if row["kind"] == "hazardHelper6BA7"
        ]
        require(
            helper_rows
            and all(row["ffb7"] == 0x02 for row in helper_rows),
            "cache-audit bank19:$6BA7 owner is not always FFB7=$02",
        )
        require(sum(row["kind"] == "observers-ready" for row in cache_rows) == 1,
                "cache-audit observer-ready row is not unique")
        frame_rows = [row for row in cache_rows if row["kind"] == "frame"]
        require(len(frame_rows) == len(rows),
                "cache-audit per-sample coverage differs from state trace")
        require(all(
            audit["sample"] == state["sample"]
            and audit["frame"] == state["frame"]
            and audit["phase"] == state["phase"]
            and audit["scene"] == state["scene"]
            and audit["room"] == state["room"]
            and audit["active"] == state["active"]
            and audit["menu"] == state["menu"]
            for audit, state in zip(frame_rows, rows, strict=True)
        ), "cache-audit per-sample state binding differs")
        require(all(row["svbk"] == 1 for row in frame_rows),
                "cache-audit has a per-sample record outside WRAM1")
        ordered_selfheal = selfheal_publication_contract(
            cache_rows,
            require_semantic_write=(
                capture["label"] in HAZARD_CAPTURE_LABELS
            ),
        )
        # r314 acceptance binds the exact fixed/RST transaction and its sole
        # delayed acknowledgment; the detailed event/value ordering above is
        # recomputed by selfheal_publication_contract().
        require(
            hits["rst18Route001A"] > 0
            and hits["selfhealEntry6CEA"] > 0
            and hits["selfhealRepair6D35"] == 1
            and hits["selfhealStart6D4D"] == 1
            and hits["transactionArmed6DCB"] == 1
            and hits["displayFlip6E25"] == 1
            and hits["commitEffect6E2A"] == 1,
            "exact r314 repair transaction did not execute once",
        )
        menu_effect_rows = [
            row for row in cache_rows if row["kind"] == "menuEffect6CE2"
        ]
        require(menu_effect_rows and all(
            row["scene"] == 0x0B and row["ffb7"] == 0x02
            and row["svbk"] == 0x01
            and row["df53"] == 0xFF and row["df57"] == 0xFF
            for row in menu_effect_rows
        ), "current menu mux did not invalidate both physical-map caches")

        write_rows = [
            row for row in cache_rows if row["kind"].startswith("write")
        ]
        write_events = reported("write_events")
        transition_events = reported("transition_events")
        require(len(write_rows) == write_events,
                "cache-audit writer rows do not match report")
        require(sum(
            row["old_value"] != row["new_value"] for row in write_rows
        ) == transition_events,
            "cache-audit transition rows do not match report")
        write_counts: dict[str, int] = {}
        transition_counts: dict[str, int] = {}
        for address in (0xDF53, 0xDF54, 0xDF55, 0xDF57, 0xDF58, 0xDF59):
            label = f"{address:04X}"
            write_counts[label] = reported(f"{label}_writes")
            transition_counts[label] = reported(f"{label}_transitions")
            address_rows = [
                row for row in write_rows if row["write_address"] == address
            ]
            require(len(address_rows) == write_counts[label],
                    f"cache-audit {label} writer count differs")
            require(sum(
                row["old_value"] != row["new_value"] for row in address_rows
            ) == transition_counts[label],
                f"cache-audit {label} transition count differs")
        require(write_counts["DF53"] > 0 and write_counts["DF57"] > 0,
                "current route did not write both physical-map caches")
        require(reported("wrong_svbk_writes") == 0,
                "cache-audit writer fired outside WRAM1")
        # Lua's publication/repopulation counters are intentionally armed at
        # r314's transaction start.  The delayed DAD7 acknowledgement is a
        # separate boundary: only runtime observations after commit may be
        # counted as current.
        first_selfheal = ordered_selfheal["start_event"]
        committed_selfheal = ordered_selfheal["commit_event"]
        consumer_after = sum(
            row["kind"] == "consumer4100" and row["event"] > first_selfheal
            for row in cache_rows
        )
        publication_after = sum(
            row["kind"] == "publication4354"
            and row["event"] > first_selfheal
            for row in cache_rows
        )
        compiler_after = sum(
            row["kind"] == "compiler4302"
            and row["event"] > first_selfheal
            for row in cache_rows
        )
        repopulation_by_address = {
            f"{address:04X}": sum(
                row["event"] > first_selfheal
                and row["write_address"] == address
                and row["old_value"] == 0xFF and row["new_value"] != 0xFF
                and row["new_value"]
                == (row["scy"] ^ row["dc02"] ^ row["c21b"] ^ row["c2b8"])
                for row in write_rows
            )
            for address in (0xDF53, 0xDF57)
        }
        repopulation_after = sum(
            row["event"] > first_selfheal
            and row["write_address"] in {0xDF53, 0xDF57}
            and row["old_value"] == 0xFF and row["new_value"] != 0xFF
            for row in write_rows
        )
        runtime_after_rows = [
            row for row in cache_rows
            if row["kind"] == "runtimeDAD7"
            and row["event"] > committed_selfheal
        ]
        runtime_matches = sum(
            (row["dad7_7"], row["dad7_8"], row["dad7_9"])
            == (0xC4, 0x13, 0x00) for row in runtime_after_rows
        )
        require(runtime_after_rows,
                "self-heal effect was not followed by current DAD7")
        require(consumer_after == reported("consumer_after_selfheal") > 0,
                "post-self-heal split-key consumer count differs or is zero")
        require(publication_after == reported("publication_after_selfheal") > 0,
                "post-self-heal physical publication count differs or is zero")
        require(compiler_after > 0,
                "post-self-heal native attribute compiler did not execute")
        require(repopulation_after == reported("repopulation_after_selfheal") > 0,
                "post-self-heal cache repopulation count differs or is zero")
        require(all(value > 0 for value in repopulation_by_address.values()),
                "both DF53 and DF57 were not independently repopulated")
        require(runtime_matches == reported("runtime_after_selfheal_matches") > 0,
                "post-self-heal DAD7 match count differs or is zero")
        require(reported("runtime_after_selfheal_mismatches") == 0
                and runtime_matches == len(runtime_after_rows),
                "post-self-heal execution observed stale DAD7 bytes")
        # The atomic first publication precedes commit in r314 and is already
        # ordered exactly by selfheal_publication_contract().  Do not impose
        # the obsolete r313 effect->runtime->publication sequence here.
        physical_publication_targets = {
            "9800": sum(
                row["kind"] == "publication4354" and row["ff01"] == 0x99
                and row["event"] > first_selfheal for row in cache_rows
            ),
            "9C00": sum(
                row["kind"] == "publication4354" and row["ff01"] == 0x9D
                and row["event"] > first_selfheal for row in cache_rows
            ),
        }
        require(all(value > 0 for value in physical_publication_targets.values()),
                "both physical attribute maps were not published after self-heal")
        hazard_owner = ordered_selfheal["hazard_semantic_owner"]
        require(hazard_owner == {
            "postcopy": hits["postcopy10E2"],
            "dispatcher": hits["hazardDispatch6CCE"],
            "helper": hits["hazardHelper6BA7"],
            "geometry_front": hits["hazardFront61B7"],
            "writer_4300": hits["hazardWrite4300"],
            "writer_4500": hits["hazardWrite4500"],
        }, "semantic hazard-owner report/count rows differ")
        diagnosis = (
            "exact-legacy-DAD7-self-healed-consumer-and-"
            "physical-and-semantic-publication-observed"
        )
        cache_audit_receipt = {
            "path": str(cache_audit_path.resolve()),
            "sha256": sha256(cache_audit_path),
            "observations": len(cache_rows),
            "sample_observations": len(frame_rows),
            "hits": hits,
            "breakpoint_failures": breakpoint_failures,
            "watchpoint_failures": watchpoint_failures,
            "deferred_wram_frames": deferred_wram_frames,
            "write_events": write_events,
            "transition_events": transition_events,
            "write_counts": write_counts,
            "transition_counts": transition_counts,
            "consumer_after_selfheal": consumer_after,
            "publication_after_selfheal": publication_after,
            "compiler_after_selfheal": compiler_after,
            "repopulation_after_selfheal": repopulation_after,
            "repopulation_after_selfheal_by_address": repopulation_by_address,
            "runtime_after_selfheal_matches": runtime_matches,
            "runtime_after_selfheal_mismatches": 0,
            "physical_publication_targets": physical_publication_targets,
            "hazard_semantic_owner": hazard_owner,
            "hazard_helper_FFB7_values": sorted({
                row["ffb7"] for row in helper_rows
            }),
            "diagnosis": diagnosis,
            "ordered_selfheal_contract": ordered_selfheal,
            "FFB7_values": sorted({row["ffb7"] for row in cache_rows}),
            "sampled_cache_values": {
                name: sorted({row[name.lower()] for row in frame_rows})
                for name in (
                    "DF51", "DF53", "DF54", "DF55",
                    "DF57", "DF58", "DF59",
                )
            },
        }
    replay = {
        "capture_label": capture["label"],
        "replay_index": replay_index,
        "source_capture_path": capture["path"],
        "source_capture_sha256": capture["sha256"],
        "source_state_loaded": True,
        "initial_scene": "0B",
        "initial_menu_flag": capture["captured_state"]["FFE4"],
        "scene_values": ["0B"],
        "normalization": "rom-identity-only",
        "normalization_writes": 0,
        "fixture_writes": 0,
        "scene_injection": False,
        "vram_injection_bytes": 0,
        "retargeted_state_sha256": retarget["sha256"],
        "retargeted_state": {
            "path": retarget["path"], "sha256": retarget["sha256"],
        },
        "retarget_changed_gbAs_offsets": retarget["changed_gbAs_offsets"],
        "retargeted_state_rom_crc32": retarget["rom_crc32"],
        "retargeted_state_rom_identity": retarget["rom_identity"],
        "native_menu_transitions": True,
        "process_teardown": process_teardown,
        "menu_open_events": open_events,
        "menu_close_events": close_events,
        "captured_state_frames": phase_counts["captured"],
        "repair_settle_frames": phase_counts["repair_settle"],
        "menu_entry_frames": phase_counts["menu_entry"],
        "menu_held_frames": phase_counts["menu_hold"],
        "menu_exit_frames": phase_counts["menu_exit"],
        "post_close_frames": phase_counts["post_close"],
        "rendered_frames": len(frames),
        **metrics,
        "visible_attr_mismatch_frames": visible_attr_mismatch_frames,
        "postrepair_semantic_attr_mismatch_frames": (
            postrepair_semantic_attr_mismatch_frames
        ),
        "postsettle_semantic_attr_mismatch_frames": (
            postsettle_semantic_attr_mismatch_frames
        ),
        "postrepair_immutable_tile_mismatch_frames": (
            postrepair_immutable_tile_mismatch_frames
        ),
        "postsettle_immutable_tile_mismatch_frames": (
            postsettle_immutable_tile_mismatch_frames
        ),
        "late_tile_art_mismatch_frames": late_tile_art_mismatch_frames,
        "postrepair_bg_cram_mismatch_frames": (
            postrepair_bg_cram_mismatch_frames
        ),
        "semantic_checked_samples": int(report["semantic_checked_samples"]),
        "semantic_unreadable_samples": int(
            report["semantic_unreadable_samples"]
        ),
        "immutable_tile_checked_samples": int(
            report["immutable_tile_checked_samples"]
        ),
        "immutable_tile_unreadable_samples": int(
            report["immutable_tile_unreadable_samples"]
        ),
        "cram_checked_samples": int(report["cram_checked_samples"]),
        "cram_unreadable_samples": int(report["cram_unreadable_samples"]),
        "runtime_lut_mutation_frames": runtime_lut_mutation_frames,
        "runtime_oracles": {
            "path": str(runtime_oracles_path.resolve()),
            "sha256": sha256(runtime_oracles_path),
        },
        "launch_contract": {
            "path": str(launch_contract_path.resolve()),
            "sha256": sha256(launch_contract_path),
        },
        "final_bg_chr": final_bg_chr,
        "final_physical_planes": physical_planes,
        "baseline_ready": int(report["baseline_ready"]) == 1,
        "attr_checked_samples": int(report["attr_checked_samples"]),
        "attr_unreadable_samples": int(report["attr_unreadable_samples"]),
        "observation_restore_failures": int(
            report["observation_restore_failures"]
        ),
        "scene_violation_frames": int(report["scene_violation_frames"]),
        "active_violation_frames": int(report["active_violation_frames"]),
        "oam_dma_unreadable_frames": int(
            report["oam_dma_unreadable_frames"]
        ),
        "semantic_fingerprint_sha256": semantic_fingerprint(rows, frames),
        "state_trace": {
            "path": str(trace_path.resolve()), "sha256": sha256(trace_path),
        },
        "rendered_manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": sha256(manifest_path),
        },
    }
    if cache_audit:
        require(cache_audit_receipt is not None,
                "cache-audit receipt was not produced")
        replay["cache_audit"] = cache_audit_receipt
    return replay


def receipt_checks(
    captures: Sequence[dict[str, Any]], replays: Sequence[dict[str, Any]],
    negative_controls: dict[str, bool],
    archived_incompatible: dict[str, Any],
    native_provenance: dict[str, Any],
) -> dict[str, bool]:
    by_label = {capture["label"]: capture for capture in captures}
    grouped = {
        label: [row for row in replays if row["capture_label"] == label]
        for label in by_label
    }
    def semantic_planes_clean(row: dict[str, Any]) -> bool:
        planes = row.get("final_physical_planes", {})
        maps = planes.get("maps", {}) if isinstance(planes, dict) else {}
        return (
            set(maps) == {"9800", "9C00"}
            and sum(bool(item.get("active")) for item in maps.values()) == 1
            and all(
                item.get("semantic_mismatches_visible") == 0
                for item in maps.values()
            )
        )

    def tile_planes_clean(row: dict[str, Any]) -> bool:
        planes = row.get("final_physical_planes", {})
        maps = planes.get("maps", {}) if isinstance(planes, dict) else {}
        if row.get("capture_label") in HAZARD_CAPTURE_LABELS:
            exact_hazards_clean = (
                isinstance(planes.get("exact_hazard_oracle"), dict)
                and planes["exact_hazard_oracle"].get("legal") is True
                and all(
                    isinstance(item.get("exact_hazard_oracle"), dict)
                    and item["exact_hazard_oracle"].get("legal") is True
                    for item in maps.values()
                )
            )
        else:
            exact_hazards_clean = (
                planes.get("exact_hazard_oracle") is None
                and all(item.get("exact_hazard_oracle") is None
                        for item in maps.values())
            )
        low_health_hazard_fixture = (
            row.get("capture_label") in HAZARD_CAPTURE_LABELS
        )
        return (
            exact_hazards_clean
            and
            planes.get(
                "source_immutable_mismatches_outside_hazard_visible"
            ) == 0
            and planes.get(
                "source_immutable_mismatches_right_edge_visible"
            ) == 0
            and set(maps) == {"9800", "9C00"} and all(
            item.get("tile_immutable_mismatches_outside_hazard_visible") == 0
            and item.get("tile_immutable_mismatches_right_edge_visible") == 0
            and (
                not item.get("active")
                or (
                    low_health_hazard_fixture
                    and item.get(
                        "tile_source_mismatches_outside_hazard_visible"
                    ) == 0
                    and item.get(
                        "tile_source_mismatches_right_edge_visible"
                    ) == 0
                    and item.get("tile_source_mismatches_visible")
                    == item.get(
                        "tile_source_mismatches_hazard_owned_visible"
                    )
                )
                or (
                    not low_health_hazard_fixture
                    and item.get("tile_source_mismatches_visible") == 0
                )
            )
            for item in maps.values()
        ))
    complete_replay_set = (
        len(captures) == 2 and len(replays) == 4
        and set(grouped) == HAZARD_CAPTURE_LABELS
        and all(len(rows) == 2 for rows in grouped.values())
    )
    checks = {
        "archived incompatible wall capture remains exact and unnormalized": (
            archived_incompatible.get("label") == "operator-corrupted-walls"
            and archived_incompatible.get("captured_state", {}).get("D880")
            == "0B"
            and archived_incompatible.get("incompatibility", {}).get(
                "live_replays"
            ) == 0
            and archived_incompatible.get("incompatibility", {}).get(
                "policy"
            ) == (
                "archive-exact-and-reject-live-resume-without-"
                "cpu-stack-normalization"
            )
        ),
        "compatible operator and candidate-native captures are exact scene-$0B states": (
            len(captures) == 2
            and {item["captured_state"]["D880"] for item in captures} == {"0B"}
            and native_provenance.get("native_select_only") is True
            and native_provenance.get("machine_state_writes") == 0
        ),
        "both safe captures have duplicate live replays": (
            all(len(rows) == 2 for rows in grouped.values())
        ),
        "every live replay starts from its exact authenticated capture": all(
            row["source_state_loaded"] is True
            and row["source_capture_sha256"]
            == by_label[row["capture_label"]]["sha256"]
            for row in replays
        ),
        "every sampled route frame remains in scene $0B": all(
            row["scene_values"] == ["0B"] for row in replays
        ),
        "candidate-native closed capture opens, holds, and closes the native menu": (
            len(grouped.get(
                "candidate-native-closed-after-operator-low-health", []
            )) == 2
            and all(
                row["menu_open_events"] == 1 and row["menu_close_events"] == 1
                for row in grouped[
                    "candidate-native-closed-after-operator-low-health"
                ]
            )
        ),
        "menu-loaded capture closes, reopens, holds, and closes the native menu": (
            len(grouped.get("operator-low-health-menu-loaded", [])) == 2
            and all(
                row["menu_open_events"] == 1 and row["menu_close_events"] == 2
                for row in grouped["operator-low-health-menu-loaded"]
            )
        ),
        "menu transitions are native and injection-free": all(
            row["native_menu_transitions"] is True
            and row["process_teardown"]["completion_authenticated"] is True
            and row["process_teardown"]["policy"] in {
                "natural-zero-exit", "authenticated-exact-child-termination",
            }
            and row["normalization"] == "rom-identity-only"
            and row["normalization_writes"] == 0
            and row["fixture_writes"] == 0
            and row["scene_injection"] is False
            and row["vram_injection_bytes"] == 0
            for row in replays
        ),
        "captured-state, repair-settle, menu-entry, held, exit, and post-close frames exist": all(
            row["captured_state_frames"] >= CAPTURE_FRAMES
            and row["repair_settle_frames"] >= REPAIR_SETTLE_FRAMES
            and row["menu_entry_frames"] >= 1
            and row["menu_held_frames"] >= MENU_HOLD_FRAMES
            and row["menu_exit_frames"] >= 1
            and row["post_close_frames"] >= POST_CLOSE_FRAMES
            for row in replays
        ),
        "immutable semantic attrs are clean in every post-repair phase": all(
            row["postsettle_semantic_attr_mismatch_frames"] == 0
            and row["clear_tile_frames"] == 0
            and row["postsettle_wall_edge_artifact_frames"] == 0
            and row["postsettle_red_green_artifact_frames"] == 0
            and row["postsettle_weird_edge_tile_frames"] == 0
            and semantic_planes_clean(row)
            for row in replays
        ),
        "wall and right-edge tiles are exact outside hazard animation": all(
            row["postsettle_immutable_tile_mismatch_frames"] == 0
            and row["late_tile_art_mismatch_frames"] == 0
            and tile_planes_clean(row) for row in replays
        ),
        "Stage-1 background CRAM is exact in every post-repair phase": all(
            row["postrepair_bg_cram_mismatch_frames"] == 0
            for row in replays
        ),
        "final referenced background CHR is independently exact": all(
            isinstance(row.get("final_bg_chr"), dict)
            and row["final_bg_chr"].get("referenced_patterns", 0) > 0
            and row["final_bg_chr"].get("illegal_bank1_patterns") == 0
            and row["final_bg_chr"].get("pattern_mismatches") == 0
            and row["final_bg_chr"].get("byte_mismatches") == 0
            for row in replays
        ),
        "scene-$0B changes only the four reviewed terminal runtime attrs": all(
            row["runtime_lut_mutation_frames"] == 0 for row in replays
        ),
        "native semantic and all-frame state observations are complete": all(
            row["baseline_ready"] is True
            and row["attr_checked_samples"] >= 24
            and row["attr_unreadable_samples"] == 0
            and row["semantic_checked_samples"] == row["rendered_frames"]
            and row["semantic_unreadable_samples"] == 0
            and row["immutable_tile_checked_samples"]
            == row["rendered_frames"]
            and row["immutable_tile_unreadable_samples"] == 0
            and row["cram_checked_samples"] == row["rendered_frames"]
            and row["cram_unreadable_samples"] == 0
            and row["observation_restore_failures"] == 0
            and row["scene_violation_frames"] == 0
            and row["active_violation_frames"] == 0
            for row in replays
        ),
        "operator screenshots retain both archived negative signatures": (
            bool(negative_controls) and all(negative_controls.values())
        ),
        "live replay semantics are byte-deterministic": all(
            len({row["semantic_fingerprint_sha256"] for row in rows}) == 1
            for rows in grouped.values()
        ),
    }
    # A rejected/partial replay must never make an informational all([])
    # aggregate look green. Every acceptance check is gated on all four exact
    # capture/replay slots having returned authenticated evidence.
    return {
        name: bool(complete_replay_set and passed)
        for name, passed in checks.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--cache-audit", action="store_true",
        help=(
            "diagnostic-only: record per-sample DF53-55/DF57-59 keys, all "
            "cache writers, bank21:$6A49/$6CB4/$6CD3/$4100 execution, and "
            "bank1:$42FC/$4348 compile/publication; never use this "
            "breakpointed route as a visual acceptance gate"
        ),
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    observation_contract: dict[str, Any] | None = None

    try:
        probe_contract = audit_probe_source(PROBE.read_text())
        negative_controls = archived_negative_controls()
        require(all(negative_controls.values()),
                f"scene-$0B visual negative controls failed: {negative_controls}")
        if args.self_test:
            print(json.dumps({
                "status": "PASS", "emulator_run": False,
                "probe_contract": probe_contract,
                "negative_controls": negative_controls,
                "launcher": str(LAUNCHER),
            }, indent=2, sort_keys=True))
            return 0
        require(args.rom is not None, "ROM is required outside --self-test")
        require(args.output is not None,
                "--output is required outside --self-test")
        require(args.timeout > 5.0, "--timeout must be greater than five seconds")
        candidate = args.rom.resolve()
        require(candidate.is_file(), f"candidate ROM is missing: {candidate}")
        if args.cache_audit:
            observation_contract = runtime_observation_contract(candidate)
        output = scratch_output(args.output)
    except (LiveError, OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1

    candidate_sha256 = sha256(candidate)
    contract = load_capture_contract()
    captures = sorted(
        capture_evidence(contract),
        key=lambda item: item["captured_state"]["FFE4"] != "01",
    )
    try:
        archived_incompatible = archived_incompatible_evidence(
            contract, candidate, candidate_sha256
        )
        native_provenance = validate_native_capture_provenance(
            captures, candidate, candidate_sha256
        )
    except (ContractError, OSError, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: scene-$0B capture provenance: {error}")
        return 1
    replays: list[dict[str, Any]] = []
    failures: list[str] = []
    stop = False
    for capture in captures:
        for replay_index in (1, 2):
            try:
                replays.append(run_replay(
                    candidate=candidate,
                    candidate_sha256=candidate_sha256,
                    capture=capture,
                    replay_index=replay_index,
                    output=output / capture["label"] / f"replay-{replay_index}",
                    timeout=args.timeout, cache_audit=args.cache_audit,
                ))
            except SingleFlightBusy as error:
                failures.append(
                    f"{capture['label']} replay {replay_index}: {error}"
                )
                stop = True
            except (LiveError, OSError, KeyError, TypeError, ValueError,
                    subprocess.SubprocessError) as error:
                failures.append(
                    f"{capture['label']} replay {replay_index}: {error}"
                )
                stop = True
            if stop:
                break
        if stop:
            break

    checks = receipt_checks(
        captures, replays, negative_controls,
        archived_incompatible, native_provenance,
    )
    if args.cache_audit:
        diagnostic_checks = {
            "all four authenticated replays produced cache audits": (
                len(replays) == 4
                and all(isinstance(row.get("cache_audit"), dict)
                        for row in replays)
            ),
            "exact legacy DAD7 commits once after the clean map flip": (
                len(replays) == 4 and all(
                    row["cache_audit"]["hits"]["rst18Route001A"] > 0
                    and row["cache_audit"]["hits"]["selfhealEntry6CEA"] > 0
                    and row["cache_audit"]["hits"]["selfhealRepair6D35"] == 1
                    and row["cache_audit"]["hits"]["selfhealStart6D4D"] == 1
                    and row["cache_audit"]["hits"]["transactionArmed6DCB"] == 1
                    and row["cache_audit"]["hits"]["displayFlip6E25"] == 1
                    and row["cache_audit"]["hits"]["commitEffect6E2A"] == 1
                    for row in replays
                )
            ),
            "current menu route writes both semantic caches": (
                len(replays) == 4 and all(
                    row["cache_audit"]["write_counts"]["DF53"] > 0
                    and row["cache_audit"]["write_counts"]["DF57"] > 0
                    and row["cache_audit"]["hits"]["menuMux6CC5"] > 0
                    and row["cache_audit"]["hits"]["menuEffect6CE2"] > 0
                    for row in replays
                )
            ),
            "candidate DAD7 reaches consumer and physical publication": (
                len(replays) == 4 and all(
                    row["cache_audit"]["runtime_after_selfheal_matches"] > 0
                    and row["cache_audit"]["runtime_after_selfheal_mismatches"] == 0
                    and row["cache_audit"]["consumer_after_selfheal"] > 0
                    and row["cache_audit"]["compiler_after_selfheal"] > 0
                    and row["cache_audit"]["publication_after_selfheal"] > 0
                    and all(value > 0 for value in row["cache_audit"]
                            ["repopulation_after_selfheal_by_address"].values())
                    and all(value > 0 for value in row["cache_audit"]
                            ["physical_publication_targets"].values())
                    for row in replays
                )
            ),
            "per-sample cache records and observers are complete": (
                len(replays) == 4 and all(
                    row["cache_audit"]["sample_observations"]
                    == row["rendered_frames"]
                    and row["cache_audit"]["breakpoint_failures"] == 0
                    and row["cache_audit"]["watchpoint_failures"] == 0
                    for row in replays
                )
            ),
            "both final physical maps match immutable semantic attributes": (
                len(replays) == 4 and all(
                    row["final_physical_planes"]
                    ["runtime_lut_matches_canonical"]
                    and all(
                        map_row["semantic_mismatches_visible"] == 0
                        for map_row in row["final_physical_planes"]
                        ["maps"].values()
                    )
                    for row in replays
                )
            ),
            "every post-repair rendered frame has immutable semantic attrs": (
                len(replays) == 4 and all(
                    row["postrepair_semantic_attr_mismatch_frames"] == 0
                    and row["semantic_checked_samples"]
                    == row["rendered_frames"]
                    for row in replays
                )
            ),
            "immutable tiles and CRAM are exact across menu transitions": (
                len(replays) == 4 and all(
                    row["postrepair_immutable_tile_mismatch_frames"] == 0
                    and row["postrepair_bg_cram_mismatch_frames"] == 0
                    and row["immutable_tile_checked_samples"]
                    == row["rendered_frames"]
                    and row["cram_checked_samples"]
                    == row["rendered_frames"]
                    for row in replays
                )
            ),
            "final tile planes match immutable captures outside hazards": (
                len(replays) == 4 and all(
                    row["final_physical_planes"][
                        "source_immutable_mismatches_outside_hazard_visible"
                    ] == 0
                    and row["final_physical_planes"][
                        "source_immutable_mismatches_right_edge_visible"
                    ] == 0
                    and
                    all(
                        map_row[
                            "tile_immutable_mismatches_outside_hazard_visible"
                        ] == 0
                        and map_row[
                            "tile_immutable_mismatches_right_edge_visible"
                        ] == 0
                        and (
                            not map_row["active"]
                            or map_row["tile_source_mismatches_visible"] == 0
                        )
                        for map_row in row["final_physical_planes"]
                        ["maps"].values()
                    )
                    for row in replays
                )
            ),
            "low-health hazard geometry and semantic writer are nonvacuous": (
                len(replays) == 4 and all(
                    sum(
                        map_row["hazard_positions"]
                        for map_row in row["final_physical_planes"]
                        ["maps"].values()
                    ) > 0
                    and (
                        row["cache_audit"]["hazard_semantic_owner"]
                        ["writer_4300"]
                        + row["cache_audit"]["hazard_semantic_owner"]
                        ["writer_4500"]
                    ) > 0
                    for row in replays
                    if row["capture_label"]
                    == "operator-low-health-menu-loaded"
                )
            ),
        }
        for name, passed in diagnostic_checks.items():
            if not passed:
                failures.append(f"diagnostic check failed: {name}")
        receipt = {
            "schema": "penta-stage1-scene0b-cache-publication-diagnostic-v5",
            "status": "DIAGNOSTIC_PASS" if not failures else "FAIL",
            "candidate": str(candidate),
            "candidate_sha256": candidate_sha256,
            "archived_incompatible_capture": archived_incompatible,
            "source_captures": captures,
            "route_policy": contract["live_policy"],
            "runtime_observation_contract": observation_contract,
            "replays": replays,
            "diagnostic_checks": diagnostic_checks,
            "live_checks_informational": checks,
            "failures": failures,
            "tool_identity": expected_live_tool_identity(),
        }
    else:
        for name, passed in checks.items():
            if not passed:
                failures.append(f"check failed: {name}")
        receipt = {
            "schema": LIVE_SCHEMA,
            "status": "PASS" if not failures else "FAIL",
            "candidate": str(candidate),
            "candidate_sha256": candidate_sha256,
            "archived_incompatible_capture": archived_incompatible,
            "source_captures": captures,
            "route_policy": contract["live_policy"],
            "replays": replays,
            "checks": checks,
            "failures": failures,
            "tool_identity": expected_live_tool_identity(),
        }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if not failures and not args.cache_audit:
        try:
            validate_live_receipt(receipt_path, candidate, candidate_sha256)
        except BaseException as error:
            receipt["status"] = "FAIL"
            receipt["failures"] = [f"binder revalidation failed: {error}"]
            receipt_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n"
            )
            failures = receipt["failures"]
    if failures:
        print("FAIL: scene-$0B captured-state/menu live gate")
        for failure in failures:
            print(f"  {failure}")
        print(f"Receipt: {receipt_path}")
        return 1
    if args.cache_audit:
        print("DIAGNOSTIC PASS: runtime self-heal/publication audit is complete")
    else:
        print("PASS: both safe scene-$0B captures completed duplicate live menus")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
