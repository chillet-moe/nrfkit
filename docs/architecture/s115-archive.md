# S115 implementation archive

On 2026-09-06, the stopped S115 consumer integration was retired with explicit
maintainer authorization. Its last complete implementation is Git commit
`5097adce03338d33ad8f9b2d10b5d4e1214209de`.

To inspect or reproduce the historical experiment, use a separate checkout of
that commit and follow its [failure record](m6-official-baseline-failure.md) and
local-input instructions. Reproduction still requires the exact locked external
Nordic inputs; the archive does not redistribute them or authorize hardware writes.

The current SDK no longer includes the S115 CMake entry point/example, nRF-BM
compatibility and crypto shims, board initialization, generated compatibility
configuration, fixed linker layout, SoftDevice manifest assembly, or the dedicated
`reference equivalence-audit` command and implementation tests. Historical commands
must run from the archived checkout. Old layouts containing a `softdevice` field
are rejected by current SDK manifest validation, not converted into application-only
programming requests.

The official S115 reference oracles, P0 workflow, L15 central and bounded BlueZ
tools remain independent reference infrastructure. Version/license/source records
and both historical equivalence JSON receipts remain unchanged. Receipt paths and
hashes describe the recorded experiment; shared build files subsequently evolved,
so these receipts are not assertions about the current tree or every file at the
archive commit.

The experiment stopped at the documented platform lifecycle boundary. This is not
evidence that S115 itself is unusable. Current consumer wireless support continues
through SDC/MPSL. Retirement requires host and consumer build checks; it adds no
new hardware validation claim.
