# nrfx 4.6.0 GRTC compare enable adaptation

NrfKit applies `patches/nrfx/0001-grtc-enable-compare-after-programming.patch`
to the generated nrfx view. The immutable `external/nrfx` submodule remains at
commit `d1f2c35a4820961f4f7b7b2ece007f8e037842db`.

The nRF54LM20A/nRF54LM20B Datasheet v1.0, GRTC “Compare and Capture (CC)”
section, states that a compare event is generated only while
`CC[n].CCEN.ACTIVE` is enabled. It also says that writing `CCL` disables the
channel and writing `CCH` enables it. nrfx 4.6.0's legacy absolute and relative
setter path first disables the channel, writes the compare value, and enables
the interrupt, but does not explicitly restore `CCEN`.

On the locked LM20 DK, the M3 GRTC minimal reproduction did not produce a
compare interrupt after `nrfx_grtc_syscounter_cc_absolute_set()` alone. Reading
the channel state showed it inactive. Calling the HAL compare-event enable
operation after programming the value made the same image produce the expected
interrupt. The explicit enable is idempotent with hardware that already enables
the channel on the `CCH` write and makes the driver contract match the observed
silicon behavior.

The v4.6.0 implementation was checked on 2026-09-19 and still has the same
disable/write/interrupt-enable sequence, so no upstream fix is available to
replace the adaptation. Both absolute and relative legacy setters receive the
same correction because they share the same channel-preparation behavior.

This evidence does not prove a general GRTC or System OFF defect. True System
OFF is not observable while the chip is in Debug Interface mode: the datasheet
specifies that System OFF is emulated and the CPU remains on. The M3 automated
gate therefore validates System ON sleep/wake and RAM retention separately;
detached System OFF wake requires a future repository workflow that releases
Debug Interface mode before entry.
