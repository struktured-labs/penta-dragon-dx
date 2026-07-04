#include <gb/gb.h>

#include "core/rng.h"
#include "input/input.h"
#include "audio/audio.h"
#include "game/loop.h"
#include "game/title.h"
#include "game/scratch.h"
#include "game/class_select.h"
#include "game/run_init.h"
#include "game/room.h"
#include "game/gameover.h"
#include "game/victory.h"
#include "game/inventory.h"

screen_id_t loop_current_screen = SCREEN_BOOT;
u16         loop_frame_counter  = 0;

// The screen table. Each screen lives in its own translation unit.
const screen_t screens[SCREEN_COUNT] = {
    [SCREEN_BOOT]         = { 0, 0, 0, 0 },
    [SCREEN_TITLE]        = { title_enter,   title_exit,   title_tick,   title_draw   },
    [SCREEN_CLASS_SELECT] = { class_select_enter, class_select_exit, class_select_tick, class_select_draw },
    [SCREEN_RUN_INIT]     = { run_init_enter,     run_init_exit,     run_init_tick,     run_init_draw     },
    [SCREEN_PROCGEN]      = { 0, 0, 0, 0 },
    [SCREEN_ROOM]         = { room_enter,         room_exit,         room_tick,         room_draw         },
    [SCREEN_REST_ROOM]    = { 0, 0, 0, 0 },
    [SCREEN_BOSS]         = { 0, 0, 0, 0 },
    [SCREEN_INVENTORY]    = { inventory_enter, inventory_exit, inventory_tick, inventory_draw },
    [SCREEN_DIALOG]       = { 0, 0, 0, 0 },
    [SCREEN_GAMEOVER]     = { gameover_enter, gameover_exit, gameover_tick, gameover_draw },
    [SCREEN_VICTORY]      = { victory_enter,  victory_exit,  victory_tick,  victory_draw  },
    [SCREEN_SCRATCH]      = { scratch_enter, scratch_exit, scratch_tick, scratch_draw },
};

void loop_init(screen_id_t start) {
    loop_current_screen = start;
    loop_frame_counter  = 0;
    if (screens[start].enter) screens[start].enter();
}

void loop_run(void) {
    screen_id_t cur = loop_current_screen;
    screen_id_t next;

    for (;;) {
        input_poll();

        if (screens[cur].tick) {
            next = screens[cur].tick(input_keys, input_pressed);
            if (next != SCREEN_SELF && next != cur) {
                if (screens[cur].exit)  screens[cur].exit();
                cur = next;
                loop_current_screen = cur;
                if (screens[cur].enter) screens[cur].enter();
            }
        }

        if (screens[cur].draw) screens[cur].draw();

        audio_tick();

        wait_vbl_done();
        loop_frame_counter++;
        // Mix a bit of the frame counter into the RNG state for entropy
        if ((loop_frame_counter & 0x3FFF) == 0) rng_next();
    }
}
