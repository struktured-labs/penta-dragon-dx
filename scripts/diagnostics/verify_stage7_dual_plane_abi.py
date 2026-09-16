#!/usr/bin/env python3
"""Fail-fast candidate-only ABI smoke for the Stage-7 dual-plane helper.

The checked-in speed probe performs the native cold Stage-7 route and records
candidate-owned helper boundaries.  This wrapper intentionally runs before
the long visual soaks.  It rejects an active DMA or wrong VRAM/WRAM bank at
entry, every declared safe phase boundary, and exit; wrong IE restoration;
unbalanced helper calls; absent Timer service; unexpected HDMA commands; scene
escape; or main-loop loss.

mGBA's Lua API does not expose the CPU IME latch.  Timer-vector hits inside
the helper and again after a completed exit are the strongest live surrogate;
the candidate's static disassembly must still prove its exact EI/DI paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage_speed.lua"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
ROW_HELPER_OWNERSHIP_SNIPPET = """local function in_owned_row_helper(pc, svbk, mapped_bank)
  return pc >= 0xD400 and pc <= 0xD478
    and (svbk & 0x07) == 0x03
    and (mapped_bank == 0x01
      or (COMPILER_BANK > 0 and mapped_bank == COMPILER_BANK))
end"""
WINDOW_HELPER_ADDR = 0x6A40
WINDOW_HELPER_BANK = 13
WINDOW_HELPER_AUDIT_SNIPPET = """if WINDOW_HELPER_ADDR > 0 and WINDOW_HELPER_BANK > 0 then
    emu:setBreakpoint(function()
      if (phase ~= \"play\" and phase ~= \"drain\")
          or emu:read8(0xFF99) ~= WINDOW_HELPER_BANK then return end
      window_helper_hits = window_helper_hits + 1
      if emu:read8(0xFFE4) ~= 0 then
        window_helper_ffe4_nonzero_hits =
          window_helper_ffe4_nonzero_hits + 1
      end
    end, WINDOW_HELPER_ADDR)"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_address(raw: str) -> int:
    value = int(raw, 0)
    if not 0 < value <= 0xFFFF:
        raise argparse.ArgumentTypeError("address must be in $0001-$FFFF")
    return value


def parse_byte(raw: str) -> int:
    value = int(raw, 0)
    if not 0 <= value <= 0xFF:
        raise argparse.ArgumentTypeError("byte must be in $00-$FF")
    return value


def parse_sha256(raw: str) -> str:
    value = raw.lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise argparse.ArgumentTypeError("SHA-256 must be 64 hexadecimal digits")
    return value


def dollar_address(raw: object, label: str) -> int:
    require(isinstance(raw, str) and raw.startswith("$"),
            f"static receipt has invalid {label}: {raw!r}")
    try:
        return int(raw[1:], 16)
    except ValueError as error:
        raise AssertionError(
            f"static receipt has invalid {label}: {raw!r}"
        ) from error


def banked_label(raw: object, expected_bank: int, label: str) -> int:
    prefix = f"bank{expected_bank}:$"
    require(isinstance(raw, str) and raw.startswith(prefix),
            f"static receipt has invalid {label}: {raw!r}")
    try:
        return int(raw[len(prefix):], 16)
    except ValueError as error:
        raise AssertionError(
            f"static receipt has invalid {label}: {raw!r}"
        ) from error


def fixed_labels(raw: object, label: str) -> set[int]:
    require(isinstance(raw, list), f"static receipt has invalid {label}")
    values: set[int] = set()
    for index, item in enumerate(raw):
        prefix = "fixed:$"
        require(isinstance(item, str) and item.startswith(prefix),
                f"static receipt has invalid {label}[{index}]: {item!r}")
        try:
            values.add(int(item[len(prefix):], 16))
        except ValueError as error:
            raise AssertionError(
                f"static receipt has invalid {label}[{index}]: {item!r}"
            ) from error
    require(len(values) == len(raw), f"static receipt has duplicate {label}")
    return values


def hex_pattern(raw: object, label: str) -> bytes:
    require(isinstance(raw, str),
            f"static receipt has invalid {label}: {raw!r}")
    try:
        pattern = bytes.fromhex(raw)
    except ValueError as error:
        raise AssertionError(
            f"static receipt has invalid {label}: {raw!r}"
        ) from error
    require(pattern, f"static receipt has empty {label}")
    return pattern


def validate_probe_ownership_contract(compiler_bank: int) -> dict:
    """Fail before launch unless D400 ownership is exact and mutation-sensitive."""

    require(compiler_bank > 1,
            "row-helper compiler-bank control needs a non-bank1 compiler")
    source = PROBE.read_text()
    require(source.count(ROW_HELPER_OWNERSHIP_SNIPPET) == 1,
            "speed probe lacks the exact row-helper ownership classifier")
    require(
        source.count("or in_owned_row_helper(pc, svbk, mapped_bank)") == 1,
        "scene sampler does not use the exact row-helper ownership classifier",
    )
    require(source.count(WINDOW_HELPER_AUDIT_SNIPPET) == 1,
            "speed probe lacks the exact FFE4 Window-helper audit")
    for text in (
        'os.getenv("STAGE_SPEED_WINDOW_HELPER_ADDR")',
        'os.getenv("STAGE_SPEED_WINDOW_HELPER_BANK")',
        'local sampled_ffe4 = emu:read8(0xFFE4)',
        '"safe_boundary_drain_ffe4_nonzero_frames"',
        '"window_helper_ffe4_nonzero_hits"',
    ):
        require(text in source,
                f"speed probe lacks FFE4 source contract: {text}")

    def owned(pc: int, svbk: int, mapped_bank: int) -> bool:
        return (
            0xD400 <= pc <= 0xD478
            and svbk & 7 == 3
            and mapped_bank in {0x01, compiler_bank}
        )

    domain = {
        (pc, svbk, bank)
        for pc in (0xD3FF, 0xD400, 0xD423, 0xD478, 0xD479)
        for svbk in (0x01, 0x02, 0x03, 0xFB)
        for bank in (0x00, 0x01, compiler_bank - 1, compiler_bank,
                     compiler_bank + 1)
    }
    positive = {state for state in domain if owned(*state)}
    expected = {
        (pc, svbk, bank)
        for pc in (0xD400, 0xD423, 0xD478)
        for svbk in (0x03, 0xFB)
        for bank in (0x01, compiler_bank)
    }
    require(positive == expected,
            "row-helper ownership truth table is not the exact bounded set")

    mutants = {
        "bank": {
            state for state in domain
            if 0xD400 <= state[0] <= 0xD478 and state[1] & 7 == 3
        },
        "svbk": {
            state for state in domain
            if 0xD400 <= state[0] <= 0xD478
            and state[2] in {0x01, compiler_bank}
        },
        "pc_boundary": {
            state for state in domain
            if 0xD3FF <= state[0] <= 0xD479 and state[1] & 7 == 3
            and state[2] in {0x01, compiler_bank}
        },
    }
    for name, mutant in mutants.items():
        require(mutant != positive and positive < mutant,
                f"row-helper {name} mutation control escaped")
    return {
        "source_contract_exact": True,
        "positive_states": len(positive),
        "bank_mutation_rejected": True,
        "svbk_mutation_rejected": True,
        "pc_boundary_mutation_rejected": True,
        "allowed_rom_banks": [1, compiler_bank],
        "svbk": 3,
        "pc_range": "D400-D478",
        "window_helper": "bank13:$6A40",
        "FFE4_transfer_condition": (
            "every measured/safe-drain callback is accounted as context; "
            "zero changed-helper executions or FFE4=0 at every exact entry"
        ),
    }


def validate_static_receipt(
    path: Path, candidate: Path, candidate_sha256: str, args: argparse.Namespace,
) -> dict:
    receipt = json.loads(path.read_text())
    require(
        receipt.get("schema")
        == "penta-stage7-hidden-dual-plane-hdma-r264-static-v1",
        "wrong Stage-7 static receipt schema",
    )
    require(receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "Stage-7 static audit did not pass")
    require(receipt.get("promotable") is False,
            "static receipt incorrectly claims promotion")
    require(receipt.get("emulator_run") is False,
            "static receipt unexpectedly claims an emulator run")
    built = receipt.get("in_memory_candidate", {})
    require(built.get("sha256") == candidate_sha256,
            "static receipt is for a different candidate")
    require(built.get("rom_emitted") is True,
            "static receipt did not emit its audited candidate")

    guard = receipt.get("emitted_guard_verification", {})
    required_guards = {
        "post_DI_scene", "post_DI_dungeon", "gameplay_FFC1_exact",
        "window_LCDC5_clear", "incoming_FF55_exact_idle",
        "SCX_domain", "SCY_domain",
    }
    guard_patterns = guard.get("patterns", {})
    require(isinstance(guard_patterns, dict),
            "static receipt has invalid emitted guard patterns")
    require(required_guards <= set(guard_patterns),
            "emitted helper lacks a required fail-closed guard proof")
    controls = guard.get("mutation_controls", {})
    for name in required_guards:
        require(controls.get(f"mutated_{name}_rejected") is True,
                f"guard mutation control did not reject: {name}")
    require(controls.get("mutated_exact_caller_rejected") is True,
            "exact caller-guard mutation did not reject")

    required_post_service_guards = {
        "post_service_scene", "post_service_dungeon",
        "post_service_gameplay", "post_service_window",
        "post_service_FF55_idle", "post_service_SCX", "post_service_SCY",
    }
    post_service_patterns = guard.get("post_service_patterns", {})
    require(isinstance(post_service_patterns, dict),
            "static receipt has invalid post-service guard patterns")
    require(required_post_service_guards <= set(post_service_patterns),
            "post-service revalidation omits mutable guard state")
    require(guard.get("post_service_call_count") == 2,
            "both interrupt-open service phases must revalidate")
    require(
        controls.get("mutated_post_service_FF55_idle_rejected") is True,
        "post-service FF55-idle mutation did not reject",
    )

    helper = receipt.get("helper", {})
    require(helper.get("bank") == args.compiler_bank,
            "static helper bank differs from ABI command")
    helper_start = dollar_address(helper.get("entry"), "helper entry")
    helper_end = dollar_address(helper.get("end"), "helper end")
    require(args.entry_addr == helper_start,
            "ABI entry differs from static helper entry")
    require(args.compiler_start == helper_start and args.compiler_end == helper_end,
            "ABI compiler window must cover the exact full helper")
    labels = helper.get("trace_labels", {})
    require(
        set(args.phase_addr)
        == {
            banked_label(labels.get("phase1_service"), args.compiler_bank,
                         "phase1 service"),
            banked_label(labels.get("phase2_service"), args.compiler_bank,
                         "phase2 service"),
        },
        "ABI phases differ from static safe-service labels",
    )
    require(
        args.fallback_addr
        == banked_label(labels.get("fallback_native"), args.compiler_bank,
                        "native fallback"),
        "ABI fallback differs from static label",
    )
    if args.caller_reject_addr is not None:
        require(
            args.caller_reject_addr
            == banked_label(labels.get("caller_reject"), args.compiler_bank,
                            "caller rejection"),
            "ABI caller rejection differs from static label",
        )
    if args.atomic_fallback_addr is not None:
        require(
            args.atomic_fallback_addr
            == banked_label(labels.get("fallback_after_atomic"),
                            args.compiler_bank, "after-atomic fallback"),
            "ABI after-atomic fallback differs from static label",
        )

    expected_outer_returns = {0x0AB8, 0x12E0}
    require(set(args.outer_return_addr) == {0x0AB8, 0x12E0},
            "ABI command must classify both stock $4295 outer callers")
    require(args.exit_bank == 0x01 and args.exit_addr == 0x436D,
            "exact pre-RETI ABI exit must be bank1:$436D")

    caller_camera = receipt.get("caller_and_camera_contract", {})
    require(
        fixed_labels(caller_camera.get("admitted_outer_returns"),
                     "admitted outer returns") == {0x12E0},
        "static helper must admit only the natural Stage-7 $12E0 caller",
    )
    require(
        fixed_labels(caller_camera.get("rejected_outer_returns"),
                     "rejected outer returns") == {0x0AB8},
        "static helper must reject the unreachable Stage-7 $0AB8 caller",
    )
    require(
        fixed_labels(caller_camera.get("whole_ROM_occurrences"),
                     "whole-ROM CALL $4295 occurrences") == {0x0AB5, 0x12DD},
        "static caller census differs from the two stock CALL $4295 sites",
    )
    require(caller_camera.get("rejected_caller_policy")
            == "native fallback before $DA13",
            "$0AB8 caller is not rejected before helper mutation")
    require(caller_camera.get("unknown_outer_return_policy")
            == "native fallback before $DA13",
            "unknown callers are not rejected before helper mutation")
    secondary = caller_camera.get("secondary", {})
    require(secondary.get("continuation") == "$0AB8 CALL $307B",
            "secondary caller continuation is not bound")
    require(secondary.get("fast_path_policy")
            == "rejected; untouched native dirty copier",
            "secondary caller is not bound to the untouched native copier")
    require(
        secondary.get("strict_publisher_preimage") == "$307B-$3099 inclusive",
        "secondary publisher preimage is not exact",
    )
    require(
        secondary.get("write_order")
        == "FF42, FF43, then LCDC at $3095",
        "secondary publisher order/address differs",
    )
    require(secondary.get("exhaustive_states") == 1024,
            "secondary pending-camera state space was not exhaustive")
    require(secondary.get("padding_exposures") == 0,
            "secondary pending camera exposes padding")
    require(secondary.get("maximum_touched_column") == 23,
            "secondary maximum touched column changed")
    require(secondary.get("maximum_touched_row") == 21,
            "secondary maximum touched row changed")
    primary = caller_camera.get("primary", {})
    require(primary.get("continuation") == "$12E0",
            "primary caller continuation is not bound")
    require(
        primary.get("strict_publisher_preimage") == "$12E0-$1302 inclusive",
        "primary publisher preimage is not exact",
    )
    require(
        primary.get("write_order")
        == "LCDC at $12EC, then FF43=DC00&$0F and FF42=DC02&$0F",
        "primary publisher order/address differs",
    )
    require(primary.get("exhaustive_pending_states") == 256,
            "primary pending-camera state space was not exhaustive")
    require(primary.get("padding_exposures") == 0,
            "primary pending camera exposes padding")

    payload = candidate.read_bytes()
    require(payload[0x4368:0x436E] == bytes.fromhex("E0 FF 3E 01 BF D9"),
            "native IE/AF/RETI completion bytes changed")
    helper_offset = args.compiler_bank * 0x4000 + helper_start - 0x4000
    helper_blob = payload[
        helper_offset:helper_offset + helper_end - helper_start + 1
    ]
    require(len(helper_blob) == helper.get("length"),
            "candidate helper length differs from static receipt")
    require(hashlib.sha256(helper_blob).hexdigest() == helper.get("sha256"),
            "candidate helper bytes differ from static receipt")
    for name in sorted(required_guards):
        pattern = hex_pattern(guard_patterns.get(name), f"guard pattern {name}")
        require(pattern in helper_blob,
                f"emitted helper does not contain guard pattern {name}")
    caller_pattern = hex_pattern(guard.get("caller_pattern"), "caller pattern")
    require(helper_blob.count(caller_pattern) == 1,
            "emitted helper does not contain one exact caller pattern")
    require(guard.get("caller_policy") == {
        "admitted_outer_returns": ["fixed:$12E0"],
        "rejected_outer_returns": ["fixed:$0AB8"],
        "rejected_continuation": "native fallback before $DA13",
    }, "emitted caller policy differs from the narrowed static policy")
    require(guard.get("first_mutation_after_guards")
            == "$DA13 tagged atomic setup",
            "caller rejection is not before the first helper mutation")
    for name in (
        "mutated_exact_caller_rejected",
        "mutated_caller_reject_POP_HL_rejected",
        "mutated_secondary_0AB8_admission_rejected",
        "mutated_secondary_native_fallback_rejected",
    ):
        require(controls.get(name) is True,
                f"caller mutation control did not reject: {name}")
    require(guard.get("secondary_stack_model") == {
        "helper_entry": ["$084D", "$0AB8"],
        "after_balanced_HL_probe": ["$084D", "$0AB8"],
        "native_mapper_entry": ["$42B3", "$0AB8"],
        "after_mapper_RET": ["$0AB8"],
    }, "rejected $0AB8 stack-word simulation differs")
    fallback = banked_label(
        labels.get("fallback_native"), args.compiler_bank, "native fallback"
    )
    caller_reject = banked_label(
        labels.get("caller_reject"), args.compiler_bank, "caller rejection"
    )
    fallback_pattern = hex_pattern(
        guard.get("native_fallback_pattern"), "native fallback pattern"
    )
    caller_reject_pattern = hex_pattern(
        guard.get("caller_reject_pattern"), "caller reject pattern"
    )
    require(fallback_pattern == bytes.fromhex(
        "F1 11 B3 42 D5 3E 01 C3 61 00"
    ), "native fallback no longer synthesizes bank1:$42B3")
    require(caller_reject_pattern
            == bytes((0xE1, 0xC3)) + fallback.to_bytes(2, "little"),
            "caller rejection no longer balances HL then jumps native")
    require(helper_blob[fallback - helper_start:
                        fallback - helper_start + len(fallback_pattern)]
            == fallback_pattern,
            "candidate lacks exact native fallback at declared label")
    require(helper_blob[caller_reject - helper_start:
                        caller_reject - helper_start
                        + len(caller_reject_pattern)] == caller_reject_pattern,
            "candidate lacks exact caller rejection at declared label")
    for name in sorted(required_post_service_guards):
        pattern = hex_pattern(
            post_service_patterns.get(name), f"post-service pattern {name}",
        )
        require(pattern in helper_blob,
                f"emitted helper does not contain post-service pattern {name}")
    observed_dma_sites = {
        helper_start + offset
        for offset in range(len(helper_blob) - 1)
        if helper_blob[offset:offset + 2] == bytes.fromhex("E0 55")
    }
    require(observed_dma_sites == set(args.dma_command_addr),
            f"ABI DMA sites {sorted(args.dma_command_addr)} do not cover "
            f"all emitted FF55 stores {sorted(observed_dma_sites)}")
    banked_stack = receipt.get("banked_stack_contract", {})
    inline_stores = banked_stack.get("inline_FF55_stores", {})
    require(
        banked_label(inline_stores.get("attribute"), args.compiler_bank,
                     "inline attribute FF55 store") in observed_dma_sites,
        "static attribute FF55 store is not an emitted inline store",
    )
    require(
        banked_label(inline_stores.get("tile"), args.compiler_bank,
                     "inline tile FF55 store") in observed_dma_sites,
        "static tile FF55 store is not an emitted inline store",
    )
    stack_controls = banked_stack.get("mutation_controls", {})
    require(stack_controls.get("mutated_attr_inline_store_rejected") is True,
            "attribute inline-store mutation did not reject")
    require(stack_controls.get("mutated_tile_inline_store_rejected") is True,
            "tile inline-store mutation did not reject")
    for zone_name, zone in banked_stack.get("zones", {}).items():
        require(zone.get("stack_operations") == [],
                f"banked transport zone has stack operations: {zone_name}")
    require(set(banked_stack.get("zones", {})) == {
        "SVBK2_odd_row_staging", "SVBK3_attr_transport",
        "SVBK2_tile_transport",
    }, "banked stack proof does not cover every transport zone")

    dma_contract = receipt.get("dma_contract", {})
    active_commands = dma_contract.get("active_lcd_commands", {})
    require(isinstance(active_commands, dict),
            "static active-LCD DMA command contract is not a mapping")
    attr_match = re.fullmatch(r"\$([0-9A-Fa-f]{2})",
                             str(active_commands.get("attrs", "")))
    tile_match = re.fullmatch(r"\$([0-9A-Fa-f]{2}) x([1-9][0-9]*)",
                             str(active_commands.get("tile_rows", "")))
    require(attr_match is not None and tile_match is not None,
            "static active-LCD DMA command contract differs")
    tile_commands_per_admitted_entry = int(tile_match.group(2))
    require(tile_commands_per_admitted_entry > 0,
            "static tile-command count must be positive")
    static_commands = {
        int(attr_match.group(1), 16), int(tile_match.group(1), 16),
    }
    require(set(args.expected_dma_command) == static_commands,
            "live Stage-7 command set differs from the static receipt")
    require(dma_contract.get("active_DMA_VBK_changes") == 0,
            "static DMA contract permits an active-DMA VBK change")
    require(dma_contract.get("active_DMA_SVBK_changes") == 0,
            "static DMA contract permits an active-DMA SVBK change")
    negative_controls = dma_contract.get("negative_controls", {})
    require(all(negative_controls.get(name) is True for name in (
        "active_VBK_switch_rejected", "mode0_HBlank_start_rejected",
        "LCD_off_HBlank_command_rejected",
    )), "a DMA safety mutation/negative control did not reject")

    global_controls = receipt.get("mutation_controls", {})
    for name in (
        "mutated_source_then_publisher_rejected",
        "mutated_secondary_caller_rejected",
        "mutated_secondary_pending_camera_publisher_rejected",
        "mutated_primary_postcaller_camera_publisher_rejected",
        "mutated_atomic_completion_rejected",
        "mutated_timer_isr_rejected",
    ):
        require(global_controls.get(name) is True,
                f"static mutation control did not reject: {name}")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "required_guards": sorted(required_guards),
        "required_post_service_guards": sorted(required_post_service_guards),
        "helper_range": f"bank{args.compiler_bank}:${helper_start:04X}-${helper_end:04X}",
        "dma_sites": [f"{value:04X}" for value in sorted(observed_dma_sites)],
        "attribute_dma_site": (
            f"${banked_label(inline_stores.get('attribute'), args.compiler_bank, 'inline attribute FF55 store'):04X}"
        ),
        "tile_dma_site": (
            f"${banked_label(inline_stores.get('tile'), args.compiler_bank, 'inline tile FF55 store'):04X}"
        ),
        "attribute_commands_per_admitted_entry": 1,
        "tile_commands_per_admitted_entry": tile_commands_per_admitted_entry,
        "classified_outer_callers": ["0AB8", "12E0"],
        "admitted_outer_callers": ["12E0"],
        "rejected_outer_callers": ["0AB8"],
    }


