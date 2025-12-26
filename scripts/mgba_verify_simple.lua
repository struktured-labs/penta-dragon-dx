
            local frame = 0
            callbacks:add("frame", function()
                frame = frame + 1
                if frame > 300 then 
                    console:log("SUCCESS")
                    emu:exit() 
                end
            end)
            