#ifndef __MUSIC_H__
#define __MUSIC_H__

#include <gb/gb.h>
#include <stdint.h>

// Initialize the music system and load Level 1 BGM.
// Call once after sound_init().
void music_init(void);

// Advance music playback by one frame.
// Call once per frame from the main loop.
// Automatically yields channels to SFX:
//   - Skips Ch1 writes when an SFX is using Ch1
//   - Skips Ch4 writes when an SFX is using Ch4
//   - Ch2 and Ch3 are music-only (SFX uses Ch2 for pickup only briefly)
void music_update(void);

// Pause music playback (silences all music channels).
void music_pause(void);

// Resume music playback from where it was paused.
void music_resume(void);

// Returns 1 if music is currently playing, 0 if paused/stopped.
uint8_t music_is_playing(void);

// Notify music that an SFX has taken over Ch1 (square+sweep).
// Music will yield Ch1 for the specified number of frames.
// Call this right after triggering any SFX that uses Ch1.
void music_sfx_ch1(uint8_t frames);

// Notify music that an SFX has taken over Ch2 (square).
// Music will yield Ch2 for the specified number of frames.
void music_sfx_ch2(uint8_t frames);

#endif /* __MUSIC_H__ */
