"""Verify native Stage-1 sound requests and engine consumption (issue #16).

Frame-sampled D887 transitions are retained as diagnostics, not used as a
command counter: requests can be consumed between samples. Both ROMs are
freshly measured with the checked-in single-flight launcher. This gate is
not a claim of PCM/acoustic equivalence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from sound_command_oracle import CALLERS, inspect_commands, compare_commands

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MGBA_QT = PROJECT_ROOT / "scripts/mgba-qt-singleflight"
NATIVE_AUDIO_OPTIONS = ("mute=0", "volume=256", "fastForwardMute=-1",
                        "fastForwardVolume=256")
PROBE = Path(__file__).with_name("phantom_d887.lua")
ROUTE_COMMAND_VALUES = set(CALLERS)
ENGINE_BYTES = bytes.fromhex("fa87d8b7c84ffa88d8b7280ab928073005afea87d8c9cd7b45")


def parse_probe_metrics(text: str) -> dict:
    metrics = {}
    for line in text.splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key == "command_values":
            metrics[key] = {int(k, 16): int(v) for k, v in
                            (item.split(":", 1) for item in value.split(",") if item)}
        elif key == "transitions_per_second":
            metrics[key] = float(value)
        else:
            try:
                metrics[key] = int(value)
            except ValueError:
                continue
    return metrics


def run_d887(rom_path: str, frames: int, *, engine_trace: bool = False) -> dict:
    rom = Path(rom_path).resolve()
    data = rom.read_bytes()
    if engine_trace and data[0xC5B1:0xC5CA] != ENGINE_BYTES:
        raise ValueError("unauthenticated bank-3 sound-engine observation sites")
    scratch_root = PROJECT_ROOT / "tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="penta-phantom-", dir=scratch_root) as temp:
        out = Path(temp) / "result.txt"
        marker = Path(str(out) + ".done")
        env = os.environ.copy()
        env.update(STATE_PATH=str(out), MEASURE_FRAMES=str(frames),
                   QT_QPA_PLATFORM="offscreen", SDL_AUDIODRIVER="dummy")
        if engine_trace:
            env["PENTA_PHANTOM_ENGINE_TRACE"] = str(Path(temp) / "engine.tsv")
        native_capture = bool(env.get("PENTA_NATIVE_AV_PREFIX"))
        # #43: native captures must not inherit implicit Qt mute/fast-forward
        # audio settings (they changed serialized APU capacitor bytes in cold
        # builders). Match run_secret_entry_probe's explicit configuration.
        audio_options = ([item for option in NATIVE_AUDIO_OPTIONS
                          for item in ("-C", option)] if native_capture else [])
        command = [str(MGBA_QT), *audio_options, "-C", f"savegamePath={temp}", "-C",
                   f"savestatePath={temp}", str(rom), "--script", str(PROBE), "-l", "0"]
        with (Path(temp) / "process.log").open("w+") as log:
            process = subprocess.Popen(command, cwd=temp, env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
            stopped_on_marker = False
            try:
                deadline = time.monotonic() + 180
                while process.poll() is None:
                    if not native_capture and marker.is_file() and marker.read_text() == "complete\n":
                        stopped_on_marker = True
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"phantom_d887 timed out for {rom}")
                    time.sleep(0.02)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            log.seek(0)
            error_log = log.read()
        if (not marker.is_file() or marker.read_text() != "complete\n"
                or not out.is_file()
                or (not stopped_on_marker and process.returncode != 0)):
            raise RuntimeError(f"phantom_d887 incomplete: exit={process.returncode}\n{error_log[-3000:]}")
        text = out.read_text()
        engine = ""
        if env.get("PENTA_PHANTOM_ENGINE_TRACE"):
            engine = Path(env["PENTA_PHANTOM_ENGINE_TRACE"]).read_text()
    if rom.read_bytes() != data:
        raise ValueError("ROM changed during replay")
    metrics = parse_probe_metrics(text)
    if metrics.get("transitions", -1) < 0:
        raise RuntimeError("missing gameplay/transition receipt")
    return {"transitions": metrics["transitions"], "metrics": metrics, "raw": text,
            "engine": engine, "elapsed_seconds": time.monotonic() - started,
            "audio_options": audio_options}


def identity(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--baseline-rom", type=Path, default=PROJECT_ROOT / "rom/Penta Dragon (J).gb")
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--tolerance", type=float, default=1.5)
    parser.add_argument("--rebaseline", action="store_true", help="compatibility flag; baselines are always fresh")
    parser.add_argument("--raw-output-dir", type=Path)
    args = parser.parse_args()
    if args.raw_output_dir is None:
        (PROJECT_ROOT / "tmp").mkdir(exist_ok=True)
        args.raw_output_dir = Path(tempfile.mkdtemp(prefix="phantom-sound-", dir=PROJECT_ROOT / "tmp"))
    else:
        args.raw_output_dir.mkdir(parents=True, exist_ok=False)
    # Never reuse the old mtime/size-only baseline cache. Resolve the exact
    # guarded binary and linked core without launching an emulator.
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from mgba_singleflight import resolve_binary
    binary = resolve_binary("qt").resolve()
    linked = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=True).stdout
    libraries = [Path(line.split("=>", 1)[1].strip().split()[0]) for line in linked.splitlines()
                 if "libmgba.so" in line and "=>" in line]
    if len(libraries) != 1 or not libraries[0].is_file():
        raise RuntimeError("cannot resolve the active libmgba identity")
    bound_paths = [args.rom, args.baseline_rom, PROBE, Path(__file__),
                   Path(__file__).with_name("sound_command_oracle.py"), MGBA_QT,
                   PROJECT_ROOT / "scripts/mgba_singleflight.py", binary, libraries[0]]
    before = [identity(path) for path in bound_paths]
    records, audio_options = {}, {}
    for name, rom in (("baseline", args.baseline_rom), ("candidate", args.rom)):
        print(f"Measuring fresh {name}: {rom}", flush=True)
        result = run_d887(str(rom), args.frames, engine_trace=True)
        (args.raw_output_dir / f"{name}.txt").write_text(result["raw"])
        audio_options[name] = result["audio_options"]
        (args.raw_output_dir / f"{name}.engine.tsv").write_text(result["engine"])
        records[name] = inspect_commands(result["raw"], result["engine"], result["metrics"],
                                         args.frames, bool(rom.read_bytes()[0x143] & 0x80))
        print(json.dumps(records[name]), flush=True)
    if before != [identity(path) for path in bound_paths]:
        raise RuntimeError("bound ROM/tool/core changed during verification")
    receipt = compare_commands(records["baseline"], records["candidate"], args.tolerance)
    receipt.update(identities=before, baseline_reused=False,
                   audio_options=audio_options)
    (args.raw_output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
