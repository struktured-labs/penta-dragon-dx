#!/usr/bin/env python3
"""Keep release screenshot inputs aligned with the authoritative gates."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_release_bundle.py"


def load_bundle_module():
    spec = importlib.util.spec_from_file_location("build_release_bundle", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseBundleScreenshotContractTests(unittest.TestCase):
    def test_title_screenshot_matches_current_mgba_gate_output(self) -> None:
        module = load_bundle_module()
        self.assertEqual(
            module.SCREENSHOT_SPECS[0],
            (
                "01_title_opening.png",
                "title-cursor/title-cursor.opening.png",
            ),
        )


if __name__ == "__main__":
    unittest.main()
