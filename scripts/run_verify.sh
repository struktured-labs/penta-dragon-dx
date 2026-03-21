#!/bin/bash
# Run OG vs Remake verification with regression check
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
OG_ROM="/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J).gb"
RM_ROM="$DIR/rom/working/penta_dragon_dx.gbc"
VERIFIER="/home/struktured/projects/gb-game-verifier"
INPUT="$DIR/tmp/verify_inputs.csv"

mkdir -p "$DIR/tmp/verify_og" "$DIR/tmp/verify_rm"

# Generate inputs if needed
if [ ! -f "$INPUT" ]; then
    cat > "$INPUT" << 'EOF'
130,128
133,0
150,1
153,0
500,1
503,0
700,1
703,0
EOF
fi

# Create dump scripts with hardcoded paths
for side in og rm; do
    cat > "$DIR/tmp/dump_${side}_verify.lua" << LUAEOF
local frame=0; local inp={}
local fi=io.open("$INPUT","r")
if fi then for line in fi:lines() do local fr,keys=line:match("(%d+),(%d+)"); if fr then inp[tonumber(fr)]=tonumber(keys) end end fi:close() end
local csv=io.open("$DIR/tmp/verify_${side}/state.csv","w")
csv:write("frame,SCX,SCY,LCDC,room,form,boss,powerup,gameplay,stage,OAM0_Y,OAM0_X\n"); csv:flush()
callbacks:add("frame",function() frame=frame+1; if inp[frame] then emu:setKeys(inp[frame]) end
if frame%30==0 then
csv:write(tostring(frame)..","..tostring(emu:read8(0xFF43))..","..tostring(emu:read8(0xFF42))..","..tostring(emu:read8(0xFF40))..","..tostring(emu:read8(0xFFBD))..","..tostring(emu:read8(0xFFBE))..","..tostring(emu:read8(0xFFBF))..","..tostring(emu:read8(0xFFC0))..","..tostring(emu:read8(0xFFC1))..","..tostring(emu:read8(0xFFD0))..","..tostring(emu:read8(0xFE00))..","..tostring(emu:read8(0xFE01)).."\n")
csv:flush()
end
if frame>=1800 then csv:close(); emu:quit() end end)
LUAEOF
done

# Run OG
echo "=== OG ==="
rm -f "$DIR/tmp/verify_og/state.csv"
Xvfb :97 -screen 0 640x480x24 &
XPID=$!
sleep 1
DISPLAY=:97 QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
timeout 60 mgba-qt "$OG_ROM" --script "$DIR/tmp/dump_og_verify.lua" -l 0 2>/dev/null || true
kill $XPID 2>/dev/null; wait $XPID 2>/dev/null; sleep 1

# Run Remake
echo "=== Remake ==="
rm -f "$DIR/tmp/verify_rm/state.csv"
Xvfb :97 -screen 0 640x480x24 &
XPID=$!
sleep 1
DISPLAY=:97 QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
timeout 60 mgba-qt "$RM_ROM" --script "$DIR/tmp/dump_rm_verify.lua" -l 0 2>/dev/null || true
kill $XPID 2>/dev/null; wait $XPID 2>/dev/null

# Check data exists
OG_LINES=$(wc -l < "$DIR/tmp/verify_og/state.csv" 2>/dev/null || echo 0)
RM_LINES=$(wc -l < "$DIR/tmp/verify_rm/state.csv" 2>/dev/null || echo 0)
echo "OG: $OG_LINES lines, RM: $RM_LINES lines"

if [ "$OG_LINES" -lt 10 ] || [ "$RM_LINES" -lt 10 ]; then
    echo "ERROR: insufficient data"
    exit 2
fi

# Report + regression test
echo ""
python3 "$VERIFIER/diff_report.py" "$DIR/tmp/verify_og/state.csv" "$DIR/tmp/verify_rm/state.csv"
echo ""
python3 "$VERIFIER/regression_test.py" "$DIR/tmp/verify_og/state.csv" "$DIR/tmp/verify_rm/state.csv" --threshold 90
