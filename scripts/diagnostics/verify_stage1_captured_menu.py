#!/usr/bin/env python3
"""Observe menu close and movement recovery from an untouched exact-ROM state."""
# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: only the checked-in wrapper is used.
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zlib
from PIL import Image

from normalize_mgba_state_pc import png_chunks, write_png, GB_STATE_SIZE

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_stage1_captured_menu.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
OPERATOR_STATE = ROOT / "tmp/r534-headed-menu-incident-current533/operator.ss9"
OPERATOR_SHA = "dd15cb653f5208a3c5597e861ff5942f1c9189a2b5302f72063cc094504621bd"
OPERATOR_ROM_SHA = "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"


# The release lock's #27 arena-completion-safe stage relocates the always-
# mapped bank-1 WRAM runtime images that the cold installer copies from bank13
# (post-copy guard $DBF1->$DBF3, dirty bridge $DBDF->$DBDC, DABB/DB80 calls).
# The r534 operator capture serializes the 4f5a-ABI images, so replaying it
# unchanged executes stale WRAM code against the candidate's callers. Refresh
# exactly these installer images, only after proving the capture holds the
# ancestor's bytes there; CPU, stack, mapper, VRAM and game data stay untouched.
RELEASE_LOCK_WRAM_IMAGES = (
    (0xDAB0, 13 * 0x4000 + 0x3C6F, 14),
    (0xDB80, 13 * 0x4000 + 0x163A, 36),
    (0xDBA4, 13 * 0x4000 + 0x169A, 36),
    (0xDBC8, 13 * 0x4000 + 0x16CA, 36),
    (0xDBEC, 13 * 0x4000 + 0x16FA, 5),
    (0xDBF1, 13 * 0x4000 + 0x1830, 12),
)


def menu_contract_rom(rom: bytes) -> bytes:
    """#61: authenticate unchanged menu ABI; never execute this reconstructed ROM."""
    import playtest_successor_lineage as successor

    if not successor.is_candidate(rom):
        return rom
    spans = [(20 * 0x4000, 21 * 0x4000)]
    spans.extend((source, source + length)
                 for _, source, length in RELEASE_LOCK_WRAM_IMAGES)
    return successor.authenticated_parent(rom, *spans)


def release_lock_runtime_refresh(raw: bytearray, rom: bytes) -> list | None:
    import release_lock_lineage as lineage

    contract = menu_contract_rom(rom)
    if not lineage.is_candidate(contract):
        return None
    parent = lineage.ancestor_bytes(
        contract, 0, 32 * 0x4000, set().union(*lineage.RUN_OWNERS.values()))
    records = []
    for address, source, length in RELEASE_LOCK_WRAM_IMAGES:
        offset = 0x4400 + 0x1000 + address - 0xD000
        if bytes(raw[offset:offset + length]) != parent[source:source + length]:
            raise ValueError(f"operator WRAM ${address:04X} is not the 4f5a installer image")
        for start, end in [(source, source + length)]:
            lineage.ancestor_bytes(contract, start, end,
                                   {"arena-completion-safe", "arena-graphics-owner"})
        raw[offset:offset + length] = rom[source:source + length]
        records.append({"wram": f"{address:04X}", "rom_offset": f"{source:05X}",
                        "length": length,
                        "sha256": hashlib.sha256(rom[source:source + length]).hexdigest()})
    return records


SETTLE_PROBE = Path(__file__).with_name("probe_stage1_captured_menu_settle.lua")
MEMORY_CURRENT_BANK = 0x0168
CPU_SP, CPU_PC = 0x0028, 0x002A


def _gbas(state_bytes: bytes) -> tuple[list, int, bytes]:
    chunks = png_chunks(state_bytes)
    indices = [i for i, (kind, _) in enumerate(chunks) if kind == b"gbAs"]
    if len(indices) != 1:
        raise ValueError("state needs exactly one machine state")
    raw = zlib.decompress(chunks[indices[0]][1])
    if len(raw) != GB_STATE_SIZE:
        raise ValueError("unexpected machine state size")
    return chunks, indices[0], raw


