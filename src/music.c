// Penta Dragon DX Remake - Background Music Player
//
// Replays the Level 1 BGM extracted from the original Penta Dragon ROM.
// Three music channels:
//   Ch1 (square + sweep): Melody
//   Ch2 (square):         Harmony / arpeggio accompaniment
//   Ch3 (wave):           Bass line
//
// Channel 4 (noise) is reserved for SFX (enemy_hit).
// When an SFX triggers on Ch1 or Ch2, music yields that channel.
//
// The music data is stored as note_event_t arrays (freq + duration pairs)
// that loop seamlessly.

#include "music.h"
#include "music_data.h"
#include <gb/gb.h>
#include <gb/hardware.h>

// Per-channel playback state
typedef struct {
    uint8_t pos;            // Current position in note array
    uint8_t timer;          // Frames remaining for current note
    uint8_t len;            // Total events in this channel
    uint8_t needs_trigger;  // 1 = need to trigger note on next update
} channel_state_t;

static channel_state_t ch1_state;
static channel_state_t ch2_state;
static channel_state_t ch3_state;

static uint8_t music_playing;

// SFX yield counters: when > 0, music skips writing to that channel
static uint8_t sfx_ch1_frames;   // Ch1 owned by SFX (shoot, player_hit)
static uint8_t sfx_ch2_frames;   // Ch2 owned by SFX (pickup arpeggio)

// ---------- Internal helpers ----------

static void load_wave_ram(void) {
    uint8_t i;

    // Must disable wave channel before writing wave RAM
    NR30_REG = 0x00;

    // Write 16 bytes to wave RAM (0xFF30-0xFF3F)
    for (i = 0; i < 16; i++) {
        *((volatile uint8_t *)(0xFF30 + i)) = music_wave[i];
    }

    // Re-enable wave channel
    NR30_REG = MUSIC_CH3_ONOFF;
}

static void init_channel(channel_state_t *ch, uint8_t len) {
    ch->pos = 0;
    ch->timer = 0;
    ch->len = len;
    ch->needs_trigger = 1;
}

// Update a single channel's sequencer (advance timer, load next note)
// Returns the note_event_t for the current note, or NULL if channel
// is being yielded to SFX.
static const note_event_t *advance_channel(channel_state_t *ch,
                                            const note_event_t *data,
                                            uint8_t sfx_frames) {
    const note_event_t *note;

    // Always advance the sequencer timer, even during SFX
    // This keeps the music in sync when the SFX ends
    if (ch->timer > 0) {
        ch->timer--;
    }

    if (ch->timer == 0) {
        // Load next note event
        note = &data[ch->pos];
        ch->timer = note->dur;

        ch->pos++;
        if (ch->pos >= ch->len) {
            ch->pos = 0;
        }
        ch->needs_trigger = 1;
    }

    // If SFX is active on this channel, don't write registers
    if (sfx_frames > 0) {
        return (const note_event_t *)0;
    }

    if (ch->needs_trigger) {
        ch->needs_trigger = 0;
        // Return the current note (the one we just loaded or the current one)
        return &data[(ch->pos > 0) ? ch->pos - 1 : ch->len - 1];
    }

    return (const note_event_t *)0;
}

// ---------- Public API ----------

void music_init(void) {
    init_channel(&ch1_state, MUSIC_CH1_LEN);
    init_channel(&ch2_state, MUSIC_CH2_LEN);
    init_channel(&ch3_state, MUSIC_CH3_LEN);

    load_wave_ram();

    sfx_ch1_frames = 0;
    sfx_ch2_frames = 0;

    music_playing = 1;
}

void music_update(void) {
    const note_event_t *note;

    if (!music_playing) return;

    // Decrement SFX yield counters
    if (sfx_ch1_frames > 0) sfx_ch1_frames--;
    if (sfx_ch2_frames > 0) sfx_ch2_frames--;

    // --- Channel 1: Melody (square + sweep) ---
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

    // --- Channel 2: Harmony (square) ---
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

    // --- Channel 3: Bass (wave) --- (no SFX uses Ch3)
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
}

void music_pause(void) {
    music_playing = 0;

    // Silence all music channels
    NR12_REG = 0x00;
    NR14_REG = 0x80;
    NR22_REG = 0x00;
    NR24_REG = 0x80;
    NR30_REG = 0x00;
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
