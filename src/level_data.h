#ifndef __LEVEL_DATA_H__
#define __LEVEL_DATA_H__

// Level data from RE-extracted metatile expansion (127 columns).
// OG tile IDs work directly because bg_gameplay.h loads OG's actual
// VRAM tile graphics into the same tile slots.
#include "level_data_extracted.h"

#define LEVEL1_NUM_COLUMNS LEVEL1_EXTRACTED_COLUMNS

// Alias so level.c can reference level1_data
#define level1_data level1_extracted

#endif
