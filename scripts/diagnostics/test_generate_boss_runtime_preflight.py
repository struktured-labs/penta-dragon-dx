#!/usr/bin/env python3
"""#32 negative controls for the boss-state generator runtime preflight.

No emulator is launched: the snapshot is mocked except for the optional
read-only ``ldd`` identity check of the real guard-resolved runtime.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import generate_stream_boss_states as gen  # noqa: E402
import runtime_tools  # noqa: E402

GOOD = "20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf"


def snapshot(sha: str) -> dict:
    lib = {"path": "/x/libmgba.so.0.11.0", "size": 1, "sha256": sha}
    other = {"path": "/x/libc.so.6", "size": 1, "sha256": "0" * 64}
    return {mode: {"binary": {}, "libraries": [other, lib]} for mode in ("qt", "headless")}


class Preflight(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.dir = Path(tempfile.mkdtemp(prefix="boss-preflight-", dir=ROOT / "tmp"))
        self.cgb = self.dir / "cgb.gb"
        self.dmg = self.dir / "dmg.gb"
        rom = bytearray(0x8000)
        rom[0x143] = 0x80
        self.cgb.write_bytes(bytes(rom))
        rom[0x143] = 0x00
        self.dmg.write_bytes(bytes(rom))
        self.wrapper = str(ROOT / "scripts/mgba-qt-singleflight")

    def tearDown(self):
        for path in sorted(self.dir.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.dir.rmdir()

    def test_broken_library_rejected_before_any_capture(self):
        broken = snapshot(runtime_tools.BROKEN_CGB_LATCH_LIBRARY)
        argv = ["gen", str(self.cgb), "--output", str(self.dir / "out"), "--target", "4"]
        with patch.object(gen, "emulator_runtime_snapshot", return_value=broken), \
             patch.object(gen, "generate_safe_stage1", side_effect=AssertionError("launched")), \
             patch.object(gen, "recapture_from_fixtures", side_effect=AssertionError("launched")), \
             patch.object(sys, "argv", argv):
            self.assertEqual(gen.main(), 2)
        self.assertFalse((self.dir / "out").exists(), "no output before preflight")

    def test_cache_reuse_is_also_gated(self):
        out = self.dir / "cache"
        out.mkdir()
        (out / "manifest.json").write_text(json.dumps({"rom_md5": gen.md5(self.cgb)}))
        broken = snapshot(runtime_tools.BROKEN_CGB_LATCH_LIBRARY)
        with patch.object(gen, "emulator_runtime_snapshot", return_value=broken), \
             patch.object(sys, "argv", ["gen", str(self.cgb), "--output", str(out)]):
            self.assertEqual(gen.main(), 2)

    def test_corrected_library_fingerprinted(self):
        with patch.object(gen, "emulator_runtime_snapshot", return_value=snapshot(GOOD)):
            runtime = gen.cgb_runtime_preflight(self.cgb, self.wrapper)
        self.assertEqual(runtime, [{"mode": "headless", "sha256": GOOD},
                                   {"mode": "qt", "sha256": GOOD}])

    def test_dmg_stock_control_exempt(self):
        with patch.object(gen, "emulator_runtime_snapshot", side_effect=AssertionError):
            self.assertIsNone(gen.cgb_runtime_preflight(self.dmg, "/usr/bin/anything"))

    def test_unguarded_binary_refused(self):
        with patch.object(gen, "emulator_runtime_snapshot", return_value=snapshot(GOOD)):
            with self.assertRaisesRegex(RuntimeError, "single-flight"):
                gen.cgb_runtime_preflight(self.cgb, "/usr/local/bin/mgba-qt")

    def test_cache_invalidated_by_runtime_change(self):
        out = self.dir / "c2"
        out.mkdir()
        for target, name in enumerate(gen.BOSS_NAMES):
            (out / f"boss{target}_{name}.ss0").write_bytes(b"x" * 1024)
        md5 = gen.md5(self.cgb)
        runtime = gen.runtime_fingerprint(snapshot(GOOD))
        (out / "manifest.json").write_text(json.dumps({"rom_md5": md5}))
        self.assertTrue(gen.cached(out, md5))            # DMG/legacy semantics
        self.assertFalse(gen.cached(out, md5, runtime))  # unstamped legacy cache
        gen.stamp_runtime(out, md5, runtime)
        self.assertTrue(gen.cached(out, md5, runtime))
        other = gen.runtime_fingerprint(snapshot("1" * 64))
        self.assertFalse(gen.cached(out, md5, other))
        gen.stamp_runtime(out, "not-this-rom", other)    # foreign ROM: no stamp
        self.assertTrue(gen.cached(out, md5, runtime))

    @unittest.skipUnless(
        os.environ.get("LD_LIBRARY_PATH", "").endswith("tmp/mgba-cgb-latches-r454/build"),
        "corrected runtime not selected")
    def test_real_guard_runtime_is_corrected(self):
        runtime = gen.cgb_runtime_preflight(self.cgb, self.wrapper)
        self.assertTrue(runtime and all(item["sha256"] == GOOD for item in runtime))


if __name__ == "__main__":
    unittest.main()
