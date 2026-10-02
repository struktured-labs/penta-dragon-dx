from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/diagnostics/probe_ending_inventory_mgba.lua"


class EndingInventoryProbeContractTests(unittest.TestCase):
    def test_story_table_neutrality_requires_committed_active_guard(self) -> None:
        source = PROBE.read_text()
        self.assertIn("local table_active = scene == EXPECTED_SCENE", source)
        self.assertIn("state.d889 == 0x01 and state.dce2 == 0x00", source)
        self.assertIn(
            "local table_bad = (table_active and not table_is_neutral())",
            source,
        )


if __name__ == "__main__":
    unittest.main()
