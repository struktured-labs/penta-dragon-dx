#!/usr/bin/env bash
# Compare which hook tests pass on v3.01 production vs teleport ROM.
# Useful for tracking what backports are needed to bring v3.01 to parity.
# Iter 45: parallelized via xargs -P (same pattern as scripts/hooks/pre-commit).
# Full 65-test matrix runs in ~3-5 min on a 4-core machine.
cd "$(git rev-parse --show-toplevel)"

# Pull tests from the pre-commit hook (the TESTS=(...) array).
# Allow digits in test names (iter 45 fix — earlier regex missed
# lava_stage5_override + similar names with digits).
TESTS=$(awk '/^TESTS=\(/,/^\)$/' scripts/hooks/pre-commit \
  | grep -E '^[[:space:]]+[a-z][a-z_0-9]*$' | tr -d ' ')

PROD_ROM="rom/working/penta_dragon_dx_v301.gb"
TELE_ROM="rom/working/penta_dragon_dx_teleport.gb"

results_dir="/tmp/v301_vs_teleport"
rm -rf "$results_dir"
mkdir -p "$results_dir"

NPROC=$(nproc 2>/dev/null || echo 4)
PARALLEL=$((NPROC > 4 ? 4 : NPROC))

run_one_pair() {
  local t="$1"
  for label in prod tele; do
    local rom
    case "$label" in
      prod) rom="$PROD_ROM" ;;
      tele) rom="$TELE_ROM" ;;
    esac
    if QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy xvfb-run -a \
        uv run python scripts/run_color_regression.py --rom "$rom" --test "$t" \
        > "$results_dir/${label}_${t}.log" 2>&1; then
      : > "$results_dir/${label}_${t}.ok"
    else
      : > "$results_dir/${label}_${t}.fail"
    fi
  done
}
export -f run_one_pair
export PROD_ROM TELE_ROM results_dir

printf '%s\n' $TESTS | xargs -I {} -P "$PARALLEL" \
  bash -c 'run_one_pair "$1"' _ {}

printf "%-46s | %-6s | %-6s\n" "Test" "v3.01" "teleport"
printf '%.0s-' {1..70}; echo
prod_pass=0; prod_fail=0
tele_pass=0; tele_fail=0
both_fail=()
v301_only_fail=()
for t in $TESTS; do
  [[ -e "$results_dir/prod_${t}.ok" ]] && p="PASS" || p="FAIL"
  [[ -e "$results_dir/tele_${t}.ok" ]] && r="PASS" || r="FAIL"
  printf "%-46s | %-6s | %-6s\n" "$t" "$p" "$r"
  if [[ "$p" == "PASS" ]]; then prod_pass=$((prod_pass+1)); else prod_fail=$((prod_fail+1)); fi
  if [[ "$r" == "PASS" ]]; then tele_pass=$((tele_pass+1)); else tele_fail=$((tele_fail+1)); fi
  if [[ "$p" == "FAIL" && "$r" == "FAIL" ]]; then both_fail+=("$t"); fi
  if [[ "$p" == "FAIL" && "$r" == "PASS" ]]; then v301_only_fail+=("$t"); fi
done
echo
echo "v3.01    : $prod_pass passed, $prod_fail failed"
echo "teleport : $tele_pass passed, $tele_fail failed"
echo
echo "v3.01-only failures (${#v301_only_fail[@]}, teleport-only features):"
for t in "${v301_only_fail[@]}"; do echo "  $t"; done
echo
echo "Both failing (${#both_fail[@]}, real gaps):"
for t in "${both_fail[@]}"; do echo "  $t"; done
echo
echo "Detail logs: $results_dir"