def release_lock_boundary(raw: bytes, rom: bytes) -> dict:
    """CPU PC and every stacked word stay outside the release-lock rewrites."""
    import release_lock_lineage as lineage
    import playtest_successor_lineage as successor

    sp = int.from_bytes(raw[CPU_SP:CPU_SP + 2], "little")
    pc = int.from_bytes(raw[CPU_PC:CPU_PC + 2], "little")
    bank = int.from_bytes(raw[MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2], "little")
    if not 0xDF00 <= sp <= 0xDFFE:
        return {"safe": False, "reason": f"stack outside the native page (SP={sp:04X})"}
    words = [pc] + [raw[0x4400 + 0x1000 + a - 0xD000] | raw[0x4400 + 0x1000 + a + 1 - 0xD000] << 8
                    for a in range(sp, 0xDFFE, 2)]
    hits = []
    for index, word in enumerate(words):
        if word >= 0x8000:
            continue
        base = word if word < 0x4000 else bank * 0x4000 + word - 0x4000
        # PC: the executing neighbourhood must be byte-identical. Stacked
        # return words: the CALL that pushed them (and the opcode they resume
        # at) must be unchanged, so they resume on an instruction boundary
        # shared by both ABIs; later candidate code may legitimately differ.
        span = (base - 8, base + 8) if index == 0 else (base - 3, base + 1)
        successor_hit = successor.is_candidate(rom) and any(
            span[0] < offset + len(bytes.fromhex(after)) and offset < span[1]
            for offset, _, after in successor.RUNS)
        if lineage.touched(*span) or successor_hit:
            hits.append(f"{word:04X}")
    # #33 replaces the bank-20 menu row prologue ($404A) and re-enters native
    # code at $406F. A frame frozen in [$4040,$406F) was built by the native
    # prologue and would resume into the staged contract, so reject it.
    in_menu_bank = bank == 20 and any(0x4040 <= word < 0x406F for word in words)
    return {"safe": not hits and not in_menu_bank, "pc": f"{pc:04X}", "sp": f"{sp:04X}",
            "rom_bank": bank, "stack_words": [f"{w:04X}" for w in words[1:]],
            "release_lock_hits": hits, "inside_bank20_menu": in_menu_bank}


def settle_on_ancestor(state_bytes: bytes, rom: bytes, work: Path) -> tuple[bytes, dict]:
    """Release lock: advance the operator capture on the authenticated 4f5a ABI.

    The r534 capture freezes the CPU inside the bank-20 menu attribute row
    routine (PC $406B). #33's staged rows replace that routine's $404A
    prologue, so resuming the old frame on the candidate unbalances SP
    (it walks to $E1C3) and the corrupt stack forces FFB7=$0C (Shalamar
    arena). Run the identical no-input frames on the candidate's 4f5a ancestor
    (which shares the r534 ABI and passes this gate) until CPU and stack are
    outside every release-lock rewrite; the close/stationary contract then
    runs entirely on the candidate.
    """
    import release_lock_lineage as lineage

    ancestor = lineage.ancestor_bytes(
        menu_contract_rom(rom), 0, 32 * 0x4000, set().union(*lineage.RUN_OWNERS.values()))
    if hashlib.sha256(ancestor).hexdigest() != lineage.SARA_SHA256:
        raise ValueError("release-lock ancestor reconstruction failed")
    chunks, index, raw = _gbas(state_bytes)
    retargeted = bytearray(raw)
    retargeted[4:8] = (zlib.crc32(ancestor) & 0xFFFFFFFF).to_bytes(4, "little")
    chunks[index] = (b"gbAs", zlib.compress(bytes(retargeted), level=9))
    work.mkdir(parents=True)
    (work / "ancestor.gb").write_bytes(ancestor)
    write_png(work / "operator-on-ancestor.ss9", chunks)
    env = os.environ.copy()
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        env.pop(key, None)
    env.update(PENTA_CAPTURED_MENU_SETTLE_OUT=str(work),
               PENTA_CAPTURED_MENU_STATE=str(work / "operator-on-ancestor.ss9"),
               QT_QPA_PLATFORM="offscreen", SDL_AUDIODRIVER="dummy", TMPDIR=str(ROOT / "tmp"))
    run = subprocess.run([str(MGBA), "--fastforward", str(work / "ancestor.gb"),
                          "--script", str(SETTLE_PROBE), "-C", f"savegamePath={work}",
                          "-C", f"savestatePath={work}"], env=env, cwd=ROOT,
                         capture_output=True, timeout=60, check=False)
    (work / "emulator.log").write_bytes(run.stdout + run.stderr)
    if run.returncode != 0 or not (work / "done.txt").is_file():
        raise ValueError(f"ancestor settle incomplete (exit {run.returncode})")
    for frame in range(1, 25):
        settled = (work / f"settle-{frame:02d}.ss0").read_bytes()
        _, _, settled_raw = _gbas(settled)
        boundary = release_lock_boundary(settled_raw, rom)
        if boundary["safe"]:
            return settled, {"ancestor_sha256": lineage.SARA_SHA256, "frames": frame,
                             "state_sha256": hashlib.sha256(settled).hexdigest(),
                             "boundary": boundary}
    raise ValueError("operator capture never reached a release-lock-safe boundary")


