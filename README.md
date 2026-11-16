# CloseWRT-CI-H5000M

基于 [OpenWRT-CI-H5000M](https://github.com/Starktomy/OpenWRT-CI-H5000M) 的独立 H5000M 固件构建项目，参考 [VIKINGYFY/CloseWRT-CI](https://github.com/VIKINGYFY/CloseWRT-CI) 的厂商 SDK 集成方式。

五套固件统一编译 [chasey-dev/immortalwrt-mt798x-rebase](https://github.com/chasey-dev/immortalwrt-mt798x-rebase/tree/25.12-dev-wifi7) 的 **`25.12-dev-wifi7`** 分支，使用 MediaTek `mt_wifi7` 厂商驱动、SDK HNAT 和 MT7987 WARP 3.1。默认 `25.12` 分支的 H5000M 设备仍选择 mt76，因此本仓库固定 Wi-Fi 7 SDK 分支。

[![Build](https://img.shields.io/github/actions/workflow/status/Starktomy/CloseWRT-CI-H5000M/MTK-AUTO.yml?branch=main&label=Firmware)](https://github.com/Starktomy/CloseWRT-CI-H5000M/actions)
[固件下载](https://github.com/Starktomy/CloseWRT-CI-H5000M/releases) · [下载页面](https://starktomy.github.io/CloseWRT-CI-H5000M/)

## 五套方案

| 配置 | 模组管理 | 风扇控制 |
|---|---|---|
| `H5000M-qmodem-next` | QModem Next | LianXia233 Rust 新版 |
| `H5000M-qmodem` | 经典 QModem | FAN789 原版 |
| `H5000M-modem-pro` | Modem Pro | FAN789 原版 |
| `H5000M-mt5700` | LianXia233/luci-app-mt5700 | LianXia233 Rust 新版 |
| `H5000M-mt5700m` | FAN789/luci-app-mt5700m + 原生串口传输 | FAN789 原版 |

每个固件只选择对应的一套模组管理。MT5700/MT5700M 表示两套管理方案；硬件目标均为 Hiveton H5000M。QModem Next 新风扇读取 QModem 温度缓存，关闭 MT5700 专用 RPC；MT5700 保留配套 RPC。

## 硬件与驱动

- SoC：MT7987A；无线：MT7992。`mt7996e` 是原开源模块名称，不能据此把无线芯片写成 MT7996。
- 系统：ImmortalWrt 25.12 开发分支；当前源码使用 Linux 6.12，具体提交与内核版本记录在每次 Release 中。
- 无线：`mt_wifi7`、`mt_hwifi`、MT7992 与 OSAL 配套；使用 `mtwifi-cfg-ucode` 和厂商 LuCI 页面。
- 加速：`kmod-mediatek_hnat`、WARP 3.1、RRO mode 5、`hnat-detect`、TurboACC MTK。首次启动关闭标准 `flow_offloading` / `flow_offloading_hw`，由 SDK HNAT 管理 PPE。
- USB 5G：保留通用 QMI、MBIM、ECM、NCM、RNDIS 和 AT 串口驱动；不混装提供同名模块的厂商 QMI 驱动。

SDK 无线配置位于 `Config/H5000M-MTK-WIFI7.txt`，从上游 MT7987/MT7992 示例提取 SDK 部分，设备仅选择 H5000M。使用 2+3 的 BE6500 DAT，eMMC `factory` 分区 offset 0、长度 `0x1e00` 对齐设备树；读取本机校准数据，不随固件分发其他设备 EEPROM。射频链路、FEM、MAC 与实际性能仍需实机验证。

这里的“CloseWRT”指厂商 SDK 驱动方案。系统、驱动源码、芯片二进制固件和插件分别遵守其自身许可证。

## 使用 CI

- **MTK-AUTO**：手动或定时批量构建五套方案。`TEST=true` 时只执行插件测试和配置断言。
- **WRT-BUILD**：按需手动构建一套，或用 `TEST=true` 单独预检。
- **WRT-CORE**：两种入口共用的构建核心。
- **Auto-Clean**：每种驱动 × 每套模组方案保留最近 **3** 个完整固件 Release；手动可勾选 `dry_run` 只预览。只有定时清理成功才联动 MTK-AUTO，手动清理和预览不会触发固件编译。

默认地址、SSID、密码、国家码和频宽统一在 `Config/OWRT-DEFAULT.txt` 修改。无线默认值直接注入厂商 ucode 的配置生成器，适配其动态设备名称。LuCI 默认主题、网络模式切换和在线升级插件沿用原项目。

在线升级与下载页面只读取 **Starktomy/CloseWRT-CI-H5000M** 的 Release，并按当前模组方案、源码和分支筛选；原开源仓库保留独立的更新来源。

历史版本按发布时间全局排序。当前 SDK 矩阵为 mt_wifi7 五套，正常保留至多 15 个日常版本；与开源仓库分别轮换。同驱动的不同源码共用保留名额。固件发布成功后再次清理超额版本，失败构建、草稿和未完成上传不会淘汰旧固件。

稳定版建议独立发布到 `Starktomy/H5000M-OTA`（规划），将选定固件及 SHA256 一并存入该仓库的 Release，长期保留。只保存指向编译仓库的链接无法避免被日常轮换删除。

产物命名：`H5000M-<方案>-YYYYMMDD-sysupgrade.bin`。发布正文含源码提交、插件与风扇版本、内核版本、SHA256；只发布完整刷写镜像。

## 验证与实机检查

CI 在编译前验证五套方案互斥、USB 驱动、SDK 无线栈、WARP/RRO 参数、L1 profile 和风扇插件。新版风扇与 MT5700 后端由宿主 Rust 交叉编译，检查为静态 aarch64 ELF，再交给 OpenWrt 打包。

构建通过证明配置、编译和打包成功。无线射频、风扇转速、USB 5G 拨号和 HNAT 实际卸载需在 H5000M 上测试。USB 以太网帧模式与 QMI/MBIM raw-IP 的路径不同，不能仅凭模块加载宣称全部获得硬件卸载；应检查双向 FOE/BIND 计数、CPU 占用与吞吐。`hnat-detect` 负责原生端口、外部接口和 `rxppd` 的配套配置。

## 来源与许可

- 原五套方案与构建逻辑：[Starktomy/OpenWRT-CI-H5000M](https://github.com/Starktomy/OpenWRT-CI-H5000M)
- SDK CI 参考：[VIKINGYFY/CloseWRT-CI](https://github.com/VIKINGYFY/CloseWRT-CI)
- 固件源码：[chasey-dev/immortalwrt-mt798x-rebase](https://github.com/chasey-dev/immortalwrt-mt798x-rebase/tree/25.12-dev-wifi7)
- 新版风扇：[LianXia233/luci-app-h5000m-fancontrol](https://github.com/LianXia233/luci-app-h5000m-fancontrol)
- MT5700：[LianXia233/luci-app-mt5700](https://github.com/LianXia233/luci-app-mt5700)
- MT5700M：[FAN789/luci-app-mt5700m](https://github.com/FAN789/luci-app-mt5700m)

CI 仓库采用 MIT 许可，保留原作者版权信息；第三方组件许可不变。

## H5000M 统一 OTA

客户端由 [H5000M-OTA](https://github.com/Starktomy/H5000M-OTA) 子目录导入，支持驱动、五套方案和历史版本选择。构建期将真实身份写入 `/usr/share/h5000m/firmware.json`。

同驱动＋同模组方案可选保留配置（默认清空）；跨驱动、跨方案或当前身份未知时必须清空。后端强制执行，重装或切换历史版本也不能跳过 SHA256 和机型检查。稳定版复制到 OTA 仓库 Releases 长期保存。

此前已发布的固件未包含本次客户端改造，首次迁移请取消保留配置并刷入新版。
