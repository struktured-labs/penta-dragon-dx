#!/usr/bin/env python3
"""Bind the r265 Stage-1 menu/hazard receipt without launching an emulator.

This verifier is intentionally narrow.  It authenticates the exact duplicate
artifact corpus that exercises the reported stationary menu -> item use ->
menu close -> low-health hazard failure.  It does not turn the receipt's four
explicitly excluded diagnostics into passes, and it does not claim a fresh
r265 mutation run.

The last four-way mutation receipt belongs to the exact aa4 r264 ancestor.
Its calibration is carried forward only as a static transfer: the e048 Stage-7
patch and the r265 Window-helper patch are exhaustively confined away from all
four mutated Stage-1 instruction spans, while scene $02 keeps the same Window
invalidation semantics.  A future live r265 mutation run can supersede that
limited transfer evidence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
from typing import Any
import zlib


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

CANDIDATE = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
LIVE_RECEIPT = (
    ROOT
    / "tmp/stage7-menu-signature-invalidation-r265/"
    "stage1-current-hazard-menu-r1/receipt.json"
)
AA4_CANDIDATE = ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb"
E048_CANDIDATE = ROOT / "tmp/stage7-dual-plane-hdma-r264/candidate.gb"
E048_STATIC_RECEIPT = (
    ROOT / "tmp/stage7-dual-plane-hdma-r264/static-receipt.json"
)
HELPER_EQUIVALENCE_RECEIPT = (
    ROOT
    / "tmp/stage7-menu-signature-invalidation-r265/"
    "helper-equivalence-static-receipt.json"
)
R265_BUILD_RECEIPT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/static-receipt.json"
)
AA4_MUTATION_RECEIPT = (
    ROOT
    / "tmp/stage1-menu-hidden-repair-r264/"
    "current-hazard-mutations/receipt.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "tmp/stage7-menu-signature-invalidation-r265/"
    "stage1-current-hazard-menu-r1/bound-offline-receipt.json"
)

EXPECTED = {
    "candidate": "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273",
    "live_receipt": "1e56ed46137a8fb4f1da8a64e009e8208c0b63f51a1a45fbeccff8f6df521d55",
    "source_state": "d2fc9ce5bd93bec73d88bd2234cc56b7b76440cf1d51debd858ae9877aa83456",
    "source_state_receipt": "f171373a22e077d43709f8a17cbced708f9a1478f1560a36ffb9d7fb7e166e38",
    "aa4_candidate": "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1",
    "e048_candidate": "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0",
    "e048_static_receipt": "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272",
    "helper_equivalence_receipt": "295ce612d6dc1dead72e776f44dafb3bd22b6bc0e44b101435b27d7ddafe0583",
    "r265_build_receipt": "9567c8babe7be863ecbd5a7c6ba9a8234cd81aef7508a1f6e3c184773c3a6ab7",
    "aa4_mutation_receipt": "a786d5937c634347bb9a34740f11cd85586e43062d14720d0963fb6d3102738e",
    "artifact_manifest": "cedd24a859763592a5e61cee22ef28b0eae90ba4ca6b383c92fb03af03c01174",
    "normalized_raw_report": "074ffd934e60d5fc7bb76711521b0472203f1cf26887d88af8ad8bae672a1323",
}

EXPECTED_TOOLS = {
    "current_receipt_verifier": (
        ROOT / "scripts/diagnostics/verify_stage1_current_hazard_menu.py",
        "2128d7e130a2207e27d9571ba8e2d4ac18c0c3c50c011d2a2ac11f4bf76898dd",
    ),
    "hazard_menu_contract": (
        ROOT / "scripts/diagnostics/verify_stage1_hazard_menu.py",
        "177583878eab5eaa7d47ea1fab9fd306113c1b7a8a52932ee7366706d3d75a92",
    ),
    "spike_verifier": (
        ROOT / "scripts/diagnostics/verify_stage1_spike_palettes.py",
        "239a87eb2a73f26f6319418afe2853f4c5b38438b2b576abdb73a635fefaf34f",
    ),
    "spike_probe": (
        ROOT / "scripts/diagnostics/probe_stage1_spike_palettes.lua",
        "da5e18291fce446f64011ebc90870c53c6db8c0128a5f10f5f6caa9fa1d88338",
    ),
    "state_generator": (
        ROOT / "scripts/diagnostics/generate_stage1_hazard_state.py",
        "9f8d06e65d3c2c07a044e5c85c4712fc07d3b5bec3284b42c40380c5d83cd185",
    ),
    "mutation_verifier": (
        ROOT / "scripts/diagnostics/verify_stage1_current_hazard_mutations.py",
        "d6d4f77a13f8fe1eb700ac00016a21b14801669f7c3a4b2b01301eaf777da916",
    ),
    "singleflight_launcher": (
        ROOT / "scripts/mgba-qt-singleflight",
        "46fe5b57771627e9141e359bd93c9d821c2b873d34162e355dfec33896649570",
    ),
    "palette_yaml": (
        ROOT / "palettes/penta_palettes_v097.yaml",
        "71e3ae76ac88151173d2113df1592c470ecd0c8a984e60ca0d36f84174a1935a",
    ),
}

REQUIRED_HAZARD_CHECKS = (
    "visible patterned floors never inherit a hazard palette",
    "every atomic floor compile reads Dungeon BG0",
    "historical spike room remains a live Stage-1 phase",
    "active map contains the rotating spike family",
    "every active-map spike tile uses its YAML material split",
    "all bank-1 neutral/tooth art finished and matches bank 0",
    "visible map contains BG5 rings and fire body",
    "visible support and shadow cells remain metallic BG6",
    "left/right endpoints match tooth/retracted semantics every frame",
    "every visible animation frame keeps tile and palette atomic",
    "live BG5 CRAM matches the candidate",
    "live Stage-1 BG7 CRAM matches the YAML hazard row",
    "Stage-1 hazard BG5/BG7 never flicker during the sampled interval",
    "all four live cylinder phases have rendered-frame receipts",
    "normalized fixtures render current candidate hazard art",
    "rendered candidate pixels never expose gray palette-0 teeth",
    "every rendered phase visibly contains candidate BG7 gold teeth",
    "rendered cylinder phases visibly contain red and gold material",
    "every native map flip is transfer-idle and complete",
    "SELECT opens and holds the native item menu",
    "frozen item menu never recolors visible Stage-1 floor cells",
    "frozen item menu keeps every visible BG attribute exact",
    "frozen item menu never exposes gray spike teeth",
    "item Window never aliases the visible gameplay BG map",
    "item use input is accepted for six visible-menu frames",
    "seeded item crosses the real native item dispatcher",
    "item-use redraw keeps Window and gameplay maps isolated",
    "SELECT closes the native item menu on schedule",
    "menu-close recovery uses the requested movement policy",
    "menu close executes exactly one native hidden-map handoff",
    "stationary post-menu gameplay has no stale red floor attrs",
    "stationary post-menu gameplay keeps every visible BG attribute exact",
    "stationary post-menu gameplay keeps BG5/BG7 CRAM stable",
    "stationary post-menu hazard tiles and attrs stay atomic",
    "left/right spike endpoints stay gold after menu close",
    "post-menu rendered frames contain no gray tooth pixels",
    "semantic hazard attributes never write the visible BG map",
    "menu close never repaints hazards into the visible BG map",
    "warning health is held after the menu/item sequence",
    "post-menu warning mode leaves floors, endpoints and hazards exact",
)

EXCLUDED_FALSE_DIAGNOSTICS = {
    "both physical maps are observed active with exact tooth colors",
    "hidden-map preparation never leaks through a physical-map flip",
    "a semantic hazard publication path is exercised",
    "rendered lower field has no legacy red/gold palette wash",
}

GB_STATE_SIZE = 0x11800
GB_STATE_MAGIC = 0x00400003


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    require(path.is_file(), f"required file is missing: {path}")
    return digest(path.read_bytes())


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def scratch(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(
        root.exists() and resolved != root and resolved.is_relative_to(root)
        for root in roots
    ), "output must be a child of repo tmp/ or /mnt/data/tmp/")
    return resolved


def png_state(path: Path) -> bytes:
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"not an mGBA PNG savestate: {path}")
    offset = 8
    states: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        require(offset + 12 <= len(data), f"truncated PNG chunk: {path}")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc = data[offset + 8 + length:offset + 12 + length]
        require(len(payload) == length and len(crc) == 4,
                f"truncated PNG payload: {path}")
        expected_crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        require(int.from_bytes(crc, "big") == expected_crc,
                f"bad PNG chunk CRC: {path}")
        if kind == b"gbAs":
            states.append(zlib.decompress(payload))
        if kind == b"IEND":
            saw_iend = True
        offset += 12 + length
    require(offset == len(data) and saw_iend,
            f"savestate PNG is incomplete: {path}")
    require(len(states) == 1, f"expected one gbAs chunk: {path}")
    state = states[0]
    require(len(state) == GB_STATE_SIZE,
            f"wrong gbAs size {len(state):#x}: {path}")
    require(int.from_bytes(state[:4], "little") == GB_STATE_MAGIC,
            f"unsupported gbAs version: {path}")
    return state


def state_binds_rom(state_path: Path, rom: bytes) -> dict[str, Any]:
    state = png_state(state_path)
    state_crc = int.from_bytes(state[4:8], "little")
    rom_crc = zlib.crc32(rom) & 0xFFFFFFFF
    require(state_crc == rom_crc,
            f"savestate ROM CRC is not candidate-bound: {state_path}")
    return {
        "sha256": sha256(state_path),
        "gbas_sha256": digest(state),
        "rom_crc32": f"{rom_crc:08x}",
    }


def normalized_report(path: Path, replay_root: Path) -> bytes:
    payload = path.read_bytes()
    return payload.replace(str(replay_root.resolve()).encode(), b"<REPLAY>")


def artifact_manifest(replay_root: Path) -> tuple[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in replay_root.rglob("*") if item.is_file()):
        name = path.relative_to(replay_root).as_posix()
        payload = (
            normalized_report(path, replay_root)
            if name == "current-hazard-menu.txt"
            else path.read_bytes()
        )
        rows.append({
            "path": name,
            "size": len(payload),
            "sha256": digest(payload),
        })
    encoded = json.dumps(
        rows, sort_keys=True, separators=(",", ":")
    ).encode()
    return digest(encoded), rows


def audit_live_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    require(receipt.get("schema") == "penta-stage1-current-hazard-menu-v1",
            "wrong Stage-1 live receipt schema")
    require(receipt.get("passed") is True,
            "Stage-1 targeted live receipt is not PASS")
    require(receipt.get("rom_sha256") == EXPECTED["candidate"],
            "Stage-1 live receipt targets another ROM")
    require(receipt.get("state_sha256") == EXPECTED["source_state"],
            "Stage-1 live receipt targets another state")
    require(receipt.get("state_receipt_sha256")
            == EXPECTED["source_state_receipt"],
            "Stage-1 live receipt targets another state receipt")
    require(receipt.get("timeline") == {
        "menu_anchor_delay": 20,
        "menu_hold_frames": 240,
        "menu_use_delay": 80,
        "low_health_delay": 270,
    }, "Stage-1 live timeline changed")
    top_checks = receipt.get("checks")
    require(isinstance(top_checks, dict) and top_checks
            and all(value is True for value in top_checks.values()),
            "Stage-1 top-level check failed")
    replays = receipt.get("replays")
    require(isinstance(replays, list) and len(replays) == 2,
            "exactly two Stage-1 replays are required")
    require(replays[0] == replays[1],
            "Stage-1 stable summaries are not byte-semantic equal")
    for index, replay in enumerate(replays, 1):
        checks = replay.get("checks")
        require(isinstance(checks, dict),
                f"replay {index} has no check mapping")
        require(all(checks.get(name) is True for name in REQUIRED_HAZARD_CHECKS),
                f"replay {index} failed a required targeted hazard check")
        observed_false = {name for name, passed in checks.items()
                          if passed is not True}
        require(observed_false == EXCLUDED_FALSE_DIAGNOSTICS,
                f"replay {index} excluded diagnostics changed: "
                f"{sorted(observed_false)}")
        expected_scalars = {
            "scene": "02", "room": "01", "menu_open_frames": 241,
            "menu_closed_frame": 272, "post_menu_closed_frames": 379,
            "post_menu_input_mask": 0, "menu_use_input_frames": 6,
            "menu_a_handler_hits": 1, "menu_item_dispatch_hits": 1,
            "menu_close_repair_hits": 1, "menu_close_native_tail_hits": 1,
            "map_flip_events": 86, "unsafe_map_flip_events": 0,
            "transient_mismatch_frames": 0, "floor_mismatch_frames": 0,
            "palette_mismatch_frames": 0, "endpoint_mismatch_frames": 0,
            "post_menu_transient_mismatch_frames": 0,
            "post_menu_palette_mismatch_frames": 0,
            "post_menu_floor_mismatch_frames": 0,
            "post_menu_endpoint_mismatch_frames": 0,
            "active_hazard_attr_write_hits": 0,
            "post_menu_active_hazard_attr_write_hits": 0,
            "rendered_wrong_palette0_tooth_cells": 0,
            "menu_map_alias_frames": 0, "low_health_forced_frames": 350,
        }
        for name, expected in expected_scalars.items():
            require(replay.get(name) == expected,
                    f"replay {index} {name} changed")
        require(replay.get("map_flip_bases") == ["9800", "9C00"],
                f"replay {index} did not alternate both physical maps")
        temporal = replay.get("temporal_raster")
        require(temporal == {
            "enabled": False,
            "baseline_frames": 6,
            "checked_frames": 124,
            "mismatch_frames": 62,
            "first_mismatch": {
                "frame": 280, "pixels": 231, "first_xy": [87, 0],
            },
        }, f"replay {index} temporal-raster limitation changed")
    return {
        "duplicate_stable_summaries": True,
        "required_targeted_checks": len(REQUIRED_HAZARD_CHECKS),
        "excluded_false_diagnostics": sorted(EXCLUDED_FALSE_DIAGNOSTICS),
        "menu_frames": 241,
        "stationary_post_menu_frames": 379,
        "low_health_frames": 350,
        "physical_map_flips": 86,
    }


def allowed_stage7_offsets() -> set[int]:
    def bank_offset(bank: int, address: int) -> int:
        return bank * 0x4000 + address - 0x4000

    allowed = {0x014E, 0x014F}
    for bank in (13, 16):
        allowed.add(bank_offset(bank, 0x7C76))
        allowed.update(range(
            bank_offset(bank, 0x7CA8), bank_offset(bank, 0x7CBE)
        ))
    allowed.update(range(bank_offset(22, 0x6C80), bank_offset(22, 0x7233)))
    allowed.update(range(bank_offset(22, 0x7500), bank_offset(22, 0x7560)))
    allowed.update(range(bank_offset(22, 0x7600), bank_offset(22, 0x7700)))
    return allowed


def allowed_r265_offsets() -> set[int]:
    start = 13 * 0x4000 + 0x6A40 - 0x4000
    return {0x014D, 0x014E, 0x014F, *range(start, start + 23)}


def difference_set(first: bytes, second: bytes) -> set[int]:
    require(len(first) == len(second) == 0x80000,
            "candidate ancestry ROM size changed")
    return {index for index, pair in enumerate(zip(first, second))
            if pair[0] != pair[1]}


def mutation_target_spans(rom: bytes) -> dict[str, tuple[int, bytes]]:
    def bank_offset(bank: int, address: int) -> int:
        return bank * 0x4000 + address - 0x4000

    targets = {
        "forced_visible_menu_repair": (0x77A8, bytes.fromhex("AF E0 E4 C9")),
        "alternate_phase": (bank_offset(19, 0x62CB), bytes.fromhex("9E 6D")),
        "short_left_endpoint": (bank_offset(19, 0x62D4), bytes([0x0B])),
        "short_right_endpoint": (bank_offset(19, 0x61A5), bytes([0x0A])),
    }
    return targets


def audit_mutation_transfer(
    aa4: bytes, e048: bytes, r265: bytes,
    static_receipt: dict[str, Any], equivalence: dict[str, Any],
    build_receipt: dict[str, Any], mutation_receipt: dict[str, Any],
) -> dict[str, Any]:
    aa4_e048 = difference_set(aa4, e048)
    e048_r265 = difference_set(e048, r265)
    require(len(aa4_e048) == 1856
            and aa4_e048 <= allowed_stage7_offsets(),
            "aa4->e048 differs outside the frozen Stage-7 patch")
    require(len(e048_r265) == 17
            and e048_r265 <= allowed_r265_offsets(),
            "e048->r265 differs outside Window helper/checksums")
    require(static_receipt.get("base_sha256") == EXPECTED["aa4_candidate"]
            and static_receipt.get("in_memory_candidate", {}).get("sha256")
            == EXPECTED["e048_candidate"]
            and static_receipt.get("in_memory_candidate", {}).get(
                "changed_byte_count"
            ) == 1856,
            "e048 static ancestry receipt changed")
    identities = equivalence.get("identities", {})
    require(equivalence.get("status")
            == "STATIC_PASS_REBIND_WRAPPERS_REQUIRED"
            and identities.get("e048_rom") == EXPECTED["e048_candidate"]
            and identities.get("r265_rom") == EXPECTED["candidate"],
            "r265 helper-equivalence ancestry changed")
    require(build_receipt.get("candidate_sha256") == EXPECTED["candidate"]
            and build_receipt.get("status")
            == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "r265 build receipt changed")
    timing = build_receipt.get("timing_t_cycles", {})
    require(timing.get("FFE4_nonzero_scene02") == {
        "old": 112, "new": 116, "delta": 4,
        "old_opcode_t_cycles": [12, 4, 8, 16, 8, 8, 4, 16, 16, 4, 16],
        "new_opcode_t_cycles": [12, 4, 8, 16, 8, 12, 4, 16, 16, 4, 16],
    }, "r265 scene-$02 timing/semantics receipt changed")
    behavior = build_receipt.get("signature_contract", {})
    require(behavior.get("scene02")
            == "DF53=DF57=0 while FFE4!=0 (preserved)",
            "r265 no longer preserves scene-$02 Window invalidation")

    require(mutation_receipt.get("schema")
            == "penta-stage1-current-hazard-mutations-v1"
            and mutation_receipt.get("passed") is True
            and mutation_receipt.get("source_sha256")
            == EXPECTED["aa4_candidate"],
            "aa4 mutation receipt is not exact PASS")
    require(all(value is True
                for value in mutation_receipt.get("checks", {}).values())
            and len(mutation_receipt.get("checks", {})) == 4,
            "aa4 mutation calibration is incomplete")
    for name, result in mutation_receipt.get("mutants", {}).items():
        require(result.get("route_valid") is True
                and result.get("visibly_rejected") is True
                and result.get("rejected") is True
                and result.get("passed") is True,
                f"aa4 mutation {name} did not fail closed")

    spans = mutation_target_spans(aa4)
    span_receipt = {}
    for name, (offset, expected) in spans.items():
        require(aa4[offset:offset + len(expected)] == expected,
                f"aa4 mutation preimage changed: {name}")
        require(e048[offset:offset + len(expected)] == expected
                and r265[offset:offset + len(expected)] == expected,
                f"mutation target is not byte-exact through r265: {name}")
        span_receipt[name] = {
            "file_offset": f"0x{offset:05X}",
            "length": len(expected),
            "sha256": digest(expected),
        }
    return {
        "status": "STATIC_TRANSFER_ONLY",
        "aa4_mutation_receipt": EXPECTED["aa4_mutation_receipt"],
        "aa4_to_e048_changed_bytes": len(aa4_e048),
        "e048_to_r265_changed_bytes": len(e048_r265),
        "mutation_instruction_spans": span_receipt,
        "scene02_window_semantics": "preserved; +4T only",
        "live_r265_mutants_run": False,
    }


def mutation_controls(live: dict[str, Any], aa4: bytes,
                      e048: bytes, r265: bytes) -> dict[str, bool]:
    controls: dict[str, bool] = {}

    def rejected(name: str, mutator: Any) -> None:
        mutant = copy.deepcopy(live)
        mutator(mutant)
        try:
            audit_live_payload(mutant)
        except AssertionError:
            controls[name] = True
        else:
            controls[name] = False

    rejected("mutated_live_status_rejected",
             lambda value: value.__setitem__("passed", False))
    rejected("mutated_candidate_identity_rejected",
             lambda value: value.__setitem__("rom_sha256", "0" * 64))
    rejected("mutated_required_check_rejected",
             lambda value: value["replays"][0]["checks"].__setitem__(
                 REQUIRED_HAZARD_CHECKS[0], False
             ))
    rejected("mutated_extra_false_check_rejected",
             lambda value: value["replays"][0]["checks"].__setitem__(
                 "unexpected diagnostic", False
             ))
    rejected("mutated_map_coverage_rejected",
             lambda value: value["replays"][0].__setitem__(
                 "map_flip_bases", ["9800"]
             ))
    rejected("mutated_visible_write_rejected",
             lambda value: value["replays"][0].__setitem__(
                 "active_hazard_attr_write_hits", 1
             ))
    rejected("mutated_temporal_limit_rejected",
             lambda value: value["replays"][0]["temporal_raster"].__setitem__(
                 "enabled", True
             ))

    outside = bytearray(e048)
    outside[0x2000] ^= 1
    controls["mutated_stage7_scope_rejected"] = not (
        difference_set(aa4, bytes(outside)) <= allowed_stage7_offsets()
    )
    window_outside = bytearray(r265)
    window_outside[0x2001] ^= 1
    controls["mutated_window_scope_rejected"] = not (
        difference_set(e048, bytes(window_outside)) <= allowed_r265_offsets()
    )
    target_offset, _ = mutation_target_spans(aa4)["short_left_endpoint"]
    target_mutant = bytearray(r265)
    target_mutant[target_offset] ^= 1
    controls["mutated_transferred_target_rejected"] = (
        target_mutant[target_offset:target_offset + 1]
        != aa4[target_offset:target_offset + 1]
    )
    require(all(controls.values()), "offline mutation control escaped")
    return controls


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "candidate": args.candidate.resolve(),
        "live_receipt": args.live_receipt.resolve(),
        "aa4_candidate": args.aa4_candidate.resolve(),
        "e048_candidate": args.e048_candidate.resolve(),
        "e048_static_receipt": args.e048_static_receipt.resolve(),
        "helper_equivalence_receipt": (
            args.helper_equivalence_receipt.resolve()
        ),
        "r265_build_receipt": args.r265_build_receipt.resolve(),
        "aa4_mutation_receipt": args.aa4_mutation_receipt.resolve(),
    }
    identities = {name: {"path": relative(path), "sha256": sha256(path)}
                  for name, path in paths.items()}
    for name, expected in EXPECTED.items():
        if name in identities:
            require(identities[name]["sha256"] == expected,
                    f"{name} identity changed")

    tool_identities = {
        name: {"path": relative(path), "sha256": sha256(path)}
        for name, (path, _expected) in EXPECTED_TOOLS.items()
    }
    for name, (_path, expected) in EXPECTED_TOOLS.items():
        require(tool_identities[name]["sha256"] == expected,
                f"{name} identity changed")

    live_path = paths["live_receipt"]
    live = json.loads(live_path.read_text())
    live_contract = audit_live_payload(live)
    state_path = Path(live["state"]).resolve()
    state_receipt_path = Path(live["state_receipt"]).resolve()
    require(sha256(state_path) == EXPECTED["source_state"],
            "source state bytes changed")
    require(sha256(state_receipt_path) == EXPECTED["source_state_receipt"],
            "source state receipt bytes changed")
    state_receipt = json.loads(state_receipt_path.read_text())
    require(state_receipt.get("passed") is True
            and state_receipt.get("rom_sha256") == EXPECTED["candidate"]
            and state_receipt.get("state_sha256") == EXPECTED["source_state"]
            and state_receipt.get("hazard_cells") == 77
            and state_receipt.get("tooth_cells") == 25
            and state_receipt.get("hardware", {}).get("settled") is True,
            "source hazard-state receipt changed")

    candidate = paths["candidate"].read_bytes()
    state_contract = state_binds_rom(state_path, candidate)
    raw_report_paths = [Path(path).resolve() for path in live["raw_reports"]]
    replay_roots = [path.parent for path in raw_report_paths]
    manifests = []
    for index, (root, report_path) in enumerate(
        zip(replay_roots, raw_report_paths), 1
    ):
        require(report_path.name == "current-hazard-menu.txt"
                and report_path.is_file(),
                f"replay {index} raw report is missing")
        manifest_sha, rows = artifact_manifest(root)
        require(manifest_sha == EXPECTED["artifact_manifest"],
                f"replay {index} artifact manifest changed")
        normalized_sha = digest(normalized_report(report_path, root))
        require(normalized_sha == EXPECTED["normalized_raw_report"],
                f"replay {index} normalized raw report changed")
        require(len(rows) == 140
                and sum(row["path"].endswith(".png") for row in rows) == 137
                and sum("-frame" in row["path"] for row in rows) == 130,
                f"replay {index} artifact corpus is incomplete")
        replay_state = root / "stage1-spike-current.ss0"
        manifests.append({
            "root": relative(root),
            "artifact_count": len(rows),
            "manifest_sha256": manifest_sha,
            "normalized_report_sha256": normalized_sha,
            "final_screenshot_sha256": live["replays"][index - 1][
                "final_screenshot_sha256"
            ],
            "final_state": state_binds_rom(replay_state, candidate),
        })
    require(manifests[0]["manifest_sha256"]
            == manifests[1]["manifest_sha256"],
            "duplicate artifact manifests differ")

    live_mtime = live_path.stat().st_mtime_ns
    require(all(path.stat().st_mtime_ns <= live_mtime
                for path, _expected in EXPECTED_TOOLS.values()),
            "a bound Stage-1 tool is newer than the live receipt")
    tool_temporal_note = (
        "supporting post-hoc provenance only: exact current tool hashes are "
        "pinned and their filesystem mtimes predate the live receipt; the "
        "original live receipt did not embed those hashes"
    )

    aa4 = paths["aa4_candidate"].read_bytes()
    e048 = paths["e048_candidate"].read_bytes()
    mutation_transfer = audit_mutation_transfer(
        aa4, e048, candidate,
        json.loads(paths["e048_static_receipt"].read_text()),
        json.loads(paths["helper_equivalence_receipt"].read_text()),
        json.loads(paths["r265_build_receipt"].read_text()),
        json.loads(paths["aa4_mutation_receipt"].read_text()),
    )
    controls = mutation_controls(live, aa4, e048, candidate)
    return {
        "schema": "penta-stage1-r265-hazard-menu-bound-offline-v1",
        "status": "PASS_TARGETED_RECEIPT_BOUND_STATIC_MUTATION_TRANSFER",
        "promotable_by_itself": False,
        "emulator_run": False,
        "identities": identities,
        "tool_identities": tool_identities,
        "offline_verifier": {
            "path": relative(SELF), "sha256": sha256(SELF),
        },
        "tool_provenance_limit": tool_temporal_note,
        "live_contract": live_contract,
        "source_state": state_contract,
        "duplicate_artifacts": manifests,
        "mutation_calibration": mutation_transfer,
        "mutation_controls": controls,
        "covered": [
            "exact a4c ROM and candidate-owned settled Stage-1 hazard state",
            "duplicate stationary SELECT/item-use/close/low-health route",
            "both physical map bases with 86 transfer-idle flips",
            "zero completed-frame visible attribute, floor, palette, endpoint, or hazard-write mismatch",
            "byte-identical screenshots and savestates across both replays",
            "static transfer of four aa4 mutation targets through byte-exact r265 ancestry",
        ],
        "not_covered": [
            "fresh live execution of the four mutants on r265",
            "both-map rendered-tooth phase completeness",
            "semantic hazard-publisher nonvacuity",
            "legacy lower-field color-count heuristic",
            "scanline/sub-frame raster behavior (temporal raster had only six baseline frames and is disabled)",
            "cryptographic proof that the pinned post-hoc tool files were the exact live-run files",
        ],
        "decision": (
            "STATIC GO for the reported Stage-1 stationary menu/item/low-health "
            "artifact class; retain the listed exclusions as separate gates"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    parser.add_argument("--live-receipt", type=Path, default=LIVE_RECEIPT)
    parser.add_argument("--aa4-candidate", type=Path, default=AA4_CANDIDATE)
    parser.add_argument("--e048-candidate", type=Path, default=E048_CANDIDATE)
    parser.add_argument(
        "--e048-static-receipt", type=Path, default=E048_STATIC_RECEIPT,
    )
    parser.add_argument(
        "--helper-equivalence-receipt", type=Path,
        default=HELPER_EQUIVALENCE_RECEIPT,
    )
    parser.add_argument(
        "--r265-build-receipt", type=Path, default=R265_BUILD_RECEIPT,
    )
    parser.add_argument(
        "--aa4-mutation-receipt", type=Path, default=AA4_MUTATION_RECEIPT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = scratch(args.output)
    receipt = build_receipt(args)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
    print("PASS: bound r265 Stage-1 targeted hazard/menu receipt")
    print(f"Receipt: {relative(output)}")
    print(f"Receipt SHA-256: {digest(payload.encode())}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
