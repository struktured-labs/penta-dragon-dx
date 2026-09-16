"""Issue #11: interpreter aliases must not bypass exact invocation checks."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import rebuild_r534_from_original as factory


class FactoryInterpreterAliasTests(unittest.TestCase):
    def fixture(self):
        generated = ROOT / "tmp/unit-factory-alias"
        palette = ROOT / "palettes/penta_palettes_v097.yaml"
        command = factory.factory_command(generated, palette)
        command[0] = str(Path(sys.executable).resolve())
        return generated, palette, command

    def test_equivalent_binary_reaches_independent_environment_check(self):
        generated, palette, command = self.fixture()
        with self.assertRaisesRegex(ValueError, "environment policy differs"):
            factory.verify_factory_run({"command": command}, generated, palette)

    def test_alias_still_rechecks_trace_and_environment(self):
        generated, palette, command = self.fixture()
        trace = generated / "file-access.trace"
        run = {
            "command": command,
            "environment_policy": {
                "inherited_PENTA_overrides_removed": True,
                "bytecode_writes_disabled": True,
                "pycache_prefix": str(generated / "unused-bytecode"),
            },
            "file_access_trace": str(trace),
            "file_access_trace_sha256": "wrong",
        }
        with patch.object(Path, "read_bytes", return_value=b"trace"):
            with self.assertRaisesRegex(ValueError, "file-access trace changed"):
                factory.verify_factory_run(run, generated, palette)

    def test_different_interpreter_or_arguments_fail_before_trace_access(self):
        generated, palette, command = self.fixture()
        for changed in (None, [], "python", [None, *command[1:]],
                        ["/not/the/interpreter", *command[1:]],
                        ["python", *command[1:]],
                        [command[0], "--unknown", *command[1:]],
                        [*command[:-1], "--unknown"]):
            with self.subTest(command=changed), \
                 patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected trace access")):
                with self.assertRaisesRegex(ValueError, "factory invocation differs"):
                    factory.verify_factory_run({"command": changed}, generated, palette)
