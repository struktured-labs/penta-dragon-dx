// AUTO-GENERATED - Penta Dragon Level 1 Gameplay BGM
// Extracted from original ROM via register-intercept capture
// Loop: ~1407 frames (~23.4 seconds)
// Ch1: melody (square+sweep), Ch2: harmony (square),
// Ch3: bass/arpeggio (wave), Ch4: snare percussion (noise)

#ifndef __MUSIC_DATA_H__
#define __MUSIC_DATA_H__

#include <stdint.h>

// Note event: frequency (GB 11-bit), duration in frames
typedef struct {
    uint16_t freq;   // GB frequency register value (11-bit)
    uint8_t  dur;    // Duration in frames (1-255)
} note_event_t;

// Special frequency value: rest (silence)
#define MUSIC_REST 0x0000

// Channel 1 - Melody (square + sweep)
// 8 intro notes, then 87 notes loop
#define MUSIC_CH1_LEN 95
#define MUSIC_CH1_LOOP_START 8
static const note_event_t music_ch1[MUSIC_CH1_LEN] = {
    {0x0783,   5},  //  0: C6  // intro
    {0x0759,  24},  //  1: G5  // intro
    {0x074F,  12},  //  2: F#5  // intro
    {0x0759,  17},  //  3: G5  // intro
    {0x074F,   6},  //  4: F#5  // intro
    {0x0759,  18},  //  5: G5  // intro
    {0x0721,  35},  //  6: D5  // intro
    {0x0706,  25},  //  7: C5  // intro
    {0x060B,  11},  //  8: C4  // <-- loop start
    {0x06F7,  10},  //  9: B4
    {0x060B,  12},  // 10: C4
    {0x06C4,   3},  // 11: G#4
    {0x06D6,   2},  // 12: A4
    {0x06E7,   3},  // 13: A#4
    {0x06F7,   3},  // 14: B4
    {0x0706,  44},  // 15: C5
    {0x05ED,  11},  // 16: B3
    {0x05AC,  10},  // 17: A3
    {0x05ED,  12},  // 18: B3
    {0x06B2,   2},  // 19: G4
    {0x06C4,   3},  // 20: G#4
    {0x06D6,   3},  // 21: A4
    {0x06E7,   2},  // 22: A#4
    {0x06F7,  47},  // 23: B4
    {0x060B,  33},  // 24: C4
    {0x05AC,  33},  // 25: A3
    {0x05ED,  22},  // 26: B3
    {0x060B,  33},  // 27: C4
    {0x05ED,  33},  // 28: B3
    {0x0642,  20},  // 29: D4
    {0x060B,  10},  // 30: C4
    {0x06F7,  12},  // 31: B4
    {0x060B,  10},  // 32: C4
    {0x06C4,   3},  // 33: G#4
    {0x06D6,   3},  // 34: A4
    {0x06E7,   2},  // 35: A#4
    {0x06F7,   3},  // 36: B4
    {0x0706,  44},  // 37: C5
    {0x05ED,  11},  // 38: B3
    {0x05AC,  12},  // 39: A3
    {0x05ED,  10},  // 40: B3
    {0x06B2,   3},  // 41: G4
    {0x06C4,   3},  // 42: G#4
    {0x06D6,   2},  // 43: A4
    {0x06E7,   4},  // 44: A#4
    {0x06F7,  46},  // 45: B4
    {0x060B,  33},  // 46: C4
    {0x05AC,  33},  // 47: A3
    {0x05ED,  22},  // 48: B3
    {0x060B,  33},  // 49: C4
    {0x0642,  55},  // 50: D4
    {0x060B,  11},  // 51: C4
    {0x0563,  11},  // 52: G3
    {0x05ED,  11},  // 53: B3
    {0x060B,  22},  // 54: C4
    {0x0563,  11},  // 55: G3
    {0x05ED,  11},  // 56: B3
    {0x060B,  11},  // 57: C4
    {0x0642,  11},  // 58: D4
    {0x0563,  11},  // 59: G3
    {0x0689,  11},  // 60: F4
    {0x0672,  11},  // 61: E4
    {0x0642,  11},  // 62: D4
    {0x05ED,  11},  // 63: B3
    {0x060B,  11},  // 64: C4
    {0x0642,  10},  // 65: D4
    {0x06B2,  34},  // 66: G4
    {0x060B,  33},  // 67: C4
    {0x0689,  27},  // 68: F4
    {0x0672,  33},  // 69: E4
    {0x0689,  50},  // 70: F4
    {0x060B,  11},  // 71: C4
    {0x0563,  10},  // 72: G3
    {0x05ED,  12},  // 73: B3
    {0x060B,  21},  // 74: C4
    {0x0563,  12},  // 75: G3
    {0x05ED,  10},  // 76: B3
    {0x060B,  12},  // 77: C4
    {0x0642,  10},  // 78: D4
    {0x0563,  11},  // 79: G3
    {0x0689,  12},  // 80: F4
    {0x0672,  10},  // 81: E4
    {0x0642,  12},  // 82: D4
    {0x05ED,  10},  // 83: B3
    {0x060B,  11},  // 84: C4
    {0x0642,  12},  // 85: D4
    {0x06B2,  32},  // 86: G4
    {0x060B,  33},  // 87: C4
    {0x0689,  20},  // 88: F4
    {0x0672,  10},  // 89: E4
    {0x0642,  11},  // 90: D4
    {0x0672,  12},  // 91: E4
    {0x0642,  22},  // 92: D4
    {0x060B,  10},  // 93: C4
    {0x0642,  23}  // 94: D4
};

