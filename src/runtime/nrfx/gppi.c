/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrfkit/nrfx.h>

#include <helpers/nrfx_gppi.h>
#include <nrfx_gppi_d2ppi.h>

#define AVAILABLE_MASK(count, reserved) \
    ((UINT32_MAX >> (32U - (count))) & ~(uint32_t)(reserved))

void nrfkit_gppi_init(void)
{
    static nrfx_gppi_t instance;

    nrfx_gppi_channel_init(NRFX_GPPI_NODE_DPPIC00,
        AVAILABLE_MASK(DPPIC00_CH_NUM, NRFKIT_DPPI00_CHANNELS_RESERVED));
    nrfx_gppi_channel_init(NRFX_GPPI_NODE_DPPIC10,
        AVAILABLE_MASK(DPPIC10_CH_NUM, NRFKIT_DPPI10_CHANNELS_RESERVED));
    nrfx_gppi_channel_init(NRFX_GPPI_NODE_DPPIC20,
        AVAILABLE_MASK(DPPIC20_CH_NUM, NRFKIT_DPPI20_CHANNELS_RESERVED));
    nrfx_gppi_channel_init(NRFX_GPPI_NODE_DPPIC30,
        AVAILABLE_MASK(DPPIC30_CH_NUM, NRFKIT_DPPI30_CHANNELS_RESERVED));

    nrfx_gppi_groups_init(NRFX_GPPI_NODE_DPPIC00,
        AVAILABLE_MASK(DPPIC00_GROUP_NUM, NRFKIT_DPPI00_GROUPS_RESERVED));
    nrfx_gppi_groups_init(NRFX_GPPI_NODE_DPPIC10,
        AVAILABLE_MASK(DPPIC10_GROUP_NUM, NRFKIT_DPPI10_GROUPS_RESERVED));
    nrfx_gppi_groups_init(NRFX_GPPI_NODE_DPPIC20,
        AVAILABLE_MASK(DPPIC20_GROUP_NUM, NRFKIT_DPPI20_GROUPS_RESERVED));
    nrfx_gppi_groups_init(NRFX_GPPI_NODE_DPPIC30,
        AVAILABLE_MASK(DPPIC30_GROUP_NUM, NRFKIT_DPPI30_GROUPS_RESERVED));

    instance.routes = nrfx_gppi_routes_get();
    instance.route_map = nrfx_gppi_route_map_get();
    instance.nodes = nrfx_gppi_nodes_get();
    nrfx_gppi_init(&instance);
}
