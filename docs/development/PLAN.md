# nrfkit：目标与执行计划

> 状态：P0、M0、M1、M2、M3、M6、M8、M9 已完成；M4 仅余但暂缓直连拓扑 remote wake；M5 direct-RADIO 基线已收束；M7 功能、时序、retry 与共存门禁已完成，外部仪器电气功耗测量暂缓；0.1.0-rc.2 已完成发布验收并推送公开 main/签名 tag
> 计划基线：2026-09-05<br>
> 唯一 SDK 支持目标：nRF54LM20A / nRF54LM20 DK<br>
> 实验室夹具：nRF54L15 DK（不属于 SDK 支持目标）<br>
> 推荐的本地工作目录：`$HOME/Projects/nrfkit`

本文是项目的约束性执行文件，面向后续维护者和自动化 agent。除非新的实板证据、官方文档或用户明确决定推翻某项结论，否则实现应按本文推进。文中的“必须”“禁止”“验收”不是建议。

文档职责必须保持分离：

- `AGENTS.md` 只保存整个项目生命周期内稳定的行为、安全和公开边界，不记录当前里程碑、临时环境状态或本轮任务；
- `docs/development/PLAN.md` 保存目标、设计决策、里程碑顺序、动态状态和退出条件；
- `docs/development-inputs.md` 说明可公开的输入类别、发现顺序和 provenance 契约；
- `.local/AVAILABLE_INPUTS.md` 保存本机实际路径、私有只读参考、已连接硬件和工具现状，必须由 `.gitignore` 排除；
- `.work/` 保存构建 receipt、manifest、运行报告和原始日志，必须由 `.gitignore` 排除。

自主 goal 的启动文本只需要求 agent 读取上述文件并持续完成 `docs/development/PLAN.md`；具体任务不得复制进 `AGENTS.md` 或堆叠在启动文本中。

## 当前剩余工作（2026-09-11 复核）

首阶段主体已完成；以下项目仍有明确的证据或工具缺口：

- **M7 电气功耗验收**：建立外部仪器采集与报告工作流，以相同方法测量
  4/2/1 Mbit/s、retry 和 BLE 共存的电流、功率与能量；duty 指标不能替代电气测量。
  仪器现状以 ignored local inventory 为准，历史缺少仪器不应成为永久阻塞结论。
- **M4 USB remote wake**：在直连拓扑完成 device-initiated resume，确认没有
  reset/re-enumeration；已有 host-initiated resume 通过不能替代该门禁。
- **真实 System OFF 唤醒**：建立退出 Debug Interface mode 后的睡眠与唤醒验证，
  补齐 M3 记录中明确未覆盖的行为，并与功耗测量关联。
- **OpenOCD backend 评估与接入**：公共工具已加入受 guard 约束的 CMSIS-DAP/OpenOCD
  入口；探针枚举、目标 attach、program/readback、backup/restore 与冷启动后 GDB
  读取已通过。当前接线下 pin reset 未能重启 CPU，相关 step/watchpoint 门禁仍未通过。
  外部实现须分别审查 attach/RAM、RRAM program/readback、reset 和 GDB 能力；
  在本仓库复用镜像 guard、探针选择/锁、timeout、清理和报告后重跑验收。
  nRF54LM20 DK 上的 LM20B 可用于 SDK 的 LM20A 共同功能验收；锁定的 A/B
  Datasheet v1.0 §3.2 Table 6 列出相同的 RRAM/RAM 容量，B 增加 Axon NPU。
  NPU 不在当前 SDK 范围内；报告仍保留实际 PART/revision，并匹配适用勘误。
  B 型号本身不是沿用 DK 实板证据的阻塞项。

M4/M7 的暂缓决定仍保留；输入到位本身不表示验收完成。后续 CMake/ELF 接口整理
已有 host/build 证据，但没有新增实板结论；下次发布应对最终提交重新完成对应回归
与归档验收。开放 BLE Host、产品 profile、其他 SoC 和实际量产 provisioning 不属于
这些遗留项；已完成的 M8/M9 不因它们重新打开。

功耗采集已有公共 PPK2 CLI 与原始数据/校准元数据报告。2026-09-11 在 3.0 V 下完成
空闲与 1/2/4 Mbit/s 周期发射采样；GDB 后验检查确认发射程序运行。PPK2 缺失校准系数且
使用默认系数，因此数值仅为当前夹具估计，不完成 M7 电气门禁。真实 System OFF 的
5 秒 GRTC 唤醒未通过，两次采样均没有预期转换，随后调试接入得到 DIF 复位原因。
详见[测量记录](../validation/power-measurement-2026-09-11.md)。

## 1. 最终目标

建立一个非官方、可开源、可复用的 Nordic nRF 裸机 SDK：

- 应用使用标准 CMake、Ninja 和本机 Arm 交叉工具链构建；
- 最终构建不依赖 west、sysbuild、Devicetree、Kconfig 或 Zephyr；
- 完整支持 nRF54LM20A；当前阶段不实现 nRF54L15、nRF52、nRF53 或其他 nRF54 器件支持；
- nRF54L15 DK 仅作为 BLE central/peripheral、私有 2.4 GHz 对端和差分测试夹具，不因此产生 L15 consumer target、公共 API 或完整器件支持工作；
- 将版本锁定的 Nordic `sdk-nrfxlib` 作为一级官方输入，复用其中适用于 LM20 的 MPSL 与 SoftDevice Controller 预编译库，并复用官方 CMSIS/MDK、nrfx HAL/driver、启动与系统初始化代码；
- 支持纯裸机 C 和 C++ 应用，最终面向同时具备 BLE 与高性能私有 2.4 GHz 能力的低延迟、低功耗无线 HID 类外设；
- 当前无线阶段先建立可独立验收的 BLE Controller/HCI 与 MPSL Timeslot 能力，开放 Host、ATT/GATT、HID profile 和配对策略不属于本计划；
- 支持编译、ELF/HEX/BIN 产物、烧写、复位、GDB 调试和无人值守实板验收；
- SDK 自身保持下游无关，不能泄漏任何未公开的下游项目、产品、品牌、目录、探针序列号或日志内容。

首个可用版本不是“把 NCS 的命令换一层包装”，而是一个在没有 NCS/Zephyr 安装的干净环境里仍能独立构建的 SDK。NCS 只作为权威源码来源、行为对照和回归 oracle；无线 target 只消费显式提供且通过版本校验的 `sdk-nrfxlib`，不得搜索已安装的 NCS。

## 2. 已确定的方案

### 2.1 项目名与定位

项目名采用 `nrfkit`，以避免仓库名、CMake 函数和 C/C++ 宏出现冗长前缀。公开标识统一为 CLI `nrfkit`、CMake package `NrfKit`、函数前缀 `nrfkit_`、宏前缀 `NRFKIT_` 和头文件目录 `nrfkit/`。公开 README 必须显著注明：这是社区项目，与 Nordic Semiconductor 无隶属或背书关系；nRF 等商标归各自权利人所有。

自有代码默认采用 BSD-3-Clause。第三方文件保留各自许可证，不得用项目许可证覆盖：

- nrfx/MDK 通常为 BSD-3-Clause；
- Arm CMSIS 和 TF-M 文件可能分别为 Apache-2.0 或 BSD-3-Clause；
- `sdk-nrfxlib` 中的 MPSL/SoftDevice Controller 以及 NCS Bare Metal/SoftDevice 包含 `LicenseRef-Nordic-5-Clause` 内容，只能按原许可使用和再分发；预编译二进制不得逆向、反汇编或修改；
- 每次导入都必须记录来源、tag/commit、SHA-256、许可证、是否修改和修改补丁。

若许可证审计尚未完成，相关二进制只能通过用户提供的外部路径使用，不能先复制到仓库再补手续。

### 2.2 构建与依赖模型

面向 SDK 使用者的默认体验必须满足：一次包含已初始化 submodule 的 checkout（例如 `git clone --recurse-submodules`）或完整 release archive 后即可离线配置和编译，不在 CMake configure 阶段访问网络，也不要求运行包管理器。

因此采用以下策略：

1. 所有随 SDK 提供的第三方输入统一放在 `external/`；CMSIS Core 保留为 `external/cmsis` 中逐文件 hash 锁定的未修改快照。nrfx 的 startup/MDK 与 HAL/driver 共用同一上游，不再维护重复的 `third_party/nrfx` 快照。nrfx 作为 `external/nrfx` 中固定到精确 commit 的只读 Git submodule；本仓库不把完整 nrfx 源码树作为普通文件提交。项目只跟踪逐文件选择清单、自有适配层和 `patches/nrfx/` 下的可审查补丁。需要修改上游时，在 consumer workspace 的 ignored shared cache 中复制被选文件并以普通 `git apply` 应用补丁，绝不直接修改 submodule。
2. `sdk-nrfxlib` 是无线功能的一级、不可变、版本锁定输入，以
   `external/sdk-nrfxlib` Git submodule 固定到 tag `v3.4.0` 的准确 commit。来源锁同时记录
   SDC/MPSL component manifest revision、所选头文件/静态库 hash、许可证、安全域和
   float ABI。完整 checkout 随项目取得，但构建只暴露实际选择的 component；release
   archive 必须包含同一固定 checkout。允许显式 `NRFKIT_NRFXLIB_ROOT` 覆盖，但必须通过
   同样的 identity/hash 校验；不得从 `$HOME/ncs` 自动发现或拼装库。
3. SDC 的 Multirole、Peripheral-only、Central-only archive 与 `libmpsl.a` 必须来自同一锁定 release、`nrf54lm` security domain 和 hard-float ABI，不能跨版本混用。submodule 与其二进制保持原样，项目适配只能位于自有 CMake/platform layer；不得修改、反汇编、反编译或逆向预编译 archive。
4. 旧 S115 适配实验通过 [归档提交](../architecture/s115-archive.md) 保留历史复现能力和原始 license/attribution；当前 SDK 不提供 S115 集成。官方 S115 oracle 仍使用锁定外部输入。
5. SDK 构建不能搜索或隐式借用 `$HOME/ncs`。本机 NCS 目录只允许被显式的开发者对照测试使用。缺失或 commit 不匹配的上游输入必须给出明确诊断；普通 configure/build 不得自行联网更新它。
6. Python 可以用于维护者工具、HEX 检查和硬件测试，但不得成为编译一个普通应用的必需依赖。核心构建只要求 CMake、构建器、编译器及 binutils 等效工具。
7. 不引入 west manifest 的替代品，也不实现 Kconfig 或 Devicetree 的小型克隆。
8. 官方参考样例允许在 `tools/reference/` 的显式维护者流程中调用其原生 west、sysbuild、Kconfig、Devicetree 和 Zephyr；该例外只能用于建立可运行的官方 oracle，不能进入 SDK consumer 的 configure/build dependency graph。

### 2.3 工具链

第一工具链为主机安装的 LLVM/Clang + LLD；第二工具链为 GNU Arm Embedded，用于兼容性回归。不要依赖 NCS 工具链环境变量。

工具链文件只负责交叉编译事实：

- `CMAKE_SYSTEM_NAME=Generic`；
- `CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY`；
- `--target=arm-none-eabi`；
- 每个 SoC/core 自己提供 `-mcpu`、FPU、ABI 和安全域参数；
- 编译、链接、objcopy、size、readelf 和 GDB 路径都可以通过标准 CMake cache 覆盖；
- 所有编译选项必须按 target 设置，不能污染父项目的全局 flags。

第一阶段使用 freestanding runtime，消除 libc 对 bring-up 的干扰；随后提供 picolibc 或明确配置的 newlib 适配。即使默认禁用 C++ exceptions/RTTI，链接布局也必须正确保留 `.preinit_array`、`.init_array`、`.fini_array`，并有一个 C++23 构造器验收程序。不能把 C++ 支持留到下游集成时才补。

### 2.4 CMake 公共接口

SDK 既支持源码方式加入，也支持安装后的 `find_package`。建议的应用接口如下，具体拼写可在 M0 中微调，但语义不得变成隐式全局状态：

```cmake
cmake_minimum_required(VERSION 3.25)
project(example C CXX ASM)

list(PREPEND CMAKE_PREFIX_PATH "${NRFKIT_ROOT}")
find_package(NrfKit CONFIG REQUIRED)

add_executable(firmware main.cpp)
target_link_libraries(firmware PRIVATE
  NrfKit::runtime_freestanding NrfKit::board_nrf54lm20dk
  NrfKit::nrfx_gpio)
target_compile_definitions(firmware PRIVATE __STACK_SIZE=0x4000 __HEAP_SIZE=0)
set(linker_script "${CMAKE_CURRENT_SOURCE_DIR}/image/application.ld")
target_link_options(firmware PRIVATE "LINKER:-T,${linker_script}")
set_property(TARGET firmware APPEND PROPERTY LINK_DEPENDS "${linker_script}")
```

必须遵守的 API 原则：

- 一个 ELF target 明确绑定一个 SoC、core、security domain、board 和 memory layout；
- board 是普通 CMake target 加普通 C/C++ header，不是 YAML/DTS 输入；
- 链接 `NrfKit::nrfx_<driver>` 只把所选 driver 及依赖加入当前固件；
- 同一个构建树可以包含多个不同配置的 firmware target，不使用全局 `NRFX_CONFIG_*` 污染；
- 应用可以只链接 CMSIS/MDK/HAL，而不强制使用 SDK runtime 或 nrfx driver；
- 能力选择与配置由实际编译命令、预处理结果和最终 link map 审计；
- 未知 SoC、不可用外设、冲突的 IRQ/DPPI 资源和越界内存必须在 configure/compile/link 阶段失败，不能静默退化。

预期命令行保持普通 CMake 形态：

```sh
cmake -S examples/blinky -B build/lm20 -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$SDK_ROOT/cmake/toolchains/arm-clang.cmake" \
  -DNRFKIT_ROOT="$SDK_ROOT" \
  -DNRF_SOC=nrf54lm20a \
  -DNRF_BOARD=nrf54lm20dk
cmake --build build/lm20
cmake --build build/lm20 --target flash
cmake --build build/lm20 --target gdbserver
```

