#!/usr/bin/env bash
# Iter 270: quick regression harness health report. Summarizes:
# - byte-verifier check count (teleport + v3.01)
# - YAML test count
# - fresh-boot expectation count
# - hook test list size
# - savestate file count
#
# Runs in ~5s, no mGBA invocations. Use to quickly answer "how healthy
# is the test infrastructure right now?"

cd "$(git rev-parse --show-toplevel)" || exit 1

echo "=== Penta Dragon DX regression harness status ==="
echo

echo "ROM-byte checks:"
T_PASS=$(uv run python scripts/diagnostics/verify_colorizer_bytes.py \
    --rom rom/working/penta_dragon_dx_teleport.gb 2>&1 | grep -c "PASS")
V_PASS=$(uv run python scripts/diagnostics/verify_colorizer_bytes.py \
    --rom rom/working/penta_dragon_dx_v301.gb 2>&1 | grep -c "PASS")
echo "  teleport.gb: $T_PASS"
echo "  v3.01.gb:    $V_PASS"

echo
echo "YAML test definitions:"
YAML_TOTAL=$(grep -cE '^  - name: ' tests/color_regression_tests.yaml)
HOOK_TESTS=$(awk '/TESTS=\(/{in_t=1; next} /^\)/{in_t=0} in_t && /^  [a-z]/' scripts/hooks/pre-commit | wc -l)
EXCLUDED=$((YAML_TOTAL - HOOK_TESTS))
echo "  total in YAML: $YAML_TOTAL"
echo "  in hook list:  $HOOK_TESTS"
if [ "$EXCLUDED" -gt 0 ]; then
  echo "  excluded:      $EXCLUDED (intentional — see verify_hook_tests_exist.py)"
fi

echo
echo "Fresh-boot expectations:"
PHASE_CRAM=$(grep -cE '^\s+\("[BO][BG]P[0-9]\.' scripts/diagnostics/test_fresh_boot.py)
PHASE_PIX=$(grep -cE '"[0-9A-Fa-f]{6}".*min_pixels?|EXPECTED.*\[' scripts/diagnostics/test_fresh_boot.py)
echo "  CRAM checks:   $PHASE_CRAM"
echo "  pixel checks:  ~$PHASE_PIX (rough — includes per-phase)"

echo
echo "Savestate files:"
SS_COUNT=$(ls save_states_for_claude/*.ss0 2>/dev/null | wc -l)
SS_USED=$(grep -oE 'savestate: "[^"]+"' tests/color_regression_tests.yaml | sort -u | wc -l)
echo "  on disk:    $SS_COUNT"
echo "  YAML uses:  $SS_USED unique"

echo
echo "Hook verifier:"
uv run python scripts/diagnostics/verify_hook_tests_exist.py 2>&1 | head -2
