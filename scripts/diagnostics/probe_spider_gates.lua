-- iter 24 probe: spider miniboss colorize-chain gates.
--
-- Discovers why the spider miniboss save state shows Sara slots at pal 1
-- instead of the colorize chain's expected pal 2.
--
-- Run:
--   QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy timeout 12 xvfb-run -a \
--     mgba-qt rom/working/penta_dragon_dx_teleport.gb \
--     -t save_states_for_claude/level1_sara_w_spier_miniboss.ss0 \
--     --script scripts/diagnostics/probe_spider_gates.lua -l 0
--   cat /tmp/spider_gates.log
--
-- Findings (iter 24, 2026-06-18 against teleport.gb):
--
--   At f=1 AND f=60:
--     FFBE=0 (Sara W expected → colorizer D=2)
--     FFBF=2 (spider mode → boss palette table[1]=7 → E=7)
--     D880=0x0B (dungeon-family, < 0x0C → HW OAM recolor's gate PASSES)
--     FFC1=0x01 (colorizer enabled)
--     DF1F=0xFF (colorize-skip counter — 255 frames remaining!)
--     DF1D=0xFF (re-fire sit-out counter)
--     DF0C=0xFF (debounce counter)
--     DF20=0x00 DF21=0x00 (stack redirect target — uninit)
--     DF23=0x00 (prev-D880 cache — uninit)
--
--   slot 0: shA(y=50 x=50 t=24 f=01) shB(y=50 x=50 t=24 f=01) real(t=24 f=01)
--   slot 4: shA(y=2A x=5A t=40 f=07) shB(y=2A x=5A t=40 f=07) real(t=40 f=07)
--   slot 8: shA(y=2A x=6A t=42 f=07) shB(y=2A x=6A t=42 f=07) real(t=42 f=07)
--
--   For 120 frames: only the f=1 initial reads register as "changes".
--   shA, shB, real OAM Sara slot 0 attr STAY at 0x01.
--
-- Diagnosis:
--
--   DF1F=0xFF means the teleport routine's `DF1F gate` is active for 255
--   frames. While DF1F > 0, the teleport routine returns BEFORE issuing the
--   JP to colorize → no scene_detect, no shadow_main, no OAM DMA fires.
--
--   The hwoam_recolor that should fix the OBJ side AFTER teleport+colorize
--   passes its own gate (D880=0x0B < 0x0C), but slot 0 attr STILL ends up
--   at 0x01 (pal 1, Sara Dragon) when probed at the frame boundary, despite
--   FFBE=0 (which should set D=2 → pal 2 Sara Witch). Slot 4 (spider body
--   at tile 0x40, expected to get boss_palette E=7) DOES show pal 7 — so
--   the recolor IS running and IS reaching the boss_palette branch for the
--   spider tiles. The Sara slot 0 path through low_tiles → sara_palette is
--   the one that's wrong.
--
--   Two follow-up hypotheses to test once an interactive debugger /
--   GDB stub is available (see docs/mgba_lua_api_capabilities.md):
--
--     1. shadow_main writes to shadow OAM and then teleport's DMA fires
--        AFTER hwoam_recolor (out-of-order) — DMA's shadow→real copy
--        would clobber our pal 2 write back to pal 1.
--     2. The colorizer's low_tiles dispatch may have a subtle ordering bug
--        when entered via the hwoam_recolor tail-jump (vs the shadow_main
--        regular entry) — e.g. D is being clobbered between hwoam_recolor's
--        setup and the sara_palette branch's `LD A, D`. Verify by setting a
--        write watchpoint on 0xFE03 + a read watchpoint on 0xFFBE during
--        the recolor's execution.
--
--   Whichever is the case, the savestate was captured during a teleport
--   transition (DF1F=0xFF, DCBB=0x80 — boss HP topped up by teleport,
--   confirming this). The spider_miniboss_* tests are therefore testing
--   the BEHAVIOR DURING A TELEPORT TRANSITION, not normal gameplay. The
--   "real" spider Sara color in normal gameplay (FFBA=2, DCB8=5 spawn,
--   normal entry path with DF1F=0) may be entirely different.

local LOG = io.open("/tmp/spider_gates.log", "w")
local function log(m) if LOG then LOG:write(m.."\n"); LOG:flush() end end
local f = 0
callbacks:add("frame", function()
  f = f + 1
  if f == 1 or f == 60 then
    log(string.format("== f=%d ==", f))
    log(string.format("State: FFBE=%d FFBF=%d D880=0x%02X FFC1=0x%02X",
      emu:read8(0xFFBE), emu:read8(0xFFBF), emu:read8(0xD880), emu:read8(0xFFC1)))
    log(string.format("Teleport gates: DF1F=0x%02X DF1D=0x%02X DF0C=0x%02X",
      emu:read8(0xDF1F), emu:read8(0xDF1D), emu:read8(0xDF0C)))
    log(string.format("Scene cache: DF23=0x%02X  Stack redirect: DF20-21=0x%02X%02X",
      emu:read8(0xDF23), emu:read8(0xDF21), emu:read8(0xDF20)))
    log(string.format("Boss HP: DCBB=0x%02X  Sara HP: DCDC=0x%02X DCDD=0x%02X",
      emu:read8(0xDCBB), emu:read8(0xDCDC), emu:read8(0xDCDD)))
    -- Dump key OAM slots: shadow A vs shadow B vs real OAM
    for _, slot in ipairs({0, 4, 8}) do
      local off = slot * 4
      local sA = {emu:read8(0xC000+off), emu:read8(0xC001+off), emu:read8(0xC002+off), emu:read8(0xC003+off)}
      local sB = {emu:read8(0xC100+off), emu:read8(0xC101+off), emu:read8(0xC102+off), emu:read8(0xC103+off)}
      local rO = {emu:read8(0xFE00+off), emu:read8(0xFE01+off), emu:read8(0xFE02+off), emu:read8(0xFE03+off)}
      log(string.format("slot %02d: shA(t=%02X f=%02X) shB(t=%02X f=%02X) real(t=%02X f=%02X)",
        slot, sA[3], sA[4], sB[3], sB[4], rO[3], rO[4]))
    end
  end
  if f >= 60 then emu:stop() end
end)
