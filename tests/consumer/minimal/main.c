// SPDX-License-Identifier: BSD-3-Clause

#include <nrfkit/version.h>

#if NRFKIT_VERSION_MAJOR != 0
#error "unexpected nrfkit major version"
#endif

int main(void)
{
    return NRFKIT_VERSION_MINOR;
}
