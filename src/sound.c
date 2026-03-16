// Penta Dragon DX Remake — Sound Effects
//
// Uses Game Boy sound hardware directly via NRxx registers.
// Channel allocation:
//   Channel 1 (square + sweep): shoot, player_hit
//   Channel 2 (square):         pickup arpeggio
//   Channel 4 (noise):          enemy_hit
//   Channel 3 (wave):           reserved for future music

#include "sound.h"
#include <gb/gb.h>
#include <gb/hardware.h>

// --- Note frequency table (GB format: 2048 - 131072/freq) ---
// Subset of useful notes for SFX. Values are 11-bit GB frequency codes.
#define NOTE_C4   1046U
#define NOTE_D4   1102U
#define NOTE_E4   1155U
#define NOTE_F4   1205U
#define NOTE_G4   1253U
#define NOTE_A4   1297U
#define NOTE_B4   1339U
#define NOTE_C5   1379U
#define NOTE_D5   1417U
#define NOTE_E5   1452U
#define NOTE_F5   1486U
#define NOTE_G5   1517U
#define NOTE_A5   1546U
#define NOTE_B5   1575U
#define NOTE_C6   1602U

// Helper to build an envelope byte without overflow warnings
#define SFX_ENV(vol, dir, len) ((uint8_t)(((vol) << 4) | (dir) | (len)))

// Pickup arpeggio state machine
static uint8_t pickup_phase;     // 0 = idle, 1-3 = note phases
static uint8_t pickup_timer;     // frames remaining in current phase

// ---------- Initialization ----------

void sound_init(void) {
    // Turn on the sound hardware (bit 7 of NR52)
    NR52_REG = AUDENA_ON;

    // Master volume: max on both left and right (7 = max)
    NR50_REG = AUDVOL_VOL_LEFT(7) | AUDVOL_VOL_RIGHT(7);

    // Route all 4 channels to both speakers
    NR51_REG = 0xFF;

    // Reset pickup state
    pickup_phase = 0;
    pickup_timer = 0;
}

// ---------- Sound Effects ----------

void sound_shoot(void) {
    // Channel 1: fast downward sweep — classic laser/pew sound
    //
    // NR10: Sweep period=2, subtract mode, shift=4
    //   -> frequency decreases rapidly over ~2 sweep steps
    NR10_REG = AUD1SWEEP_TIME(2) | AUD1SWEEP_DOWN | AUD1SWEEP_LENGTH(4);

    // NR11: 25% duty cycle (thin/sharp), no length counter
    NR11_REG = AUDLEN_DUTY_25;

    // NR12: Initial volume 12 (of 15), decrease, step=3
    //   -> sound fades out over ~3 envelope steps
    NR12_REG = SFX_ENV(12, AUDENV_DOWN, 3);

    // NR13/NR14: Start frequency ~1600 (high pitch), trigger
    NR13_REG = NOTE_C6 & 0xFF;
    NR14_REG = AUDHIGH_RESTART | ((NOTE_C6 >> 8) & 0x07);
}

void sound_enemy_hit(void) {
    // Channel 4: short noise burst — impact/crunch
    //
    // NR41: Length counter (not used, continuous mode)
    NR41_REG = AUDLEN_LENGTH(1);

    // NR42: Initial volume 15 (max), decrease, step=2
    //   -> fast decay for a sharp hit sound
    NR42_REG = SFX_ENV(15, AUDENV_DOWN, 2);

    // NR43: Polynomial counter
    //   Shift=3, 15-bit mode, divider=1
    //   -> medium-pitched noise, not too harsh
    NR43_REG = (3 << 4) | AUD4POLY_WIDTH_15BIT | 1;

    // NR44: Trigger, continuous (no length limit)
    NR44_REG = AUDHIGH_RESTART;
}

void sound_player_hit(void) {
    // Channel 1: descending tone — "ow" / damage feedback
    //
    // NR10: Sweep period=3, subtract mode, shift=2
    //   -> pitch drops noticeably over time
    NR10_REG = AUD1SWEEP_TIME(3) | AUD1SWEEP_DOWN | AUD1SWEEP_LENGTH(2);

    // NR11: 50% duty cycle (fuller sound), no length
    NR11_REG = AUDLEN_DUTY_50;

    // NR12: Volume 15, decrease, step=4
    //   -> slower fade than shoot, sustains longer for "ouch" feel
    NR12_REG = SFX_ENV(15, AUDENV_DOWN, 4);

    // NR13/NR14: Start at ~A4 (medium pitch), trigger
    NR13_REG = NOTE_A4 & 0xFF;
    NR14_REG = AUDHIGH_RESTART | ((NOTE_A4 >> 8) & 0x07);
}

void sound_pickup(void) {
    // Start the 3-note ascending arpeggio on channel 2.
    // The actual note progression is driven by sound_update()
    // called each frame from the main loop.
    pickup_phase = 1;
    pickup_timer = 0;  // will trigger first note immediately in sound_update

    // Play the first note right away
    // Note 1: E5
    NR21_REG = AUDLEN_DUTY_50;
    NR22_REG = SFX_ENV(12, AUDENV_DOWN, 5);
    NR23_REG = NOTE_E5 & 0xFF;
    NR24_REG = AUDHIGH_RESTART | ((NOTE_E5 >> 8) & 0x07);

    pickup_timer = 6;  // hold for 6 frames (~100ms at 60fps)
}

// ---------- Per-frame update ----------

void sound_update(void) {
    if (pickup_phase == 0) {
        return;
    }

    if (pickup_timer > 0) {
        pickup_timer--;
        return;
    }

    // Timer expired — advance to next note
    pickup_phase++;

    if (pickup_phase == 2) {
        // Note 2: A5 (ascending)
        NR21_REG = AUDLEN_DUTY_50;
        NR22_REG = SFX_ENV(12, AUDENV_DOWN, 5);
        NR23_REG = NOTE_A5 & 0xFF;
        NR24_REG = AUDHIGH_RESTART | ((NOTE_A5 >> 8) & 0x07);
        pickup_timer = 6;
    } else if (pickup_phase == 3) {
        // Note 3: C6 (highest, resolve)
        NR21_REG = AUDLEN_DUTY_75;
        NR22_REG = SFX_ENV(14, AUDENV_DOWN, 4);
        NR23_REG = NOTE_C6 & 0xFF;
        NR24_REG = AUDHIGH_RESTART | ((NOTE_C6 >> 8) & 0x07);
        pickup_timer = 8;
    } else {
        // Done — arpeggio complete
        pickup_phase = 0;
        pickup_timer = 0;
    }
}
