// HUD — top-row strip rendered via the GBC WINDOW layer.
// Shows: hearts (HP) | blank | coin icon + 3-digit coin count
#ifndef QUINTRA_RENDER_HUD_H
#define QUINTRA_RENDER_HUD_H

#include "core/types.h"

// 6 hearts = 12 half-hearts, the run's HP cap. Every point of HP is shown,
// so a hit always visibly registers (fixes the &gt;5-heart misread).
#define HUD_MAX_HEARTS 6
#define HP_CAP        12     // half-hearts; enforced on all HP gains

void hud_init(void);          // load tiles + position window + initial draw
void hud_show(void);          // SHOW_WIN
void hud_hide(void);          // HIDE_WIN
void hud_redraw_hp(void);     // call when player.hp / hp_max changes
void hud_redraw_coins(void);  // call when player.coins changes
void hud_redraw_depth(void);  // call when run_state.room_counter changes
void hud_redraw_all(void);

#endif