// Channel 2 - Harmony (square)
#define MUSIC_CH2_LEN 71
static const note_event_t music_ch2[MUSIC_CH2_LEN] = {
    {0x06D6,  11},  //  0: A4
    {0x06F7,  11},  //  1: B4
    {0x0739,  55},  //  2: E5
    {0x0642,  11},  //  3: D4
    {0x06B2,  11},  //  4: G4
    {0x06D6,  11},  //  5: A4
    {0x0721,  55},  //  6: D5
    {0x060B,  33},  //  7: C4
    {0x05AC,  33},  //  8: A3
    {0x05ED,  22},  //  9: B3
    {0x0689,  33},  // 10: F4
    {0x0672,  33},  // 11: E4
    {0x06B2,  22},  // 12: G4
    {0x0672,  11},  // 13: E4
    {0x06D6,  11},  // 14: A4
    {0x06F7,  11},  // 15: B4
    {0x0739,  55},  // 16: E5
    {0x0642,  10},  // 17: D4
    {0x06B2,  12},  // 18: G4
    {0x06D6,  11},  // 19: A4
    {0x0721,  55},  // 20: D5
    {0x060B,  32},  // 21: C4
    {0x05AC,  33},  // 22: A3
    {0x05ED,  23},  // 23: B3
    {0x0689,  32},  // 24: F4
    {0x06B2,  55},  // 25: G4
    {0x060B,  11},  // 26: C4
    {0x0563,  11},  // 27: G3
    {0x05ED,  11},  // 28: B3
    {0x060B,  22},  // 29: C4
    {0x0563,  11},  // 30: G3
    {0x05ED,  11},  // 31: B3
    {0x060B,  11},  // 32: C4
    {0x0642,  12},  // 33: D4
    {0x0563,  10},  // 34: G3
    {0x0689,  11},  // 35: F4
    {0x0672,  11},  // 36: E4
    {0x0642,  11},  // 37: D4
    {0x05ED,  11},  // 38: B3
    {0x060B,  11},  // 39: C4
    {0x0642,  11},  // 40: D4
    {0x06B2,  33},  // 41: G4
    {0x060B,  33},  // 42: C4
    {0x0689,  33},  // 43: F4
    {0x060B,  33},  // 44: C4
    {0x0642,  44},  // 45: D4
    {0x060B,  11},  // 46: C4
    {0x0563,  11},  // 47: G3
    {0x05ED,  11},  // 48: B3
    {0x060B,  22},  // 49: C4
    {0x0563,  11},  // 50: G3
    {0x05ED,  11},  // 51: B3
    {0x060B,  11},  // 52: C4
    {0x0642,  11},  // 53: D4
    {0x0563,  11},  // 54: G3
    {0x0689,  11},  // 55: F4
    {0x0672,  11},  // 56: E4
    {0x0642,  11},  // 57: D4
    {0x05ED,  11},  // 58: B3
    {0x060B,  11},  // 59: C4
    {0x0642,  11},  // 60: D4
    {0x06B2,  33},  // 61: G4
    {0x060B,  33},  // 62: C4
    {0x0689,  22},  // 63: F4
    {0x0672,  11},  // 64: E4
    {0x0642,  11},  // 65: D4
    {0x0672,  11},  // 66: E4
    {0x0642,  22},  // 67: D4
    {0x060B,  11},  // 68: C4
    {0x0642,  22},  // 69: D4
    {0x0672,  11}  // 70: E4
};

