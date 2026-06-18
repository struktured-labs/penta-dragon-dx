-- iter 23 probe: spider miniboss OAM forensics.
--
-- Reads Sara slot 0+1 attr bytes from both shadow OAM buffers (0xC003/07 and
-- 0xC103/07) AND real OAM (0xFE03/07) at multiple frames during the spider
-- fight. Reads control vars too (FFCB DMA selector, FFBE/FFBF state, D880
-- scene).
--
-- Run:
--   QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy timeout 20 xvfb-run -a \
--     mgba-qt rom/working/penta_dragon_dx_teleport.gb \
--     -t save_states_for_claude/level1_sara_w_spier_miniboss.ss0 \
--     --script scripts/diagnostics/probe_spider_oam_state.lua -l 0
--   cat /tmp/spider_shadow.log
--
-- Findings (iter 23, 2026-06-18 against teleport.gb):
--
--   f=30  D880=0x0B FFBF=2 FFBE=0 FFCB=0x01
--   f=60  D880=0x0B FFBF=2 FFBE=0 FFCB=0x01
--   f=90  ...same...
--   slot0 tile=0x24 FE03=0x01 C003=0x01 C103=0x01
--   slot1 tile=0x25 FE07=0x01 C007=0x01 C107=0x01
--
-- Conclusion: pal 1 is present in BOTH shadow buffers AND real OAM at every
-- sampled frame. The colorize chain's shadow_main routine should write pal 2
-- to Sara slots (FFBE=0 → D=2 → sara_palette branch writes A=D), but those
-- writes get clobbered (pal 1) before our probe reads them. Two equivalent
-- ways for this to happen:
--
--   1. The game's main-loop OAM-build code writes pal 1 to shadow OAM
--      faster than the VBlank colorize re-writes it (the "write-rate
--      DMA-race" pattern from docs/audit/oam_read_timing.md and iter 12).
--   2. The game's OAM-build code targets BOTH shadow buffers (or a third
--      mechanism altogether), so even the alternating buffer trick can't
--      escape.
--
-- Identifying the specific writer requires CPU PC access at the moment of
-- the corrupting write — see docs/mgba_lua_api_capabilities.md (PC is not
-- exposed via headless Lua) and scripts/diagnostics/scan_sara_attr_writers.py
-- (the writer doesn't use a fixed-address pattern that a static scan finds).
--
-- Next step for someone with mgba's GDB stub or interactive debugger:
-- breakpoint on write to 0xC003 in this save state, observe HL/A/PC.

local LOG = io.open("/tmp/spider_shadow.log", "w")
local function log(m) if LOG then LOG:write(m.."\n"); LOG:flush() end end
local f = 0
callbacks:add("frame", function()
  f = f + 1
  if f == 30 or f == 60 or f == 90 or f == 120 or f == 180 then
    local fe03 = emu:read8(0xFE03)
    local fe07 = emu:read8(0xFE07)
    local c003 = emu:read8(0xC003)
    local c007 = emu:read8(0xC007)
    local c103 = emu:read8(0xC103)
    local c107 = emu:read8(0xC107)
    local ffcb = emu:read8(0xFFCB)
    local ffbf = emu:read8(0xFFBF)
    local ffbe = emu:read8(0xFFBE)
    local d880 = emu:read8(0xD880)
    local t0 = emu:read8(0xFE02)
    local t1 = emu:read8(0xFE06)
    log(string.format(
      "f=%d D880=0x%02X FFBF=%d FFBE=%d FFCB=0x%02X | s0(tile=0x%02X FE03=0x%02X C003=0x%02X C103=0x%02X) | s1(tile=0x%02X FE07=0x%02X C007=0x%02X C107=0x%02X)",
      f, d880, ffbf, ffbe, ffcb,
      t0, fe03, c003, c103,
      t1, fe07, c007, c107))
  end
  if f >= 200 then emu:stop() end
end)
