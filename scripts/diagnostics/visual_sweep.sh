#!/usr/bin/env bash
# Take settled screenshots across key scenes to verify nothing's catastrophically
# broken. Headless via xvfb-run; each shot is captured at frame 300 after load.
#
# IMPORTANT: frame 300, not 68. The teleport ROM's DF1F gate skips JP COLORIZE
# while DF1F > 0; uninitialized WRAM gives DF1F=0xFF on savestate load, which
# decrements 1/frame, so OBJ/BG palette CRAM stays at savestate values for the
# first ~255 frames after load. By frame 300 DF1F has reached 0 and cond_pal
# has run, so the screenshot reflects the real colorized state. (Real gameplay
# is not affected — DF1F naturally drains to 0 during title/menu before the
# dungeon ever loads, so end-users never see the transient. iter 53.)
cd "$(git rev-parse --show-toplevel)"
ROM="rom/working/penta_dragon_dx_teleport.gb"
OUT_DIR="/tmp/visual_sweep"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

SCENES=(
  # Sara form / dungeon baseline
  "sara_w_baseline:level1_sara_w_alone.ss0"
  "sara_d_baseline:level1_sara_d_alone.ss0"
  # Mini-boss types
  "miniboss_gargoyle:level1_sara_w_gargoyle_mini_boss.ss0"
  "miniboss_spider_d:level1_sara_d_spider_miniboss.ss0"
  # Iter 31 OBJ slot-10+ unlock proof
  "orc_slot14:level1_sara_w_orc.ss0"
  "soldier_slot12:level1_sara_w_soldier.ss0"
  "catfish:level1_sara_w_cat_fish_moth_spike_hazard_orb_item.ss0"
  # Special states
  "secret_stage_shmup:level1_sara_w_secret_stage_1_gbc.ss0"
  "spike_hazard_metallic:level1_sara_w_pulsing_bg_tiles.ss0"
)

cat > "$OUT_DIR/dump.lua" << 'LUA'
local f = 0
callbacks:add("frame", function()
  f = f + 1
  if f == 300 then
    emu:screenshot(os.getenv("SHOT_PATH"))
    emu:stop()
  end
end)
LUA

for entry in "${SCENES[@]}"; do
  label="${entry%%:*}"
  ss="${entry#*:}"
  out="$OUT_DIR/${label}.png"
  SHOT_PATH="$out" QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
    timeout 40 xvfb-run -a mgba-qt "$ROM" -t "save_states_for_claude/${ss}" \
    --script "$OUT_DIR/dump.lua" -l 0 > /dev/null 2>&1
  if [[ -s "$out" ]]; then
    size=$(stat -c%s "$out")
    echo "  [OK] $label ($size bytes) — $out"
  else
    echo "  [FAIL] $label — empty/missing"
  fi
done
echo
echo "Screenshots in $OUT_DIR — visually inspect with: ls $OUT_DIR/*.png"
