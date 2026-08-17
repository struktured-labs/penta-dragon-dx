#!/usr/bin/env python3
"""Generate release-ROM mGBA states for all nine boss arenas.

The release ROM has no debug teleport. This tool creates a safe Stage 1 state
through the stock title/GAME START route, redirects a temporary serialized
copy to the game's original boss dispatcher, and lets the untouched candidate
run the complete arena setup. Strict rendered-frame, palette, table, LCD, and
scene checks reject phase-sensitive bad landings instead of publishing them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from boss_geometry_contract import BOSSES, NAMES as BOSS_NAMES
from normalize_mgba_state_pc import normalize


ROOT = Path(__file__).resolve().parents[2]
# Same supported Japanese base as build_release_bundle.py / verify_release_patch.py.
SUPPORTED_BASE_MD5 = "df43e0adfdc74b2829c7e95e91c71a28"
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = ROOT / "tmp/palette_session/boss_states"
BOSS_PROBE = Path(__file__).with_name("probe_generate_boss_state.lua")
RECEIPT_PROBE = Path(__file__).with_name("probe_boss_state_receipt.lua")
STAGE_PROBE = Path(__file__).with_name("probe_stage_integrity.lua")
DEFAULT_SOURCE_STATES = ROOT / "tmp/palette_session/boss_states"

BOSS_ENTRY = 0x1A2B
LANDING_PAD = 0xCF82
BOSS_SETTLE_FRAMES = 60
# Deterministic normalized-entry budgets. These are measured from the same
# synthetic landing after patch_state() explicitly restores IE=$07, so a ROM
# cannot hide publisher latency behind a lucky serialized interrupt phase.
# Ted v10's accepted performance baseline settles at frame 77; one frame of
# tolerance keeps the gate below a 2% regression.
BOSS_ENTRY_FRAME_LIMITS = {4: 78}
ROM_BANK_SIZE = 0x4000
PALETTE_ROM_BANK = 13
ARENA_TABLE_BASE = 0x7200
BG_TABLE_SIZE = 0x100
TUNED_BG7_SOURCE_ADDR = 0x68F8
CRYSTAL_TARGET = 2
CRYSTAL_OBJ_SOURCE_ADDR = 0x6898
GB_STATE_SIZE = 0x11800
CPU_SP = 0x0028
CPU_PC = 0x002A
CPU_EXECUTION_STATE = 0x0039
CPU_FLAGS = 0x0044
MEMORY_CURRENT_BANK = 0x0168
MEMORY_FLAGS = 0x0194
MBC1_BANK_LO = 0x0186
MBC1_BANK_HI = 0x0187
HRAM = 0x0380
IE = 0x03FF
WRAM = 0x4400
WRAM_START = 0xC000
DCBB = WRAM + (0xDCBB - WRAM_START)
DCFD = WRAM + (0xDCFD - WRAM_START)
DF53 = WRAM + (0xDF53 - WRAM_START)
DF54 = WRAM + (0xDF54 - WRAM_START)
DBFF = WRAM + (0xDBFF - WRAM_START)
DF0D = WRAM + (0xDF0D - WRAM_START)
DF00 = WRAM + (0xDF00 - WRAM_START)
DF4C = WRAM + (0xDF4C - WRAM_START)
DF51 = WRAM + (0xDF51 - WRAM_START)
C5FF = WRAM + (0xC5FF - WRAM_START)
FF99 = HRAM + (0xFF99 - 0xFF80)
FFBA = HRAM + (0xFFBA - 0xFF80)
FFBF = HRAM + (0xFFBF - 0xFF80)
FFC0 = HRAM + (0xFFC0 - 0xFF80)
FFD0 = HRAM + (0xFFD0 - 0xFF80)
FF91 = HRAM + (0xFF91 - 0xFF80)
FFA7 = HRAM + (0xFFA7 - 0xFF80)
FFA8 = HRAM + (0xFFA8 - 0xFF80)
FFA9 = HRAM + (0xFFA9 - 0xFF80)
def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_until_marker(
    command: list[str],
    env: dict[str, str],
    cwd: Path,
    marker: Path,
    timeout: float,
) -> None:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file():
                # Lua creates the marker before writing its status. Do not
                # terminate mGBA in that tiny window or an otherwise valid
                # capture leaves an empty marker and is misreported as failed.
                try:
                    if marker.read_text().strip():
                        return
                except OSError:
                    pass
            if process.poll() is not None:
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before {marker.name}"
                )
            time.sleep(0.05)
        raise TimeoutError(f"timed out waiting for {marker.name}")
    finally:
        terminate(process)


def generate_safe_stage1(
    mgba: str,
    rom: Path,
    output: Path,
    timeout: float,
    *,
    stock_rom: bool = False,
) -> Path:
    prefix = output / "safe_stage1"
    state = prefix.with_suffix(".ss0")
    meta = prefix.with_suffix(".meta")
    env = os.environ.copy()
    env.update(
        STAGE_TARGET="0",
        STAGE_OUT=str(prefix),
        STAGE_SHOT="0",
        STAGE_STATE_OUT=str(state),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    result = subprocess.run(
        [
            mgba,
            "--fastforward",
            "-C",
            f"savegamePath={output}",
            "-C",
            f"savestatePath={output}",
            str(rom.resolve()),
            "--script",
            str(STAGE_PROBE),
        ],
        cwd=output,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"safe Stage 1 generation exited {result.returncode}")
    if not state.is_file() or state.stat().st_size < 1024:
        raise RuntimeError("safe Stage 1 state was not created")
    if not meta.is_file():
        raise RuntimeError("safe Stage 1 metadata was not created")
    detail = meta.read_text()
    required = (
        "target=0",
        "expected_scene=02",
        "D880=02",
        "FFC1=01",
        "FFBA=00",
        "state_saved=true",
    )
    if not stock_rom:
        required += ("FF91=01", "DF0D=02", "unsafe_attr=0")
    missing = [token for token in required if token not in detail]
    if missing:
        raise RuntimeError(
            f"safe Stage 1 state failed validation: {', '.join(missing)}"
        )
    return state


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("mGBA state is not a PNG container")
    chunks: list[tuple[bytes, bytes]] = []
    offset = 8
    while offset < len(data):
        if offset + 12 > len(data):
            raise RuntimeError("truncated PNG chunk")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if len(payload) != length:
            raise RuntimeError("truncated PNG payload")
        chunks.append((kind, payload))
        offset += 12 + length
    return chunks


def write_png(path: Path, chunks: list[tuple[bytes, bytes]]) -> None:
    data = bytearray(b"\x89PNG\r\n\x1a\n")
    for kind, payload in chunks:
        data.extend(struct.pack(">I", len(payload)))
        data.extend(kind)
        data.extend(payload)
        data.extend(struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    path.write_bytes(data)


def patch_state(
    source: Path, destination: Path, target: int, *, stock_rom: bool = False,
) -> None:
    chunks = png_chunks(source.read_bytes())
    state_indices = [
        index for index, (kind, _payload) in enumerate(chunks) if kind == b"gbAs"
    ]
    if len(state_indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(state_indices)}")
    index = state_indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(
            f"unexpected mGBA Game Boy state size: 0x{len(raw):X}"
        )
    if raw[CPU_EXECUTION_STATE] != 3:
        raise RuntimeError(
            f"safe state is not at FETCH: {raw[CPU_EXECUTION_STATE]}"
        )

    normalized_hash = (target + 1) & 0xFF  # FFBF/FFC0/FFD0 are normalized 0
    palette_normalization = (
        [
            0xAF,
            0xEA, 0x4C, 0xDF,              # no inherited palette phase
            0x3E, normalized_hash,
            0xEA, 0x00, 0xDF,              # exact constructed-state hash
        ]
        if target == 4 and not stock_rom
        else []
    )
    landing = bytes([
        0xF3,                               # DI while phase-aligning
        0xF0, 0x44, 0xFE, 0x90, 0x38, 0xFA, # wait until VBlank
        0xF0, 0x44, 0xFE, 0x90, 0x30, 0xFA, # wait for next line 0
        *palette_normalization,
        0xFB, 0x00,                         # EI; activation delay
        0x3E, 0x03,                         # LD A,$03
        0xEA, 0x00, 0x21,                   # map ROM bank 3
        0xE0, 0x99,                         # publish FF99 bank shadow
        0xCD, BOSS_ENTRY & 0xFF, BOSS_ENTRY >> 8,
        0x18, 0xFE,                         # defensive loop if it returns
    ])
    landing_offset = WRAM + (LANDING_PAD - WRAM_START)
    raw[landing_offset:landing_offset + len(landing)] = landing
    raw[CPU_SP:CPU_SP + 2] = (0xDFFF).to_bytes(2, "little")
    raw[CPU_PC:CPU_PC + 2] = LANDING_PAD.to_bytes(2, "little")
    # Frame callbacks often serialize while the VBlank handler has IME
    # cleared. The proven teleport landing pad reaches this dispatcher via
    # RETI, with IME enabled and no pending/halted CPU microstate.
    raw[CPU_FLAGS:CPU_FLAGS + 4] = bytes(4)
    memory_flags = int.from_bytes(
        raw[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little"
    )
    raw[MEMORY_FLAGS:MEMORY_FLAGS + 2] = (
        memory_flags | 0x0008
    ).to_bytes(2, "little")
    raw[MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2] = (3).to_bytes(2, "little")
    raw[MBC1_BANK_LO] = 3
    raw[MBC1_BANK_HI] = 0
    raw[FF99] = 3
    raw[FFBA] = target
    raw[FFBF] = 0
    # The source fixture is already a settled Stage-1 scene. Preserve that
    # scene identity until the stock boss dispatcher changes D880 to the arena;
    # forging FF91=1 here falsely replays Stage-1 entry and arms a redundant
    # 17-row palette job immediately before the boss fade.
    raw[FF91] = 2 if target == 4 and not stock_rom else 1
    raw[DF0D] = 0x02 if target == 4 and not stock_rom else 0xFF
    # The synthetic redirect abandons the serialized caller's stack and PC,
    # so it must not inherit that caller's temporary atomic-copy IE=$04 mask.
    # Normalize the native boss-loop VBlank/Timer/Joypad contract explicitly;
    # otherwise fixture success depends on the exact Stage-1 save phase.
    raw[IE] = 0x07
    # Seed boss HP before entry so the synthetic arena cannot immediately take
    # the post-boss exit path.
    raw[DCBB] = 0x80
    # The injected route represents a live boss fight, not prerecorded title
    # demo playback. Leaving the safe Stage-1 state's zero discriminator here
    # sent the arena through the demo-only pure copier and exposed transient
    # C1A0 staging tiles as fake terrain in the visual gallery.
    raw[DCFD] = 1
    raw[DF53] = 0
    raw[DF54] = 0
    # Normalize the global palette cursor just like IE. The accepted v10
    # benchmark began at phase zero; inheriting Stage 1's transient $0B made
    # newer candidates perform a different workload before boss dispatch.
    raw[DF4C] = int(os.environ.get("BOSS_NORMALIZED_PALETTE_PHASE", "00"), 16)
    # The serialized route also changes FFBA behind the palette scheduler's
    # back. Seed its exact production hash to the state we just constructed;
    # otherwise the first pre-fade VBlank manufactures an unnecessary full
    # 17-row palette pass even though the fixture's CRAM is already current.
    # That synthetic job delayed Ted's receipt by 19 frames and did not occur
    # on a natural playthrough where the stage pass settled long beforehand.
    if target == 4 and not stock_rom:
        raw[DF00] = (
            raw[FFBF] ^ raw[FFC0] ^ raw[FFD0] ^ raw[FFBA]
        ) + 1 & 0xFF
    if not stock_rom:
        # These are DX runtime sentinels/mailboxes, not stock-game scratch.
        # Touching them in the OG fixture changes native boss behavior and can
        # prevent the stock dispatcher from ever reaching a stable receipt.
        raw[C5FF] = 0
        raw[DBFF] = 0
        raw[DF51] = 0
        raw[FFA7] = raw[FFA8] = raw[FFA9] = 0

    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(destination, chunks)


def capture_final(
    mgba: str,
    rom: Path,
    injected_state: Path,
    prefix: Path,
    target: int,
    timeout: float,
    sidecar_dir: Path,
    *,
    stock_rom: bool = False,
) -> str:
    state = prefix.with_suffix(".ss0")
    done = prefix.with_suffix(".done")
    report = prefix.with_suffix(".report")
    env = os.environ.copy()
    env.update(
        BOSS_TARGET=str(target),
        BOSS_STATE_OUT=str(state),
        BOSS_OUT=str(prefix),
        BOSS_STABLE_FRAMES=str(BOSS_SETTLE_FRAMES),
        BOSS_ENTRY_TIMEOUT="1200",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        BOSS_STOCK_ROM="1" if stock_rom else "0",
    )
    if target == CRYSTAL_TARGET:
        source_offset = (
            PALETTE_ROM_BANK * ROM_BANK_SIZE
            + CRYSTAL_OBJ_SOURCE_ADDR
            - ROM_BANK_SIZE
        )
        frost = rom.read_bytes()[source_offset:source_offset + 8]
        # OBJ slots 4..7 must all carry the scene-local Crystal material row
        # before the fixture can be serialized. This rejects an idle loader
        # that has not yet observed the true Crystal scene publisher.
        env["BOSS_OBJ_EXPECTED"] = (frost * 4).hex().upper()
    run_until_marker(
        [
            mgba,
            "--fastforward",
            "-t",
            str(injected_state),
            "-C",
            f"savegamePath={sidecar_dir}",
            "-C",
            f"savestatePath={sidecar_dir}",
            str(rom.resolve()),
            "--script",
            str(BOSS_PROBE),
        ],
        env,
        sidecar_dir,
        done,
        timeout,
    )
    if not report.is_file():
        raise RuntimeError("boss capture did not create a report")
    detail = report.read_text().strip()
    if done.read_text().strip() != "ok":
        raise RuntimeError(f"boss capture failed: {detail}")
    if not state.is_file() or state.stat().st_size < 1024:
        raise RuntimeError("boss capture did not create a usable savestate")
    return detail


def generate_one(
    mgba: str,
    rom: Path,
    safe_state: Path,
    output: Path,
    target: int,
    expected_table: bytes,
    timeout: float,
    *,
    stock_rom: bool = False,
) -> tuple[int, str]:
    name = BOSS_NAMES[target]
    expected_scene = BOSSES[target].scene
    with tempfile.TemporaryDirectory(
        prefix=f"penta-boss{target}-", dir="/mnt/data/tmp"
    ) as tmp:
        tmpdir = Path(tmp)
        injected = tmpdir / "injected.ss0"
        patch_state(safe_state, injected, target, stock_rom=stock_rom)

        prefix = tmpdir / f"boss{target}_{name}"
        try:
            detail = capture_final(
                mgba,
                rom,
                injected,
                prefix,
                target,
                timeout,
                tmpdir,
                stock_rom=stock_rom,
            )
        except Exception:
            # Entry timeouts, scene exits, and save failures occur before the
            # ordinary report-validation branch below. Preserve those receipts
            # too; otherwise TemporaryDirectory erases the most important
            # evidence from long-running corrupt candidates.
            failed_stem = f"boss{target}_{name}.failed"
            for artifact, suffix in (
                (prefix.with_suffix(".report"), ".report"),
                (prefix.with_suffix(".trace"), ".trace"),
                (prefix.with_suffix(".png"), ".png"),
                (prefix.with_suffix(".ss0"), ".ss0"),
                (prefix.with_suffix(".done"), ".done"),
            ):
                if artifact.is_file():
                    shutil.copy2(artifact, output / f"{failed_stem}{suffix}")
            raise
        required = (
            "status=ok",
            f"target={target}",
            f"expected_scene={expected_scene:02X}",
            f"d880={expected_scene:02X}",
            # FFBA selects the boss at $1A2B but is ordinary runtime scratch
            # after that dispatcher consumes it.  D880 is the persistent,
            # production colorizer identity and must remain stable instead.
            "phase=00",
            "message=saved",
        )
        missing = [token for token in required if token not in detail]
        fields = dict(
            field.split("=", 1)
            for field in detail.split()
            if "=" in field
        )
        try:
            stable_frames = int(fields.get("stable", "0"))
        except ValueError:
            stable_frames = 0
        if stable_frames < BOSS_SETTLE_FRAMES:
            missing.append(
                f"at least {BOSS_SETTLE_FRAMES} arena frames "
                f"(got {stable_frames})"
            )
        try:
            entry_frame = int(fields.get("settle_frame", fields.get("frame", "0")))
        except ValueError:
            entry_frame = 0
        if target in BOSS_ENTRY_FRAME_LIMITS:
            maximum_frame = BOSS_ENTRY_FRAME_LIMITS[target]
            if entry_frame <= 0 or entry_frame > maximum_frame:
                missing.append(
                    f"normalized entry settle by frame {maximum_frame} "
                    f"(got {entry_frame})"
                )
        actual_table_hex = fields.get("active_table", "")
        expected_table_hex = expected_table.hex().upper()
        if not stock_rom and actual_table_hex != expected_table_hex:
            try:
                actual_table = bytes.fromhex(actual_table_hex)
            except ValueError:
                actual_table = b""
            mismatches = sum(
                actual != expected
                for actual, expected in zip(actual_table, expected_table)
            ) + abs(len(actual_table) - len(expected_table))
            missing.append(
                f"active_table exact match ({mismatches}/256 mismatches)"
            )
        try:
            bg_cram = bytes.fromhex(fields.get("bg_cram", ""))
        except ValueError:
            bg_cram = b""
        words = {
            bg_cram[index] | (bg_cram[index + 1] << 8)
            for index in range(0, len(bg_cram) - 1, 2)
        }
        if not stock_rom and len(bg_cram) != 64:
            missing.append(f"64-byte bg_cram (got {len(bg_cram)})")
        if not stock_rom and not words - {0x0000, 0x7FFF}:
            missing.append("nontrivial bg_cram")
        try:
            palette_settled = int(fields.get("palette_settled", "0"))
        except ValueError:
            palette_settled = 0
        if not stock_rom and palette_settled < 1:
            missing.append(
                f"a phase-zero palette frame (got {palette_settled})"
            )
        expected_bg7_offset = (
            PALETTE_ROM_BANK * ROM_BANK_SIZE
            + TUNED_BG7_SOURCE_ADDR - ROM_BANK_SIZE
        )
        expected_bg7 = rom.read_bytes()[
            expected_bg7_offset:expected_bg7_offset + 8
        ]
        # A stale inactive CRAM row is not a rendered defect. Crystal's cached
        # portal table uses only BG0/BG4, so requiring BG7 there falsely fails
        # a visually exact arena because its synthetic entry began in the
        # Stage-1 spike room. Arenas that actually reference BG7 remain exact.
        bg7_is_rendered = 7 in expected_table
        if (not stock_rom and bg7_is_rendered
                and bg_cram[56:64] != expected_bg7):
            missing.append(
                "rendered BG7 exact tuned row "
                f"({bg_cram[56:64].hex().upper()} != "
                f"{expected_bg7.hex().upper()})"
            )
        try:
            obj_cram = bytes.fromhex(fields.get("obj_cram", ""))
        except ValueError:
            obj_cram = b""
        if not stock_rom and len(obj_cram) != 64:
            missing.append(f"64-byte obj_cram (got {len(obj_cram)})")
        if not stock_rom and target == CRYSTAL_TARGET:
            source_offset = (
                PALETTE_ROM_BANK * ROM_BANK_SIZE
                + CRYSTAL_OBJ_SOURCE_ADDR
                - ROM_BANK_SIZE
            )
            frost = rom.read_bytes()[source_offset:source_offset + 8]
            expected_crystal = frost * 4
            if obj_cram[32:64] != expected_crystal:
                missing.append(
                    "Crystal OBJ4-7 exact scene-local frost rows "
                    f"({obj_cram[32:64].hex().upper()} != "
                    f"{expected_crystal.hex().upper()})"
                )
        if missing:
            # Preserve the failing transition trace and rendered evidence;
            # TemporaryDirectory cleanup must not erase the only receipt for
            # a palette-trigger collision.
            failed_stem = f"boss{target}_{name}.failed"
            for artifact, suffix in (
                (prefix.with_suffix(".report"), ".report"),
                (prefix.with_suffix(".trace"), ".trace"),
                (prefix.with_suffix(".png"), ".png"),
                (prefix.with_suffix(".ss0"), ".ss0"),
            ):
                if artifact.is_file():
                    shutil.copy2(artifact, output / f"{failed_stem}{suffix}")
            raise RuntimeError(
                f"{name}: bad final report: missing {', '.join(missing)}; "
                f"actual {detail}"
            )

        state = prefix.with_suffix(".ss0")
        report = prefix.with_suffix(".report")
        screenshot = prefix.with_suffix(".png")
        trace = prefix.with_suffix(".trace")
        if not screenshot.is_file() or screenshot.stat().st_size < 1000:
            # Cold-path failures are precisely the cases that need retained
            # evidence; do not let TemporaryDirectory erase their trace.
            failed_stem = f"boss{target}_{name}.failed"
            for artifact, suffix in (
                (report, ".report"),
                (trace, ".trace"),
                (screenshot, ".png"),
                (state, ".ss0"),
            ):
                if artifact.is_file():
                    shutil.copy2(artifact, output / f"{failed_stem}{suffix}")
            raise RuntimeError(
                f"{name}: final screenshot is missing or structurally trivial"
            )
        with Image.open(screenshot) as source:
            rendered = source.convert("RGB")
            rendered_colors = len(set(rendered.getdata()))
            if rendered.size != (160, 144):
                raise RuntimeError(
                    f"{name}: rendered size {rendered.size}, expected 160x144"
                )
        # The known bad serialized landing renders a five-color horizontal
        # stripe field. Ted's valid early arena frame can legitimately have
        # six or seven colors before its animation exposes the full set.
        if not stock_rom and rendered_colors < 6:
            raise RuntimeError(
                f"{name}: rendered frame has only {rendered_colors} colors"
            )
        stem = f"boss{target}_{name}"
        shutil.move(state, output / f"{stem}.ss0")
        shutil.move(report, output / f"{stem}.report")
        shutil.move(screenshot, output / f"{stem}.png")
        if trace.is_file():
            shutil.move(trace, output / f"{stem}.trace")
        return target, detail


def report_fields(path: Path) -> dict[str, str]:
    return dict(
        field.split("=", 1)
        for field in path.read_text().split()
        if "=" in field
    )


def recapture_one(
    mgba: str,
    rom: Path,
    source_state: Path,
    staging: Path,
    target: int,
    expected_table: bytes,
    timeout: float,
) -> tuple[int, str]:
    name = BOSS_NAMES[target]
    stem = f"boss{target}_{name}"
    prefix = staging / stem
    state = prefix.with_suffix(".ss0")
    marker = Path(f"{prefix}.audit.done")
    report = Path(f"{prefix}.audit.report")
    screenshot = prefix.with_suffix(".png")
    env = os.environ.copy()
    env.update(
        BOSS_RECEIPT_OUT=str(prefix),
        BOSS_RECEIPT_STATE_OUT=str(state),
        BOSS_RECEIPT_FRAMES="120",
        # The fixture is machine-preservingly retargeted below with the
        # candidate's exact C600/DA60/DB80 payloads. Replaying scene_detect on
        # a live final-boss state is synthetic and makes Penta leave its arena.
        BOSS_RECEIPT_REARM="0",
        BOSS_TARGET=str(target),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    run_until_marker(
        [
            mgba,
            "--fastforward",
            "-t",
            str(source_state),
            "-C",
            f"savegamePath={staging}",
            "-C",
            f"savestatePath={staging}",
            str(rom.resolve()),
            "--script",
            str(RECEIPT_PROBE),
        ],
        env,
        staging,
        marker,
        timeout,
    )
    if marker.read_text().strip() != "ok" or not report.is_file():
        raise RuntimeError(f"{name}: fixture recapture failed")
    data = report_fields(report)
    failures: list[str] = []
    expected_scene = f"{BOSSES[target].scene:02X}"
    for field, wanted in (
        ("status", "ok"),
        ("d880", expected_scene),
        ("ffc1", "1"),
        ("state_saved", "true"),
    ):
        if data.get(field) != wanted:
            failures.append(f"{field}={data.get(field)} expected {wanted}")
    try:
        lcdc = int(data.get("lcdc", "0"), 16)
    except ValueError:
        lcdc = 0
    if not lcdc & 0x80:
        failures.append(f"LCDC={lcdc:02X} (display disabled)")
    try:
        active_table = bytes.fromhex(data.get("active_table", ""))
    except ValueError:
        active_table = b""
    mismatches = sum(
        actual != expected
        for actual, expected in zip(active_table, expected_table)
    ) + abs(len(active_table) - len(expected_table))
    # Arena rendering also uses live per-cell position attributes, so the
    # mutable $C600 working table is not required to remain byte-identical to
    # its ROM seed. It must still be a complete, valid CGB palette-index LUT.
    if len(active_table) != 256 or any(value > 7 for value in active_table):
        failures.append("active_table is missing or contains invalid slots")
    try:
        bg_cram = bytes.fromhex(data.get("bg_cram", ""))
    except ValueError:
        bg_cram = b""
    words = {
        bg_cram[index] | (bg_cram[index + 1] << 8)
        for index in range(0, len(bg_cram) - 1, 2)
    }
    if len(bg_cram) != 64 or not words - {0x0000, 0x7FFF}:
        failures.append("BG CRAM is missing or trivial")
    expected_bg7_offset = (
        PALETTE_ROM_BANK * ROM_BANK_SIZE
        + TUNED_BG7_SOURCE_ADDR - ROM_BANK_SIZE
    )
    expected_bg7 = rom.read_bytes()[
        expected_bg7_offset:expected_bg7_offset + 8
    ]
    if 7 in expected_table and bg_cram[56:64] != expected_bg7:
        failures.append(
            "rendered BG7 does not match the candidate's tuned YAML row "
            f"({bg_cram[56:64].hex().upper()} != "
            f"{expected_bg7.hex().upper()})"
        )
    rendered_colors = 0
    if not screenshot.is_file() or screenshot.stat().st_size < 1000:
        failures.append("rendered screenshot is missing/structurally trivial")
    else:
        with Image.open(screenshot) as source:
            rendered_colors = len(set(source.convert("RGB").getdata()))
        # A deliberately coherent single-material boss can render with six or
        # seven RGB values; reject only the known five-color serialized stripe
        # failure, matching the fresh-state gate above.
        if rendered_colors < 6:
            failures.append(
                f"rendered screenshot has only {rendered_colors} colors"
            )
    if not state.is_file() or state.stat().st_size < 1024:
        failures.append("current-ROM state was not saved")
    if failures:
        raise RuntimeError(f"{name}: " + "; ".join(failures))
    final_report = staging / f"{stem}.report"
    report.replace(final_report)
    marker.unlink(missing_ok=True)
    return target, (
        f"D880={expected_scene} LCDC={lcdc:02X} "
        f"rom_seed_differences={mismatches} rendered_colors={rendered_colors}"
    )


def recapture_from_fixtures(
    mgba: str,
    rom: Path,
    source: Path,
    output: Path,
    targets: list[int],
    timeout: float,
    write_manifest: bool,
) -> list[tuple[int, str]]:
    missing = [
        source / f"boss{target}_{BOSS_NAMES[target]}.ss0"
        for target in targets
        if not (source / f"boss{target}_{BOSS_NAMES[target]}.ss0").is_file()
    ]
    if missing:
        raise RuntimeError(
            "curated boss fixture states are missing: "
            + ", ".join(str(path) for path in missing)
        )
    rom_bytes = rom.read_bytes()
    with tempfile.TemporaryDirectory(
        prefix="penta-boss-recapture-", dir="/mnt/data/tmp"
    ) as tmp:
        staging = Path(tmp)
        normalized_states: dict[int, Path] = {}
        for target in targets:
            source_state = source / f"boss{target}_{BOSS_NAMES[target]}.ss0"
            normalized_state = staging / (
                f"boss{target}_{BOSS_NAMES[target]}.candidate.ss0"
            )
            normalize(
                source_state,
                normalized_state,
                0,
                [],
                rom,
                preserve_machine=True,
                arena_table=target,
            )
            normalized_states[target] = normalized_state
        results = [
            recapture_one(
                mgba,
                rom,
                normalized_states[target],
                staging,
                target,
                rom_bytes[
                    PALETTE_ROM_BANK * ROM_BANK_SIZE
                    + ARENA_TABLE_BASE
                    + target * BG_TABLE_SIZE
                    - ROM_BANK_SIZE:
                    PALETTE_ROM_BANK * ROM_BANK_SIZE
                    + ARENA_TABLE_BASE
                    + (target + 1) * BG_TABLE_SIZE
                    - ROM_BANK_SIZE
                ],
                timeout,
            )
            for target in targets
        ]
        output.mkdir(parents=True, exist_ok=True)
        for target in targets:
            stem = f"boss{target}_{BOSS_NAMES[target]}"
            for suffix in (".ss0", ".report", ".png"):
                shutil.move(staging / f"{stem}{suffix}", output / f"{stem}{suffix}")
        if write_manifest:
            manifest = {
                "rom": str(rom.resolve()),
                "rom_md5": md5(rom),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "method": "fresh current-ROM recapture from curated visual fixtures",
                "source_states": str(source),
                "bosses": [
                    {"target": target, "name": BOSS_NAMES[target]}
                    for target in targets
                ],
            }
            temporary = output / "manifest.json.tmp"
            temporary.write_text(json.dumps(manifest, indent=2) + "\n")
            temporary.replace(output / "manifest.json")
    return results


def cached(output: Path, rom_md5: str) -> bool:
    manifest = output / "manifest.json"
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        data.get("rom_md5") == rom_md5
        and all(
            (output / f"boss{target}_{name}.ss0").is_file()
            and (output / f"boss{target}_{name}.ss0").stat().st_size >= 1024
            for target, name in enumerate(BOSS_NAMES)
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--source-states",
        type=Path,
        default=DEFAULT_SOURCE_STATES,
        help=(
            "curated, visually valid boss states used only with --fixtures"
        ),
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help=(
            "recapture curated visual fixtures instead of generating fresh "
            "stock-dispatcher states"
        ),
    )
    parser.add_argument(
        "--target",
        type=int,
        action="append",
        choices=range(len(BOSS_NAMES)),
        help="generate only this boss index (repeatable; default: all nine)",
    )
    args = parser.parse_args()

    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rom_md5 = md5(args.rom)
    targets = args.target or list(range(len(BOSS_NAMES)))
    if args.target is None and not args.force and cached(output, rom_md5):
        print(f"Stream boss states are current for {rom_md5}.")
        return 0

    if args.fixtures:
        source = args.source_states.resolve()
        try:
            results = recapture_from_fixtures(
                args.mgba,
                args.rom.resolve(),
                source,
                output,
                targets,
                args.timeout,
                args.target is None,
            )
        except Exception as error:
            print(f"FAIL: boss fixture recapture: {error}")
            return 1
        for target, detail in results:
            print(f"Boss {target} {BOSS_NAMES[target]}: PASS | {detail}")
        print(
            f"Recaptured {len(results)} current-ROM stream boss "
            f"{'state' if len(results) == 1 else 'states'} in {output}."
        )
        return 0

    rom_bytes = args.rom.read_bytes()
    # Identify the stock base by CONTENT, never by path. The release matrix
    # runs gates against isolated copies under tmp/, so a path comparison
    # silently reports "candidate" for a byte-identical vanilla ROM and then
    # applies the DX-only FF91/DF0D/unsafe_attr assertions to it. That is the
    # exact failure that blocked boss_publication_cadence behind boss_og_states.
    stock_rom = hashlib.md5(rom_bytes).hexdigest() == SUPPORTED_BASE_MD5
    # Bosses 0..7 share the ordinary stage-boss dispatcher. Penta Dragon is
    # entered by the native pre-final bridge and a synthetic Stage-1 CALL can
    # legitimately fall through into final-story state before a long palette
    # hold. Generate the ordinary eight from Stage 1, then retarget the curated
    # live Penta fixture with the candidate's exact runtime/table payloads.
    fresh_targets = [target for target in targets if target != 8]
    results: list[tuple[int, str]] = []
    if fresh_targets:
        with tempfile.TemporaryDirectory(
            prefix="penta-safe-stage1-",
            dir="/mnt/data/tmp",
        ) as tmp:
            safe_state = generate_safe_stage1(
                args.mgba,
                args.rom,
                Path(tmp),
                args.timeout,
                stock_rom=stock_rom,
            )
            results.extend(
                generate_one(
                    args.mgba,
                    args.rom,
                    safe_state,
                    output,
                    target,
                    rom_bytes[
                        PALETTE_ROM_BANK * ROM_BANK_SIZE
                        + ARENA_TABLE_BASE
                        + target * BG_TABLE_SIZE
                        - ROM_BANK_SIZE:
                        PALETTE_ROM_BANK * ROM_BANK_SIZE
                        + ARENA_TABLE_BASE
                        + (target + 1) * BG_TABLE_SIZE
                        - ROM_BANK_SIZE
                    ],
                    args.timeout,
                    stock_rom=stock_rom,
                )
                for target in fresh_targets
            )
    if 8 in targets:
        results.extend(
            recapture_from_fixtures(
                args.mgba,
                args.rom.resolve(),
                args.source_states.resolve(),
                output,
                [8],
                args.timeout,
                False,
            )
        )
    results.sort()

    manifest = {
        "rom": str(args.rom.resolve()),
        "rom_md5": rom_md5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "fresh Stage-1 stock dispatcher for bosses 0-7; machine-preserved "
            "native pre-final fixture for Penta Dragon; release ROM capture"
        ),
        "bosses": [
            {"target": target, "name": BOSS_NAMES[target]}
            for target, _detail in results
        ],
    }
    if args.target is None:
        temporary = output / "manifest.json.tmp"
        temporary.write_text(json.dumps(manifest, indent=2) + "\n")
        temporary.replace(output / "manifest.json")
    for target, detail in results:
        print(f"Boss {target} {BOSS_NAMES[target]}: PASS | {detail}")
    print(
        f"Generated {len(results)} release-ROM stream boss "
        f"{'state' if len(results) == 1 else 'states'} in {output}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
