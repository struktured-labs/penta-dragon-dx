#!/usr/bin/env bash
# Probe a batch of untested savestates to see what passes Sara colorization.
set -e
cd "$(git rev-parse --show-toplevel)"
ROM="rom/working/penta_dragon_dx_teleport.gb"
LUA="scripts/diagnostics/probe_savestate_sara.lua"
STATES=(
  level1_sara_w_p_item
  level1_sara_w_dragon_powerup_item
  level1_sara_w_extra_life_item
  level1_sara_w_flash_item
  level1_sara_w_rock_item
  level1_sara_w_pulsing_bg_tiles
  level1_sara_w_healpotion1_poison_cure_slow_cure
  level1_sara_w_health2_health1_poision_cure_wild_card
  level1_sara_d_metal_ball
  level1_sara_d_soldier
  level1_sara_d_turbo_powerup_health1_item
  level1_sara_w_2_metal_ball
  level1_sara_w_2_soldier
  level1_sara_w_rock_item
  level1_sara_w_secret_stage_1_dmg
  level1_sara_w_secret_stage_1_gbc
  level1_sara_w_before_entering_secret_stage
)
printf "%-55s | %-4s | %-3s | %-4s | %-4s | %-4s | %-4s | sara slots(t/p)\n" "state" "d880" "fba" "ffbe" "ffbf" "ffc1" "df1f"
echo "----------------------------------------------------------------------------------------------"
for s in "${STATES[@]}"; do
  SS="save_states_for_claude/${s}.ss0"
  if [[ ! -f "$SS" ]]; then echo "MISSING: $SS"; continue; fi
  PROBE_OUT="/tmp/probe_${s}.json"
  rm -f "$PROBE_OUT"
  PROBE_OUT="$PROBE_OUT" QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
    timeout 30 xvfb-run -a mgba-qt "$ROM" -t "$SS" --script "$LUA" -l 0 \
    > /dev/null 2>&1 || true
  if [[ -f "$PROBE_OUT" ]]; then
    python3 -c "
import json
d = json.load(open('$PROBE_OUT'))
s0 = d['slot0']; s1 = d['slot1']; s2 = d['slot2']; s3 = d['slot3']
print(f\"{'${s}':<55s} | {d['d880']:>4d} | {d['ffba']:>3d} | {d['ffbe']:>4d} | {d['ffbf']:>4d} | {d['ffc1']:>4d} | {d['df1f']:>4d} | s0={hex(s0['tile'])}/{s0['pal']} s1={hex(s1['tile'])}/{s1['pal']} s2={hex(s2['tile'])}/{s2['pal']} s3={hex(s3['tile'])}/{s3['pal']}\")
"
  else
    echo "FAIL: $s (no output)"
  fi
done
