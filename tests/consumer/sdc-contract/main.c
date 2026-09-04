/* SPDX-License-Identifier: BSD-3-Clause */

#include <mpsl.h>
#include <sdc.h>

int main(void)
{
    return (MPSL_BUILD_REVISION_SIZE == 20 && SDC_BUILD_REVISION_SIZE == 20) ? 0 : 1;
}