// Channel 3 - Bass/arpeggio (wave)
#define MUSIC_CH3_LEN 134
static const note_event_t music_ch3[MUSIC_CH3_LEN] = {
    {0x0672,   6},  //   0: E4
    {0x05AC,  17},  //   1: A3
    {0x0672,   5},  //   2: E4
    {0x05AC,  17},  //   3: A3
    {0x0672,   5},  //   4: E4
    {0x060B,  11},  //   5: C4
    {0x05AC,   5},  //   6: A3
    {0x0672,   6},  //   7: E4
    {0x0563,  16},  //   8: G3
    {0x0642,   6},  //   9: D4
    {0x0563,  16},  //  10: G3
    {0x0642,   6},  //  11: D4
    {0x0563,  17},  //  12: G3
    {0x0642,   5},  //  13: D4
    {0x053B,  11},  //  14: F#3
    {0x0563,   5},  //  15: G3
    {0x0642,   6},  //  16: D4
    {0x060B,  16},  //  17: C4
    {0x06B2,   6},  //  18: G4
    {0x060B,   6},  //  19: C4
    {0x06B2,  16},  //  20: G4
    {0x060B,  16},  //  21: C4
    {0x06B2,   6},  //  22: G4
    {0x0672,   5},  //  23: E4
    {0x06B2,  17},  //  24: G4
    {0x060B,  11},  //  25: C4
    {0x0511,  11},  //  26: F3
    {0x060B,  11},  //  27: C4
    {0x05ED,  22},  //  28: B3
    {0x04E5,  11},  //  29: E3
    {0x05ED,  22},  //  30: B3
    {0x05AC,  16},  //  31: A3
    {0x0672,   6},  //  32: E4
    {0x05AC,  16},  //  33: A3
    {0x0672,   5},  //  34: E4
    {0x05AC,  17},  //  35: A3
    {0x0672,   6},  //  36: E4
    {0x060B,  10},  //  37: C4
    {0x05AC,   6},  //  38: A3
    {0x0672,   6},  //  39: E4
    {0x0563,  16},  //  40: G3
    {0x0642,   6},  //  41: D4
    {0x0563,  16},  //  42: G3
    {0x0642,   5},  //  43: D4
    {0x0563,  17},  //  44: G3
    {0x0642,   5},  //  45: D4
    {0x053B,  12},  //  46: F#3
    {0x0563,   5},  //  47: G3
    {0x0642,   6},  //  48: D4
    {0x060B,  16},  //  49: C4
    {0x06B2,   6},  //  50: G4
    {0x060B,   5},  //  51: C4
    {0x06B2,  16},  //  52: G4
    {0x060B,  17},  //  53: C4
    {0x06B2,   5},  //  54: G4
    {0x0672,   6},  //  55: E4
    {0x06B2,  17},  //  56: G4
    {0x060B,  10},  //  57: C4
    {0x0511,  12},  //  58: F3
    {0x060B,  10},  //  59: C4
    {0x0563,  22},  //  60: G3
    {0x060B,  11},  //  61: C4
    {0x05ED,  22},  //  62: B3
    {0x0511,  17},  //  63: F3
    {0x060B,   6},  //  64: C4
    {0x0511,  16},  //  65: F3
    {0x060B,   6},  //  66: C4
    {0x0511,  16},  //  67: F3
    {0x060B,   5},  //  68: C4
    {0x04E5,  11},  //  69: E3
    {0x0511,   6},  //  70: F3
    {0x060B,   5},  //  71: C4
    {0x0563,  17},  //  72: G3
    {0x0642,   5},  //  73: D4
    {0x0563,  17},  //  74: G3
    {0x0642,   5},  //  75: D4
    {0x0563,  17},  //  76: G3
    {0x0642,   5},  //  77: D4
    {0x053B,  11},  //  78: F#3
    {0x0563,   6},  //  79: G3
    {0x0642,   5},  //  80: D4
    {0x060B,  17},  //  81: C4
    {0x06B2,   5},  //  82: G4
    {0x060B,   6},  //  83: C4
    {0x06B2,  16},  //  84: G4
    {0x060B,  16},  //  85: C4
    {0x06B2,   6},  //  86: G4
    {0x0672,   6},  //  87: E4
    {0x06B2,  16},  //  88: G4
    {0x05AC,  17},  //  89: A3
    {0x0672,   5},  //  90: E4
    {0x05AC,  17},  //  91: A3
    {0x0672,   5},  //  92: E4
    {0x05AC,  16},  //  93: A3
    {0x0672,   6},  //  94: E4
    {0x060B,  11},  //  95: C4
    {0x05AC,   5},  //  96: A3
    {0x0672,   6},  //  97: E4
    {0x0511,  17},  //  98: F3
    {0x060B,   5},  //  99: C4
    {0x0511,  17},  // 100: F3
    {0x060B,   5},  // 101: C4
    {0x0511,  16},  // 102: F3
    {0x060B,   6},  // 103: C4
    {0x04E5,  11},  // 104: E3
    {0x0511,   5},  // 105: F3
    {0x060B,   6},  // 106: C4
    {0x0563,  16},  // 107: G3
    {0x0642,   6},  // 108: D4
    {0x0563,  17},  // 109: G3
    {0x0642,   5},  // 110: D4
    {0x0563,  17},  // 111: G3
    {0x0642,   5},  // 112: D4
    {0x053B,  11},  // 113: F#3
    {0x0563,   5},  // 114: G3
    {0x0642,   6},  // 115: D4
    {0x060B,  16},  // 116: C4
    {0x06B2,   6},  // 117: G4
    {0x060B,   5},  // 118: C4
    {0x06B2,  17},  // 119: G4
    {0x060B,  17},  // 120: C4
    {0x06B2,   5},  // 121: G4
    {0x0672,   5},  // 122: E4
    {0x06B2,  17},  // 123: G4
    {0x0672,  16},  // 124: E4
    {0x06F7,   6},  // 125: B4
    {0x0672,   6},  // 126: E4
    {0x06F7,   5},  // 127: B4
    {0x0689,  16},  // 128: F4
    {0x0706,   6},  // 129: C5
    {0x0689,   5},  // 130: F4
    {0x0706,   6},  // 131: C5
    {0x0721,  22},  // 132: D5
    {0x05AC,  16}  // 133: A3
};

