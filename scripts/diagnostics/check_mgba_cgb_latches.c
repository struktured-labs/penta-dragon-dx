/* Register-level regression: no ROM, CPU execution, or GUI is started.
 * Contract: https://gbdev.io/pandocs/CGB_Registers.html#undocumented-registers
 */
#include <stdio.h>
#include <stdlib.h>
#include <mgba/internal/gb/gb.h>
#include <mgba/internal/gb/io.h>

int main(void) {
    struct GB *gb = calloc(1, sizeof(*gb));
    if (!gb) return 2;
    unsigned failures = 0, checks = 0;
    gb->model = GB_MODEL_CGB;
    for (unsigned reg = 0x72; reg <= 0x74; ++reg) {
        for (unsigned value = 0; value <= 0xFF; ++value) {
            GBIOWrite(gb, reg, value);
            ++checks;
            failures += GBIORead(gb, reg) != value;
        }
    }
    /* The CGB-only implementation must not make these writable on DMG. */
    gb->model = GB_MODEL_DMG;
    for (unsigned reg = 0x72; reg <= 0x74; ++reg) {
        gb->memory.io[reg] = 0xFF;
        GBIOWrite(gb, reg, 0);
        ++checks;
        failures += GBIORead(gb, reg) != 0xFF;
    }
    printf("checks=%u failures=%u\n", checks, failures);
    free(gb);
    return failures ? 1 : 0;
}
