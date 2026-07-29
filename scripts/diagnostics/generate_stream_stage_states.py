#!/usr/bin/env python3
"""Generate ROM-matched mGBA states for livestream Stages 2–7."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = ROOT / "tmp/palette_session/states"
PROBE = Path(__file__).with_name("probe_stage_integrity.lua")
TARGETS = tuple(range(1, 7))


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate_one(
    mgba: str,
    rom: Path,
    output: Path,
    target: int,
    timeout: float,
) -> tuple[int, str]:
    stage = target + 1
    with tempfile.TemporaryDirectory(
        prefix=f".stage{stage}-",
        dir=output,
    ) as tmp:
        tmpdir = Path(tmp)
        prefix = tmpdir / f"stage{stage}"
        state = tmpdir / f"stage{stage}.ss0"
        env = os.environ.copy()
        env.update(
            STAGE_TARGET=str(target),
            STAGE_OUT=str(prefix),
            STAGE_SHOT="1",
            STAGE_STATE_OUT=str(state),
            QT_QPA_PLATFORM="offscreen",
            SDL_AUDIODRIVER="dummy",
        )
        result = subprocess.run(
            [
                mgba,
                "--fastforward",
                "-C",
                f"savegamePath={tmpdir}",
                "-C",
                f"savestatePath={tmpdir}",
                str(rom.resolve()),
                "--script",
                str(PROBE),
            ],
            # Isolate mGBA's sidecar save/config writes. Parallel targets must
            # not contend on one ROM-adjacent .sav file.
            cwd=tmpdir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        meta_path = prefix.with_suffix(".meta")
        screenshot = prefix.with_suffix(".png")
        if result.returncode != 0:
            raise RuntimeError(f"Stage {stage}: mGBA exited {result.returncode}")
        if not state.is_file() or state.stat().st_size < 1024:
            raise RuntimeError(f"Stage {stage}: state was not created")
        if not meta_path.is_file():
            raise RuntimeError(f"Stage {stage}: metadata was not created")
        meta = meta_path.read_text()
        expected_scene = target + 2
        required = (
            f"target={target}",
            f"expected_scene={expected_scene:02X}",
            f"D880={expected_scene:02X}",
            "FFC1=01",
            f"FFBA={target:02X}",
            "unsafe_attr=0",
            "state_saved=true",
        )
        missing = [token for token in required if token not in meta]
        if missing:
            raise RuntimeError(f"Stage {stage}: bad metadata: {', '.join(missing)}")
        if not screenshot.is_file() or screenshot.stat().st_size < 100:
            raise RuntimeError(f"Stage {stage}: screenshot was not rendered")

        state.replace(output / f"stage{stage}.ss0")
        meta_path.replace(output / f"stage{stage}.meta")
        screenshot.replace(output / f"stage{stage}.png")
        return stage, meta.splitlines()[0]


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
            (output / f"stage{stage}.ss0").is_file()
            and (output / f"stage{stage}.ss0").stat().st_size >= 1024
            for stage in range(2, 8)
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
    args = parser.parse_args()

    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rom_md5 = md5(args.rom)
    if not args.force and cached(output, rom_md5):
        print(f"Stream stage states are current for {rom_md5}.")
        return 0

    # mGBA-Qt can segfault while several offscreen Qt display contexts are
    # created concurrently (observed as exit -11 on Stage 3 in the complete
    # release matrix). Six sequential captures take only about one second and
    # avoid making livestream readiness depend on a host GPU/Qt race.
    results = [
        generate_one(
            args.mgba,
            args.rom,
            output,
            target,
            args.timeout,
        )
        for target in TARGETS
    ]
    manifest = {
        "rom": str(args.rom.resolve()),
        "rom_md5": rom_md5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stages": [stage for stage, _meta in results],
    }
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(output / "manifest.json")
    for stage, meta in results:
        print(f"Stage {stage}: PASS | {meta}")
    print(f"Generated 6 ROM-matched stream states in {output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