`flash` 和 `gdbserver` 是便利 target，不是构建固件的前置条件。

### 2.5 分层架构

预期目录结构：

```text
nrfkit/
├── AGENTS.md
├── LICENSE
├── README.md
├── CMakeLists.txt
├── src/
│   ├── boards/
│   ├── runtime/
│   ├── usb/                  # optional built-in port; consumer may maintain a copy
│   ├── soc/
│   └── wireless/
│       ├── include/
│       ├── radio/
│       ├── sdc/
│       └── timeslot/
├── cmake/
│   ├── NrfKitConfig.cmake
│   ├── modules/
│   └── toolchains/
├── external/
│   ├── cmsis/                 # unmodified, hash-locked Core snapshot
│   ├── cherryusb/             # immutable, version-locked submodule
│   ├── nrfx/                  # immutable, version-locked submodule
│   └── sdk-nrfxlib/           # fixed read-only official submodule
├── include/nrfkit/
├── linker/
│   ├── common/
│   └── layouts/
├── patches/
│   └── nrfx/                  # project-owned, evidence-backed patches
├── examples/
│   └── common/usb/            # example-owned USB configuration
├── tests/
│   ├── host/
│   ├── link/
│   └── hardware/
├── tools/
│   ├── nrfkit
│   ├── image/
│   ├── hardware/
│   └── reference/
├── docs/
│   ├── architecture/
│   ├── development/
│   │   └── PLAN.md
│   ├── provenance/
│   └── porting/
└── .agents/skills/
```

公共层只能表达通用概念。差异必须落在正确层级：

| 层 | 负责内容 | 禁止内容 |
|---|---|---|
| toolchain/core | ISA、ABI、编译器 runtime | SoC 地址、board pin |
| family | nRF54L 共同初始化和能力 | 假定所有 nRF 都是 RRAM |
| SoC | 内存、IRQ、外设实例、errata | 产品 pin 和业务策略 |
| board | LED、按钮、晶振、VCOM、调试探针约定 | 应用功能和私有标识 |
| image/layout | 起始地址、保留区、SoftDevice/boot slot | 用板级名字推导地址 |
| driver/integration | nrfx 配置、资源声明、ISR glue | 隐式抢占其他模块资源 |
| application | 业务资源选择和策略 | 修改 SDK 内部来适配单一产品 |

当前公共层只需要正确表达 LM20 已验证的事实，不为未来器件预先增加抽象。若以后重新授权跨器件支持，应另行制定以实板证据驱动的迁移计划，不能让尚未进入范围的多核、NOR Flash 或其他 SoC 差异增加当前 LM20 实现复杂度。

## 3. 官方来源优先级与启动/链接规则

### 3.1 证据优先级

遇到冲突时按以下优先级处理，并记录具体版本，而不是凭经验合并：

1. 与实际 silicon revision 匹配的 Nordic Product Specification、Datasheet 和 Errata；
2. 同一版本官方 MDK/SVD、`sdk-nrfxlib` SDC/MPSL README、CHANGELOG、component manifest、API 与旧 SoftDevice specification/release notes；
3. 精确 tag/commit 的 `sdk-nrfxlib`、nrfx、NCS Bare Metal 和 NCS；
4. Arm CMSIS、Trusted Firmware-M、MCUboot 的上游实现；
5. 官方开发板硬件文档；
6. 社区资料仅作为线索，寄存器、IRQ、内存和安全结论必须回到以上来源验证。

若前两级彼此冲突，暂停相关实现，生成一份最小复现和差异报告。不能为了让示例运行而挑选更方便的数值。

### 3.2 当前可复现的来源基线

当前采用以下已经检查并锁定的基线。自动化任务不得只因上游出现新 release 就切换；
升级必须作为单独的兼容性决定并重新生成来源、ABI 与实板证据：

- NCS `v3.4.0`，本机 checkout commit `99553055607b2e9885fbc80ccd11fa9da81c2df0`；
- NCS 中 Nordic HAL/nrfx commit `18da0cc9726f8759c627dba3180b3ba9294e433c`；
- `sdk-nrfxlib` tag `v3.4.0`，仓库 commit `d4ce5fe1a7d8af29bc01a4e1ddf5540ef65b6a3b`，SDC/MPSL `nrf54lm` binary manifest revision `c8da3098f9f034a44b6ebad30819cc0cea51da47`；
- NCS Bare Metal `v2.0.1`，commit `51484143c09199e19bccc16fa3b437f7a502a72b`；
- nRF54LM20A/nRF54LM20B Datasheet v1.0；
- S115 for nRF54LM20 `10.0.1`；
- S145 for nRF54L15 `10.0.1`，仅用于版本锁定的实验室 central 夹具。

M6 首先使用 `nrf54lm/hard-float` secure MPSL 与 SDC archive，因为当前 LM20
standalone target 使用 hard-float 且在 secure domain 运行。官方仍将 nRF54L 的
non-secure SDC 标为 experimental；它不得作为首个实板门禁或 production 能力声明。
`sdk-nrfxlib` v3.4.0 只声明与对应 NCS 所用 nrfx revision 一起测试过，而本项目核心
使用较新的 nrfx v4.5.0，因此头文件、ELF attributes、未解析符号、资源定义和实板
行为兼容性是 M6 的第一道门禁，不能按同一系列名称假设兼容。

本机候选位置仅用于发现，不得成为构建依赖：

```text
$HOME/ncs/v3.4.0
$HOME/ncs/v3.4.0/nrfxlib
$HOME/ncs/nrf-bm/v2.0.1
$HOME/Documents/Datasheets/NORDIC/nRF54LM20A_nRF54LM20B_Datasheet_v1.0.pdf
```

每个被采用的文件都要进入 `docs/provenance/sources.lock`，至少记录 URL、release、commit、文件路径、SHA-256、SPDX、导入日期和 patch 状态。不能只记录“来自 NCS 3.4”。

### 3.3 启动代码的硬约束

初始 NCS v3.4.0 所带 nrfx/MDK 基线中存在：

- `system_nrf54l.c/.h`；
- nRF54LM20A 与 nRF54L15 的 CMSIS 设备头、peripheral 头、SVD 和 memory header；
- nrfx SoC IRQ 映射；

但该旧基线没有传统的、专用于 LM20/L15 的 GNU `startup_*.S`。M0 后续审计确认 nrfx v4.5.0 已发布专用 GNU startup；M1 采用该精确版本的官方文件。NCS 的普通应用启动仍由 Zephyr 的通用 Cortex-M 代码生成；TF-M 中 Nordic/Arm 维护的 CMSIS 衍生 startup 保留为版本差异对照。

因此 M0 必须先完成一次独立来源审计：

1. 检查最新 nrfx release archive，而不仅是 NCS 子仓库；
2. 检查 Nordic 官方 MDK/CMSIS pack、NCS Bare Metal、NCS 和 TF-M；
3. 搜索 GNU/Clang、IAR、ArmClang 三类 startup/linker 文件；
4. 把“存在”或“未找到”的证据、版本和搜索范围写入 provenance 文档。

审计后的选择顺序：

1. 若存在适配该 SoC 的官方 GNU/Clang startup，则原样导入或仅用薄 wrapper 包装；
2. 若不存在，不为了满足文件扩展名而自行臆造大型汇编文件；优先采用官方 TF-M/CMSIS 衍生的 C vector table 与 Reset Handler；
3. 只有 C runtime 入口确实要求时，才加入最小 `reset_entry.S`，且逐条注明对应的 CMSIS/TF-M 官方来源；
4. IRQ 数量、索引和 reserved slot 必须由设备头的 `IRQn_Type`、SVD、TF-M vector table 和参考 ELF 四方交叉检查；
5. `SystemInit()` 优先使用对应 nrfx/MDK 的 `system_nrf54l.c`，不得自行删去 KMU 时序、trim、approtect、RAM/RRAM power 或 errata 逻辑；需要改变默认行为时只通过官方宏或单独、可审查的 wrapper 完成。

### 3.4 链接脚本的硬约束

初始 NCS 基线同样没有 Nordic 为 LM20/L15 发布的独立 GNU linker script；M0 后续确认 nrfx v4.5.0 已包含 per-device GNU linker script。M1 将其作为官方内存输入，但使用带更严格边界和断言的仓库自有布局，且不把 Zephyr 生成结果当成模板。

信息来源至少包括：

- `nrf54lm20a_xxaa_application_memory.h` / `nrf54l15_xxaa_application_memory.h`；
- 对应 SVD 和设备头；
- Datasheet 的 memory map、RRAMC、MEMCONF、MPC/SPU 与启动章节；
- 官方 NCS/NCS Bare Metal 构建得到的 ELF、map 和 HEX；
- S115 release notes 中的固定 NVM/RAM 边界（仅用于 legacy S115 layout）；
- SDC/MPSL resource configuration、最终 link map 和 archive ABI；SDC/MPSL 是链接进
  应用的静态库，不能沿用 S115 固定镜像基址或 RAM 边界。

链接层分成两部分：

- 通用 Cortex-M sections：vector、text/rodata、ARM unwind、copy/zero table、data、bss、noinit、retained、init arrays、stack/heap、RAM function；
- 每个 SoC/layout 的 `MEMORY`、起始地址、保留区和 alignment。

每个布局必须有 linker `ASSERT()` 和构建后检查，至少验证：

- vector 位于镜像要求的地址且对齐正确；
- 初始 MSP 落在允许的 RAM 中；
- Reset Handler Thumb bit 和地址范围正确；
- load/run address 与 copy table 一致；
- stack、heap、retained、SoftDevice 和持久化区域不重叠；
- HEX 不包含 FICR/UICR/SICR 或未声明地址；
- C++ arrays 没有被 `--gc-sections` 丢弃；
- section overflow 在链接时失败。

### 3.5 LM20 初始内存事实

以下值可作为测试断言的种子，但实现前仍要从锁定版本的官方文件生成最终常量：

| 区域 | nRF54LM20A |
|---|---:|
| RRAM | `0x00000000..0x001FCFFF`，`0x001FD000` bytes |
| UICR | `0x00FFD000..0x00FFDFFF` |
| SRAM bank 0 | `0x20000000..0x2003FFFF` |
| SRAM bank 1 | `0x20040000..0x2007FFFF` |
| S115 10.0.1 base | `0x001E3800` |
| S115 10.0.1 NVM size | `0x00019400` |
| S115 minimum RAM | `0x00001080`，实际由配置决定 |
| S115 worst-case additional call stack | `0x00000700` |

初始实现不得把物理 SRAM 全部自动交给应用。应先采用与官方参考一致的保守上界，确认末端系统保留区后再扩大。

## 4. 硬件与无人值守安全策略

### 4.1 已授权操作范围

自动化任务可自行执行以下操作，无需等待交互确认：

- 枚举探针、板卡、VCOM 和读取芯片信息；
- 读取 FICR、普通寄存器、RAM 和普通 RRAM；
- 在 SDK 明确分配的普通应用 RRAM 范围内烧写并读回验证；
- 写 RAM、启动 RAM test image；
- halt、reset、run、设置断点、单步和 GDB 检查；
- 在专门声明的普通 RRAM scratch region 做次数受控的写入测试；
- 烧写经过 hash 验证的官方 SoftDevice 到其固定普通 RRAM 区域。

### 4.2 默认禁止的操作

无人值守流程中绝对禁止：

- 写 UICR、SICR、OTP、User RoT、KMU slots、BOOTCONF 或任何 protection 字段；
- 调用 `nrfutil device erase`、`recover`、`protection-set`；
- 使用 `chip_erase_mode=ERASE_ALL` 或任何等价 mass erase；
- 启用 APPROTECT、SECUREAPPROTECT、AUXAPPROTECT、ERASEPROTECT；
- 更新板载调试器固件；
- 对来源未知的 BIN 猜测烧写地址；
- 为了解决连接失败而自动恢复、解锁或清除整片；
- 运行 production provisioning target。

若工具声称必须执行上述任一操作，任务必须停止该路径、保留日志，并改用安全 backend 或向用户报告。不能把“开发板可恢复”当作授权。

### 4.3 烧写防线

对外只提供稳定入口 `tools/nrfkit`；烧写子命令由内部 `tools/hardware/flash-safe` 实现，并在调用 vendor tool 前完成独立校验：

1. 只接受具有明确加载地址的 ELF/HEX；BIN 仅作打包产物，不能单独作为烧写输入；
2. 解析全部 load segment/HEX record；
3. 拒绝越过当前 image layout allowlist 的任何 byte；
4. 硬编码拒绝 FICR/UICR/SICR 和系统保留区域，即使 manifest 错误也不能绕过；
5. 校验 SoC、board、image type、origin、SoftDevice version/hash；
6. 默认调用 `nrfutil device program` 的 `ERASE_NONE` 与 read-back verify；
7. 烧写后 reset，等待带 build ID 的测试 token；
8. 保存结构化结果，但 tracked 文件和公开 CI artifact 中删除探针序列号与本地路径。

烧写时必须先将已验证的输入复制为当次 run directory 内的只读快照，再次校验 hash 和地址契约后才传给 vendor tool；不能让并发重建改变正在烧写的文件。

不得把 `nrfutil device program` 直接暴露为默认 `flash` target；`flash` 必须经过以上 guard。

### 4.4 探针选择与并发

- 每次运行都动态枚举，不能硬编码规划阶段看到的序列号或 `/dev/ttyACM*`；
- 恰好一块匹配 board 时自动选择；
- 多块板时必须由 `NRF_PROBE_SERIAL` 或测试 inventory 显式选择，不能“取第一块”；
- 使用按探针加锁的 OS lock，防止两个 agent 同时烧写或启动 GDB server；
- 所有串口、GDB server、烧写命令和测试都必须有 timeout；
- 进程退出时清理 GDB server、串口句柄和 lock，不留下后台进程；
- 没有硬件时继续完成 host/link 测试，并把 hardware gate 标记为 pending；不能把未测功能标记为完成。

规划时本机曾成功发现一块 PCA10184、nRF54L family DK 和两个 VCOM。该事实只是环境预检，不是未来运行的假设。