def operator_retarget(state_bytes: bytes, rom: bytes, settled: bytes | None = None,
                      settle: dict | None = None) -> tuple[list, dict]:
    """Explicit cross-build fixture: alter CRC metadata, never machine state."""
    if hashlib.sha256(state_bytes).hexdigest() != OPERATOR_SHA:
        raise ValueError("operator fixture SHA differs; refusing an unknown baseline")
    chunks = png_chunks(settled if settled is not None else state_bytes)
    indices = [i for i,(kind,_) in enumerate(chunks) if kind == b"gbAs"]
    if len(indices) != 1:
        raise ValueError("operator fixture needs exactly one machine state")
    index = indices[0]
    before = zlib.decompress(chunks[index][1])
    if len(before) != GB_STATE_SIZE or before[0x10:0x20] != rom[0x134:0x144]:
        raise ValueError("operator fixture machine format/title changed")
    after = bytearray(before)
    after[4:8] = (zlib.crc32(rom) & 0xFFFFFFFF).to_bytes(4, "little")
    assert after[:4] == before[:4] and after[8:] == before[8:]
    runtime_refresh = release_lock_runtime_refresh(after, rom)
    chunks[index] = (b"gbAs", zlib.compress(after, level=9))
    if runtime_refresh is not None:
        return chunks, {"source_state_sha256": OPERATOR_SHA,
                        "source_rom_sha256": OPERATOR_ROM_SHA,
                        "target_rom_sha256": hashlib.sha256(rom).hexdigest(),
                        "changed_state_offsets": [i for i,(a,b) in enumerate(zip(before, after))
                                                  if a != b and not 0x5A00 <= i < 0x6000],
                        "cpu_stack_mapper_wram_vram_unchanged": False,
                        "release_lock_wram_runtime_refresh": runtime_refresh,
                        "release_lock_ancestor_settle": settle,
                        "cold_boot_qualification": False}
    return chunks, {"source_state_sha256": OPERATOR_SHA,
                    "source_rom_sha256": OPERATOR_ROM_SHA,
                    "target_rom_sha256": hashlib.sha256(rom).hexdigest(),
                    "changed_state_offsets": [i for i,(a,b) in enumerate(zip(before, after)) if a != b],
                    "cpu_stack_mapper_wram_vram_unchanged": True,
                    "cold_boot_qualification": False}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def room01_lut(rom: bytes) -> bytes:
    """Four reviewed dual-use wall IDs are BG6 only in room 01.

    The global page describes room 05, where these IDs must stay neutral.
    Require the ROM's existing room-01 semantic page to agree with the fixed
    reviewed values; never learn expectations from the captured bad map.
    """
    result = bytearray(rom[0x37000:0x37100])
    if len(result) != 256 or any(v > 15 for v in result):
        raise ValueError("invalid canonical Stage-1 lookup page")
    for tile in (0x24, 0x27, 0x30, 0x33):
        if result[tile] != 0 or rom[20 * 0x4000 + 0x600 + tile] != 6:
            raise ValueError("reviewed room-01/global dual-use wall contract changed")
        result[tile] = 6
    return bytes(result)


