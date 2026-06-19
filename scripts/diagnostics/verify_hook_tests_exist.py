"""Verify that every test referenced in scripts/hooks/pre-commit actually
exists in tests/color_regression_tests.yaml. Catches a common silent failure:
a hook entry survives a YAML rename or delete, and the test runner just
reports "Test 'X' not found" — the hook still passes because exit code is
nonzero but the orchestrator may not surface it cleanly.

Run from the pre-commit hook (millisecond-scale).
"""

import re
import sys
from pathlib import Path

import yaml


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent
    hook_path = repo / "scripts" / "hooks" / "pre-commit"
    yaml_path = repo / "tests" / "color_regression_tests.yaml"

    # Pull names from the TESTS=(...) array in the hook script.
    hook_lines = hook_path.read_text().splitlines()
    in_tests = False
    hook_tests: list[str] = []
    for line in hook_lines:
        if line.strip().startswith("TESTS=("):
            in_tests = True
            continue
        if in_tests and line.strip() == ")":
            break
        if in_tests:
            m = re.match(r"^\s+([a-z][a-z_0-9]*)\s*$", line)
            if m:
                hook_tests.append(m.group(1))

    # Pull names from the YAML.
    yaml_doc = yaml.safe_load(yaml_path.read_text())
    yaml_names: set[str] = set()
    # YAML structure: list of sections, each with `tests:` list. Walk
    # recursively to handle either flat or nested structures.
    def walk(node):
        if isinstance(node, dict):
            if "name" in node and "savestate" in node:
                yaml_names.add(node["name"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(yaml_doc)

    missing = [t for t in hook_tests if t not in yaml_names]
    if missing:
        print(f"  [FAIL] hook references {len(missing)} tests not present in YAML:")
        for t in missing:
            print(f"          - {t}")
        return 1
    yaml_only = sorted(yaml_names - set(hook_tests))
    print(f"  [PASS] all {len(hook_tests)} hook tests exist in YAML "
          f"({len(yaml_names)} YAML tests total)")
    if yaml_only:
        print(f"  [INFO] {len(yaml_only)} YAML test(s) intentionally excluded from hook:")
        for t in yaml_only:
            print(f"          - {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