### 4.5 RRAM 耐久与测试区

RRAM 测试必须：

- 使用 linker 明确保留的 scratch region；
- 按 128-bit data unit 统计写次数；
- 使用 append/rotation，避免每次 CI 改写同一单元；
- 在板外日志记录估算写入次数；
- 等待 RRAMC ready/buffer flush 后才 reset 或进入 System OFF；
- 不用擦除整个器件来“恢复干净状态”。

## 5. 烧写和 GDB backend 决策

### 5.1 首选基线

LM20 的第一条可靠路径采用 Nordic/SEGGER 官方支持组合：

- 烧写：`nrfutil device`，经过 `flash-safe` 包装；
- GDB server：SEGGER J-Link GDB Server；
- GDB client：本机 `arm-none-eabi-gdb` 或 `gdb-multiarch`；
- 编译：本机 Clang/LLD，不使用 NCS 的编译 wrapper。

这样只有芯片访问部分依赖 vendor tool，编译、链接、测试调度和应用构建均使用普通本机工具。

### 5.2 OpenOCD

OpenOCD 作为可插拔 backend，而不是 LM20 首个里程碑的阻塞项：

1. 先确认所用 OpenOCD 版本是否识别 LM20 的 DP、AP、Cortex-M33、reset 和 RRAM 编程算法；
2. 只读 attach、halt、register/RAM access 验证通过后，才允许 RAM image；
3. 只有普通 RRAM range program + verify 通过安全审查后，才标记 `flash` 支持；
4. 与 J-Link 对比 reset、breakpoint、watchpoint、vector catch 和 flash breakpoint 行为；
5. upstream OpenOCD 不支持时，记录清晰的 capability matrix，继续使用 J-Link；初期不维护一个未经评估的私有 OpenOCD fork。

公开文档必须区分“GDB server 可连接”“RAM 调试可用”“RRAM 烧写可用”三个能力，不能因为第一项成功就宣称 OpenOCD 完整支持 LM20。

### 5.3 GDB 自动验收

提供 batch GDB 脚本，至少自动完成：

1. 启动 server 并等待端口 ready；
2. 连接 target，读取 CPUID 和关键 memory map；
3. reset halt；
4. 在 `Reset_Handler` 和 `main` 设置硬件/软件断点；
5. continue 到两个断点；
6. 检查 MSP、PC、VTOR、`.data` 初始化、`.bss` 清零和一个全局 C++ 构造对象；
7. 单步一段 GPIO 或 timer 代码；
8. 触发并捕获一个可恢复的测试 fault；
9. detach、关闭 server，确认没有孤儿进程。

每个步骤输出机器可解析的 PASS/FAIL 和工具版本。

## 6. 功能范围与优先级

### 6.1 首个 LM20 可用面

按以下顺序实现；后面的模块不能反向污染更低层：

1. CMSIS/MDK、startup、SystemInit、linker、fault handler；
2. GPIO、clock/power、GRTC/TIMER、DPPI/PPIB、GPIOTE、UARTE/RTT；
3. SPIM、TWIM、PWM、SAADC、RRAMC、watchdog、reset reason；
4. RAM power/retention 与 System ON idle/System OFF 基础；
5. USBHS device controller 适配；
6. 私有 2.4 GHz 所需 RADIO/timer/DPPI/CCM 基础；
7. 版本锁定的 MPSL 基础平台适配与 SoftDevice Controller；
8. 受 MPSL 调度的 4 Mbit/s 优先私有 2.4 GHz packet engine；
9. image layout、bootloader/DFU 和 production support。

无线主线固定为：先锁定并审计 `sdk-nrfxlib`，随后以满足 SDC 启动所需的最小 MPSL
平台层跑通 SoftDevice Controller 三种 archive，最后在 MPSL Timeslot 内实现私有
2.4 GHz。SDC 的第一个验收对象是 Multirole；Peripheral-only 和 Central-only 在相同
底座上随后验收。当前阶段只验证 Controller/HCI，不引入开放 Host、ATT/GATT、HID
profile 或产品配对策略。旧 S115 路线仅保留为历史可复现检查点，GZLL 不在范围内。

SDK 不需要发明通用 driver framework。优先暴露正确的 nrfx/HAL target、IRQ glue 和资源约束；只有确实跨 SoC 重复且 API 稳定的薄层才进入公共 API。

### 6.2 USBHS

LM20 有 USBHS HAL，但当前 nrfx 基线没有与旧 `nrfx_usbd` 等价的完整 LM20 USBHS device driver。此项必须单独立项：

- 先审计官方 NCS USBHS driver、芯片文档、errata 和公开 bare-metal USB stack；
- 为可移植 USB device stack 提供 DCD/port，优先评估与现有裸机 CMake 工程适配良好的 CherryUSB；同时记录 TinyUSB 的可行性；
- USB stack 与 SDK core 解耦，可由下游提供；
- 验收包括枚举、control transfer、多 endpoint IN/OUT、连续压力、suspend/resume、remote wakeup 和拔插；
- 不创建 L15 USB consumer target；L15 目前只允许作为测试夹具存在于显式 reference workflow 中。

### 6.3 私有 2.4 GHz

SDK 的职责是提供经实板验证的 RADIO 访问基础、时钟/timer/DPPI 组合、IRQ/resource
ownership 和一个最小 packet-radio 示例，不把某个产品协议放入 SDK。现有 direct-RADIO
实现保留为独占运行时的诊断、互通和性能基线；SDC 启用后，它不构成安全的共存机制，
应用只能在 MPSL 明确授予的 Timeslot 内直接访问 RADIO/timer/DPPI 等受管资源。

LM20 和 L15 的锁定 MDK 均公开定义 Nordic proprietary 4 Mbit/s PHY。私有链路必须
把 4 Mbit/s 作为首要性能目标和独立验收配置；2 Mbit/s、1 Mbit/s 仅作为兼容、回归
和故障定位基线，不能以它们通过代替 4 Mbit/s 验收。两种公开的 4 Mbit/s mode/调制
参数都先按匹配 silicon 文档、errata 与空口结果审计，再选出默认配置。

验收按可独立复现的阶段推进：

- 单板：HFCLK、RADIO state、TX READY/END/DISABLED、RX timeout、CRC/packet layout 寄存器和功耗状态可重复；
- 双板基础：LM20 与 reference peer 均能成功发包和收包，双向交换固定已知载荷，并连续重复运行得到相同判定；
- 链路行为：按现有协议资料逐项加入包长边界、CRC/白化、序号与丢包、重试、信道切换、睡眠唤醒和延迟统计；
- 4 Mbit/s 性能：LM20 与 L15 双向运行，量化 payload goodput、端到端延迟、丢包、
  重试、队列上界、连续稳定性和可测功耗，并与 2 Mbit/s、1 Mbit/s 基线比较；
- 键盘需求：只实现已由本地参考资料和真实互通证明需要的链路行为，不把私有业务协议或消费者标识固化进公共 SDK。

每个双板阶段都必须通过仓库公共 CLI 重新枚举并显式选择两个目标、校验芯片与镜像
地址、持有逐设备锁、使用硬超时和可靠清理，并在 `.work/` 保存 SDK/source lock、
镜像 hash、工具版本、命令、结构化结果和原始本机日志。没有双板空口证据时不得宣称
互通完成。

### 6.4 SoftDevice Controller 与 MPSL

`sdk-nrfxlib` 是当前无线实现的一级官方输入。SDC 以静态库形式提供 BLE Controller，
并依赖同一发行版、同一安全域和同一 float ABI 的 MPSL；因此“MPSL 在 SDC 之后”只指
Timeslot/私有无线功能里程碑，满足 `sdc_init()` 的最小 MPSL 初始化、时钟、IRQ、低优先级
执行与资源配置必须先完成。

SDC 的公共边界是原始 HCI command/event/ACL transport 和明确的 controller lifecycle。
首轮无需 Host：使用小型、可审计、确定性的 HCI 测试驱动验证 reset、版本、features、
advertising、scanning、建连、断连和重复 enable/disable。Multirole 首先同时证明 central
和 peripheral 能力；随后链接 Peripheral-only 与 Central-only archive，按各自能力子集
重复门禁。不得因示例依赖 Zephyr 就把其 build-system glue 搬进 consumer SDK。

MPSL Timeslot 阶段在 SDC 已工作后开始。私有 radio backend 必须正确处理 grant、blocked、
cancel、extend、deadline、资源清理和时钟生命周期，并分别在 SDC disabled、BLE advertising
以及活动 BLE connection 下获得实板证据。直接 RADIO backend 与 Timeslot backend 应共享
packet-format 和计数逻辑，以便做可信差分。

### 6.5 明确不在当前范围内

- 开放 BLE Host、ATT/GATT、HID profile、用户态配对/绑定策略和产品协议；
- 继续扩充 S115/nRF-BM compatibility layer；
- GZLL；
- nRF52、nRF53、L15 consumer target 或其他 nRF54 器件支持。

现有 S115/HIDS oracle、L15 central、BlueZ 门禁、receipt、测试工具和结构化失败结论作为
历史诊断资产保留。根据 2026-09-06 用户授权，SDK compatibility layer 与专用等价审计工具
移至固定 Git 归档；官方 oracle、L15 central、通用测试工具与历史证据保留在当前树中。
这些资产不得成为当前 SDC/MPSL 路线的隐式前置条件。
自动 HID 测试仍不得向日常桌面注入危险按键序列。

## 7. 镜像、A/B 与安全启动的架构预留

这部分不是首次 blinky 的前置条件，但 linker/image API 从第一天起不能堵死它。

### 7.1 普通镜像

SDK 验证示例显式选择并输出以下产物；普通消费者按自己的构建与发布流程选择：

- `.elf`：含 symbols 和 DWARF，供调试；
- `.hex`：保留离散目标地址，作为默认烧写产物；
- `.bin`：与带布局绝对符号的 ELF 同时输出，仅用于外部打包；
- `.map` 和 section summary；布局由 ELF 中直接源于 MEMORY 的绝对符号表达；
- 可选合并 HEX，但每个输入 image 的来源/hash 可追踪。

### 7.2 A/B 策略

不能假设 LM20 有硬件地址 remap。仅修改 VTOR 不能重定位 `.text`、`.rodata`、函数指针、copy table 或 linker symbols。

因此显式支持两条路线：

- 固定执行地址：B 是 staging，验证后 swap/move/overwrite 到 A；应用只链接一次；
- Direct-XIP A/B：相同 sources 建立两个 CMake ELF target，分别使用 A/B origin，生成两个签名镜像。

不要把 PIC 当作默认方案。完整 position-independent firmware 对启动、C++、第三方库和绝对外设引用的验证成本更高。

多镜像组合使用普通、显式 CMake target；不同 ISA 的异构核可以使用独立 build tree 加一个很薄的 bundle target，但不得重新创造带隐式全局状态的 sysbuild。

### 7.3 安全与量产

- 可优先复用 MCUboot 的公开 image format、bootutil、安全检查和断电恢复逻辑；
- Nordic/Zephyr glue 只能作为移植参考，不得使最终 bootloader 依赖 Zephyr；
- CRACEN/KMU/RRAMC 驱动优先基于官方实现；
- production provisioning 与日常 SDK/测试必须物理和命令层隔离；
- regular CMake configure 不生成可写 OTP/UICR 的 target；
- 真正的 provision 工具必须另行显式启用，并始终要求人工授权和审计记录，不能成为无人值守任务的一部分；
- Direct-XIP 必须双链接；fixed-A staging/swap 不需要双链接。

## 8. 里程碑

### P0：官方可运行基线与设备工作流工具化

这是首个实施任务，必须在自研 startup/linker/runtime 之前完成。目的是先建立一条已由官方固件验证的端到端真值链，后续任务只替换 firmware provider，不重新发明探针选择、地址审计、烧写、串口和 GDB 流程。

设计 P0 工具前，必须先阅读 `docs/development-inputs.md` 和本机 `.local/AVAILABLE_INPUTS.md` 中列出的相关只读实现参考。参考重点包括：官方工程的显式准备与可运行 oracle、稳定公共 CLI、CMake/ELF 绑定的 manifest、地址与擦写范围审计、不可变烧写快照、动态探针选择、硬件锁、timeout、进程组清理、结构化结果和“基础设施失败先修工具”的工作方式。私有参考只提供设计经验，不授权复制其名称、路径、产品假设、文字或代码到公开仓库。

固定两个官方 oracle：

1. 必选基线：NCS `v3.4.0` 的 `zephyr/samples/hello_world`，board target 为 `nrf54lm20dk/nrf54lm20a/cpuapp`；
2. 第一条稳定后执行：NCS Bare Metal `v2.0.1` 的 `samples/peripherals/leds`，board target 为 `bm_nrf54lm20dk/nrf54lm20a/cpuapp/s115_softdevice`；它用于同时验证 bare-metal 官方封装、SoftDevice 组合镜像和日志串口。

两个 oracle 均允许使用官方原生构建流程，但只能由显式的 `reference` 子命令调用。第二个 oracle 不使用 MCUboot 变体，不允许密钥 provisioning，也不允许因为 readback protection 报错而自动 `recover`。

交付：

