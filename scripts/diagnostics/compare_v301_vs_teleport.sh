#!/usr/bin/env bash
# Compare which hook tests pass on v3.01 production vs teleport ROM.
# Useful for tracking what backports are needed to bring v3.01 to parity.
# NOTE: no `set -e` because we rely on test exits for the matrix; would
# bail on the first v3.01 fail otherwise.
cd "$(git rev-parse --show-toplevel)"

# Pull tests from the pre-commit hook (the TESTS=(...) array).
TESTS=$(awk '/^TESTS=\(/,/^\)$/' scripts/hooks/pre-commit \
  | grep -E '^  [a-z][a-z_]+$' | tr -d ' ')

PROD_ROM="rom/working/penta_dragon_dx_v301.gb"
TELE_ROM="rom/working/penta_dragon_dx_teleport.gb"

results_dir="/tmp/v301_vs_teleport_$$"
mkdir -p "$results_dir"

run_one() {
  local rom="$1"; local t="$2"; local label="$3"
  if QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy xvfb-run -a \
      uv run python scripts/run_color_regression.py --rom "$rom" --test "$t" \
      > "$results_dir/${label}_${t}.log" 2>&1; then
    echo "PASS"
  else
    echo "FAIL"
  fi
}

printf "%-46s | %-6s | %-6s\n" "Test" "v3.01" "teleport"
printf '%.0s-' {1..70}; echo
prod_pass=0; prod_fail=0
tele_pass=0; tele_fail=0
for t in $TESTS; do
  p_result=$(run_one "$PROD_ROM" "$t" "prod")
  t_result=$(run_one "$TELE_ROM" "$t" "tele")
  printf "%-46s | %-6s | %-6s\n" "$t" "$p_result" "$t_result"
  if [[ "$p_result" == "PASS" ]]; then prod_pass=$((prod_pass+1)); else prod_fail=$((prod_fail+1)); fi
  if [[ "$t_result" == "PASS" ]]; then tele_pass=$((tele_pass+1)); else tele_fail=$((tele_fail+1)); fi
done
echo
echo "v3.01    : $prod_pass passed, $prod_fail failed"
echo "teleport : $tele_pass passed, $tele_fail failed"
echo "Detail logs: $results_dir"