def expected_incident_pixels(state_bytes: bytes, rom: bytes) -> list[tuple]:
    """Independent palette reconstruction for the stationary upper-left ROI.

    Exact captured tile/art bytes define geometry only. Colors come from the
    canonical contextual LUT and ROM palette, never the corrupted attributes
    or screenshot. The 32x40 ROI has no native sprite in this fixed incident.
    """
    if hashlib.sha256(state_bytes).hexdigest() != OPERATOR_SHA:
        raise ValueError("pixel oracle requires the exact operator geometry")
    raw = next(zlib.decompress(p) for k,p in png_chunks(state_bytes) if k == b"gbAs")
    vram, lut = raw[0x400:0x4400], room01_lut(rom)
    palette = rom[13 * 0x4000 + 0x2800:13 * 0x4000 + 0x2840]
    result = []
    for y in range(40):
        for x in range(32):
            sx, sy = x + 12, y + 8
            tile = vram[0x1800 + (sy // 8) * 32 + sx // 8]
            attr = lut[tile]
            signed = tile if tile < 128 else tile - 256
            art = 0x1000 + 16 * signed + (0x2000 if attr & 8 else 0)
            row, bit = sy % 8, 7 - sx % 8
            index = ((vram[art + row * 2] >> bit) & 1) | (((vram[art + row * 2 + 1] >> bit) & 1) << 1)
            color = int.from_bytes(palette[(attr & 7) * 8 + index * 2:(attr & 7) * 8 + index * 2 + 2], "little")
            result.append(tuple(((color >> shift & 31) << 3) | ((color >> shift & 31) >> 2) for shift in (0,5,10)))
    return result


def incident_raster(rows: list[dict], out: Path, expected: list[tuple]) -> dict:
    checked, bad = [], []
    for row in rows:
        frame = int(row["frame"])
        if not (60 <= frame < 240 and row["menu"] == "00" and not (int(row["lcdc"],16) & 0x20)):
            continue
        if row["scx"] != "0C" or row["scy"] != "08":
            return {"passed": False, "reason": "incident-camera-changed"}
        with Image.open(out / f"frame-{frame:04d}.png") as source:
            if source.size != (160,144):
                return {"passed": False, "reason": "wrong-screenshot-size"}
            actual = list(source.convert("RGB").crop((0,0,32,40)).getdata())
        checked.append(frame)
        errors = sum(a != b for a,b in zip(actual, expected, strict=True))
        if errors:
            bad.append({"frame": frame, "pixels": errors})
    return {"passed": len(checked) >= 150 and not bad,
            "region": [0,0,32,40], "checked_frames": len(checked),
            "bad_frames": bad, "expected_pixels_sha256": hashlib.sha256(bytes(c for rgb in expected for c in rgb)).hexdigest()}


def summarize(rows: list[dict]) -> dict:
    complete = [int(r["frame"]) for r in rows] == list(range(1, 361))
    def hidden(r):
        return r["menu"] == "00" and not (int(r["lcdc"], 16) & 0x20)
    stationary = [r for r in rows if 90 <= int(r["frame"]) < 240]
    recovery = [r for r in rows if 300 <= int(r["frame"]) <= 360]
    close_transition = [r for r in rows if 60 <= int(r["frame"]) < 90 and hidden(r)]
    checks = {
        "all 360 consecutive frames retained": complete,
        "captured menu was actually visible": bool(rows) and rows[0]["menu"] == "01" and bool(int(rows[0]["lcdc"], 16) & 0x20),
        "stationary close stays in room 01": len(stationary) == 150 and all(r["room"] == "01" and r["scene"] == "02" for r in stationary),
        "no input during stationary close interval": bool(stationary) and all(r["keys"] == "00" for r in stationary),
        "menu ownership and Window are released": bool(stationary) and all(hidden(r) for r in stationary),
        "stationary background has exact canonical attributes": bool(stationary) and all(int(r["mismatches"]) == 0 for r in stationary),
        "immediate closed-menu background has exact canonical attributes": bool(close_transition) and all(int(r["mismatches"]) == 0 for r in close_transition),
    }
    return {"checks": checks,
            "stationary_bad_frames": sum(int(r["mismatches"]) > 0 for r in stationary),
            "stationary_peak_mismatches": max((int(r["mismatches"]) for r in stationary), default=-1),
            "recovery_frames": len(recovery),
            "recovery_bad_frames": sum(int(r["mismatches"]) > 0 for r in recovery),
            "close_transition_bad_frames": sum(int(r["mismatches"]) > 0 for r in close_transition),
            "close_transition_is_separate_from_stationary_contract": True,
            "first_stationary": stationary[0] if stationary else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    fixture = parser.add_mutually_exclusive_group(required=True)
    fixture.add_argument("--state", type=Path)
    fixture.add_argument("--operator-fixture", action="store_true",
                         help="use the hash-pinned operator capture, changing only ROM CRC metadata")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--close-key", choices=("b", "select", "start"), default="b")
    args = parser.parse_args()
    rom, state, out = args.rom.resolve(), (OPERATOR_STATE if args.operator_fixture else args.state).resolve(), args.output.resolve()
    if out.exists() or (ROOT / "tmp").resolve() not in out.parents:
        parser.error("output must be a fresh directory below repository tmp/")
    rom_bytes, state_bytes = rom.read_bytes(), state.read_bytes()
    payloads = [zlib.decompress(p) for k,p in png_chunks(state_bytes) if k == b"gbAs"]
    if len(payloads) != 1 or len(payloads[0]) != GB_STATE_SIZE:
        parser.error("expected one complete mGBA GB state")
    raw = payloads[0]
    if not args.operator_fixture and (int.from_bytes(raw[4:8], "little") != zlib.crc32(rom_bytes) & 0xFFFFFFFF or raw[0x10:0x20] != rom_bytes[0x134:0x144]):
        parser.error("state is not for this exact ROM; no retargeting/normalization is permitted")
    retarget = None
    if args.operator_fixture:
        try:
            settled = settle = None
            import release_lock_lineage
            if release_lock_lineage.is_candidate(menu_contract_rom(rom_bytes)):
                if out.exists():
                    parser.error("output must be a fresh directory below repository tmp/")
                settled, settle = settle_on_ancestor(
                    state_bytes, rom_bytes, out / "ancestor-settle")
            retarget_chunks, retarget = operator_retarget(
                state_bytes, rom_bytes, settled, settle)
        except ValueError as error:
            parser.error(str(error))
    verifier = Path(__file__).resolve()
    before = {"rom": sha(rom), "state": sha(state), "probe": sha(PROBE),
              "verifier": sha(verifier), "guard": sha(MGBA)}
    out.mkdir(parents=True, exist_ok=True)
    runtime = out / "runtime"
    runtime.mkdir()
    replay_state = state
    if retarget is not None:
        replay_state = runtime / "operator-crc-only.ss9"
        write_png(replay_state, retarget_chunks)
    shutil.copyfile(rom, runtime / "candidate.gb")
    lut = out / "canonical-lut.bin"
    lut.write_bytes(room01_lut(rom_bytes))
    env = os.environ.copy()
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        env.pop(key, None)
    env.update(PENTA_CAPTURED_MENU_OUT=str(out), PENTA_CAPTURED_MENU_STATE=str(replay_state),
               PENTA_CAPTURED_MENU_LUT=str(lut), PENTA_CAPTURED_MENU_CLOSE=args.close_key,
               QT_QPA_PLATFORM="offscreen", SDL_AUDIODRIVER="dummy", TMPDIR=str(ROOT / "tmp"))
    try:
        run = subprocess.run([str(MGBA), "--fastforward", str(runtime / "candidate.gb"),
                              "--script", str(PROBE), "-C", f"savegamePath={runtime}",
                              "-C", f"savestatePath={runtime}"], env=env, cwd=ROOT,
                             capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        print("FAIL: capture timed out; perform host process check before another emulator")
        return 1
    (out / "emulator.log").write_bytes(run.stdout + run.stderr)
    if run.returncode != 0 or not (out / "done.txt").is_file():
        print(f"FAIL: capture incomplete, emulator exit {run.returncode}; see {out / 'emulator.log'}")
        return run.returncode or 1
    rows = list(csv.DictReader((out / "frames.tsv").open(), delimiter="\t"))
    result = summarize(rows)
    intact = before == {"rom": sha(rom), "state": sha(state), "probe": sha(PROBE),
                        "verifier": sha(verifier), "guard": sha(MGBA)}
    result["checks"]["source ROM, state and probe remain intact"] = intact
    result["checks"]["isolated tested ROM matches requested source"] = sha(runtime / "candidate.gb") == before["rom"]
    captures = [out / f"frame-{frame:04d}.png" for frame in range(1, 361)]
    snapshots = [out / f"frame-{frame:04d}.ss0" for frame in (1,59,90,239,300,360)]
    result["checks"]["all screenshots and keyframe states retained"] = all(p.is_file() and p.stat().st_size > 0 for p in captures + snapshots)
    if args.operator_fixture and result["checks"]["all screenshots and keyframe states retained"]:
        result["incident_raster"] = incident_raster(rows, out, expected_incident_pixels(state_bytes, rom_bytes))
        result["checks"]["rendered upper-left background is clean immediately after close"] = result["incident_raster"]["passed"]
    result.update(schema="penta-stage1-captured-menu-regression-v1",
                  status="pass" if all(result["checks"].values()) else "fail",
                  rom=str(rom), rom_sha256=before["rom"], state=str(state), state_sha256=before["state"],
                  probe_sha256=before["probe"], close_key=args.close_key,
                  verifier_sha256=before["verifier"], guard_sha256=before["guard"],
                  tested_rom_path=str(runtime / "candidate.gb"),
                  tested_rom_sha256=sha(runtime / "candidate.gb"),
                  state_normalized=False, game_memory_written=False,
                  operator_fixture_retarget=retarget,
                  replay_state_sha256=sha(replay_state),
                  capture_hashes={p.name: sha(p) for p in captures + snapshots if p.is_file()},
                  expected_room="01", canonical_lut_sha256=sha(lut),
                  movement_recovery_qualifies_stationary=False,
                  trace_sha256=sha(out / "frames.tsv"))
    (out / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k != "capture_hashes"}, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