- 一个稳定公共 CLI `tools/nrfkit`，至少提供 `doctor`、`reference prepare`、`reference build`、`inspect`、`flash`、`reset`、`run` 和 `gdb-smoke`；对外文档只依赖这个入口，内部按 project/reference/image/device/process 职责拆分；
- `docs/development-inputs.md` 定义公开的输入接口，`.local/AVAILABLE_INPUTS.md` 记录当前机器的实际输入；工具只读取本地清单作为显式开发者上下文，不能把其中的路径或私有标识复制到 tracked 输出；
- 在 gitignored 的 P0 工作记录中确认已检查本地输入清单列出的相关实现参考；公开设计说明只记录采用的通用机制、理由和本项目实现，不出现参考仓库身份；
- tracked 的官方来源锁定文件，记录 release/module commit、sample、board target、必要源文件 hash、期望启动 token 和产物选择规则，但不记录本地绝对路径；
- `reference prepare` 显式验证用户提供的 NCS root 及各 Git module identity，生成 gitignored 的本地 source receipt；普通 CMake configure/build 不得复制、修补、解压或下载官方 SDK；
- `reference build` 将官方命令及环境限定在 `.work/reference/`，验证完整构建成功后生成 machine-readable image manifest；不从文件名或目录名猜测主产物；
- image manifest 绑定 schema、oracle ID、source receipt hash、ELF/HEX hash、ELF entry/load ranges、HEX ranges、SoC/core/board、可写 allowlist、期望串口 token、VCOM role 和 backend 参数；本地路径可出现在 gitignored manifest，不得进入 tracked 文件；
- `inspect` 同时审计 ELF program headers 与所有 Intel HEX records，并在与 manifest 或硬编码禁止区域冲突时 fail closed；
- `flash` 必须从已验证 manifest 建立只读产物快照，动态枚举且锁定唯一探针，显式指定 family/core，并使用 `nrfutil device program --options chip_erase_mode=ERASE_NONE,verify=VERIFY_READ,reset=RESET_NONE`；绝不调用 `west flash`、mass erase 或 recover；
- `run` 编排 doctor/build/inspect/flash/serial-ready/reset/wait-token 流程，通过 `nrfutil device list --json` 与板级 VCOM 契约选择串口，不硬编码 `/dev/ttyACM*`；解析器必须按 JSON Lines 事件流读取 nrfutil 输出，不能假定 stdout 只有一个 JSON object。烧写保持 target 不复位，串口读取进入 ready 状态后才单独 reset，防止漏掉一次性启动输出；必须用限时内观察到的 token 判定运行成功，不以烧写工具返回 0 代替运行证据。两个首批 token 分别为 `Hello World! nrf54lm20dk/nrf54lm20a/cpuapp` 和 `LEDs sample initialized`；
- `gdb-smoke` 用本机 GDB client 与 SEGGER J-Link GDB Server 执行最小自动验收：连接、reset halt、读 CPUID/PC/SP、在 `main` 停止、单步、detach 并清理 server；
- `doctor` 必须分别报告 CMake/Ninja/west、官方 toolchain、nrfutil/J-Link server 和本机 Arm GDB client；west 与官方 toolchain 只服务 reference build，GDB client 不得从 NCS build environment 隐式借用。若本机没有 `arm-none-eabi-gdb` 或 `gdb-multiarch`，P0 应安装并锁定一个校验过 hash 的用户级 Arm GNU Toolchain/GDB，且不能把下载动作放进普通项目 configure/build；
- 每次操作写入独立的 `.work/runs/<id>/run.json` 和进程日志，记录产物、源码、工具版本、各阶段状态、timeout 和必要的 recovery 结果；nrfutil 必须显式使用 stdout 日志并由 runner 收集，不能把默认日志散落到用户目录。子进程使用 argv 而不是 shell string，在独立 process group 中运行，超时或异常时终止整个进程组；报告以原子替换写入。串号和本地路径只能保存在这些 gitignored 本地文件中；
- 对 HEX 解析、越界拒绝、多探针歧义、命令参数、锁、timeout、原子 JSON 报告和失败清理建立无硬件 host tests；
- 任何为建立 ground truth 而成功执行的手工构建、烧写、复位、串口或 GDB 命令，都必须在同一任务内固化到公共 CLI、测试并通过该 CLI 重跑；不能只留在 shell history、聊天记录或一次性脚本中；
- 最小 README/工作流文档、`.gitignore`、自有工具代码的 BSD-3-Clause `LICENSE` 和 SPDX headers。

退出条件：

- 在连接的 nRF54LM20 DK 上，两个 oracle 均由公共 CLI 从已锁定官方源构建、审计、安全烧写、复位，并通过串口 token 验证；
- 必选 `hello_world` 基线连续运行 3 次全部 PASS，每次产生可审计报告；
- GDB smoke test PASS，且进程、串口和 lock 无泄漏；
- 两个官方 oracle 的日常复现只需要公共 CLI，不再依赖维护者记住或重新推导底层 west、nrfutil、串口和 GDB 命令；
- 安全负向测试证明 UICR/SICR/OTP/KMU/BOOTCONF/越界 RRAM record 在 vendor tool 启动之前被拒绝；
- 全流程没有 mass erase、recover、provisioning、板载探针固件更新或一次性区域写入；
- 在一个不含 NCS 环境变量的 shell 中，普通 consumer CMake 路径不会触发任何官方参考流程；
- tracked 文件、Git diff 和准备提交的 commit message 通过私有名称、本地路径、探针序列号和原始日志泄漏扫描。

P0 于 2026-09-04 完成退出审计。公共 `p0-gate` 从锁定来源连续完成三次 hello-world exact-token PASS、一次 Bare Metal + S115 exact-token PASS，以及带 exact-token 验证的 GDB smoke PASS。所有烧写均使用 `ERASE_NONE`、`VERIFY_READ` 和 `RESET_NONE`，串口、GDB server 与探针锁均完成清理。已确认该 J-Link OB 同时暴露 MSD 与 VCOM 时会丢失启动字节；初始诊断使用了固定、可恢复的临时 MSD 事务。随后用户单独授权该受影响探针长期保持 MSD disabled，公共 `probe-msd` 工作流负责完整本机备份、固定 `MSDDisable`/reboot 和 J-Link + 双 VCOM 读回验证，后续 gate 在该状态下不再修改持久配置。此决定只适用于经验证且不需要拖拽烧写的本机探针；恢复 MSD 需要新的明确授权。host 负向测试、公用内容泄漏扫描及离线 consumer configure/build 门禁通过；未执行 mass erase、recover、provisioning、保护设置、板控器固件更新或一次性/配置区域写入。

### M0：仓库、来源与设计冻结

交付：

- 补全 README、贡献约定和对外项目说明，审核 P0 已建立的 Git/许可证基线；
- 建立上述目录骨架和最小 CMake package；
- 完成 startup/linker/MDK/nrfx/SoftDevice 的来源及许可证审计；
- 创建 `sources.lock`、SBOM 初稿、support matrix 和决策记录；
- 记录本机工具预检脚本，但不记录探针序列号；
- 建立公开内容泄漏扫描。

退出条件：

- startup/linker 是否有官方独立文件有可复核结论；
- 所有计划导入项许可证明确；
- `cmake --find-package` 或最小 consumer configure 可运行；
- configure 不访问网络、不读 NCS、不要求 west；
- public hygiene test 通过。

M0 于 2026-09-04 完成退出审计。独立检查确认 nrfx v4.5.0 已为 LM20/L15 提供官方 GNU startup 与 per-device linker script，取代了早期“只能采用 TF-M C startup fallback”的假设；精确 tag/commit、MDK 版本、文件 hash、许可证、导入状态和搜索结论已锁定。NCS v3.4.0 与 Bare Metal v2.0.1 继续作为已验证 oracle，不随 nrfx 候选升级。README、贡献约定、support matrix、ADR、SPDX SBOM 初稿和 host doctor 已建立；source-tree 与 installed package consumer 在故意无效的 NCS/Zephyr 环境路径下仍可离线 configure/build。34 个 host tests、SPDX 2.3 validator、JSON 校验、public hygiene 与 diff check 全部通过，两份官方来源 receipt 在扩展后的 `sources.lock` 上重新生成并成功构建。

### M1：LM20 freestanding ELF 与链接契约

交付：

- Clang/LLD toolchain；
- CMSIS/MDK、官方 `SystemInit`、startup/vector/fault runtime；
- LM20 linker layout 和 C/C++ runtime initialization；
- blinky/empty/fault/C++ constructors 示例；
- ELF/HEX/BIN/map/layout manifest；
- readelf/objdump/linker assertion 测试；
- 与同版本 NCS 参考 ELF 的结构对照报告。

退出条件：

- 两个不同绝对 build 路径构建得到可复现的 load image；
- vector 数量、顺序、地址与官方来源一致；
- `.data`、`.bss`、`.noinit`、constructors、stack/heap 全部通过 host 检查；
- 产物扫描确认无配置区 record；
- GNU Arm 编译至少能完成 compile/link smoke test，功能验证仍以 Clang 为主。

M1 于 2026-09-04 完成退出审计。CMSIS 6.3.0 与 nrfx 4.5.0 的 LM20A MDK、官方 GNU startup 和 `SystemInit` 子集已按逐文件来源、SHA-256、许可证和未修改状态导入；Clang/LLD 为主路径，GNU Arm 完成独立 compile/link smoke。四个示例均生成 ELF、HEX、BIN、map 和 layout manifest；两处不同绝对 build 路径的所有 load image 逐字节一致。host 合约确认 306 项 vector 的位置和地址与最新 startup、设备头、SVD 一致，并记录 NCS v3.4.0 TF-M 的旧版命名差异；`.data`、`.bss`、`.noinit`、C++23 constructors、16 KiB stack、零 heap、fault record 和越界 linker assertion 均通过。所有 ELF/HEX load ranges 通过公共配置区 guard，两份锁定 oracle receipt 已随新 `sources.lock` 重建并复编成功。共 43 个 host tests、SPDX validator、JSON、public hygiene 和 diff check 通过。M1 只宣称 host/build contract 完成，自研镜像的实板证据属于 M2。

### M2：LM20 实板启动、烧写与 GDB

交付：

- 将 P0 的安全探针发现、image guard 和 nrfutil backend 接入自研 SDK manifest，不建立第二套烧写脚本；
- 在 P0 J-Link/GDB smoke 之上增加面向自研 runtime 的 batch GDB 契约测试；
- LED、VCOM UART 和可选 RTT 输出；
- reset reason 与 fault capture；
- CTest `hardware` labels、锁、timeout 和结构化日志。

退出条件：

- 在不 mass erase、不写 UICR/SICR/OTP 的前提下连续烧写/验证/复位 20 次；
- 每次都收到匹配当前 build ID 的 boot token；
- GDB 能在 Reset Handler/main 停止、单步、读写 RAM 和观察变量；
- 故障后脚本能恢复正常 test image；
- 日志无探针序列号进入 tracked 文件。

M2 于 2026-09-04 完成退出审计。自研 SDK 的 ELF/HEX/layout artifacts 通过 `sdk manifest` 接入 P0 的同一套地址 guard、不可变 snapshot、唯一探针选择、锁和 nrfutil `ERASE_NONE` backend；没有引入第二套烧写脚本。硬件验证固件使用已锁定的官方 DK pinctrl 事实驱动 LED0 和 VCOM1/UARTE20，输出包含当前 build ID 的精确 boot token，并保留 reset reason、main 状态和可写 RAM 观察量。正式 `m2-gate` 在连接的 PCA10184 上连续完成 20 次安全烧写、读回验证、独立复位和 token 检查；batch GDB 在 Reset Handler 与 main 停止、完成单步和 RAM 读写，并观察到 reset/main 状态。故障镜像触发 HardFault 后记录了预期 magic 与 fault PC，门禁 cleanup 随后恢复正常镜像并再次通过 token。CTest 的 `hardware` label、板级资源锁、2400 秒外层 timeout 和逐子进程结构化日志已验证；47 个 host tests、两个锁定官方 reference rebuild、public hygiene 和 diff check 全部通过。所有探针身份和原始日志仅位于 `.work/`。

### M3：nrfx 与低功耗基础

交付：

- target-scoped `nrfx_config.h` 生成；
- clock、GPIO/GPIOTE、GRTC/TIMER、DPPI、UARTE；
- SPIM/TWIM/PWM/SAADC/RRAMC/watchdog/reset helpers；
- RAM bank/section retention API 与文档；
- 资源冲突检查和 IRQ glue；
- 每项至少一个最小示例和实板测试。

退出条件：

- nrfx 中只编译被请求的 sources；
- 两个不同 driver 配置的 firmware target 可在同一 build tree 共存；
- sleep/wake、timer 精度、DMA、IRQ 和 retained/noinit 行为通过实板测试；
- RRAM scratch test 遵守写次数限制；
- 不使用任何 Zephyr header、symbol 或 generated file。

M3 于 2026-09-04 完成退出审计。nrfx v4.5.0 现以精确 commit 的只读 submodule 提供，完整源码树不再作为本仓库普通文件导入；target-scoped 配置只编译所请求的 driver source，项目补丁在 consumer build tree 的共享缓存中应用。实板证据确认 nrfx 的 GRTC legacy setter 在该 LM20 上需要显式恢复 `CCEN`，因此加入了同时由 Datasheet 寄存器语义与最小实板复现支撑的补丁，没有把库实现当成硬件规范。core 验证覆盖 clock、GPIO/GPIOTE、GRTC/TIMER、DPPI、UARTE、IRQ、timer 精度与复位后 `.noinit` retention；peripheral 验证覆盖 SPIM、TWIM、PWM、SAADC、RRAMC 与 watchdog，并只在保留的 256-byte RRAM scratch 区追加一个 16-byte 记录；power 验证覆盖 100 ms GRTC System ON 睡眠/中断唤醒与 RAM retention。三份最终硬件报告 `.work/runs/20260904-120941-run-1069062/run.json`、`.work/runs/20260904-120952-run-1069135/run.json` 和 `.work/runs/20260904-121003-run-1069212/run.json` 均为 `ok`。真实 System OFF 未被宣称通过：Datasheet 明确说明 Debug Interface mode 下 System OFF 会被仿真，当前工作流保持调试连接；其 detached wake 验证留给能够先退出 DIF 的后续工作流。51 个 host tests、public hygiene、diff check、source-tree/installed package 以及同树双 nrfx 配置全部通过。

### M4：USBHS device

交付：

- 官方 USBHS 行为/errata 审计；
- 一个独立 USB device stack port；
- control/bulk/interrupt endpoint 测试设备；
- HID 示例与 host-side 自动测试；
- suspend/resume/remote-wakeup 测试。

退出条件：

- 100 次拔插或等价受控 reconnect 测试无死锁；
- 长时间 IN/OUT 压力无数据错误；
- HID、低功耗和其他 nrfx 模块可共存；
- 不存在只为一个下游项目写死的 API。

