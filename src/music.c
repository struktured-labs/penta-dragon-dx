// Penta Dragon DX Remake - Background Music Player
//
// Replays the Level 1 GAMEPLAY BGM extracted from the original Penta Dragon ROM.
// Four music channels:
//   Ch1 (square + sweep): Melody (8-note intro, then 87-note loop)
//   Ch2 (square):         Harmony / arpeggio accompaniment
//   Ch3 (wave):           Bass/arpeggio line
//   Ch4 (noise):          Snare percussion pattern
//
// SFX interaction:
//   - sound_shoot() takes Ch1 for ~15 frames
//   - sound_player_hit() takes Ch1+Ch4 for ~60 frames
//   - sound_enemy_hit() takes Ch4 for ~15 frames
//   - sound_pickup() takes Ch2 for ~20 frames
// Music yields those channels during SFX and resumes after.

#include "music.h"
#include "music_data.h"
#include <gb/gb.h>
#include <gb/hardware.h>

// Per-channel playback state (for pitched channels)
typedef struct {
    uint8_t pos;            // Current position in note array
    uint8_t timer;          // Frames remaining for current note
    uint8_t len;            // Total events in this channel
    uint8_t needs_trigger;  // 1 = need to trigger note on next update
    uint8_t loop_start;     // Position to loop back to (0 for Ch2/Ch3)
} channel_state_t;

static channel_state_t ch1_state;
static channel_state_t ch2_state;
static channel_state_t ch3_state;

// Drum channel state (Ch4)
static uint8_t drum_pos;
static uint8_t drum_timer;

static uint8_t music_playing;

// SFX yield counters: when > 0, music skips writing to that channel
static uint8_t sfx_ch1_frames;
static uint8_t sfx_ch2_frames;
static uint8_t sfx_ch4_frames;

// ---------- Internal helpers ----------

// Wave RAM base address (0xFF30-0xFF3F, 16 bytes)
#define WAVE_RAM_ADDR 0xFF30u

static void load_wave_ram(void) {
    uint8_t i;

    NR30_REG = 0x00;  // disable wave channel before writing wave RAM
    for (i = 0; i < 16; i++) {
        *((volatile uint8_t *)((uint16_t)(WAVE_RAM_ADDR + i))) = music_wave[i];
    }
    NR30_REG = MUSIC_CH3_ONOFF;
}

static void init_channel(channel_state_t *ch, uint8_t len, uint8_t loop_start) {
    ch->pos = 0;
    ch->timer = 0;
    ch->len = len;
    ch->needs_trigger = 1;
    ch->loop_start = loop_start;
}

// Advance sequencer and optionally trigger note.
// Returns note_event_t* if a note should be triggered, NULL otherwise.
static const note_event_t *advance_channel(channel_state_t *ch,
                                            const note_event_t *data,
                                            uint8_t sfx_active) {
    uint8_t current_note;

    // Safety: if len is 0, do nothing (prevents div-by-zero / infinite loop)
    if (ch->len == 0) {
        return (const note_event_t *)0;
    }

    // Bounds-check pos in case of corruption
    if (ch->pos >= ch->len) {
        ch->pos = ch->loop_start;
    }

    // Always advance timer (keeps music in sync during SFX)
    if (ch->timer > 0) {
        ch->timer--;
    }

    if (ch->timer == 0) {
        // Save the note index we're about to play BEFORE advancing
        current_note = ch->pos;

        // Load next event duration, guarding against zero-duration events
        ch->timer = data[ch->pos].dur;
        if (ch->timer == 0) {
            ch->timer = 1;  // Floor to 1 frame to prevent infinite advance
        }
        ch->pos++;
        if (ch->pos >= ch->len) {
            ch->pos = ch->loop_start;
        }
        ch->needs_trigger = 1;

        // Don't write to hardware if SFX owns this channel
        if (sfx_active) {
            ch->needs_trigger = 0;
            return (const note_event_t *)0;
        }

        ch->needs_trigger = 0;
        return &data[current_note];
    }

    return (const note_event_t *)0;
}

// ---------- Public API ----------

void music_init(void) {
    init_channel(&ch1_state, MUSIC_CH1_LEN, MUSIC_CH1_LOOP_START);
    init_channel(&ch2_state, MUSIC_CH2_LEN, 0);
    init_channel(&ch3_state, MUSIC_CH3_LEN, 0);

    drum_pos = 0;
    drum_timer = 0;

    load_wave_ram();

    sfx_ch1_frames = 0;
    sfx_ch2_frames = 0;
    sfx_ch4_frames = 0;

    music_playing = 1;
}

