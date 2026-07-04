// Tiny 2-voice music sequencer: CH2 pulse melody + CH3 wave bass.
// Placeholder engine until hUGEDriver + cowir-music's composed tracks land.
#ifndef QUINTRA_AUDIO_MUSIC_H
#define QUINTRA_AUDIO_MUSIC_H

#include "core/types.h"

void music_play_caverns(void);
void music_play_boss(void);
void music_stop(void);
void music_tick(void);        // call once per frame

#endif