M4 当前已完成 CherryUSB v1.6.1 DWC2 device port、control/bulk/HID 验证固件、
host-side gate 与来源审计。port 的接口组织遵循 CherryUSB 官方移植文档，并对照该
版本较新的 ESP、HC、Kendryte、Nation 和 ST glue；Nordic NCS 仅作为版本化比较
证据，寄存器语义和 FIFO 选择以 LM20 文档、DWC2 capability register 与可复现
实板行为为准。最终镜像已在 HS 下完成 100 次受控 reconnect 和 60 秒双向压力，
331883 次传输、每方向 169924096 bytes 均无错误，HID 与 nrfx TIMER 同时工作；
Other-Speed descriptor 也已实读确认其 full-speed bulk MPS 为 64。M4 尚未标记完成。
root-capable `m4-usb-power` 已将普通 host-initiated resume 与 device-initiated
remote wake 拆成独立结构化阶段；前者在实板上通过，固件 suspend 和 resume 计数
各递增且没有重新配置。后者在当前多级 hub 路径上成功执行 CherryUSB remote-wakeup
API，但 xHCI 随后 reset 并重新枚举设备，固件没有收到 resume 事件。因此现有证据
已把问题限定在 device-initiated resume 信号或 USB 拓扑传播，而不是普通 DWC2
resume 路径；仍需在不会重置设备的直连拓扑上得到完整成功报告，不能用
`--skip-power` 或仅 host-resume 通过的报告替代。

### M5：direct-RADIO 基线与双板工具（已收束）

此里程碑只建立独占 RADIO 的底层真值与可复用双板执行器，不宣称与 BLE 共存，也不以
尚未执行的双板空口测试冒充实板互通完成。

已交付：

- RADIO + TIMER10/DPPIC10 packet engine、cooperative ownership 与 1/2 Mbit/s 配置；
- host packet/config/状态机测试和 LM20 单板定时 TX 实板证据；
- LM20/L15 TX/RX validation firmware、版本锁定的官方 L15 peer build profile；
- 公共双板 CLI、独立探针选择、镜像/地址审计、双锁、硬超时、进程组清理、方向/轮次
  编排、payload/序号/CRC/无效包统计及结构化报告；
- 对 RX 丢包时 deadline、无符号 timeout 下溢和“等待全部包”死锁风险的修正。

这些资产转为 M7 的 direct-RADIO 差分基线。4 Mbit/s、双向互通、CRC/白化负向、重试、
soak、睡眠后接收、性能/功耗与 MPSL 共存仍未宣称通过，必须在 M7 产生真实双板证据。

### M6：SoftDevice Controller（当前）

M6 先完成文档与资源契约，再写平台适配或上板。必须完整阅读版本锁定的
`sdk-nrfxlib` SDC/MPSL README、API 文档、integration notes、release notes、component
manifest、license/attribution，以及其明确列出的占用外设、IRQ、优先级、时钟、内存、
链接、初始化顺序和调用上下文。把这些要求固化成带来源定位的机器可检查
resource/ABI contract；若尚有不确定项，不得用反复烧写猜测。

M6 的文档/资源契约阶段已完成：锁定版 SDC/MPSL 的 RST 文档、限制、changelog、
公开 headers、manifest、license/attribution 已按完整树摘要审计，LM20 外设/IRQ/channel
mask、128 MHz 与 GRTC/SYSCOUNTER 前置条件、LF/HF clock、低优先级与 callback context、
低延迟回调、初始化/teardown、entropy、fault、8-byte Controller memory alignment 及三种
SDC archive 的 hard-float ELF/link closure 已进入机器可检查 contract。官方 NCS v3.4.0
`hci_uart` oracle 已由公共 reference workflow 重复构建，配置和最终 map 证明实际链接
hard-float Multirole SDC 与匹配的 MPSL；生成的 ISR 表进一步确认 TIMER20 IRQ 202 与
ECB00 IRQ 75 均未注册并保持 spurious，而 TIMER10、GRTC_3 和 RADIO_0 绑定公开 MPSL
handler。oracle 已通过 guarded `ERASE_NONE`/read-back 编程、HCI Reset/version/features、
BlueZ 实际发现其 advertising、由 Controller 实际扫描确定性 host peer，以及独立锁定 GDB
的 main breakpoint/单步/CPUID 门禁；所有临时 advertising/scanning、VCOM 与 GDB server
均完成清理。该结果尚不等于平台适配完成；下一步以同一 contract 实现纯 CMake 底座。

交付：

- 校验 `external/sdk-nrfxlib` submodule，并在 `sources.lock` 锁定 tag、commit、SDC/MPSL binary manifest revision、
  所选 headers/archives/license/attribution hash、安全域与 float ABI；
- 对 nrfxlib v3.4.0 与当前 nrfx v4.5.0 执行头文件 API、ELF attributes、undefined symbols、
  link closure、startup/IRQ、内存对齐和资源占用兼容审计；不按系列名假定兼容；
- 先用 NCS v3.4.0 `zephyr/samples/bluetooth/hci_uart`、board
  `nrf54lm20dk/nrf54lm20a/cpuapp` 建立可运行 Controller oracle；配置与 build receipt
  必须证明实际选择 SDC Multirole archive，而不是另一个 Link Layer。先通过公共工具完成
  reference build、manifest、guarded flash、H4/HCI 观测和 GDB，再开始纯 CMake 适配；
- 满足 SDC 所需的最小 MPSL platform substrate，包括文档要求的 IRQ/priority、clock、
  GRTC/timer、低优先级执行、128 MHz/低延迟请求回调、entropy、assert/fault、8-byte
  aligned memory 和 resource configuration；
- 显式 CMake imported targets 与 consumer API，不自动发现 NCS，不引入 west、sysbuild、
  Kconfig、Devicetree 或 Zephyr；
- 独立、确定性的 raw-HCI harness；Multirole 第一，随后 Peripheral-only 与 Central-only；
- map/ELF/resource/ABI host gates，以及 bounded real-board lifecycle 和无线行为报告。

退出条件：

- 文档中的所有 required/owned peripheral、IRQ、priority、clock、RAM/flash、alignment、
  callback context 和 teardown 约束均映射到代码与自动检查，不存在未解释的资源借用；
- 官方 oracle 经统一工具重复构建、地址审计、安全烧写、运行观测和 GDB；
- oracle 的 HCI transport 通过 Reset/version/features 和至少一次 advertising/scanning
  行为验证，构建证据明确指向锁定版本的 SDC Multirole 与 MPSL；
- Multirole 在 LM20 上通过 HCI Reset/version/features、enable/disable/re-enable、advertise、
  scan、peripheral accept、central initiate、disconnect，以及 raw HCI event/ACL 路径；
- Peripheral-only 与 Central-only archive 分别在同一底座上通过其适用能力子集；
- 每种 archive 的最终 map、RAM budget、MPSL/SDC resource config、stack watermark、assert/
  fault 和重复运行结果可审计；
- 没有 Host、ATT/GATT/HID profile，也没有 S115 compatibility shim 被偷偷带入。

M6 于 2026-09-05 完成退出审计。纯 CMake consumer target 只链接锁定的 secure
hard-float MPSL、FEM common closure archive 和显式选择的 Multirole、Peripheral-only
或 Central-only SDC archive；普通 configure/build 不读取 NCS、west、Kconfig、Devicetree
或 Zephyr。最小平台底座实现并自动检查 GRTC/SYSCOUNTER、128 MHz、IRQ/priority、LF/HF
clock、低优先级串行执行、嵌套低延迟、CRACEN entropy、同步 disable、fault reset 与资源
所有权。最终 map hash、完整资源表和 ELF RRAM/RAM/16 KiB stack 预算进入每份 guarded
manifest；运行期另报告 8-byte aligned Controller buffer 的实际需求、前后 canary、栈水位和
fault 状态。

最终同一提交的三种归档各连续运行三次全部 PASS。Multirole 实测 Controller memory 为
3312 bytes，Peripheral-only 为 1496 bytes，Central-only 为 1520 bytes；三者观测栈高水位
均为 1168 bytes，所有 canary 完整且无 MPSL/SDC/UART fault。Multirole 完成
enable/disable/re-enable、Reset/version/features、可连接广播与 Peripheral accept、扫描与
Central initiate、两种角色的主动 disconnect，以及双向 raw HCI ACL；两个裁剪归档分别完成
适用子集。最终独立 GDB 门禁也完成 main breakpoint、单步、CPUID、RAM 读写、detach 和
server cleanup。所有程序写入仍为普通应用 RRAM 的 `ERASE_NONE` + read-back，未执行 mass
erase、recover、provisioning、配置区写入或探针配置变更。112 个 host tests、public hygiene
和 diff check 通过。M7 从该已验证底座开始，不再以 direct-RADIO 冒充 MPSL 共存。

### 历史检查点：S115/nRF-BM（原 M6，已停止）

官方 nRF-BM v2.0.1 HIDS oracle 已通过配对、加密属性读取与 bonded reconnect；L15 S145
central 已验证 legacy/LESC no-bond、bonding 和持久化重连。纯 CMake strict application
保存了 273-source/43-nRF-BM-source、681-config、逐文件/命令/image hash、最小
shim/patch 清单以及唯一实板结果。最终分歧定位在官方 `irq_init()` 首日志可见之前或
`CallSoftDeviceResetHandler()` 返回之前；继续定位需要扩大 Zephyr pre-main lifecycle，
不再属于薄适配。

详细复现、证据边界和失败结果保存在
`docs/architecture/m6-official-baseline-failure.md`、
`docs/provenance/nrf-bm-hids-s115-equivalence.json` 和
`docs/provenance/m6-s115-equivalence-checkpoint.json`。compatibility layer 与专用审计工具仅在
[归档提交](../architecture/s115-archive.md) 中保留；L15 central 与有界 BlueZ 工具
继续作为诊断资产保留，不进入当前完成定义。
历史 JSON 保持不可变；新方向由 ADR 与本 PLAN 覆盖。该检查点既不证明 S115 不可用，
也不是 SDC/MPSL 路线的失败证据。

### M7：MPSL Timeslot 与 4 Mbit/s 优先私有 2.4 GHz

交付：

- 基于 M6 同一锁定 MPSL 的 Timeslot backend，与 M5 direct-RADIO backend 共享 packet
  format、vectors、counter 和判断逻辑；
- grant、blocked、cancel、extend、deadline、HFCLK、IRQ/DPPI 清理和异常 teardown 测试；
- LM20 与 L15 的 4 Mbit/s TX/RX profile 及双向已知载荷公共 gate；
- 4 Mbit/s 首要门禁，以及 2 Mbit/s、1 Mbit/s 兼容/差分基线；
- CRC/白化负向、序号/丢包、限定重试、信道切换、soak、睡眠后接收和功耗测试；
- SDC disabled、BLE advertising、活动 BLE connection 三种调度场景的结构化证据。

退出条件：

- LM20 与 L15 在 4 Mbit/s 双向交换已知载荷并至少连续重复三轮；两种 4 Mbit/s mode
  均有审计记录，默认选择有数据支持；
- CRC/白化错误被拒绝，counter 守恒，重试/队列有界，soak 和睡眠后接收通过；
- 4/2/1 Mbit/s 的 payload goodput、端到端延迟、丢包、重试开销、最短安全调度间隔、
  稳定性和可测功耗均由同一方法量化；最终目标以 4 Mbit/s 为首，不以 2 Mbit/s 替代；
- Timeslot 在 SDC disabled、advertising 和 active connection 下均遵守 grant/deadline，
  不直接碰触未获授权的 RADIO/timer/DPPI 资源；
- BLE connection 与私有链路的延迟/吞吐/功耗权衡可审计，无饿死、死锁或资源泄漏；
- 公共实现和 Git 历史不含 external reference peer 的私有名称、业务协议或本机标识。

M7 当前检查点：两种 4 Mbit/s mode 已完成 LM20/L15 双向三轮，BT=0.6 由数据选为
默认；CRC/白化负向、序号、限定重试、队列上界、四次信道切换、睡眠唤醒和 20 轮
soak 均通过。4/2/1 Mbit/s 已用同一 DWT/16-byte payload 方法量化。Timeslot backend
完成 grant/deadline/extend/blocked/cancel/close 清理，并在 SDC-disabled lifecycle、广播和
活动连接下通过；最终三轮双板共存门禁要求 L15 实收只在活动连接 burst 才会出现的
序号 15，同时 LM20 保持双向 raw ACL。完整公开结果在
`docs/provenance/m7-radio-evidence.md`。M7 尚未标记完成：2026-09-05 检查点的输入与 USB inventory 没有
PPK2、示波器、电流表或功率分析仪，官方 DK 测量流程要求外部仪器；已有 60.55% retry
reservation duty 和 11.27% 共存 burst duty 只是功耗代理，不能替代安培/瓦特/焦耳。

2026-09-05 后续审查回归已闭环：输入校验和 Timeslot 请求状态修复通过 121 项 host tests；
双向 Timeslot 与活动 BLE 共存各三轮通过。retry 根因是 ACK server 在 ACK 丢失后已经
推进序号、却不重放上一序号 ACK，导致 client 永久失步。peer 现在幂等处理合法重复包，
并以每轮一次 server-side commit 后 ACK 抑制强制覆盖该路径。当前镜像先通过三轮，再通过
20 轮 soak；每轮 64/64 完成、零 drop，且一次额外真实 ACK 丢失也成功恢复。详见上述
证据文档。M4 remote wake 与 M7 外部电气功耗由用户于 2026-09-05 明确暂缓，保留为未完成
退出条件，但不再阻塞其余里程碑推进。

### M8：首个私有下游集成与 LM20 release candidate

该里程碑在下游仓库中完成，但公共 SDK 只能记录匿名、通用的验收结果。

交付：

- 下游通过 `find_package` 或明确的 source integration 使用 SDK；
- SDK 不需要下游专属 fork；
- C++23、USB HID、SDC/MPSL、4 Mbit/s 优先私有 2.4 GHz、低功耗和普通持久化需求按实际使用范围打通；
- downstream build/test 脚本和日志保留在私有位置；
- 发布 `0.x` LM20 release candidate。

