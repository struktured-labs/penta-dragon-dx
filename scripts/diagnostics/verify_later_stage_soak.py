#!/usr/bin/env python3
"""Run multi-room Stage 2–7 palette-integrity soaks under mGBA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_later_stage_soak.lua"
BANK13 = 13 * 0x4000
NATIVE_BG0_ALIAS_ADDR = 0x6838
TITLE_PALETTE_SOURCE_ADDR = 0x6800
LATER_STAGE_BG0_SOURCE_TABLE_ADDR = 0x7BAC
WINDOW_HELPER_ADDR = 0x6A40
WINDOW_HELPER_BANK = 13
WINDOW_HELPER_AUDIT_SNIPPET = """if WINDOW_HELPER_ADDR > 0 and WINDOW_HELPER_BANK > 0 then
  local breakpoint_id = emu:setBreakpoint(function()
    if phase ~= \"play\" or emu:read8(0xD880) ~= EXPECTED_SCENE
        or emu:read8(0xFF99) ~= WINDOW_HELPER_BANK then return end
    window_helper_hits = window_helper_hits + 1
    if emu:read8(0xFFE4) ~= 0 then
      window_helper_ffe4_nonzero_hits =
        window_helper_ffe4_nonzero_hits + 1
    end
  end, WINDOW_HELPER_ADDR)
  assert(type(breakpoint_id) == \"number\" and breakpoint_id > 0,
    \"failed exact Window-helper breakpoint\")
end"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_fields(report: Path) -> tuple[dict[str, int], list[int], list[int]]:
    lines = report.read_text().splitlines()
    fields = {
        key: int(raw, 16 if key == "expected_scene" else 10)
        for key, raw in re.findall(
            r"([a-z0-9_]+)=(-?[0-9A-Fa-f]+)", lines[0]
        )
    }
    rooms = [int(value, 16) for value in lines[1].split("=", 1)[1].split(",") if value]
    scenes = [int(value, 16) for value in lines[2].split("=", 1)[1].split(",") if value]
    return fields, rooms, scenes


def validate_r265_window_probe_contract() -> dict[str, object]:
    """Pin the exact non-menu Window-helper/FFE4 observation points."""

    source = PROBE.read_text()
    if source.count(WINDOW_HELPER_AUDIT_SNIPPET) != 1:
        raise RuntimeError("soak probe lacks exact Window-helper audit")
    for text in (
        'os.getenv("SOAK_WINDOW_HELPER_ADDR")',
        'os.getenv("SOAK_WINDOW_HELPER_BANK")',
        'local sampled_ffe4 = emu:read8(0xFFE4)',
        '"ffe4_zero_play_frames=%d ffe4_nonzero_play_frames=%d "',
        '"window_helper_hits=%d window_helper_ffe4_nonzero_hits=%d\\n"',
    ):
        if text not in source:
            raise RuntimeError(f"soak probe lacks FFE4 contract: {text}")
    return {
        "window_helper": "bank13:$6A40",
        "frame_boundary_FFE4": "sampled on every measured callback",
        "execution_equivalence": (
            "zero changed-helper executions, or FFE4=0 at every exact entry"
        ),
    }


def r265_window_execution_contract(fields: dict[str, int]) -> dict[str, object]:
    required = (
        "frames", "ffe4_zero_play_frames", "ffe4_nonzero_play_frames",
        "first_ffe4_nonzero_play_frame", "first_ffe4_nonzero_value",
        "window_helper_hits", "window_helper_ffe4_nonzero_hits",
    )
    integers = all(
        isinstance(fields.get(name), int)
        and not isinstance(fields.get(name), bool) for name in required
    )
    helper_hits = fields.get("window_helper_hits")
    helper_nonzero = fields.get("window_helper_ffe4_nonzero_hits")
    frames = fields.get("frames")
    zero_frames = fields.get("ffe4_zero_play_frames")
    nonzero_frames = fields.get("ffe4_nonzero_play_frames")
    first_frame = fields.get("first_ffe4_nonzero_play_frame")
    first_value = fields.get("first_ffe4_nonzero_value")
    checks = {
        "telemetry_is_integer": integers,
        "every_measured_callback_is_accounted": (
            integers and frames >= 0 and zero_frames >= 0
            and nonzero_frames >= 0 and zero_frames + nonzero_frames == frames
        ),
        "first_nonzero_callback_is_coherent": (
            integers and (
                (nonzero_frames == 0 and first_frame == -1
                 and first_value == -1)
                or (nonzero_frames > 0 and 1 <= first_frame <= frames
                    and first_value > 0)
            )
        ),
        "helper_counts_are_consistent": (
            isinstance(helper_hits, int) and not isinstance(helper_hits, bool)
            and isinstance(helper_nonzero, int)
            and not isinstance(helper_nonzero, bool)
            and helper_hits >= 0 and helper_nonzero == 0
            and helper_nonzero <= helper_hits
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def r265_window_execution_policy_controls() -> dict[str, bool]:
    valid = {
        "frames": 8000,
        "ffe4_zero_play_frames": 228,
        "ffe4_nonzero_play_frames": 7772,
        "first_ffe4_nonzero_play_frame": 229,
        "first_ffe4_nonzero_value": 1,
        "window_helper_hits": 0,
        "window_helper_ffe4_nonzero_hits": 0,
    }

    def passes(**changes: object) -> bool:
        payload = dict(valid)
        payload.update(changes)
        return bool(r265_window_execution_contract(payload)["passed"])

    return {
        "zero_helper_with_nonzero_callback_context_passes": passes(),
        "zero_path_helper_with_nonzero_callback_context_passes": passes(
            window_helper_hits=4
        ),
        "missing_boundary_rejected": not passes(ffe4_zero_play_frames=227),
        "incoherent_first_nonzero_rejected": not passes(
            first_ffe4_nonzero_play_frame=-1,
            first_ffe4_nonzero_value=-1,
        ),
        "negative_helper_count_rejected": not passes(window_helper_hits=-1),
        "nonzero_helper_entry_rejected": not passes(
            window_helper_hits=1, window_helper_ffe4_nonzero_hits=1,
        ),
        "boolean_helper_count_rejected": not passes(window_helper_hits=True),
    }


def read_display_contract(path: Path) -> tuple[int, int, list[str]]:
    """Return bank-0 pre-display scans and online contract mismatches."""
    readable = 0
    mismatches = 0
    examples: list[str] = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        columns = line.split("\t", 12)
        if len(columns) < 12:
            raise RuntimeError(
                f"short display contract row {path}:{line_number}"
            )
        readable += 1
        count = int(columns[11])
        mismatches += count
        if count and len(examples) < 8:
            detail = columns[12] if len(columns) > 12 else ""
            examples.append(
                f"p{int(columns[1]):06d}@${columns[2]} "
                f"map=${columns[5]} room={columns[6]} {detail}"
            )
    return readable, mismatches, examples


def read_flip_state_contract(path: Path, output: Path) -> int:
    """Fail closed if publication savestate names/files do not match trace."""

    expected: list[str] = []
    suffix = ".flip-events.tsv"
    if not path.name.endswith(suffix):
        raise RuntimeError(f"invalid flip trace name: {path}")
    stage_prefix = path.name[:-len(suffix)]
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        columns = line.split("\t")
        if len(columns) != 14:
            raise RuntimeError(f"short flip-state row {path}:{line_number}")
        index = int(columns[0])
        if index != line_number:
            raise RuntimeError(
                f"non-sequential flip-state row {path}:{line_number}"
            )
        trace_name = f"flip{index:06d}.ss0"
        name = f"{stage_prefix}.{trace_name}"
        if columns[13] != trace_name:
            raise RuntimeError(f"wrong flip-state name {path}:{line_number}")
        state = output / name
        if not state.is_file() or state.stat().st_size == 0:
            raise RuntimeError(f"missing publication savestate: {state}")
        expected.append(name)
    observed = sorted(
        candidate.name
        for candidate in output.glob(f"{stage_prefix}.flip*.ss0")
    )
    if observed != expected:
        raise RuntimeError("publication savestate set does not match flip trace")
    return len(expected)


def run_stage(mgba: str, rom: Path, target: int, frames: int,
              output: Path, timeout: float, screenshots: bool,
              attr_trace: bool, layout_trace: bool, stream_trace: bool,
              flip_trace: bool, lcdc_trace: bool, semantic_write_trace: bool,
              flip_states: bool, wram_audit: bool,
              capture_stable: int, sample_interval: int,
              trace_addrs: str, watch_vram_addrs: str,
              r265_window_equivalence: bool) -> Path:
    prefix = output / f"stage{target + 1}"
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "SOAK_TARGET": str(target),
        "SOAK_OUT": str(prefix),
        "SOAK_FRAMES": str(frames),
        "SOAK_SCREENSHOTS": "1" if screenshots else "0",
        "SOAK_CAPTURE_STABLE": str(capture_stable),
        "SOAK_SAMPLE_INTERVAL": str(sample_interval),
        "SOAK_WRAM_AUDIT": "1" if wram_audit else "0",
    })
    if r265_window_equivalence:
        env["SOAK_WINDOW_HELPER_ADDR"] = str(WINDOW_HELPER_ADDR)
        env["SOAK_WINDOW_HELPER_BANK"] = str(WINDOW_HELPER_BANK)
    if sha256(rom) in {
        "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702",
        "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46",
        "7a3766bde681b591013e77163be75880e44dfde106648a98f1173888b1eb2b23",
        "bdd4ac2dddc051f5256d4d382ab64f195330b90df41d363191ce03d75e3a84fd",
        "51263fe16a7308383d49bf7e6a3609bcdf543579b4365f0a1659c8644ffd6c35",
        "7b3de7acf60614b958658b9f7f7139bb7b855dd23bc5f41c6c42d7322cead620",
        "d763a2e9b4610bac28e7a54da809b74227a1baf289c851b02774a2a2968e154e",
        "6b375a8080df3c982f63a92ea0a679241d8c77cf370776d38bd5b4be8c101e35",
        "baeeb893cf5cd47192273b18eaf9d1bc7902f9ab55da2b3306d2e32db00fcebe",
        "ce8c4db2cc433fcaa3e39de68c72ea372c0fc205e1cd8ea521a3a4bd78099c92",
        "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b",
        "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9",
        "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4",
        "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722",
        # r527 inherits the fixed physical-page publisher observation sites.
        "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b",
        "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50",
        "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208",
        "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30",
        "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855",
        "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821",
        "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba",
        "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
        "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3",
        "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576",
        "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350",  # r536: inherited observer/data ABI
        "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b",  # title row guard: unchanged gameplay observer/data ABI
        "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d",  # death/restart successor: unchanged soak publisher ABI
        "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5",  # #6: unchanged soak publisher ABI
        "db09de8d1b4293401f587fcce77689d8c13799eb009f13001487786c3accdcb8",  # release lock: $12F4 and bank13 $7457/$7462 outside its delta (re-checked below)
        "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96",
        "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63",
        "d82f563d856995fc1844d48cdd317b12f2ac9218f023eec376ee73bc24308074",
        "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892",
    }:
        image = rom.read_bytes()
        if image[0x12F4:0x12FC] != bytes.fromhex("F0 40 EE 08 E0 40 18 05"):
            raise ValueError("r441 fixed publisher opcode mismatch")
        env["SOAK_PRIMARY_FIXED_STORE"] = str(0x12F8)
        for address in (0x7457, 0x7462):
            offset=13*0x4000+address-0x4000
            if image[offset:offset+2] != bytes.fromhex("E0 40"):
                raise ValueError("r441 banked publisher opcode mismatch")
        env["SOAK_PRIMARY_BANK13_STORES"] = "1"
    if attr_trace:
        env["SOAK_ATTR_TRACE"] = str(prefix.with_suffix(".attr-events.tsv"))
    if layout_trace:
        env["SOAK_LAYOUT_TRACE"] = str(prefix.with_suffix(".layout-events.tsv"))
    if stream_trace:
        env["SOAK_STREAM_TRACE"] = str(prefix.with_suffix(".stream-writers.tsv"))
    # The dual-map renderer may rebuild the just-retired active map after its
    # final scanline. Sampling that VRAM in the frame callback can therefore
    # report a semantic mismatch that was never displayed. Always inspect the
    # selected destination immediately before the native LCDC publication;
    # this is the actual visible contract for both physical maps.
    env["SOAK_FLIP_TRACE"] = str(prefix.with_suffix(".flip-events.tsv"))
    env["SOAK_FLIP_STATES"] = "1" if flip_states else "0"
    if lcdc_trace:
        env["SOAK_LCDC_TRACE"] = str(prefix.with_suffix(".lcdc-events.tsv"))
    if semantic_write_trace:
        env["SOAK_SEMANTIC_WRITE_TRACE"] = str(
            prefix.with_suffix(".semantic-writes.tsv")
        )
    if trace_addrs:
        env["SOAK_TRACE_ADDRS"] = trace_addrs
    if watch_vram_addrs:
        env["SOAK_VRAM_WATCH_ADDRS"] = watch_vram_addrs
    command = [mgba]
    # The Qt frontend accepts --fastforward; mgba-headless already runs as
    # fast as possible and rejects that option.
    if "mgba-qt" in Path(mgba).name:
        command.append("--fastforward")
    command.extend(["--script", str(PROBE), str(rom)])
    error_log = prefix.with_suffix(".emulator.log").open("wb")
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=error_log,
        stderr=subprocess.STDOUT,
    )
    report = prefix.with_suffix(".report")
    completion = prefix.with_suffix(".done")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if completion.exists() and completion.read_text() == "DONE\n":
                if not report.exists() or not report.stat().st_size:
                    raise RuntimeError(
                        f"Stage {target + 1} completed without a report"
                    )
                return report
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        raise RuntimeError(f"Stage {target + 1} soak timed out")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        error_log.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--frames", type=int, default=8000)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument(
        "--stages",
        default="2,3,4,5,6,7",
        help="comma-separated stage numbers to exercise (default: 2..7)",
    )
    parser.add_argument("--keep-dir", type=Path)
    parser.add_argument(
        "--screenshots", action="store_true",
        help="capture each visited room and first mismatch (use with mgba-qt)",
    )
    parser.add_argument(
        "--capture-stable",
        type=int,
        default=4,
        help="stable frames before each room screenshot (default: 4; use 0 "
             "to capture very brief routes)",
    )
    parser.add_argument(
        "--sample-interval", type=int, default=5,
        help="visible-map sample cadence in frames (default: 5)",
    )
    parser.add_argument(
        "--attr-trace", action="store_true",
        help="trace each Stage 5/7 desired lava map for cache-key analysis",
    )
    parser.add_argument(
        "--layout-trace", action="store_true",
        help="record every sampled C1A0 source layout and cache metadata",
    )
    parser.add_argument(
        "--stream-trace", action="store_true",
        help="trace direct Stage 5/7 packed-map writers after initial load",
    )
    parser.add_argument(
        "--flip-trace", action="store_true",
        help="retain explicit flip diagnostics (the display gate always runs)",
    )
    parser.add_argument(
        "--active-map-strict", action="store_true",
        help=(
            "also fail on callback-time mismatches in the just-retired map; "
            "normally these remain diagnostic-only"
        ),
    )
    parser.add_argument(
        "--lcdc-trace", action="store_true",
        help="trace every gameplay write that changes LCDC",
    )
    parser.add_argument(
        "--semantic-write-trace", action="store_true",
        help="trace VRAM writes that create a semantic tile/attribute mismatch",
    )
    parser.add_argument(
        "--flip-states", action="store_true",
        help=(
            "save an mGBA state at every accepted display publication so an "
            "offline gate can inspect both physical VRAM banks"
        ),
    )
    parser.add_argument(
        "--trace-addrs", default="",
        help="comma-separated optional mGBA breakpoint addresses for diagnosis",
    )
    parser.add_argument(
        "--watch-vram-addrs", default="",
        help="comma-separated exact VRAM addresses to attribute writes to",
    )
    parser.add_argument(
        "--wram-audit", action="store_true",
        help="prove candidate fixed-WRAM ranges remain unchanged during play",
    )
    parser.add_argument(
        "--require-native-bg0", action="store_true",
        help=(
            "require every captured later-stage room to retain the candidate "
            "ROM's title-safe native BG0 alias"
        ),
    )
    parser.add_argument(
        "--require-stage-bg0", action="store_true",
        help=(
            "require every captured room to retain its Stage 2-7 palette "
            "selected by the candidate ROM's stage-source table"
        ),
    )
    parser.add_argument(
        "--require-stage-base-palette", action="store_true",
        help=(
            "require every captured Stage 2-7 scene LUT to retain its exact "
            "semantic pickup/material slots (plus BG5 lava overrides)"
        ),
    )
    parser.add_argument(
        "--require-semantic-pickups", action="store_true",
        help=(
            "require the route to encounter collision-audited pickup tiles; "
            "their exact palettes are always validated"
        ),
    )
    parser.add_argument(
        "--require-r265-window-equivalence", action="store_true",
        help=(
            "Stage-7-only: account for FFE4 at every measured callback and "
            "require FFE4=0 at every exact bank13:$6A40 changed-helper entry "
            "(zero helper entries are valid for the non-menu route)"
        ),
    )
    args = parser.parse_args()
    if args.capture_stable < 0:
        parser.error("--capture-stable must be non-negative")
    if args.sample_interval < 1:
        parser.error("--sample-interval must be positive")
    semantic_pickup_samples = 0
    try:
        stages = [int(value) for value in args.stages.split(",") if value]
    except ValueError:
        parser.error("--stages must be a comma-separated list of integers")
    if not stages or any(stage < 2 or stage > 7 for stage in stages):
        parser.error("--stages entries must be between 2 and 7")
    window_probe_contract = None
    window_policy_controls = None
    if args.require_r265_window_equivalence:
        if stages != [7]:
            parser.error(
                "--require-r265-window-equivalence requires --stages 7"
            )
        window_probe_contract = validate_r265_window_probe_contract()
        window_policy_controls = r265_window_execution_policy_controls()
        if not all(window_policy_controls.values()):
            parser.error("internal r265 Window-equivalence controls failed")

    rom_path = args.rom.resolve()
    probe_path = PROBE.resolve()
    verifier_path = Path(__file__).resolve()
    launcher_path = Path(args.mgba).resolve()
    identity_before = {
        "candidate_sha256": sha256(rom_path),
        "probe_sha256": sha256(probe_path),
        "verifier_sha256": sha256(verifier_path),
        "launcher_sha256": (
            sha256(launcher_path) if launcher_path.is_file() else None
        ),
    }

    temporary = None
    if args.keep_dir:
        output = args.keep_dir.resolve()
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
    else:
        local_tmp = ROOT / "tmp"
        local_tmp.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(
            prefix="penta-later-soak-", dir=local_tmp
        )
        output = Path(temporary.name)

    failures: list[str] = []
    window_execution_receipts: dict[str, dict[str, object]] = {}
    native_bg0_offset = BANK13 + NATIVE_BG0_ALIAS_ADDR - 0x4000
    native_bg0 = args.rom.resolve().read_bytes()[
        native_bg0_offset:native_bg0_offset + 8
    ]
    if args.require_native_bg0 and len(native_bg0) != 8:
        parser.error("candidate ROM does not contain a complete native BG0 alias")
    rom_bytes = args.rom.resolve().read_bytes()
    source_table_offset = (
        BANK13 + LATER_STAGE_BG0_SOURCE_TABLE_ADDR - 0x4000
    )
    stage_source_lows = rom_bytes[source_table_offset:source_table_offset + 6]
    if args.require_stage_bg0 and len(stage_source_lows) != 6:
        parser.error("candidate ROM does not contain the Stage 2-7 BG0 table")
    if args.require_stage_base_palette and len(stage_source_lows) != 6:
        parser.error("candidate ROM does not contain the Stage 2-7 palette table")
    try:
        for stage in stages:
            target = stage - 1
            try:
                report = run_stage(
                    args.mgba, args.rom.resolve(), target, args.frames,
                    output, args.timeout, args.screenshots, args.attr_trace,
                    args.layout_trace, args.stream_trace, args.flip_trace,
                    args.lcdc_trace, args.semantic_write_trace,
                    args.flip_states, args.wram_audit,
                    args.capture_stable, args.sample_interval,
                    args.trace_addrs, args.watch_vram_addrs,
                    args.require_r265_window_equivalence,
                )
                fields, rooms, scenes = read_fields(report)
                display_scans, display_mismatches, display_examples = (
                    read_display_contract(
                        output / f"stage{target + 1}.flip-events.tsv"
                    )
                )
                visible_write_trails: list[str] = []
                if args.semantic_write_trace:
                    semantic_path = output / (
                        f"stage{target + 1}.semantic-writes.tsv"
                    )
                    if not semantic_path.is_file():
                        raise RuntimeError(
                            f"missing semantic write trace: {semantic_path}"
                        )
                    visible_write_trails = (
                        semantic_path.read_text().splitlines()
                    )
                flip_state_count = 0
                if args.flip_states:
                    flip_state_count = read_flip_state_contract(
                        output / f"stage{target + 1}.flip-events.tsv", output
                    )
                if args.require_r265_window_equivalence:
                    window_contract = r265_window_execution_contract(fields)
                    window_execution_receipts[f"stage{stage}"] = window_contract
                    if not window_contract["passed"]:
                        failed = ",".join(
                            name for name, passed
                            in window_contract["checks"].items() if not passed
                        )
                        raise RuntimeError(
                            f"Stage {stage}: r265 Window execution "
                            f"equivalence failed: {failed}"
                        )
            except Exception as exc:
                failures.append(str(exc))
                continue

            print(
                f"Stage {target + 1}: frames={fields['frames']} "
                f"rooms={[f'{room:02X}' for room in rooms]} "
                f"scenes={[f'{scene:02X}' for scene in scenes]} "
                f"retired_map_unexpected={fields['unexpected']} "
                f"retired_map_unsafe={fields['unsafe']} "
                f"retired_map_lava_mismatch={fields['lava_mismatch']} "
                f"pickup_expected={fields['pickup_expected']} "
                f"pickup_mismatch={fields['pickup_mismatch']} "
                f"material_expected={fields['material_expected']} "
                f"material_mismatch={fields['material_mismatch']} "
                f"display_scans={display_scans} "
                f"display_mismatch={display_mismatches} "
                f"visible_write_trails={len(visible_write_trails)} "
                f"flip_states={flip_state_count}"
            )
            semantic_pickup_samples += fields["pickup_expected"]
            if fields["frames"] < args.frames:
                failures.append(f"Stage {target + 1}: stopped at {fields['frames']} frames")
            if fields["samples"] < 20:
                failures.append(f"Stage {target + 1}: too few stable samples")
            if display_scans < 20:
                failures.append(
                    f"Stage {target + 1}: only {display_scans} readable "
                    "raw-VRAM pre-display map scans"
                )
            if display_mismatches:
                failures.append(
                    f"Stage {target + 1}: {display_mismatches} exact-plane/"
                    "publisher-contract mismatches before display: "
                    + "; ".join(display_examples)
                )
            if visible_write_trails:
                failures.append(
                    f"Stage {target + 1}: {len(visible_write_trails)} "
                    "active-visible tile/attribute write trails: "
                    + "; ".join(visible_write_trails[:8])
                )
            if args.active_map_strict and (
                fields["unexpected"]
                or fields["unsafe"]
                or fields["lava_mismatch"]
                or fields["pickup_mismatch"]
                or fields["material_mismatch"]
            ):
                failures.append(
                    f"Stage {target + 1}: callback-time active-map "
                    "mismatches observed"
                )
            if stage == 4 and fields["material_expected"] == 0:
                failures.append("Stage 4: no floor/wall material cells observed")
            if args.wram_audit and fields["wram_changed"]:
                failures.append(
                    f"Stage {target + 1}: audited WRAM changed "
                    f"{fields['wram_changed']} times"
                )
            if fields["expected_scene"] not in scenes:
                failures.append(f"Stage {target + 1}: expected scene was never sampled")
            if len(rooms) < 2:
                failures.append(f"Stage {target + 1}: exercised only {len(rooms)} room")
            if args.require_native_bg0:
                bg0_mismatches: list[str] = []
                bg0_receipts = 0
                for room in rooms:
                    bgp = output / f"stage{target + 1}.room{room:02X}.bgp.bin"
                    if not bgp.is_file():
                        continue
                    if len(bgp.read_bytes()) != 64:
                        bg0_mismatches.append(f"{room:02X}:short")
                        continue
                    bg0_receipts += 1
                    observed_bg0 = bgp.read_bytes()[:8]
                    if observed_bg0 != native_bg0:
                        bg0_mismatches.append(
                            f"{room:02X}:{observed_bg0.hex().upper()}"
                        )
                print(
                    f"Stage {target + 1}: native_bg0="
                    f"{'PASS' if not bg0_mismatches else 'FAIL'} "
                    f"expected={native_bg0.hex().upper()} receipts={bg0_receipts}"
                )
                if bg0_receipts < 2:
                    failures.append(
                        f"Stage {target + 1}: only {bg0_receipts} stable BG0 receipts"
                    )
                if bg0_mismatches:
                    failures.append(
                        f"Stage {target + 1}: non-native BG0 in "
                        + ",".join(bg0_mismatches)
                    )
            if args.require_stage_bg0:
                source_low = stage_source_lows[target - 1]
                source_offset = (
                    BANK13 + TITLE_PALETTE_SOURCE_ADDR - 0x4000
                    + source_low
                )
                expected_bg0 = rom_bytes[source_offset:source_offset + 8]
                bg0_mismatches: list[str] = []
                bg0_receipts = 0
                for room in rooms:
                    bgp = output / f"stage{target + 1}.room{room:02X}.bgp.bin"
                    if not bgp.is_file():
                        continue
                    if len(bgp.read_bytes()) != 64:
                        bg0_mismatches.append(f"{room:02X}:short")
                        continue
                    bg0_receipts += 1
                    observed_bg0 = bgp.read_bytes()[:8]
                    if observed_bg0 != expected_bg0:
                        bg0_mismatches.append(
                            f"{room:02X}:{observed_bg0.hex().upper()}"
                        )
                print(
                    f"Stage {target + 1}: stage_bg0="
                    f"{'PASS' if not bg0_mismatches else 'FAIL'} "
                    f"source=$68{source_low:02X} "
                    f"expected={expected_bg0.hex().upper()} receipts={bg0_receipts}"
                )
                if bg0_receipts < 2:
                    failures.append(
                        f"Stage {target + 1}: only {bg0_receipts} stable stage-BG0 receipts"
                    )
                if bg0_mismatches:
                    failures.append(
                        f"Stage {target + 1}: wrong stage BG0 in "
                        + ",".join(bg0_mismatches)
                    )
            if args.require_stage_base_palette:
                semantic_slots = {
                    1: {2},        # Stage 2: rare
                    2: {1},        # Stage 3: health
                    3: {2, 4},     # Stage 4: bridge + diamond floor
                    4: {1, 2, 5},  # Stage 5: health + rare + lava
                    5: {1},        # Stage 6: health
                    6: {2, 4, 5},  # Stage 7: rare + arrow + lava
                }
                expected_slots = semantic_slots[target]
                allowed_slots = {0, *expected_slots}
                lut_mismatches: list[str] = []
                lut_receipts = 0
                for room in rooms:
                    lut = output / f"stage{target + 1}.room{room:02X}.bg-lut.bin"
                    if not lut.is_file():
                        continue
                    if len(lut.read_bytes()) != 256:
                        lut_mismatches.append(f"{room:02X}:short")
                        continue
                    lut_receipts += 1
                    observed_slots = set(lut.read_bytes())
                    if (
                        not observed_slots <= allowed_slots
                        or not expected_slots <= observed_slots
                    ):
                        lut_mismatches.append(
                            f"{room:02X}:"
                            + ",".join(str(value) for value in sorted(observed_slots))
                        )
                print(
                    f"Stage {target + 1}: semantic_lut="
                    f"{'PASS' if not lut_mismatches else 'FAIL'} "
                    f"required={sorted(expected_slots)} "
                    f"allowed={sorted(allowed_slots)} receipts={lut_receipts}"
                )
                if lut_receipts < 2:
                    failures.append(
                        f"Stage {target + 1}: only {lut_receipts} stable semantic-LUT receipts"
                    )
                if lut_mismatches:
                    failures.append(
                        f"Stage {target + 1}: wrong scene LUT in "
                        + ",".join(lut_mismatches)
                    )
        if args.require_semantic_pickups and semantic_pickup_samples == 0:
            failures.append(
                "no collision-audited later-stage pickup tile was observed"
            )
    finally:
        if temporary is not None:
            temporary.cleanup()

    identity_after = {
        "candidate_sha256": sha256(rom_path),
        "probe_sha256": sha256(probe_path),
        "verifier_sha256": sha256(verifier_path),
        "launcher_sha256": (
            sha256(launcher_path) if launcher_path.is_file() else None
        ),
    }
    identity_intact = identity_before == identity_after
    if not identity_intact:
        failures.append("candidate, probe, verifier, or launcher changed during soak")
    if args.keep_dir:
        manifest = {
            "schema": "penta-later-stage-soak-run-v1",
            "status": "FAIL" if failures else "PASS",
            "candidate": str(rom_path),
            "probe": str(probe_path),
            "verifier": str(verifier_path),
            "launcher": str(launcher_path),
            "identity_before": identity_before,
            "identity_after": identity_after,
            "identity_intact": identity_intact,
            "invocation": {
                "stages": stages,
                "frames": args.frames,
                "sample_interval": args.sample_interval,
                "capture_stable": args.capture_stable,
                "screenshots": args.screenshots,
                "attr_trace": args.attr_trace,
                "layout_trace": args.layout_trace,
                "stream_trace": args.stream_trace,
                "active_map_strict": args.active_map_strict,
                "lcdc_trace": args.lcdc_trace,
                "semantic_write_trace": args.semantic_write_trace,
                "flip_states": args.flip_states,
                "wram_audit": args.wram_audit,
                "require_native_bg0": args.require_native_bg0,
                "require_stage_bg0": args.require_stage_bg0,
                "require_stage_base_palette": args.require_stage_base_palette,
                "require_semantic_pickups": args.require_semantic_pickups,
                "require_r265_window_equivalence": (
                    args.require_r265_window_equivalence
                ),
            },
            "r265_window_probe_contract": window_probe_contract,
            "r265_window_policy_controls": window_policy_controls,
            "r265_window_execution_receipts": window_execution_receipts,
            "failures": failures,
        }
        (output / "run-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )

    if failures:
        print("\nFAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nPASS: all later stages completed multi-room BG-integrity soaks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
