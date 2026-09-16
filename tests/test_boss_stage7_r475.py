"""The combined r475 ROM is the exact disjoint union of r462 and r467."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import compose_boss_stage7_r475 as combined
from arena_palette_storage import arena_palette_table


EXPECTED_SHA256 = (
    "59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f"
)


class BossStage7R475(unittest.TestCase):
    def test_r534_lineage_rebuilds_without_executing_scratch_code(self):
        # Deny scratch Python reads, including cached bytecode, before importing
        # the chain. ROM inputs may remain in tmp/, but executable build inputs
        # must survive a scratch cleanup and enter the release fingerprint.
        program = r'''
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
scratch = root / "tmp"
def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
        if path.is_relative_to(scratch) and path.suffix in {".py", ".pyc"}:
            raise RuntimeError(f"build executed scratch source: {path}")
sys.addaudithook(audit)
sys.path[:0] = [str(root / "scripts/diagnostics"), str(root / "scripts")]
import compose_boss_stage7_r475 as r475
import compose_stage4_cache_key_r534 as r534
from suite_contract import source_paths
source = r475.BASE.read_bytes()
middle, _ = r475.build(source)
result, _ = r534.build(middle)
again, _ = r534.build(r475.build(source)[0])
assert result == again
build_sources = {Path(r475.pure_six.__file__).resolve(), Path(r475.stage7.__file__).resolve()}
assert build_sources <= set(source_paths())
assert all(path.parent == root / "scripts/diagnostics" for path in build_sources)
print(json.dumps({"r475": hashlib.sha256(middle).hexdigest(),
                  "r534": hashlib.sha256(result).hexdigest()}))
'''
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", program, str(ROOT)],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), {
            "r475": EXPECTED_SHA256,
            "r534": "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
        })

    def test_exact_disjoint_union(self):
        if not combined.BASE.is_file():
            self.skipTest("retained exact r456d base is unavailable")
        source = combined.BASE.read_bytes()
        candidate, evidence = combined.build(source)
        self.assertEqual(hashlib.sha256(candidate).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(evidence["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(evidence["boss_banks"], [20])
        self.assertEqual(evidence["stage7_banks"], [13, 28])
        self.assertTrue(evidence["disjoint_component_footprints"])
        self.assertTrue(evidence["exact_component_union"])

        built = combined.OUT / "candidate.gb"
        self.assertTrue(built.is_file())
        self.assertEqual(built.read_bytes(), candidate)
        boss_component = ROOT / "tmp/boss-repairs-r462/candidate.gb"
        self.assertTrue(boss_component.is_file())
        boss_rom = boss_component.read_bytes()
        for target in range(9):
            self.assertEqual(
                arena_palette_table(candidate, target),
                arena_palette_table(boss_rom, target),
            )

    def test_exact_base_mutations_reject(self):
        if not combined.BASE.is_file():
            self.skipTest("retained exact r456d base is unavailable")
        source = combined.BASE.read_bytes()
        for offset in (0x14F, 13 * 0x4000, 20 * 0x4000, 28 * 0x4000):
            damaged = bytearray(source)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                combined.build(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