// Channel settings (from original engine state)
#define MUSIC_CH1_SWEEP  0x08  // NR10: no sweep
#define MUSIC_CH1_DUTY   0x80  // NR11: 50% duty
#define MUSIC_CH1_ENV    0x57  // NR12: vol=5, increase, period=7
#define MUSIC_CH2_DUTY   0x40  // NR21: 25% duty
#define MUSIC_CH2_ENV    0x77  // NR22: vol=7, increase, period=7
#define MUSIC_CH3_ONOFF  0xFF  // NR30: wave on
#define MUSIC_CH3_VOL    0xDF  // NR32: 50% volume (toggles 0xDF/0x9F)

// Wave RAM pattern (triangle-ish, from original)
static const uint8_t music_wave[16] = {
    0xFF, 0xED, 0xCB, 0xAA, 0xAA, 0xBC, 0xDE, 0xFF,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};

// Drum pattern (Ch4 noise channel)
// Gameplay uses snare hits (NR43=0x55, NR42=0xF1) at irregular intervals
// following the melody rhythm. Duration = frames until next hit.
typedef struct {
    uint8_t nr43;    // Noise polynomial (0x55=snare)
    uint8_t nr42;    // Envelope (volume + decay)
    uint8_t dur;     // Duration in frames until next hit
} drum_event_t;