退出条件：

- 从干净 SDK checkout 和干净下游 checkout 可复现构建；
- 下游不依赖 NCS、west、sysbuild、Kconfig、Devicetree 或 Zephyr；
- SDK 当前文件、Git history、commit message、issue template、CI artifact 和 release note 均无私有下游标识；
- 实板主要工作模式通过长时间运行和切换测试。

M8 当前检查点：已完成公开侧的组合 consumer 前置门禁。source-tree 与 installed
`find_package` 两条离线路径均可把 C++23、CherryUSB HID、Multirole SDC/MPSL、Timeslot
和按生命周期隔离的普通 RRAMC 支持链接进同一 LM20 target，且 USB/SDC 两种 CMake
声明顺序等价。审计同时修复了 freestanding `string.h` 的 C++ 不兼容、USB 多余引入
nrfx CLOCK ISR 与 MPSL handler 冲突，以及协议栈运行时 USBHS 直接控制 HFCLK24M 的
所有权错误；组合目标现在通过 MPSL 公共时钟 API retain/request/release。实板组合镜像
在 SDC/MPSL 持续初始化时通过 20 次 USB 重连和 20.05 秒 control/bulk/HID 压力测试，
双向各传输 57,416,192 bytes、112,141 次 transfer，端点错误为零；本地报告为
`.work/runs/20260905-142022-m4-usb-gate-1056219/run.json`，remote wake 按用户决定跳过。
用户随后明确授权修改首个私有 consumer，并将首阶段范围限定为采用新板目录结构的机械
键盘开发 target。该 consumer 现已用自有 linker script 与配套 image-layout、Clang C++23、
NrfKit USB HID、Multirole SDC/MPSL、Timeslot 与生命周期分离的普通 RRAM 设置区完成
Release configure/compile/link；生成的 ELF/HEX 通过公共 guard，load image 未进入设置区或
scratch。公共 SDK 同时补齐可选 GNU Arm C++ headers/sysroot、consumer layout 派生 allowlist
以及 LTO 下 HardFault/Arm EABI symbol retention。此结果仍是 compile/link 与离线地址审计，
开发板 scanner 只使用已记录的少量 smoke input，并非产品矩阵。首次实板配置暴露了固定 USB
TX FIFO 只覆盖两个 IN endpoint 的公共 SDK 缺口；consumer API 现显式接收从 EP1 开始的最大包长，
据此计算、校验并生成 LM20 FIFO 分配。修复后的私有组合镜像以 High Speed 枚举为四个 HID
interface，端点最大包长依次覆盖 8-byte keyboard、64-byte 双向 configurator、32-byte shared
和 32-byte NKRO，并通过 100 次普通 USB reset/re-enumeration。该 consumer smoke 只使用标准
USB configuration/descriptor/reset 事务，不发送私有协议 payload，也不替代已延期的 remote wake
或 PPK2 证据。最终 ignored local report 绑定上述公共实现提交并记录 `sdk_dirty=false`；原始
报告不进入公共仓库。用户于 2026-09-05 明确决定跳过开发板 D4/D5 物理按键输入验证；该项
保持为未覆盖的产品引脚/扫描链路证据，但不再阻塞 M8 或后续里程碑。M8 下一项实板门禁改为
普通 RRAM settings 的受控修改、延迟 flush、SDC pause/resume、reset 后读回，以及不依赖
私有协议的长时间主循环/fault-state 观测。该门禁不得触及配置区、一次性区域或 protection
状态。下游于 2026-09-05 已通过自有板级门禁完成 settings 部分：2 秒提前检查仍有一个 dirty
block 且写入计数为零；正常 15 秒期限后恰有一次普通 RRAM program、一次 SDC pause 和一次
resume，三类失败计数均为零；临时 profile 经 reset 后读回成功，cleanup 再立即 flush、reset
并读回原 profile。随后 120 秒内完成 60 次 configurator 协议版本与原 profile 查询，无失联或
状态漂移。门禁使用公共 manifest guard、`ERASE_NONE`、read-back 和 reset，只覆盖普通应用
RRAM；ignored local report 记录了中断恢复与最终 cleanup 成功，原始报告不进入公共仓库。
这组查询仍属于下游协议观测，因此另以公共 GDB workflow 对持续运行中的同一镜像做只 attach、
不 reset 的独立快照：PC 位于主循环，毫秒时钟已达到 250510 ms，通用 fault record 与 SDC
fault record 均为零；workflow 随后恢复 target 运行、detach 并确认 GDB server cleanup。至此
settings 与协议无关长稳/fault-state 门禁均已完成。随后从独立、干净的下游 checkout 初始化
全部锁定 submodule，并显式提供已按 lock 准备的 host tool 依赖；CMake configure/build 未运行
包管理器、未访问网络，也未修改 source tree。该 checkout 完成完整 Release app 构建，生成的
manifest 与 image-layout 检查通过，构建后主仓库与所有 submodule 仍为 clean。至此 M8 技术
集成门禁已完成。
RC 版本准备已把 `include/nrfkit/version.h` 设为唯一版本来源；根项目、source-tree
package 与 installed package 会从同一组 numeric/full version 生成并由离线 consumer
门禁交叉验证。首个版本选择为 `0.1.0-rc.1`：`0.x` 保留实验性 API 边界，prerelease 明确
表示 remote wake、外部仪器功耗和产品按键矩阵不在已声明证据内。SPDX SBOM、README、
changelog、CMake package 的 numeric/full version 已保持一致。CPack TGZ 安装归档包含项目
许可证、发布说明和支持所需的 nrfx、CherryUSB、SDC/MPSL 闭包；固定
`SOURCE_DATE_EPOCH` 的两次独立打包 SHA-256 相同，解包后 consumer 在故意污染的
NCS/Zephyr 环境变量下仍能离线 configure/build。`0.1.0-rc.2` 发布前 host suite 为 131/131，
SPDX 2.3 validator、public hygiene 与 diff check 通过；两次精确发布归档逐字节一致，SHA-256
为 `b99fcbb42414cf6ddc234aca76c491c02af02d8e742edec1db76f724d81ba0e7`。签名 tag
`v0.1.0-rc.2` 固定到提交 `0eac727a9df47b996557c347e4dc01a00331906d`，已验证为 Good
signature，并与公开 `main` 一同推送到 GitHub。经用户明确决定，另建 GitHub 托管 release
及上传归档附件不属于退出条件；可复现归档、校验文件和结构化验收报告保存在 ignored local
release evidence 中。至此 M8 完成。
旧签名 tag `v0.1.0-rc.1` 继续固定在原验收提交；其后的 SDC/GRTC cold-start 修复仅进入
`v0.1.0-rc.2`，未移动或重写旧 tag。
安装前缀也已从复制完整 nrfx/CherryUSB checkout 收束为 LM20 支持所需的 nrfx
driver/header closure、CherryUSB core/HID/DWC2 closure 与锁定的 SDC/MPSL selection；
无关 demo、host tool、bundled third-party example 和 Zephyr/Kconfig glue 不进入 RC 包。
从当前提交新建、不共享工作树状态的 SDK checkout，并在其中检出三份精确锁定 submodule
后，M8 组合 consumer 已重新完成 C++23 configure/link，且 checkout 保持 clean；因此
“干净 SDK checkout”公共侧已由实际克隆验证，而不是由原工作树构建替代。下游 checkout
也已按上述边界完成独立复现；实板主模式的 settings、长稳与 fault-state 验收均已完成。

### M9：boot/DFU 与 production 支持

用户已说明首个私有 consumer 有自有 bootloader；因此当前不以尽快接入 MCUboot 为目标。
M9 先对该实现与下列交付/退出条件做能力和做法差距审计，再决定复用、修正或替换。该审计
不提前于 M8 的 application 主模式实板验收，也不把 bootloader/DFU 变成当前机械键盘
bring-up 的阻塞项。

交付：

- consumer 自有的单槽明文 RRAM 布局与 vector-last 原子有效性发布；
- 有明确能力审计和取舍依据的自有 bootloader；
- 统一的签名加密传输容器、版本策略和掉电恢复测试；
- 明确的 rollback 与存储/调试保护策略；只有能减少可提取 key 或落实该策略时才接入
  CRACEN/KMU，不为形式上的平台集成增加实现层次；
- 独立的、默认不可达的 production provisioning 工具设计。

退出条件：

- 仿真和实板 fault-injection 覆盖更新关键点；
- 在线传输中的非法、损坏镜像被拒绝，降级镜像按明确选择的 rollback policy 处理；
- linker、写入范围与首个 commit unit 的最后发布共同保证无效或中断镜像
  不会启动；
- 日常 CI 仍不能写任何一次性区域；
- 实际 provision 只有在用户另行明确授权后才可执行，因此不属于本计划的无人值守完成条件。

M9 完成结论：对首个私有 consumer 自有 bootloader 的审计结论是优先复用和修正，
MCUboot 不是机械键盘首阶段的前置条件。已有实现具备签名并加密的 RAM maintenance
program、分块认证、完整解密 payload hash、产品 target 约束、WebHID transport 与受限 platform
service ABI；USBHS 更新全链路和 reset 中断恢复已经通过实板门禁。rollback policy 已明确为
不设置版本下限：正确签名的旧 updater/application 允许安装，`security_version` 仅保留为认证
metadata，不增加持久 floor 或硬件 monotonic state。真实供电切断 fault injection 已覆盖
三个未发布状态并全部恢复。trust root 和持久芯片保护明确属于默认不可达、
需单独授权的量产 provisioning，不进入 bootloader。应用、bootloader、
settings 与 scratch 的 linker script 和配套 image-layout 由 consumer 维护，公共 SDK 只负责
验证声明的边界与禁止区域，不把产品布局固化为 SDK 默认值。LM20 的传输层解密结果就是
写入普通 RRAM 的明文应用；当前范围不为其他平台引入存储格式或执行时解密抽象。

不依赖 LM20 实板的共享加固已开始完成：USB reset/disconnect 会使 maintenance session
换代并在中断外清除 loader、manifest、crypto、receive 和 storage transaction；terminal
response 增加 500 ms 有界 drain，超时只重启 transport，不执行尚未可靠回传结果的 reset
或 launch。另已建立 fail-closed Cortex-M vector contract，主机测试覆盖 image/alignment、
8-byte MSP、RAM 边界、Thumb bit 与 reset target 范围。共享层 16 项 host tests 通过，既有
另一目标 Release bootloader 仍能交叉链接。RAM maintenance program 继续使用既有 platform
service C ABI；loader 现按 target 声明的入口地址 mask 在 load-begin 拒绝 ISA 不兼容的
签名 manifest，LM20 要求 Thumb bit，既有 RISC-V target 要求 bit 0 清零。RAM upgrader
也已复用 USB session epoch 和有界 terminal-response drain：断线或 bus reset 会 abort 当前
update，reset response 不再可能无限等待。

LM20 的 opt-in bootloader/updater 构建与打包已完成，不增加新的用户配置层：consumer 只需打开
现有板级 opt-in。删除持久应用签名设计后，
Release 链接结果占 19,084 bytes RRAM；在暂定 128 KiB boot 区中余 111,988 bytes。boot 自有静态数据按对齐占 6,448 bytes；在低
64 KiB RAM 区中余 59,088 bytes。64 KiB direct-load program 区与顶部 16 KiB stack 由 linker
断言保持分离，因此 direct load 作为当前工作选择，不同时实现 persistent staging。构建读取
ignored `manufacturing/secrets.toml`，bootloader 只嵌入产品加密密钥和 publisher 公钥；同一
测试专用 key source 由既有 host packer 生成真实签名加密 `.rprog` 与 `.appimg`，没有跳过认证路径。
consumer linker script 已把这个全新板的应用迁移到暂定 `0x00020000`，不保留 legacy image
兼容路径；143,872-byte 应用到 `0x001f4000` 保护边界仍有 1,773,056 bytes 余量，之后保留
3840-byte 空隙再进入既有 settings。匹配的 image
layout 也由 consumer 维护，Release 链接确认 vector 与所有 load segment 均位于新应用范围。

LM20 bootloader 启动时只验证 vector 所表达的事务有效性、MSP 对齐/RAM 范围与 reset
target Thumb bit/应用范围，随后清理 SysTick/NVIC 状态，恢复 mask/control 状态并设置
VTOR/MSP 后分支。Release disassembly 确认最终 trampoline 是 `LDR` vector、`MSR MSP`、
`CPSIE I`、`BX` 的固定短序列。应用通过固定的一次性 RAM request 请求 maintenance，
bootloader 消费前先清除；无效 vector 进入 maintenance。2026-09-05 的受控实板门禁已验证
bootloader 到重定位应用的交接，应用协议版本为 38；门禁随后恢复地址 0 的原应用并再次
验证同一协议。全过程只经公共 guard 写普通 RRAM，没有触及配置、OTP 或保护区。按用户选择，
首版不实现 rollback floor；host tests 明确接受 `security_version=0` 的有效签名 updater 与
application。无效签名、密文认证失败和 payload hash 不匹配仍照常拒绝。

已以锁定 NCS v3.4.0 中 MCUboot commit
`c1d2d128a001a97db3ccfd66be524c0232094df6` 做了有界对照。当前方案只采用三项原则：候选
镜像在发布前完成认证、更新事务的有效标志最后写入、写入路径受到约束时普通启动无需重复
publisher signature。MCUboot 自身也允许关闭 `MCUBOOT_VALIDATE_PRIMARY_SLOT`；其双槽、
swap/trailer、revert、TLV image header、Zephyr glue 和 serial recovery 不符合当前 LM20
“单槽明文 RRAM + maintenance 可恢复”的产品选择，不引入。由此停止扩展 MPC/GDB 专用 gate。
测试 key 的完整构建、打包与 host container 传输检查已完成；signed RAM updater 与加密
`.appimg` 的端到端实板更新也已闭环，不继续搭建调试器恢复编排。