def stop_owned_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def dma_commands(result: dict) -> list[int]:
    commands: list[int] = []
    for record in result.get("attr_dma_commands_trace", []):
        fields = record.split(":")
        require(len(fields) == 4, f"invalid DMA trace record: {record!r}")
        commands.append(int(fields[1], 16))
    return commands


def safe_boundary_contract(
    result: dict,
    *,
    frames: int,
    max_drain_frames: int,
    admitted_outer_return: int,
    dma_sites: set[int],
    allowed_dma_commands: set[int],
    exit_ie: int,
) -> dict:
    """Qualify a frozen speed window plus its non-measured helper drain."""

    drain_trace = result.get("safe_boundary_drain_dma_trace", [])
    parsed_trace: list[dict[str, int]] = []
    trace_well_formed = isinstance(drain_trace, list)
    if trace_well_formed:
        for raw in drain_trace:
            if not isinstance(raw, str):
                trace_well_formed = False
                break
            fields = raw.split(":")
            if len(fields) != 5:
                trace_well_formed = False
                break
            try:
                parsed_trace.append({
                    "frame": int(fields[0]),
                    "site": int(fields[1], 16),
                    "command": int(fields[2], 16),
                    "scene": int(fields[3], 16),
                    "lcdc": int(fields[4], 16),
                })
            except ValueError:
                trace_well_formed = False
                break

    required = result.get("safe_boundary_drain_required") is True
    status = result.get("safe_boundary_status")
    drain_frames = result.get("safe_boundary_drain_frames")
    start_is_unsafe = any(
        result.get(key) != expected
        for key, expected in (
            ("safe_boundary_start_depth", 0),
            ("safe_boundary_start_pending_outer", -1),
            ("safe_boundary_start_ff55", 0xFF),
            ("safe_boundary_start_vbk", 0),
            ("safe_boundary_start_svbk", 1),
            ("safe_boundary_start_ie", exit_ie),
        )
    )
    checks = {
        "enabled": result.get("safe_boundary_drain_enabled") is True,
        "measurement_complete": (
            result.get("safe_boundary_measurement_complete") is True
        ),
        "measurement_frames_frozen": result.get("frames") == frames,
        "drain_bound_echo_exact": (
            result.get("safe_boundary_max_frames") == max_drain_frames
        ),
        "status_completed": status in {"already-safe", "completed"},
        "drain_frames_bounded": (
            isinstance(drain_frames, int)
            and not isinstance(drain_frames, bool)
            and 0 <= drain_frames <= max_drain_frames
        ),
        "no_post_measurement_helper_entry": (
            result.get("safe_boundary_extra_entries") == 0
        ),
        "no_guard_fallback_during_drain": (
            result.get("safe_boundary_drain_fallback_hits") == 0
        ),
        "final_restored": (
            result.get("safe_boundary_final_restored") is True
            and result.get("final_hdma5") == 0xFF
            and result.get("final_vbk", 0xFF) & 1 == 0
            and result.get("final_svbk", 0xFF) & 7 == 1
            and result.get("final_ie") == exit_ie
            and result.get("abi_final_depth") == 0
            and result.get("abi_pending_outer_return") == -1
        ),
        "drain_trace_well_formed": trace_well_formed,
        "drain_trace_count_exact": (
            trace_well_formed
            and len(parsed_trace)
            == result.get("safe_boundary_drain_dma_commands")
        ),
        "drain_trace_stays_at_measurement_boundary": (
            trace_well_formed
            and all(row["frame"] == frames for row in parsed_trace)
        ),
        "drain_dma_sites_exact_subset": (
            trace_well_formed
            and all(row["site"] in dma_sites for row in parsed_trace)
        ),
        "drain_dma_commands_allowed": (
            trace_well_formed
            and all(
                row["command"] in allowed_dma_commands
                for row in parsed_trace
            )
        ),
        "drain_dma_hblank_only": (
            result.get("safe_boundary_drain_gdma_commands") == 0
            and result.get("safe_boundary_drain_hblank_commands")
            == result.get("safe_boundary_drain_dma_commands")
        ),
        "drain_scene_contained": (
            result.get("safe_boundary_drain_scene_violations") == 0
        ),
        "required_drain_started_unsafe": (not required) or start_is_unsafe,
        "required_drain_reached_exact_outer_return": (
            (
                status == "completed"
                and isinstance(drain_frames, int)
                and 0 <= drain_frames <= max_drain_frames
                and result.get("safe_boundary_post_hits") == 1
                and result.get("safe_boundary_last_outer_return")
                == admitted_outer_return
                and result.get("final_cpu_pc") == admitted_outer_return
            )
            if required
            else (
                status == "already-safe"
                and drain_frames == 0
                and result.get("safe_boundary_post_hits") == 0
                and result.get("safe_boundary_last_outer_return") == -1
            )
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "drain_required": required,
        "status": status,
        "drain_frames": drain_frames,
        "parsed_dma_trace": parsed_trace,
    }


def safe_boundary_policy_controls() -> dict[str, bool]:
    """Mutation controls for the fixed-window/non-measured-drain split."""

    valid = {
        "safe_boundary_drain_enabled": True,
        "safe_boundary_measurement_complete": True,
        "safe_boundary_drain_required": True,
        "safe_boundary_status": "completed",
        "safe_boundary_max_frames": 120,
        "safe_boundary_drain_frames": 1,
        "safe_boundary_post_hits": 1,
        "safe_boundary_last_outer_return": 0x12E0,
        "safe_boundary_extra_entries": 0,
        "safe_boundary_start_depth": 1,
        "safe_boundary_start_pending_outer": -1,
        "safe_boundary_start_ff55": 0,
        "safe_boundary_start_vbk": 1,
        "safe_boundary_start_svbk": 3,
        "safe_boundary_start_ie": 4,
        "safe_boundary_drain_dma_commands": 1,
        "safe_boundary_drain_hblank_commands": 1,
        "safe_boundary_drain_gdma_commands": 0,
        "safe_boundary_drain_scene_violations": 0,
        "safe_boundary_drain_fallback_hits": 0,
        "safe_boundary_drain_dma_trace": ["2800:7187:81:08:83"],
        "safe_boundary_final_restored": True,
        "frames": 2800,
        "final_hdma5": 0xFF,
        "final_vbk": 0xFE,
        "final_svbk": 0xF9,
        "final_ie": 7,
        "final_cpu_pc": 0x12E0,
        "abi_final_depth": 0,
        "abi_pending_outer_return": -1,
    }

    def passes(payload: dict) -> bool:
        return safe_boundary_contract(
            payload,
            frames=2800,
            max_drain_frames=120,
            admitted_outer_return=0x12E0,
            dma_sites={0x713D, 0x7187},
            allowed_dma_commands={0xAF, 0x81},
            exit_ie=7,
        )["passed"]

    def mutated(**changes: object) -> dict:
        payload = dict(valid)
        payload.update(changes)
        return payload

    controls = {
        "completed_drain_passes": passes(valid),
        "active_dma_rejected": not passes(mutated(final_hdma5=0)),
        "extra_entry_rejected": not passes(
            mutated(safe_boundary_extra_entries=1)
        ),
        "drain_fallback_rejected": not passes(
            mutated(safe_boundary_drain_fallback_hits=1)
        ),
        "wrong_outer_return_rejected": not passes(
            mutated(safe_boundary_last_outer_return=0x0AB8)
        ),
        "wrong_final_pc_rejected": not passes(mutated(final_cpu_pc=0x12E1)),
        "overlong_drain_rejected": not passes(
            mutated(safe_boundary_drain_frames=121)
        ),
        "measurement_extension_rejected": not passes(mutated(frames=2801)),
        "gdma_rejected": not passes(mutated(
            safe_boundary_drain_hblank_commands=0,
            safe_boundary_drain_gdma_commands=1,
            safe_boundary_drain_dma_trace=["2800:7187:01:08:83"],
        )),
        "wrong_site_rejected": not passes(mutated(
            safe_boundary_drain_dma_trace=["2800:7000:81:08:83"]
        )),
        "wrong_command_rejected": not passes(mutated(
            safe_boundary_drain_dma_trace=["2800:7187:82:08:83"]
        )),
        "scene_escape_rejected": not passes(mutated(
            safe_boundary_drain_scene_violations=1
        )),
    }
    return controls


def abi_exit_partition_contract(result: dict) -> dict:
    """Separate optimized and guarded-native exits at common bank1:$436D."""

    entries = result.get("abi_entry_hits")
    native_entries = result.get("abi_fallback_hits")
    fast_exits = result.get("abi_fast_exit_hits")
    native_exits = result.get("abi_native_exit_hits")
    exits = result.get("abi_exit_hits")
    checks = {
        "counts_are_integers": all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (
                entries, native_entries, fast_exits, native_exits, exits,
            )
        ),
        "native_entries_bounded": (
            isinstance(entries, int)
            and isinstance(native_entries, int)
            and 0 <= native_entries <= entries
        ),
        "fast_exits_exact": (
            isinstance(entries, int)
            and isinstance(native_entries, int)
            and fast_exits == entries - native_entries
        ),
        "native_exits_exact": native_exits == native_entries,
        "common_exit_sum_exact": (
            isinstance(fast_exits, int)
            and isinstance(native_exits, int)
            and fast_exits + native_exits == exits
        ),
        "native_exit_abi_exact": (
            result.get("abi_native_exit_violations") == 0
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def abi_exit_partition_policy_controls() -> dict[str, bool]:
    valid = {
        "abi_entry_hits": 339,
        "abi_fallback_hits": 112,
        "abi_fast_exit_hits": 227,
        "abi_native_exit_hits": 112,
        "abi_exit_hits": 339,
        "abi_native_exit_violations": 0,
    }

    def passes(payload: dict) -> bool:
        return abi_exit_partition_contract(payload)["passed"]

    def mutated(**changes: object) -> dict:
        payload = dict(valid)
        payload.update(changes)
        return payload

    return {
        "mixed_fast_native_passes": passes(valid),
        "missing_fast_exit_rejected": not passes(mutated(
            abi_fast_exit_hits=226, abi_exit_hits=338
        )),
        "missing_native_exit_rejected": not passes(mutated(
            abi_native_exit_hits=111, abi_exit_hits=338
        )),
        "native_bc_mutation_rejected": not passes(mutated(
            abi_native_exit_violations=1
        )),
        "fallback_overcount_rejected": not passes(mutated(
            abi_fallback_hits=340
        )),
        "boolean_count_rejected": not passes(mutated(abi_fallback_hits=True)),
    }


def ffe4_transfer_contract(
    result: dict, *, frames: int, safe_boundary_drain: bool,
) -> dict:
    """Prove r265 executed only e048's byte/cycle-exact FFE4-zero path."""

    numeric_fields = (
        "ffe4_zero_play_frames", "ffe4_nonzero_play_frames",
        "first_ffe4_nonzero_play_frame", "first_ffe4_nonzero_value",
        "window_helper_hits", "window_helper_ffe4_nonzero_hits",
        "safe_boundary_drain_ffe4_nonzero_frames",
    )
    integers = all(
            isinstance(result.get(name), int)
            and not isinstance(result.get(name), bool)
            for name in numeric_fields
    )
    zero_frames = result.get("ffe4_zero_play_frames")
    nonzero_frames = result.get("ffe4_nonzero_play_frames")
    first_frame = result.get("first_ffe4_nonzero_play_frame")
    first_value = result.get("first_ffe4_nonzero_value")
    checks = {
        "telemetry_is_integer": integers,
        "every_measured_callback_is_accounted": (
            integers and zero_frames >= 0 and nonzero_frames >= 0
            and zero_frames + nonzero_frames == frames
        ),
        "first_nonzero_callback_is_coherent": (
            integers and (
                (nonzero_frames == 0 and first_frame == -1
                 and first_value == -1)
                or (nonzero_frames > 0 and 1 <= first_frame <= frames
                    and first_value > 0)
            )
        ),
        "window_helper_counts_are_consistent": (
            result.get("window_helper_hits", -1) >= 0
            and result.get("window_helper_ffe4_nonzero_hits") == 0
            and result.get("window_helper_ffe4_nonzero_hits", -1)
            <= result.get("window_helper_hits", -1)
        ),
        "safe_drain_telemetry_is_nonnegative": (
            not safe_boundary_drain
            or result.get("safe_boundary_drain_ffe4_nonzero_frames", -1) >= 0
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def ffe4_transfer_policy_controls() -> dict[str, bool]:
    valid = {
        "ffe4_zero_play_frames": 80,
        "ffe4_nonzero_play_frames": 220,
        "first_ffe4_nonzero_play_frame": 81,
        "first_ffe4_nonzero_value": 1,
        "window_helper_hits": 0,
        "window_helper_ffe4_nonzero_hits": 0,
        "safe_boundary_drain_ffe4_nonzero_frames": 0,
    }

    def passes(payload: dict, *, safe: bool = True) -> bool:
        return ffe4_transfer_contract(
            payload, frames=300, safe_boundary_drain=safe,
        )["passed"]

    def mutated(**changes: object) -> dict:
        payload = dict(valid)
        payload.update(changes)
        return payload

    return {
        "zero_helper_with_nonzero_callback_context_passes": passes(valid),
        "missing_frame_rejected": not passes(mutated(
            ffe4_zero_play_frames=79
        )),
        "incoherent_first_nonzero_rejected": not passes(mutated(
            first_ffe4_nonzero_play_frame=-1, first_ffe4_nonzero_value=-1,
        )),
        "zero_helper_nonmenu_route_passes": passes(valid),
        "negative_helper_count_rejected": not passes(mutated(
            window_helper_hits=-1
        )),
        "nonzero_helper_entry_rejected": not passes(mutated(
            window_helper_hits=1, window_helper_ffe4_nonzero_hits=1
        )),
        "negative_safe_drain_rejected": not passes(mutated(
            safe_boundary_drain_ffe4_nonzero_frames=-1
        )),
        "ordinary_run_ignores_absent_drain": passes(
            mutated(safe_boundary_drain_ffe4_nonzero_frames=7), safe=False,
        ),
        "boolean_count_rejected": not passes(mutated(window_helper_hits=True)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--expected-sha256", type=parse_sha256, required=True)
    parser.add_argument("--static-receipt", type=Path, required=True)
    parser.add_argument(
        "--expected-static-receipt-sha256", type=parse_sha256, required=True,
    )
    parser.add_argument("--entry-addr", type=parse_address, required=True)
    parser.add_argument(
        "--phase-addr", type=parse_address, action="append", required=True,
        help="safe FF55-idle/VBK0/SVBK1 phase boundary; repeat for every phase",
    )
    parser.add_argument("--exit-addr", type=parse_address, required=True)
    parser.add_argument("--fallback-addr", type=parse_address, required=True)
    parser.add_argument("--caller-reject-addr", type=parse_address)
    parser.add_argument("--atomic-fallback-addr", type=parse_address)
    parser.add_argument(
        "--outer-return-addr", type=parse_address, action="append", required=True,
        help=(
            "known entry-stack outer caller; repeat for every static caller, "
            "including callers that are deliberately rejected"
        ),
    )
    parser.add_argument(
        "--dma-command-addr", type=parse_address, action="append", required=True,
        help="HDMA5 write opcode address; repeat for every command site",
    )
    parser.add_argument("--compiler-bank", type=parse_byte, required=True)
    parser.add_argument(
        "--exit-bank", type=parse_byte,
        help="mapped ROM bank at the final restored-state breakpoint",
    )
    parser.add_argument("--compiler-start", type=parse_address, required=True)
    parser.add_argument("--compiler-end", type=parse_address, required=True)
    parser.add_argument(
        "--expected-dma-command", type=parse_byte, action="append",
        required=True, help="allowed live-play HDMA5 byte; repeatable",
    )
    parser.add_argument("--entry-ie", type=parse_byte, default=0x07)
    parser.add_argument("--phase-ie", type=parse_byte, default=0x04)
    parser.add_argument("--exit-ie", type=parse_byte, default=0x07)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument(
        "--safe-boundary-drain", action="store_true",
        help=(
            "freeze all measured counters at --frames, then allow only the "
            "already-entered helper to reach its exact restored outer return"
        ),
    )
    parser.add_argument(
        "--safe-boundary-max-frames", type=int, default=120,
        help="fail-closed host-frame bound for --safe-boundary-drain",
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(args.frames >= 120, "ABI smoke requires at least 120 play frames")
    require(args.timeout > 0, "timeout must be positive")
    require(args.safe_boundary_max_frames > 0,
            "safe-boundary drain bound must be positive")
    require(args.compiler_start <= args.compiler_end,
            "compiler address range is reversed")
    require(len(set(args.phase_addr)) == len(args.phase_addr),
            "phase addresses must be unique")
    require(len(set(args.expected_dma_command)) == len(args.expected_dma_command),
            "expected DMA commands must be unique")
    require(len(set(args.dma_command_addr)) == len(args.dma_command_addr),
            "DMA command addresses must be unique")
    require(len(set(args.outer_return_addr)) == len(args.outer_return_addr),
            "outer return addresses must be unique")
    require(all(command & 0x80 for command in args.expected_dma_command),
            "this helper must use HBlank DMA during live gameplay")
    exit_bank = args.compiler_bank if args.exit_bank is None else args.exit_bank

    candidate = args.candidate.resolve()
    static_receipt_path = args.static_receipt.resolve()
    output = args.output.resolve()
    require(candidate.is_file(), f"candidate is missing: {candidate}")
    require(static_receipt_path.is_file(),
            f"static receipt is missing: {static_receipt_path}")
    require(PROBE.is_file(), f"probe is missing: {PROBE}")
    require(LAUNCHER.is_file(), f"single-flight launcher is missing: {LAUNCHER}")
    allowed_scratch = [ROOT / "tmp", Path("/mnt/data/tmp")]
    require(
        any(output != root.resolve() and output.is_relative_to(root.resolve())
            for root in allowed_scratch if root.exists()),
        "output must be a child of repository tmp/ or /mnt/data/tmp/",
    )
    output.mkdir(parents=True, exist_ok=True)
    raw_result = output / "raw-result.json"
    done = output / "DONE"
    attr_trace = output / "attr-events.tsv"
    lifecycle = output / "lifecycle.tsv"
    log = output / "emulator.log"
    receipt_path = output / "receipt.json"
    for stale in (
        raw_result, done, attr_trace, lifecycle, log, receipt_path,
    ):
        stale.unlink(missing_ok=True)
    for stale_save in sorted(output.glob("*.sav")):
        stale_save.unlink()

    verifier = Path(__file__).resolve()
    identity_before = {
        "candidate_sha256": sha256(candidate),
        "probe_sha256": sha256(PROBE),
        "verifier_sha256": sha256(verifier),
        "launcher_sha256": sha256(LAUNCHER),
        "static_receipt_sha256": sha256(static_receipt_path),
    }
    require(identity_before["candidate_sha256"] == args.expected_sha256,
            "candidate SHA-256 does not match --expected-sha256")
    require(
        identity_before["static_receipt_sha256"]
        == args.expected_static_receipt_sha256,
        "static receipt SHA-256 does not match "
        "--expected-static-receipt-sha256",
    )
    static_contract = validate_static_receipt(
        static_receipt_path, candidate,
        identity_before["candidate_sha256"], args,
    )
    probe_ownership_contract = validate_probe_ownership_contract(
        args.compiler_bank
    )
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE_SPEED_TARGET": "6",
        "STAGE_SPEED_OUT": str(raw_result),
        "STAGE_SPEED_DONE": str(done),
        "STAGE_SPEED_TRACE": str(attr_trace),
        "STAGE_SPEED_LIFECYCLE": str(lifecycle),
        "STAGE_SPEED_MODE": "patrol",
        "STAGE_SPEED_FRAMES": str(args.frames),
        "STAGE_SPEED_DMA_COMMAND_ADDR": "0",
        "STAGE_SPEED_DMA_COMMAND_ADDRS": ",".join(
            map(str, args.dma_command_addr)
        ),
        "STAGE_SPEED_COMPILER_BANK": str(args.compiler_bank),
        "STAGE_SPEED_COMPILER_START": str(args.compiler_start),
        "STAGE_SPEED_COMPILER_END": str(args.compiler_end),
        "STAGE_SPEED_ABI_ENTRY_ADDR": str(args.entry_addr),
        "STAGE_SPEED_ABI_PHASE_ADDRS": ",".join(map(str, args.phase_addr)),
        "STAGE_SPEED_ABI_EXIT_ADDR": str(args.exit_addr),
        "STAGE_SPEED_ABI_FALLBACK_ADDR": str(args.fallback_addr),
        "STAGE_SPEED_ABI_CALLER_REJECT_ADDR": str(
            args.caller_reject_addr or 0
        ),
        "STAGE_SPEED_ABI_ATOMIC_FALLBACK_ADDR": str(
            args.atomic_fallback_addr or 0
        ),
        "STAGE_SPEED_ABI_OUTER_RETURNS": ",".join(
            map(str, args.outer_return_addr)
        ),
        "STAGE_SPEED_ABI_BANK": str(args.compiler_bank),
        "STAGE_SPEED_ABI_EXIT_BANK": str(exit_bank),
        "STAGE_SPEED_ABI_ENTRY_IE": str(args.entry_ie),
        "STAGE_SPEED_ABI_PHASE_IE": str(args.phase_ie),
        "STAGE_SPEED_ABI_EXIT_IE": str(args.exit_ie),
        "STAGE_SPEED_ABI_EXIT_AF": str(0x01C0),
        "STAGE_SPEED_ABI_EXIT_BC": str(0x084D),
        "STAGE_SPEED_ABI_EXIT_DE": str(0xC3E0),
        "STAGE_SPEED_ABI_EXIT_FFA5": "0",
        "STAGE_SPEED_ABI_EXIT_FFE0": "0",
        "STAGE_SPEED_ABI_EXIT_HLS": f"{0x9800},{0x9C00}",
        "STAGE_SPEED_WINDOW_HELPER_ADDR": str(WINDOW_HELPER_ADDR),
        "STAGE_SPEED_WINDOW_HELPER_BANK": str(WINDOW_HELPER_BANK),
        "STAGE_SPEED_SAFE_BOUNDARY_DRAIN": (
            "1" if args.safe_boundary_drain else "0"
        ),
        "STAGE_SPEED_SAFE_BOUNDARY_MAX_FRAMES": str(
            args.safe_boundary_max_frames
        ),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    command = [
        str(LAUNCHER), "--fastforward",
        "-C", f"savegamePath={output}",
        "-C", f"savestatePath={output}",
        str(candidate), "--script", str(PROBE), "-l", "0",
    ]
    with log.open("wb") as stream:
        process = subprocess.Popen(
            command, cwd=output, env=environment,
            stdout=stream, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + args.timeout
        try:
            while time.monotonic() < deadline:
                if raw_result.is_file() and done.is_file():
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            stop_owned_process(process)
    require(raw_result.is_file() and done.is_file(),
            f"ABI smoke did not finish; see {log}")
    require(done.read_text() == "OK", "ABI smoke completion marker is invalid")
    result = json.loads(raw_result.read_text())
    identity_after = {
        "candidate_sha256": sha256(candidate),
        "probe_sha256": sha256(PROBE),
        "verifier_sha256": sha256(verifier),
        "launcher_sha256": sha256(LAUNCHER),
        "static_receipt_sha256": sha256(static_receipt_path),
    }

    require(identity_before == identity_after,
            "candidate, probe, verifier, or launcher changed during run")
    require(result.get("target") == 6 and result.get("expected_scene") == 8,
            "probe did not run the Stage-7 fixture")
    require(result.get("final_scene") == 8, "candidate left Stage-7 gameplay")
    require(result.get("breakpoints_available") is True,
            "one or more ABI breakpoints were unavailable")
    if args.safe_boundary_drain:
        require(result.get("frames") == args.frames,
                "safe-boundary drain changed the measured frame window")
    else:
        require(args.frames <= result.get("frames", -1) <= args.frames + 120,
                "ABI helper did not drain in its bounded finish window")
    require(result.get("non_dma_scene_mismatch_frames") == 0,
            "candidate had a real scene mismatch")
    require(result.get("abi_enabled") is True, "ABI instrumentation was disabled")
    entries = result.get("abi_entry_hits", 0)
    exits = result.get("abi_exit_hits", 0)
    require(entries >= 4, f"too few helper entries: {entries}")
    native_fallbacks = result.get("abi_fallback_hits", 0)
    caller_rejects = result.get("abi_caller_reject_hits", 0)
    atomic_fallbacks = result.get("abi_atomic_fallback_hits", 0)
    if args.safe_boundary_drain:
        require(native_fallbacks > 0,
                "long patrol did not exercise the guarded native fallback")
    else:
        require(native_fallbacks == 0,
                "eligible controlled Stage-7 smoke took a native fallback")
    require(caller_rejects == 0,
            "controlled natural $12E0 smoke took the caller-reject path")
    require(atomic_fallbacks == 0,
            "controlled gameplay smoke took an after-atomic fallback")
    require(exits == entries, f"unbalanced helper entry/exit: {entries}/{exits}")
    fast_exits = result.get("abi_fast_exit_hits", 0)
    native_exits = result.get("abi_native_exit_hits", 0)
    partition_controls = abi_exit_partition_policy_controls()
    require(all(partition_controls.values()),
            "internal fast/native exit partition controls failed")
    exit_partition = abi_exit_partition_contract(result)
    require(exit_partition["passed"],
            "fast/native $436D exit partition failed: "
            + ",".join(
                name for name, passed in exit_partition["checks"].items()
                if not passed
            ))
    require(result.get("abi_final_depth") == 0, "helper remained active at finish")
    require(result.get("abi_pending_outer_return") == -1,
            "helper did not reach its post-RETI outer caller")
    require(result.get("abi_violations") == 0,
            "ABI boundary violation: "
            + ";".join(result.get("abi_violation_examples", [])))
    phase_hits = result.get("abi_phase_hits", {})
    stack_hits = result.get("abi_outer_stack_hits", {})
    admitted_entries = entries - native_fallbacks
    require(admitted_entries >= 4,
            f"too few admitted helper entries: {admitted_entries}")
    for address in args.phase_addr:
        require(phase_hits.get(f"0x{address:04X}") == admitted_entries,
                f"phase ${address:04X} did not execute once per admitted helper")
    post_hits = result.get("abi_outer_post_hits", {})
    require(sum(stack_hits.values()) == entries,
            "not every helper entry had a classified outer return")
    require(sum(post_hits.values()) == exits,
            "not every helper exit reached its post-RETI outer caller")
    for address in args.outer_return_addr:
        key = f"0x{address:04X}"
        require(post_hits.get(key, 0) == stack_hits.get(key, 0),
                f"outer return ${address:04X} did not balance")
    require(result.get("abi_timer_inside", 0) > 0,
            "no Timer IRQ reached the helper's bounded service points")
    require(result.get("abi_timer_isr_pairs") == result.get("abi_timer_inside"),
            "an in-helper Timer ISR did not complete before helper exit")
    require(result.get("abi_timer_source_changes") == 0,
            "Timer ISR mutated packed C1A0-C3DF source data")
    require(result.get("abi_timer_bank_state_changes") == 0,
            "Timer ISR disturbed FF55/VBK/SVBK/IE state")
    require(result.get("abi_timer_after_exit", 0) > 0,
            "Timer IRQ service did not resume after helper exit")
    require(result.get("last_main_loop_frame", -1) >= args.frames - 30,
            "main loop stopped before the end of the smoke")
    require(result.get("max_main_loop_gap", 9999) <= 30,
            "helper caused a main-loop gap over 30 rendered frames")
    require(result.get("final_hdma5") == 0xFF, "HDMA remained active at finish")
    require(result.get("final_vbk", 0xFF) & 1 == 0, "VBK was not restored")
    require(result.get("final_svbk", 0xFF) & 7 == 1, "SVBK was not restored")
    require(result.get("final_ie") == args.exit_ie, "IE was not restored")
    ffe4_controls = ffe4_transfer_policy_controls()
    require(all(ffe4_controls.values()),
            "internal FFE4 transfer mutation controls failed")
    ffe4_contract = ffe4_transfer_contract(
        result, frames=result["frames"],
        safe_boundary_drain=args.safe_boundary_drain,
    )
    require(ffe4_contract["passed"],
            "r265 FFE4-zero transfer contract failed: "
            + ",".join(
                name for name, passed in ffe4_contract["checks"].items()
                if not passed
            ))
    require(result.get("attr_dma_scene_violations") == 0,
            "DMA command executed outside Stage 7")
    require(result.get("attr_gdma_commands") == 0,
            "live helper issued a general DMA command")
    commands = dma_commands(result)
    require(commands, "no candidate DMA command was observed")
    expected_commands = set(args.expected_dma_command)
    require(set(commands) == expected_commands,
            f"observed DMA commands {sorted(set(commands))}, "
            f"expected {sorted(expected_commands)}")
    require(result.get("attr_dma_commands") == result.get("attr_hblank_commands"),
            "not every candidate DMA command was HBlank mode")
    site_hits = result.get("attr_dma_site_hits", {})
    for address in args.dma_command_addr:
        require(site_hits.get(f"0x{address:04X}", 0) > 0,
                f"DMA command site ${address:04X} was not observed")
    attribute_site = "0x" + static_contract["attribute_dma_site"]
    tile_site = "0x" + static_contract["tile_dma_site"]
    attribute_commands_per_entry = static_contract[
        "attribute_commands_per_admitted_entry"
    ]
    tile_commands_per_entry = static_contract[
        "tile_commands_per_admitted_entry"
    ]
    drain_site_hits = {attribute_site: 0, tile_site: 0}
    if args.safe_boundary_drain:
        for raw_record in result.get("safe_boundary_drain_dma_trace", []):
            fields = raw_record.split(":")
            require(len(fields) == 5,
                    "malformed safe-boundary DMA trace during count audit")
            site_key = "0x" + fields[1].upper()
            require(site_key in drain_site_hits,
                    "safe-boundary DMA trace used an undeclared site")
            drain_site_hits[site_key] += 1
    require(
        site_hits.get(attribute_site, 0) + drain_site_hits[attribute_site] == (
            admitted_entries * attribute_commands_per_entry
        ),
        "attribute DMA site count is not exact per admitted helper entry",
    )
    require(
        site_hits.get(tile_site, 0) + drain_site_hits[tile_site]
        == admitted_entries * tile_commands_per_entry,
        "tile DMA site count is not exact per admitted helper entry",
    )
    require(
        result.get("attr_dma_commands")
        + result.get("safe_boundary_drain_dma_commands", 0)
        == admitted_entries * (
            attribute_commands_per_entry + tile_commands_per_entry
        ),
        "full DMA command count is not exact per admitted helper entry",
    )

    boundary_controls = safe_boundary_policy_controls()
    require(all(boundary_controls.values()),
            "internal safe-boundary mutation controls failed")
    boundary_contract = None
    if args.safe_boundary_drain:
        boundary_contract = safe_boundary_contract(
            result,
            frames=args.frames,
            max_drain_frames=args.safe_boundary_max_frames,
            admitted_outer_return=0x12E0,
            dma_sites=set(args.dma_command_addr),
            allowed_dma_commands=set(args.expected_dma_command),
            exit_ie=args.exit_ie,
        )
        require(boundary_contract["passed"],
                "safe-boundary finalization failed: "
                + ",".join(
                    name for name, passed in
                    boundary_contract["checks"].items() if not passed
                ))

    receipt = {
        "schema": "penta-stage7-dual-plane-abi-smoke-v1",
        "status": "PASS",
        "candidate": str(candidate),
        "expected_candidate_sha256": args.expected_sha256,
        "expected_static_receipt_sha256": (
            args.expected_static_receipt_sha256
        ),
        "identity_before": identity_before,
        "identity_after": identity_after,
        "static_contract": static_contract,
        "probe_ownership_contract": probe_ownership_contract,
        "command": command,
        "contract": {
            "entry": f"bank{args.compiler_bank}:${args.entry_addr:04X}",
            "phases": [
                f"bank{args.compiler_bank}:${address:04X}"
                for address in args.phase_addr
            ],
            "exit": f"bank{exit_bank}:${args.exit_addr:04X}",
            "fallback": f"bank{args.compiler_bank}:${args.fallback_addr:04X}",
            "caller_reject": (
                None if args.caller_reject_addr is None
                else f"bank{args.compiler_bank}:${args.caller_reject_addr:04X}"
            ),
            "atomic_fallback": (
                None if args.atomic_fallback_addr is None
                else f"bank{args.compiler_bank}:${args.atomic_fallback_addr:04X}"
            ),
            "outer_returns": [
                f"fixed:${address:04X}" for address in args.outer_return_addr
            ],
            "dma_commands": [
                f"bank{args.compiler_bank}:${address:04X}"
                for address in args.dma_command_addr
            ],
            "expected_ie": [args.entry_ie, args.phase_ie, args.exit_ie],
            "expected_exit_registers": {
                "AF": "01C0", "BC": "084D", "DE": "C3E0",
                "HL": ["9800", "9C00"], "FFA5": "00", "FFE0": "00",
            },
            "expected_dma_commands": [
                f"{command:02X}" for command in args.expected_dma_command
            ],
            "safe_boundary_drain": {
                "enabled": args.safe_boundary_drain,
                "measurement_frames": args.frames,
                "maximum_unmeasured_drain_frames": (
                    args.safe_boundary_max_frames
                ),
                "admitted_outer_return": "fixed:$12E0",
                "measurement_counters_frozen_during_drain": True,
            },
        },
        "observed": {
            "frames": result["frames"],
            "entries": entries,
            "admitted_entries": admitted_entries,
            "fallbacks": {
                "native": native_fallbacks,
                "caller_reject": caller_rejects,
                "after_atomic": atomic_fallbacks,
                "examples": result.get("abi_fallback_examples", []),
            },
            "phase_hits": phase_hits,
            "exits": exits,
            "fast_exits": fast_exits,
            "native_fallback_exits": native_exits,
            "outer_stack_hits": stack_hits,
            "outer_post_hits": post_hits,
            "observed_outer_callers": sorted(
                key for key, hits in stack_hits.items() if hits > 0
            ),
            "timer_inside": result["abi_timer_inside"],
            "timer_isr_pairs": result["abi_timer_isr_pairs"],
            "timer_source_changes": result["abi_timer_source_changes"],
            "timer_bank_state_changes": result[
                "abi_timer_bank_state_changes"
            ],
            "timer_after_exit": result["abi_timer_after_exit"],
            "dma_commands": [f"{command:02X}" for command in commands],
            "dma_site_hits": site_hits,
            "final": {
                "ff55": result["final_hdma5"],
                "vbk": result["final_vbk"],
                "svbk": result["final_svbk"],
                "ie": result["final_ie"],
            },
            "safe_boundary": boundary_contract,
            "FFE4_transfer": ffe4_contract,
        },
        "safe_boundary_policy_controls": boundary_controls,
        "abi_exit_partition_policy_controls": partition_controls,
        "abi_exit_partition": exit_partition,
        "FFE4_transfer_policy_controls": ffe4_controls,
        "ime_note": (
            "IME is not exposed by mGBA Lua; Timer-vector liveness inside and "
            "after the helper is the live surrogate, backed by static EI/DI proof."
        ),
        "raw_result": str(raw_result),
        "raw_result_sha256": sha256(raw_result),
        "attr_trace_sha256": sha256(attr_trace),
        "lifecycle_sha256": sha256(lifecycle),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