#define MUSIC_DRUM_LEN 94
static const drum_event_t music_drums[MUSIC_DRUM_LEN] = {
    {0x55, 0xF1,   5},  //  0: snare, hold 5f
    {0x55, 0xF1,  17},  //  1: snare, hold 17f
    {0x55, 0xF1,  11},  //  2: snare, hold 11f
    {0x55, 0xF1,  44},  //  3: snare, hold 44f
    {0x55, 0xF1,  11},  //  4: snare, hold 11f
    {0x55, 0xF1,   5},  //  5: snare, hold 5f
    {0x55, 0xF1,  17},  //  6: snare, hold 17f
    {0x55, 0xF1,   5},  //  7: snare, hold 5f
    {0x55, 0xF1,  17},  //  8: snare, hold 17f
    {0x55, 0xF1,  33},  //  9: snare, hold 33f
    {0x55, 0xF1,  16},  // 10: snare, hold 16f
    {0x55, 0xF1,  17},  // 11: snare, hold 17f
    {0x55, 0xF1,   5},  // 12: snare, hold 5f
    {0x55, 0xF1,  17},  // 13: snare, hold 17f
    {0x55, 0xF1,   5},  // 14: snare, hold 5f
    {0x55, 0xF1,  28},  // 15: snare, hold 28f
    {0x55, 0xF1,  16},  // 16: snare, hold 16f
    {0x55, 0xF1,  17},  // 17: snare, hold 17f
    {0x55, 0xF1,   5},  // 18: snare, hold 5f
    {0x55, 0xF1,  17},  // 19: snare, hold 17f
    {0x55, 0xF1,   5},  // 20: snare, hold 5f
    {0x55, 0xF1,  16},  // 21: snare, hold 16f
    {0x55, 0xF1,   6},  // 22: snare, hold 6f
    {0x55, 0xF1,  22},  // 23: snare, hold 22f
    {0x55, 0xF1,  22},  // 24: snare, hold 22f
    {0x55, 0xF1,   5},  // 25: snare, hold 5f
    {0x55, 0xF1,  17},  // 26: snare, hold 17f
    {0x55, 0xF1,  16},  // 27: snare, hold 16f
    {0x55, 0xF1,  22},  // 28: snare, hold 22f
    {0x55, 0xF1,  28},  // 29: snare, hold 28f
    {0x55, 0xF1,   5},  // 30: snare, hold 5f
    {0x55, 0xF1,  17},  // 31: snare, hold 17f
    {0x55, 0xF1,  38},  // 32: snare, hold 38f
    {0x55, 0xF1,   6},  // 33: snare, hold 6f
    {0x55, 0xF1,  16},  // 34: snare, hold 16f
    {0x55, 0xF1,  11},  // 35: snare, hold 11f
    {0x55, 0xF1,  17},  // 36: snare, hold 17f
    {0x55, 0xF1,  27},  // 37: snare, hold 27f
    {0x55, 0xF1,  11},  // 38: snare, hold 11f
    {0x55, 0xF1,   6},  // 39: snare, hold 6f
    {0x55, 0xF1,  16},  // 40: snare, hold 16f
    {0x55, 0xF1,  22},  // 41: snare, hold 22f
    {0x55, 0xF1,  28},  // 42: snare, hold 28f
    {0x55, 0xF1,   5},  // 43: snare, hold 5f
    {0x55, 0xF1,  11},  // 44: snare, hold 11f
    {0x55, 0xF1,   6},  // 45: snare, hold 6f
    {0x55, 0xF1,  16},  // 46: snare, hold 16f
    {0x55, 0xF1,  22},  // 47: snare, hold 22f
    {0x55, 0xF1,  22},  // 48: snare, hold 22f
    {0x55, 0xF1,  11},  // 49: snare, hold 11f
    {0x55, 0xF1,  17},  // 50: snare, hold 17f
    {0x55, 0xF1,  16},  // 51: snare, hold 16f
    {0x55, 0xF1,   6},  // 52: snare, hold 6f
    {0x55, 0xF1,   5},  // 53: snare, hold 5f
    {0x55, 0xF1,  11},  // 54: snare, hold 11f
    {0x55, 0xF1,  22},  // 55: snare, hold 22f
    {0x55, 0xF1,  11},  // 56: snare, hold 11f
    {0x55, 0xF1,  11},  // 57: snare, hold 11f
    {0x55, 0xF1,  22},  // 58: snare, hold 22f
    {0x55, 0xF1,   6},  // 59: snare, hold 6f
    {0x55, 0xF1,   5},  // 60: snare, hold 5f
    {0x55, 0xF1,  11},  // 61: snare, hold 11f
    {0x55, 0xF1,   5},  // 62: snare, hold 5f
    {0x55, 0xF1,  17},  // 63: snare, hold 17f
    {0x55, 0xF1,  11},  // 64: snare, hold 11f
    {0x55, 0xF1,  11},  // 65: snare, hold 11f
    {0x55, 0xF1,  33},  // 66: snare, hold 33f
    {0x55, 0xF1,  11},  // 67: snare, hold 11f
    {0x55, 0xF1,   5},  // 68: snare, hold 5f
    {0x55, 0xF1,  17},  // 69: snare, hold 17f
    {0x55, 0xF1,   5},  // 70: snare, hold 5f
    {0x55, 0xF1,  17},  // 71: snare, hold 17f
    {0x55, 0xF1,  22},  // 72: snare, hold 22f
    {0x55, 0xF1,  11},  // 73: snare, hold 11f
    {0x55, 0xF1,  16},  // 74: snare, hold 16f
    {0x55, 0xF1,  17},  // 75: snare, hold 17f
    {0x55, 0xF1,  22},  // 76: snare, hold 22f
    {0x55, 0xF1,   5},  // 77: snare, hold 5f
    {0x55, 0xF1,  17},  // 78: snare, hold 17f
    {0x55, 0xF1,  11},  // 79: snare, hold 11f
    {0x55, 0xF1,  44},  // 80: snare, hold 44f
    {0x55, 0xF1,  11},  // 81: snare, hold 11f
    {0x55, 0xF1,   5},  // 82: snare, hold 5f
    {0x55, 0xF1,  17},  // 83: snare, hold 17f
    {0x55, 0xF1,   5},  // 84: snare, hold 5f
    {0x55, 0xF1,  50},  // 85: snare, hold 50f
    {0x55, 0xF1,  16},  // 86: snare, hold 16f
    {0x55, 0xF1,  17},  // 87: snare, hold 17f
    {0x55, 0xF1,   5},  // 88: snare, hold 5f
    {0x55, 0xF1,  17},  // 89: snare, hold 17f
    {0x55, 0xF1,   5},  // 90: snare, hold 5f
    {0x55, 0xF1,  22},  // 91: snare, hold 22f
    {0x55, 0xF1,   6},  // 92: snare, hold 6f
    {0x55, 0xF1,  11}  // 93: snare, hold 11f
};

// Master volume and panning
#define MUSIC_MASTER_VOL  0x77  // NR50: max volume both sides
#define MUSIC_PANNING     0xFF  // NR51: all channels both speakers

#endif /* __MUSIC_DATA_H__ */