应用更新无需另造一套事务框架：现有 updater 已把首个 update unit 缓存在 RAM，在完整
image hash 成功后才最后写回。内部 handoff ABI v2 以 application-storage 语义提供
`prepare_application_update` 与 `program_application`：Flash target 仍擦除完整应用范围，
LM20 则只覆写并读回首个 16-byte vector data unit，使应用在任何 body write 前不可启动。
LM20 的板级实现直接检查完整声明范围和 16-byte 对齐，不引入只有一个调用者的通用 RRAM
service 抽象；bootloader/settings/scratch 和配置区均不可达。最终 4 KiB 写入由板级 service
按 `+16..+4095`、最后 vector data unit 的次序发布，保证其余首个 commit unit 已落盘后才
恢复 vector。官方 Datasheet 要求的 buffered commit、buffer-empty、READY、POF abort、有界等待与
read-back 继续由既有 RRAM writer 提供；共享 host fault injection 覆盖 prepare、body 和最终
发布调用边界。受控实板门禁还分别在认证 manifest 已使 vector 无效后、以及 5 个认证 chunk
跨过首个 4 KiB commit unit 后执行外部 reset；两次均回到 bootloader maintenance，重新认证并
加载同一 updater 后完成更新。物理断电门禁又在 prepare 后、5 个 chunk 跨过首个 4 KiB 后、
以及全部 147 个 chunk 写完但尚未发送 finish 的发布前状态切断主板和目标 VBUS；三次冷启动
均只进入 idle maintenance，且都能重新认证并加载 updater。门禁按目标 VBUS 先断、主板后断，
主板先恢复并稳定后再接 VBUS，避免通过第二根 USB 线形成不完整上电。该门禁不会声称以
uhubctl 的时间精度命中最后 16-byte 写入内部；最后发布失败由 host fault injection 覆盖，
而实板证明确认任何尚未开始发布的完整 body 都不能启动。

在线 `.appimg` 仍是所有板共用的签名加密传输容器；LM20 updater 验证 publisher signature、
每块密文认证和完整 payload hash 后，把明文应用写入 RRAM。持久化应用不重复保存 publisher
signature，不保留 storage-mode 或 EXIP 字段，也不在应用 linker 中预留专用 header hole。
启动只依赖 vector-last 事务：更新开始先使首个 16-byte vector data unit 无效，body 与其余
首个 commit unit 写完且在线 payload hash 成功后，最后恢复该 data unit；bootloader 随后只做
vector 和范围验证。存储访问和调试保护属于独立产品策略，不在这一层增加未来平台抽象。
加入易失 MPC 写保护与 reset workaround 后，bootloader 的 RRAM load end 为
`0x00004a8c`（19,084 bytes），128 KiB boot 区尚余 111,988 bytes；应用 raw image 为
143,872 bytes。LM20 工具的 22 项 Python tests、完整 16-target host CTest、公共 131 项
host suite、LM20
application/bootloader/updater 与既有另一 target 的 Release app/bootloader/upgrader
均重新构建通过。最终实际测试容器分别包含 17,368-byte updater 的 18 个密文块和
143,872-byte application 的 147 个密文块；两份 device manifest 均通过公共地址审计。

同一受控门禁随后补充了 bootloader USBHS maintenance 基本传输证据：实板连续两次接收完整
1024-byte interrupt OUT request，并在中间 reset/re-enumeration 后都返回 protocol v2、匹配的
target identity、idle state 和无错误状态；64-byte response 路径也通过。这个较早的 basic
transport 阶段尚未包括真实签名 RAM program 的 load/data/commit、updater 启动或 `.appimg`
写入；后续下述 authenticated updater 门禁已补齐全链路。门禁还在两次 maintenance session
中提交了结构、target、范围和 chunk layout
均有效但 publisher signature 无效的 manifest，实板均返回 `manifest_signature_invalid`；这已
证明 manifest 签名拒绝路径。后续 restoring gate 又对 application 首个 ciphertext 修改一字节，
实板返回 `authentication_failed` 并保持 failed state；重新开始合法认证 session 后完整更新和
原应用恢复均通过。完整 payload hash 的错误路径由 host fault test 覆盖，成功路径已在实板对
147 个认证 chunk 完整执行。
同一 gate 还在认证 manifest 和首个 application chunk 后执行标准 USB bus reset；updater
重枚举后报告 idle 且无遗留错误，随后负向认证、完整更新和 cleanup 继续通过。这补齐了 USBHS
session epoch 的实板中断证据，不增加 wire ABI。

LM20 RAM updater 也已作为同一 opt-in 下的独立 target 链接并打包，不增加公共 SDK API。
consumer 自有入口把 handoff 参数保存在 callee-saved registers 中，经过官方 startup 后交给
既有 updater main，并在启动 timer/USB 前把 VTOR 指向 RAM vector table。Release ELF 的入口为
`0x20010001`；LM20 的 306 项完整 vector table 按 Cortex-M VTOR 契约以 2 KiB 对齐，位于
`0x20010800`。load image 为 17,368 bytes，BSS 结束于 `0x200168bc`，在 64 KiB
direct-load window 中尚余 38,724 bytes。generic updater 内部也把
Flash 特有的 `erase_unit` 术语改为 storage-neutral `commit_unit`；既有另一 target 的 Release
upgrader 重新链接通过。测试专用 key 已生成 bootloader 可认证的 RAM-program container；实板
已完成 18 个 updater 密文块的 load/data/commit、updater 重枚举、147 个 application 密文块
及完整 payload hash 验证、明文 vector-last 发布和 protocol 38 启动；门禁随后恢复并验证地址
零原应用。首次运行暴露的故障不是 USB shutdown 或 LLVM UB：现场 VTOR 为仅 128-byte 对齐的
RAM vector table，VREGUSB IRQ 289 以 PC 零进入 fault；把 consumer linker 的完整表约束改为
2 KiB 后，未改 USB ISR/关闭路径即连续通过。门禁现在每次从已构建 ELF 自动刷新 bootloader
device manifest，避免增量重链接后人工传递陈旧 hash。

真实冷启动还暴露并修复了一个与 bootloader 无关的 SDC 平台遗漏：代码曾直接调用
`nrfy_grtc_sys_counter_start()`，却未先用 `nrfy_grtc_prepare()` 启动 GRTC 并等待三个低频
时钟周期。warm-reset 门禁因此会掩盖 SYSCOUNTER BUSY 永久等待。只读 attach 将 PC 定位到
该轮询后，公共 SDC 平台补齐官方 nrfx 的 prepare/start 次序；重新链接的应用经完整断电后
重新枚举为 High-Speed USB 并返回协议 38，随后完整签名 updater/加密 application 门禁再次
通过并恢复原应用。

LM20 的保护审计选择“阻止未授权写入”而不是依赖启动时重复 hash。正常应用启动前，
bootloader 应把完整应用 RRAM 配置为 read/execute、禁止 write，并锁定 MPC override 到下次
reset；settings 保持为独立可写区。进入 maintenance 的 reset 路径不发布该限制，应用写入仍
只能由通过 publisher signature、分块认证和完整 payload hash 的 RAM updater 经受限 service
完成。BOOTCONF、APPROTECT、SECUREAPPROTECT、ERASEPROTECT 等持久芯片保护只由量产
provisioning 一次性写入并回读验证；它们不是 bootloader 功能，bootloader 不探测、不配置、
不修复也不为其增加抽象。
量产工具边界已定义为独立且默认只读：版本化输入绑定准确 SoC/revision、最终 boot/application
image hash 和期望的一次性值；只有新的明确授权才能进入写模式，且必须先验证最终镜像、最后
写保护字段并逐项回读。它禁止自动 recover、mass erase、猜测替代值或在结果不明确时重试
一次性写入。该设计不把工具入口加入普通 build、bootloader 或 board gate，也不授权当前实现
或执行量产写入。
这个结论不依赖 RRAMC `REGION[4]`，其 7-bit KiB size 不足以覆盖当前应用；也不声称防御
bootloader 漏洞、已授权签名代码或侵入式物理攻击。MPC normal/maintenance 配置和 reset
errata workaround 经 host/compile 与官方寄存器契约审查；不再把调试器写入/恢复编排加入普通
更新门禁。所有 UICR/protection provisioning 仍需单独明确授权。bootloader 负责的 MPC
override 是每次 reset 后的易失运行时
写保护，不属于上述量产读保护或一次性配置。

compile probe 已按这一结论实现最小运行时路径：应用范围收齐为 MPC 的 4 KiB 粒度
`0x00020000..0x001f4000`，normal handoff 前直接配置一个 read/execute、禁止 write 的 override，
先回读地址和权限，再 enable+lock 并回读；任何不一致都进入 maintenance，不启动应用。
maintenance 路径不设置该 override。nRF54L 的公共 software-reset 实现也在 SYSRESETREQ 前进入
constant-latency，使应用、bootloader 和 RAM updater 共同覆盖 anomaly 63。Release app、
bootloader、updater 均重新链接，两个 device manifest inspection 与 16 项 host tests 通过。

RRAM ECC 只保证每个 128-bit data unit 最多纠正两位并对不可纠正错误产生事件，不能证明
超过该范围的任意损坏一定被启动前发现或一定不会在应用执行后卡死。因此 M9 不把 ECC 当作
镜像完整性协议，也不为它增加持久 hash/header；vector-last 只负责更新事务有效性。当前
nRF54LM20A Engineering B 与 Revision 1 errata 未列出削弱上述 RRAM access control/ECC
边界的 anomaly；两者都包含 soft-reset anomaly 63，相关 reset 路径必须在 SYSRESETREQ 前
进入 constant-latency，并在 CTRL-AP 操作中使用 pin reset。

`ad1be17d` 复核为跨既有板、host packer、CMake 和 wire status 的纯术语重命名；它已经位于
共享的 `origin/main` 历史中，drop 会重写其后的公共历史，局部 revert 又会制造第二次 ABI/CLI
变化。因此当前任务不再改动它，也暂停继续扩散 `application_*` / `storage_failed` 术语；
LM20 新代码直接使用当前最短、最贴近硬件职责的接口，不为统一命名修改既有板或 host CLI。

## 9. 测试矩阵

### 9.1 每次提交的 host 测试

- CMake configure/build/install/find_package；
- Clang 主矩阵和 GNU smoke matrix；
- C 与 C++23 示例；
- source provenance/hash/license 检查；
- ELF vectors/sections/symbols/copy-zero table 检查；
- HEX address allowlist；
- 两次不同路径 reproducible build；
- 未使用 driver 不得出现在最终 ELF；
- public hygiene、secret 和本地路径扫描；
- 禁止依赖扫描：不能链接或 include Zephyr/Kconfig/Devicetree/sysbuild 产物。

### 9.2 实板测试层级

| 层级 | 内容 | 失败含义 |
|---|---|---|
| H0 | 只读枚举、device info、RAM 访问 | 环境/权限/探针问题 |
| H1 | safe flash、boot token、LED/UART | startup/linker/system 问题 |
| H2 | GDB reset/break/step/fault | debug backend 问题 |
| H3 | nrfx peripheral 与 DMA/IRQ | driver/resource 问题 |
| H4 | sleep/retention/RRAM scratch | power/storage 问题 |
| H5 | USB/direct proprietary RADIO | 协议、PHY 和长时稳定性问题 |
| H6 | MPSL/SDC lifecycle、HCI 与 Timeslot 共存 | 官方 binary 契约、资源或无线调度问题 |
| H7 | 下游端到端 | 公共 API 或产品集成问题 |

每个测试必须记录：SDK commit、source lock hash、tool versions、SoC/revision、board type、image hash、backend、耗时和结果。敏感/本地标识只保存在 gitignored 本地结果中。

### 9.3 官方参考对照

`tools/reference/` 可以显式调用本机 NCS/NCS Bare Metal 构建同等小程序，提取：

- vector table 与 IRQ 索引；
- loadable segments、内存起止和对齐；
- SystemInit/errata 选择；
- SDC/MPSL 官方初始化、resource configuration、IRQ/priority、clock、RAM 和 HCI 行为；
- 历史 S115 地址、forwarding 和 RAM 配置（仅用于复现停止的检查点）；
- reset 后关键寄存器；
- USB/radio/clock 初始化顺序。

参考构建必须是 opt-in developer test，不能被 SDK consumer path 调用。它的源准备与构建必须是显式的：普通 configure/build/test 不隐式复制、解压、修补或下载官方 SDK。对照的是硬件契约和行为，不追求复制 Zephyr section 命名。

官方 oracle 不仅要能编译，还必须能由同一公共工具执行安全烧写、复位、串口观测和 GDB smoke。后续官方对照只添加锁定配置与 decoder，不复制 transport/process-control 实现。

## 10. 未来 agent 的执行协议

1. 开始任何工作前完整阅读本文件和 `AGENTS.md`。
2. 先运行只读 preflight：Git 状态、工具版本、官方源版本、硬件枚举；不得先烧写。
3. 处理本 PLAN 顶部明确标记的当前里程碑；已声明暂缓、部分完成或历史停止的较早项
   不得抢占无线主线。只有后续工作能独立进行且不会掩盖当前 blocker 时才并行推进。
4. 为每个非显然决定补一条 ADR 或 provenance 记录，特别是 startup、linker、无线 binary、内存和安全行为。
5. 先写验收检查，再实现；不能用“示例看起来运行”代替可重复测试。
6. P0 工具完成后，每次板上操作都经过公共 CLI 与 safety guard；只允许在 P0 本身的 bring-up 阶段用一次性手工命令建立已记录的 ground truth，随后必须把命令固化并通过工具重跑。永远不直接运行 mass erase/recover/provision。
7. 若板未连接，继续 host 工作并留下精确的 hardware pending 项；不反复轮询，也不虚报完成。
8. 若下载受阻，记录所需官方 URL、版本、期望 hash/文件名并向用户报告；不能换用来源不明的镜像。
9. 若发现工作区已有他人修改，保留并适配；不 reset、checkout 或删除不属于当前任务的内容。
10. 完成一个里程碑时更新 support matrix、测试日志摘要和 PLAN 状态；commit message 使用英文 Conventional Commits。
11. 公开内容提交前运行泄漏扫描。不得出现下游项目名、产品名、私有目录、探针序列号或原始私有日志；发现后必须在首次公开前从 Git history 清除，而不只是删除当前文件。
12. 不因自动化任务是无人值守就扩大授权。遇到一次性配置、保护位、整片擦除、外部账号发布或其他不可逆操作时停止并请求用户明确许可。
13. 将工具链故障与 firmware 故障分类。若编译、探针、烧写、串口、GDB server 或报告基础设施失败，先修复并验证工具，不用反复手工命令绕过。
14. 对 nrfxlib 先读文档、后写代码、再上板：完整审计锁定版本的 README、API、
    integration notes、release notes、manifest、license 和资源占用说明，先提交带出处的
    ABI/resource contract 与自动检查。不得靠重复刷写猜测外设、IRQ、优先级、时钟、
    callback context、内存或初始化顺序。
