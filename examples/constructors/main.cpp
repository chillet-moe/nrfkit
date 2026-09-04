/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>

volatile uint32_t constructor_observation;

class StartupProbe {
public:
    StartupProbe()
    {
        constructor_observation = UINT32_C(0xC023C023);
    }
};

StartupProbe startup_probe;

extern "C" int main()
{
    for (;;) {
        __asm volatile ("wfe");
    }
}
