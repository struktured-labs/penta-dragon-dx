-- Probe OBJ palette CRAM at frame 68 — what RGB does Sara actually render as?
-- Try mGBA's dedicated cgbObjPalette accessor (LCD-mode-independent).
local frame_count = 0
local OUT = os.getenv("PROBE_OUT") or "/tmp/obj_cram.json"

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == 68 then
        local accessor = emu.memory.cgbObjPalette
        if accessor == nil then
            -- Fall back to FF6A/FF6B
            emu:write8(0xFF6A, 0x80)
            local pal = {}
            for i = 1, 64 do
                pal[i] = emu:read8(0xFF6B)
            end
            local f = io.open(OUT, "w")
            f:write('{"source":"FF6A","obj_pal":[')
            for i, v in ipairs(pal) do
                if i > 1 then f:write(",") end
                f:write(tostring(v))
            end
            f:write(']}')
            f:close()
        else
            local raw = accessor:readRange(0, 64)
            local f = io.open(OUT, "w")
            f:write('{"source":"cgbObjPalette","obj_pal":[')
            for i = 1, 64 do
                if i > 1 then f:write(",") end
                f:write(tostring(raw:byte(i)))
            end
            f:write(']}')
            f:close()
        end
        emu:stop()
    end
end)
