// Audio — Phase 3 stub. Phase 11 will port the GB music engine from
// the archived Penta-DX project (or replace with hUGEDriver).
#ifndef QUINTRA_AUDIO_H
#define QUINTRA_AUDIO_H

#include "core/types.h"

void audio_init(void);
void audio_tick(void);

// SFX hooks (Phase 5+)
void sfx_play(u8 sfx_id);

#endif