void music_update(void) {
    const note_event_t *note;
    const drum_event_t *drum;

    if (!music_playing) return;

    // Decrement SFX yield counters
    if (sfx_ch1_frames > 0) sfx_ch1_frames--;
    if (sfx_ch2_frames > 0) sfx_ch2_frames--;
    if (sfx_ch4_frames > 0) sfx_ch4_frames--;

    // --- Channel 1: Melody ---
    note = advance_channel(&ch1_state, music_ch1, sfx_ch1_frames);
    if (note) {
        if (note->freq != MUSIC_REST) {
            NR10_REG = MUSIC_CH1_SWEEP;
            NR11_REG = MUSIC_CH1_DUTY;
            NR12_REG = MUSIC_CH1_ENV;
            NR13_REG = (uint8_t)(note->freq & 0xFF);
            NR14_REG = 0x80 | (uint8_t)((note->freq >> 8) & 0x07);
        } else {
            NR12_REG = 0x00;
            NR14_REG = 0x80;
        }
    }

    // --- Channel 2: Harmony ---
    note = advance_channel(&ch2_state, music_ch2, sfx_ch2_frames);
    if (note) {
        if (note->freq != MUSIC_REST) {
            NR21_REG = MUSIC_CH2_DUTY;
            NR22_REG = MUSIC_CH2_ENV;
            NR23_REG = (uint8_t)(note->freq & 0xFF);
            NR24_REG = 0x80 | (uint8_t)((note->freq >> 8) & 0x07);
        } else {
            NR22_REG = 0x00;
            NR24_REG = 0x80;
        }
    }

    // --- Channel 3: Bass (wave) ---
    note = advance_channel(&ch3_state, music_ch3, 0);
    if (note) {
        if (note->freq != MUSIC_REST) {
            NR30_REG = MUSIC_CH3_ONOFF;
            NR31_REG = 0x00;
            NR32_REG = MUSIC_CH3_VOL;
            NR33_REG = (uint8_t)(note->freq & 0xFF);
            NR34_REG = 0x80 | (uint8_t)((note->freq >> 8) & 0x07);
        } else {
            NR30_REG = 0x00;
        }
    }

    // --- Channel 4: Drums (noise) ---
    // Always advance timer
    if (drum_timer > 0) {
        drum_timer--;
    }

    if (drum_timer == 0) {
        // Bounds-check drum_pos
        if (drum_pos >= MUSIC_DRUM_LEN) {
            drum_pos = 0;
        }

        drum = &music_drums[drum_pos];
        drum_timer = drum->dur;
        if (drum_timer == 0) {
            drum_timer = 1;  // Floor to 1 frame to prevent infinite advance
        }

        drum_pos++;
        if (drum_pos >= MUSIC_DRUM_LEN) {
            drum_pos = 0;
        }

        // Only write to hardware if SFX isn't using Ch4
        if (sfx_ch4_frames == 0) {
            NR41_REG = 0x00;
            NR42_REG = drum->nr42;
            NR43_REG = drum->nr43;
            NR44_REG = 0x80;  // trigger
        }
    }
}

void music_pause(void) {
    music_playing = 0;

    NR12_REG = 0x00;  NR14_REG = 0x80;  // Ch1 off
    NR22_REG = 0x00;  NR24_REG = 0x80;  // Ch2 off
    NR30_REG = 0x00;                     // Ch3 off
    NR42_REG = 0x00;  NR44_REG = 0x80;  // Ch4 off
}

void music_resume(void) {
    if (!music_playing) {
        music_playing = 1;
        load_wave_ram();
        ch1_state.needs_trigger = 1;
        ch2_state.needs_trigger = 1;
        ch3_state.needs_trigger = 1;
    }
}

uint8_t music_is_playing(void) {
    return music_playing;
}

void music_sfx_ch1(uint8_t frames) {
    sfx_ch1_frames = frames;
    ch1_state.needs_trigger = 1;
}

void music_sfx_ch2(uint8_t frames) {
    sfx_ch2_frames = frames;
    ch2_state.needs_trigger = 1;
}

void music_sfx_ch4(uint8_t frames) {
    sfx_ch4_frames = frames;
}
