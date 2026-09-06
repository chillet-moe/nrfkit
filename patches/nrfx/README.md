# nrfx patches

Keep the `external/nrfx` submodule immutable. A patch belongs here only after a
version-matched product specification, erratum, or reproducible silicon test
shows that an adaptation cannot be expressed cleanly in NrfKit-owned glue.

Patch files are applied in lexical order to an ignored prepared view below the
consumer workspace. They must use paths relative to the nrfx repository root,
include the upstream commit and evidence reference in their commit message, and
be covered by host and real-board regression tests. Do not use this directory
to carry speculative fixes or downstream product policy.

`0001-grtc-enable-compare-after-programming.patch` restores compare-event enable
after the legacy GRTC setters program a channel. The version-matched register
contract and real-board reproduction are recorded in
[the GRTC evidence](../../docs/provenance/nrfx-grtc-ccen.md).

`0002-clock-xo-allow-null-source-output.patch` restores the documented optional
source-output contract of `nrfx_clock_is_running()`. The unpatched XO path
dereferences `NULL`; this was reproduced on LM20 by the M5 clock precondition.

Both corrections are still required by the locked nrfx 4.5.0 input. Directory
reorganization does not retire them; removal requires a versioned equivalent
upstream fix and the relevant regression checks.
