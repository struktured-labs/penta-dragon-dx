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

    # Pull names from the YAML + their associated savestates for existence
    # verification.
    yaml_doc = yaml.safe_load(yaml_path.read_text())
    yaml_names: set[str] = set()
    yaml_savestates: dict[str, str] = {}
    # Iter 267: also track raw name occurrences to catch YAML-side
    # duplicates (the iter 250 bug was hook-side but YAML-side dupes
    # would silently merge here since yaml_names is a set).
    yaml_name_occurrences: list[str] = []
    # YAML structure: list of sections, each with `tests:` list. Walk
    # recursively to handle either flat or nested structures.
    def walk(node):
        if isinstance(node, dict):
            if "name" in node and "savestate" in node:
                yaml_names.add(node["name"])
                yaml_name_occurrences.append(node["name"])
                yaml_savestates[node["name"]] = node["savestate"]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(yaml_doc)
    # Iter 267: check YAML name uniqueness.
    from collections import Counter
    yaml_counts = Counter(yaml_name_occurrences)
    yaml_dups = [n for n, c in yaml_counts.items() if c > 1]
    if yaml_dups:
        print(f"  [FAIL] YAML has {len(yaml_dups)} duplicate test name(s):")
        for t in yaml_dups:
            print(f"          - {t} (defined {yaml_counts[t]}x)")
        return 1

    missing = [t for t in hook_tests if t not in yaml_names]
    if missing:
        print(f"  [FAIL] hook references {len(missing)} tests not present in YAML:")
        for t in missing:
            print(f"          - {t}")
        return 1
    # Iter 266: verify hook-referenced savestates exist on disk. Catches
    # a class of regression where a test's savestate file is deleted or
    # renamed but the YAML / hook reference isn't updated. Without this,
    # the test would only fail after mGBA invocation (5+ min into the hook).
    savestate_dir = repo / "save_states_for_claude"
    missing_savestates: list[tuple[str, str]] = []
    for t in hook_tests:
        ss = yaml_savestates.get(t)
        if ss and not (savestate_dir / ss).exists():
            missing_savestates.append((t, ss))
    if missing_savestates:
        print(f"  [FAIL] {len(missing_savestates)} hook test(s) reference missing savestate files:")
        for t, ss in missing_savestates:
            print(f"          - {t} -> {ss}")
        return 1
    # Iter 255: catch duplicate hook entries (iter 250 silently
    # re-added spider_miniboss_sara_w which already existed since
    # iter 32 — the existence-only check passed because the dup
    # name is still present in YAML).
    hook_counts = Counter(hook_tests)
    dups = [t for t, c in hook_counts.items() if c > 1]
    if dups:
        print(f"  [FAIL] hook has {len(dups)} duplicate test name(s):")
        for t in dups:
            print(f"          - {t} (listed {hook_counts[t]}x)")
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