15. 某条路径失败时先对照官方文档和同版本 oracle 判断是 source/version、ABI、link
    closure、资源配置还是 runtime 问题；不得把不同问题叠加在一次试验中，也不得为
    追求“跑起来”引入无法解释的 shim。

## 11. 停止条件与风险处理

以下情况必须停止相关路径，而不是“先做一个能跑的版本”：

- 官方 startup/linker 来源互相矛盾或 IRQ table 无法闭环验证；
- 识别到的 silicon revision 不在锁定的官方支持矩阵中；
- sdk-nrfxlib tag/commit、binary manifest、headers、archives、license、安全域或 float ABI
  不一致，或者无法证明 SDC 与 MPSL 来自同一兼容集合；
- SDC/MPSL 文档列出的资源、IRQ、优先级、时钟、内存、初始化或 teardown 要求无法
  映射到本项目，或者与实际 silicon 行为矛盾且最小复现不能解释；
- 烧写工具要求 mass erase、recover 或配置区写入；
- image 包含 allowlist 外地址；
- OpenOCD 只能 attach、不能安全写 RRAM，却被请求当作 production programmer；
- 许可证不清楚或 attribution 不完整；
- 只有编译证据，没有所宣称器件/无线能力的实板证据；
- 4 Mbit/s 仅有寄存器读回或单向发射，没有 LM20/L15 双向接收与性能证据；
- 为适配下游而需要把私有名称或业务协议放进公共 SDK；
- RAM/RRAM 溢出，需要改变产品功能或内存布局而非修复明显错误。

可以继续而不必询问用户的情况：普通实现选择、可逆重构、host 测试、允许范围内的 RRAM/RAM 烧写、reset/GDB、下载公开官方资料、修复测试发现的问题。只有选择会显著改变目标、公共 API、许可证、不可逆硬件状态或安全模型时才请求决策。

## 12. 项目完成定义

“项目完成”不是支持所有 Nordic 芯片。达到以下条件即可把首阶段目标视为完成：

- LM20 有官方来源可追溯的 startup/system/linker；L15 只作为测试夹具，不是支持目标；
- 锁定的官方样例可由统一工具重现编译、地址审计、安全烧写、复位、运行观测和 GDB 验收；
- 普通 CMake + 本机工具链能离线构建 C/C++ firmware；
- 不安装 NCS/Zephyr 也能完成 SDK consumer build；
- nrfx 和 USBHS（LM20）已按各自证据级别实板验证；
- 锁定的 sdk-nrfxlib SDC/MPSL 已完成来源、许可证、ABI、资源和链接闭环，Multirole、
  Peripheral-only、Central-only 在 LM20 上通过各自 raw-HCI 与 lifecycle 实板门禁；
- LM20 与 L15 的 MPSL Timeslot 私有 2.4 GHz 完成 4 Mbit/s 优先的双向已知载荷、
  重复运行、CRC/白化负向、丢包/限定重试、soak、接收唤醒、性能/功耗以及 BLE
  advertising/active-connection 共存门禁；
- safe flash、J-Link GDB 和至少经过评估的 OpenOCD capability matrix 完成；
- 首个私有下游无需公开专属 patch 即可消费 SDK；
- 开源仓库及其历史不含任何私有下游信息；
- 文档足以让另一位开发者在新机器和新开发板上复现；
- 正常开发和 CI 无法触达一次性/保护配置；
- 当前完成定义包含 BLE Controller/HCI 与 MPSL Timeslot，但不包含开放 BLE Host、
  ATT/GATT、HID profile、产品配对策略、S115、GZLL、nRF52、nRF53、L15 consumer
  target 或其他 nRF54 支持。

### CMake 组织简化（2026-09-06）

保留公开 configure/enable/finalize 接口与每个固件独立的配置；Timeslot、RRAM 不再要求
CMake 声明时 SDC 在前，依赖完整性在 finalize 检查。nrfx 源文件与 PRS 依赖使用普通
INTERFACE target 组合；SDC imported target 自己携带 FEM/MPSL 链接依赖。
头文件、JSON、链接断言改用模板。随后按用户授权清退历史 S115 集成：删除专用
CMake、适配层、配置、链接布局和等价审计命令；固定此前完整提交用于历史复现。
历史 JSON 不变，官方 reference 工作流保留，旧 SoftDevice layout 由现有字段白名单拒绝。
详见 [CMake 组织说明](../architecture/cmake-composition.md)。本轮不改变运行时初始化、
寄存器行为、驱动选择范围或硬件验收结论。

### 消费者边界修正（2026-09-06）

- 活跃 MPSL 下的普通 RRAM 持久化使用独立 storage Timeslot session；不再用停启
  SDC 代替调度。公开门禁增加广播、活动 BLE 连接及 RADIO burst 期间的 scratch 写入验证。
- CherryUSB 支持只接入硬件 port，由消费者保持 core/class 的唯一所有权；标准初始化
  完成硬件 attach，不要求共享业务代码包含 SoC 专用调用。
- 消费者继续拥有完整 linker script；SDK 额外验证启动 ABI、声明地址边界和栈重叠。
- 以 Engineering B v1.1 / Revision 1 v1.0 勘误为输入统一 anomaly 63 复位处理；
  [勘误覆盖表](../provenance/lm20-errata.md) 区分实现、产品约束和未验证条件。

### 依赖目录与头文件边界整理（2026-09-06）

用户确认保留固定版本 submodule，所有输入统一到 `external/`。startup/MDK 与 nrfx
HAL/driver 共用同一上游，删除重复 MDK 快照；CMSIS Core 保留原版本与逐文件 hash。
nrfx 缓存和安装使用同一文件选择清单，两个已有补丁继续在 ignored cache 应用。
项目跨模块头文件改由 target-scoped include 路径解析，仓库技能迁至 `.agents/skills/`。
设计说明见 [依赖目录](../architecture/dependency-layout.md)。本轮是来源组织和构建
边界修改，不更改硬件行为或扩大已声明的实板支持范围。
验收：134 项 host tests 通过，带空格的独立源码路径构建 28 个 ELF；7 个核心示例的
BIN/HEX 与修改前逐字节一致。安装包搬迁、缓存清单失效和可复现归档测试通过。

### CMake 能力 target 接口（2026-09-06）

按用户决定删除 `nrfkit_enable_*`，消费者以 `target_link_libraries` 选择公开
`NrfKit::nrfx_<driver>`、SDC 变体、direct/Timeslot RADIO、RRAM 和 USB target。
自有适配与 nrfx 使用 INTERFACE sources，在各固件上下文编译；nrfx 仍来自应用补丁的
ignored cache，Controller/MPSL 仍为锁定的 imported static libraries。
固件布局、USB 参数与显式资源声明保留独立配置入口，finalize 在所有能力声明后生成
每个固件的配置并检查冲突。支持经 INTERFACE library 与 alias 的传递链接；拒绝条件
表达式隐藏能力以及通过预编译 library 传播需要各固件独立编译的能力。
公开接口见 [CMake API](../architecture/cmake-api.md)。验收：139 项 host tests 通过，
包含安装包搬迁、直接/间接链接、多固件 nrfx/USB 隔离、补丁缓存来源和冲突拒绝；
28 个 SDK 示例以及消费者 application/bootloader/updater 构建通过，应用和 bootloader
镜像地址审计通过。本轮未操作硬件，不新增实板验收结论。

### USB 内置支持与消费者覆盖（2026-09-06）

SDK 在 `src/usb/nrf54l` 维护可选的内置 CherryUSB port，以 `NrfKit::usb_port`
提供源码 target。消费者可以链接默认 target，也可以复制 port 并链接自己维护的
本地 target；两条路径二选一，不要求特殊覆盖参数或 SDK fork。
CherryUSB core/class、端点/FIFO 配置与 MPSL 时钟模式由消费者拥有；删除完整协议栈
`NrfKit::usb_device` 和公共 `nrfkit_configure_usb`，不再在 finalize 自动推导 USB 配置。
`examples/common/usb` 只提供示例自身的配置和显式辅助脚本，不承载内置 port 实现。
现有 HFCLK24M 请求、查询与释放函数公开于 `nrfkit/mpsl.h`，保留原有 MPSL 客户引用
与延迟 teardown 语义，使消费者的 port 不再依赖 SDK 私有头文件。
验收：139 项 host tests 通过，包含内置 port、自定义 port 替换、安装包与 USB 配置隔离；
28 个 SDK 示例及消费者 application/bootloader/updater 构建通过，23 项消费者工具测试
及应用/bootloader 镜像审计通过。本轮未操作硬件，不新增实板验收结论。

### 平台 target 与镜像策略分离（2026-09-06）

按用户决定移除 configure/finalize、手工能力图和 Firmware/Image 模块，覆盖前述历史
CMake API 决策。SoC、官方 startup、可选 freestanding runtime 与 DK 支持改由普通
INTERFACE targets 提供。nrfx 使用编译定义和默认配置头，在各消费 target 上下文求值；
驱动/无线依赖与资源约束由对应模块负责。
消费者拥有栈/heap、C++ 策略、完整 linker script 和产物转换。runtime 保留静态启动 ABI
与物理边界断言，消费者 linker 保留产品范围断言。普通构建不再要求布局 JSON；它仅作为
显式硬件审计的 allowlist 输入，既有禁止区域、实际 ELF/HEX 范围校验不变。
SDK 验证示例仍显式生成完整产物集；消费者的审计工具通过 `sdk manifest --image-layout`
提供 reviewed allowlist，不将 JSON 加入普通 ELF 的构建依赖。
验收：141 项 host tests 通过，包含原生条件链接、多固件资源掩码隔离、默认 IRQ 覆盖、
冲突拒绝、安装包搬迁、GNU smoke、可复现构建与显式镜像审计。28 个 SDK 示例及消费者
application/bootloader/updater 完成构建，23 项消费者工具测试与应用/bootloader 地址审计
通过。验证未操作硬件，不新增实板验收结论。

### ELF 布局审计输入（2026-09-06）

当前镜像审计以 linker script 从 MEMORY 导出的全局绝对符号为唯一布局输入，
不再生成或维护配套 image-layout JSON。RRAM/RAM 边界必须存在，settings/scratch
可选边界必须成对；审计独立检查物理范围、保留区重叠和 ELF/HEX load ranges。
RAM 边界不扩大烧写 allowlist。device manifest 绑定 ELF hash 与符号，并在使用时
重新核对；既有恢复镜像的旧 manifest 仍按原 receipt/hash 规则读取。以上取代早期
里程碑中的 sidecar 布局输入约定，不改变历史构建或实板证据。
验收：149 项 SDK host tests 和 28 个示例构建通过；包含自定义保留区、坏 ELF 符号表、
manifest 篡改拒绝及旧恢复 receipt 校验。消费者构建、host tests 与应用/bootloader
地址审计通过。本轮未操作硬件。

### 2026-09-11 电源与晶振启动复核

freestanding runtime 在 C 数据初始化之后、构造器之前调用公共平台初始化，补齐
MDK `SystemInit` 未提供的主 DC/DC 与 NVM cache 默认开启。DK target 提供按 FICR
有符号 trim 计算的 HFXO 15 pF / LFXO 17 pF 内部电容，已请求或运行的晶振保持原配置。
自定义 runtime 需在对应时点显式调用；普通外设、时钟请求与 RAM 生命周期仍由应用负责。
来源与锁定 nrfx 电容宏的算术差异见[启动审计](../provenance/lm20-power-startup.md)。
167 项 host tests、LLVM/GNU、安装包与可复现构建通过；LM20B DK 冷启动 CoreMark
CRC 通过，确认 cache/DC/DC 已开启，晶振电容与 FICR 计算一致。组合应用 USB 四个
HID 接口和主循环/fault 检查通过。测量仍受 PPK2 系数缺失限制，不完成 M7 电气门禁。

## 13. 权威入口

- [Nordic nrfx](https://github.com/NordicSemiconductor/nrfx)
- [Nordic sdk-nrfxlib](https://github.com/nrfconnect/sdk-nrfxlib)
- [SoftDevice Controller](https://github.com/nrfconnect/sdk-nrfxlib/tree/main/softdevice_controller)
- [Multiprotocol Service Layer](https://github.com/nrfconnect/sdk-nrfxlib/tree/main/mpsl)
- [NCS Bare Metal repository](https://github.com/nrfconnect/sdk-nrf-bm)
- [NCS Bare Metal releases](https://github.com/nrfconnect/sdk-nrf-bm/releases)
- [nRF54LM20 compatibility matrix](https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54lm20a/page/comp/nrf54lm20a/nrf54lm20a_nrf_connect_sdk.html)
- [nRF Util: programming nRF54L](https://docs.nordicsemi.com/r/bundle/nrfutil/page/nrfutil-device/guides/programming_nrf54l15.html)
- [Arm CMSIS](https://github.com/ARM-software/CMSIS_5)
- [Trusted Firmware-M](https://git.trustedfirmware.org/TF-M/trusted-firmware-m.git/)
- [MCUboot](https://github.com/mcu-tools/mcuboot)

链接只是入口；`sources.lock` 中的精确 release、commit 和 hash 才是可复现构建依据。
