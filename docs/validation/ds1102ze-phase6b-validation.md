# Phase 6B - DS1102Z-E communication and driver contract validation

验证日期：2026-09-06。起始基线：
`0c96f93 docs(hardware): establish DS1102Z-E phase 6 audit baseline`。

本阶段建立 Communication、provider-neutral Oscilloscope Port 和 DS1102Z-E
基本 Driver contract。先使用 fake/recorded transport 完成自动测试，再执行有限的真实
Phase 6B HIL。实机结论只覆盖基础通信、配置回读和 instrument measurement query。

## 1. Implemented boundary

依赖方向为：

`OscilloscopeInterface <- DS1102ZEDriver -> ScpiSession -> VisaTransport <- PyVisaTransport`

- `VisaTransport` 只暴露资源发现和连接；`VisaConnection` 只暴露文本 write/query、
  原样 binary read 和 close。
- `ScpiSession` 只处理串行 SCPI exchange、连接生命周期和有限通信错误；
  不知道 Rigol、通道或测量语义。
- `OscilloscopeInterface` 只使用 instrument Domain 类型；不依赖 VISA、SCPI、Rigol 或 JLCEDA。
- `OscilloscopeInterface` 与 Driver 都采用同步 contract，因为 PyVISA 是同步阻塞 I/O；
  若 Application 将来需要 async，应在更高层建立明确的 executor/thread boundary。
- `DS1102ZEDriver` 只实现已由 Phase 6A 命令矩阵核对的静态语义操作。
- `PyVisaTransport` 是唯一允许导入 PyVISA 的边界；PyVISA 作为可选 hardware dependency
  固定为 1.16.2；真实 HIL 使用了该版本和 IVI / NI-VISA backend。

本阶段没有创建 Waveform、parser、analysis、MeasurementService 或 Hardware Tool，
也没有暴露任意 raw SCPI 接口。

## 2. Driver contract

当前支持：

- `*IDN?` 四字段解析，并严格接受 `RIGOL TECHNOLOGIES / DS1102Z-E`。
- 显式 `connect` / `disconnect` / cached `get_identity` 生命周期。
- CH1/CH2 的 display、AC/DC/GND coupling 和官方枚举中的 probe ratio getter/setter。
- channel scale getter/setter；1X/10X 且 vernier off 时使用手册明确的范围和 1-2-5 校验，
  其他 probe/vernier 状态只做结构校验并依赖仪器 read-back，不伪造完整范围。
- MAIN timebase 的 2 ns/div 到 50 s/div 1-2-5 scale。
- 指定 CH1/CH2 的 instrument frequency 和 Vpp query。

连接时首先完成 identity verification。连接前的合法业务操作会得到
`InstrumentDisconnectedError`。所有输入在首次 SCPI I/O 之前验证；非法 channel、
probe、scale、timebase 不产生任何命令。每个 setter 都在 write 后 query read-back，
不把“write 未抛异常”当作配置成功。

Driver 级可重入互斥锁覆盖整个公开操作，避免另一线程把命令插入多条配置事务；
ScpiSession 另外序列化单次 write/query/binary-read/close，保护 request/response 边界。
这只是进程内同步，不表示多进程或其他软件不会同时控制同一仪器。

## 3. Error model and cleanup

共享根错误为 `HardwareError`。通信边界分类为 `TransportError`、
`TransportTimeoutError` 和 `TransportDisconnectedError`。Driver 将其转换为
`InstrumentConnectionError`、`InstrumentCommandError`、`InstrumentTimeoutError`
或 `InstrumentDisconnectedError`；不向上泄漏 backend exception 文本。

不兼容型号使用 `InstrumentIdentityMismatchError`，格式或数值响应使用
`InstrumentResponseError`，状态前置条件和 read-back mismatch 使用
`InstrumentStateVerificationError`。
`WaveformDecodeError` 已保留为后续 6C 的明确错误类别，本阶段没有 waveform decoder。

VISA resource 打开后若 timeout/termination 配置失败，会 best-effort close；
错误身份也会关闭连接。清理失败不会覆盖更关键的身份拒绝原因。close 是幂等的。

## 4. TDD evidence

初始 Red：在实现包尚不存在时，完整 Python 测试运行 134 项，出现 1 个 failure 和
6 个 import/path error，分别证明新 contract 与 architecture tests 没有误用旧实现而通过。

后续 hardening Red 分别复现：

- 未验证 identity 仍可发命令；
- 部分打开的 VISA resource 配置失败后未关闭；
- cleanup error 覆盖 identity error；
- 非有限 timeout 在打开 resource 后才失败；
- 并发操作可插入 Driver 配置事务；
- ScpiSession exchange 可被另一 I/O 插入。

依据最终 Phase 6B 接口清单重写 contract tests 后，目标测试第一次运行 8 项，
出现 1 个 failure 和 4 个 errors：旧 port 缺少逐项 getter/setter 和连接生命周期，
并且新的统一错误类型及 raw identity 尚不存在。实现没有借旧组合接口“假通过”。

最终统一测试入口 `python scripts/run_contract_tests.py`：

| Suite | Result |
|---|---:|
| Python unit/contract/architecture | 167 passed |
| TypeScript shared protocol contract | 14 passed |
| TypeScript runtime/architecture | 70 passed |
| TypeScript strict typecheck | passed（由 npm test 执行） |

硬件专项自动测试覆盖 discovery/open/close、identity、错误型号、timeout/disconnect、
输入零 I/O 拒绝、精确 SCPI 序列、post-condition mismatch、instrument measurement
解析、binary bytes 不被文本修剪、并发序列化和依赖方向。

## 5. Explicit unresolved items

1. PyVISA 1.16.2、IVI / NI-VISA 和当前 USB resource 已通过基础 HIL，但 timeout、
   热插拔、长时间运行和 waveform binary transport 尚未实机验证。
2. 系统 error queue 的空队列响应仍未知，本阶段未实现 `check_errors()`；frequency
   `9.9e37` 只按一次实机观察做有限 unavailable 拒绝，不推广到所有 measurement item。
3. probe ratio getter/setter 接受命令矩阵中的官方枚举；只有 1X/10X 的 non-vernier
   scale 端点被手册明确证明，本地 scale 完整校验不会擅自推广到其他 ratio。
4. 波形配置、binary block parsing、preamble、BYTE scaling、RAW/STOP 状态机属于 6C，
   当前 port 特意不包含 `capture_waveform`。
5. 没有软件 frequency/Vpp/duty 分析、MeasurementResult 或 Tool；这些仍受后续阶段门控。
6. 本阶段证明 basic communication/configuration/measurement query 的有限实机兼容，
   不能称为完整 DS1102Z-E Driver 或工业级可靠。

## 6. Manual HIL procedure

脚本：`scripts/check_ds1102ze_basic.py`。它不进入默认 CI，不包含 raw SCPI，
不执行 AUTO、CLEAR、reset 或 waveform capture。默认只发现资源；连接后的 serial 默认脱敏。

1. 用 USB 将 DS1102Z-E 连接电脑并开机。本轮无需探测任何电路；禁止连接市电或高压。
2. 在项目虚拟环境安装 hardware extra：
   `.venv\Scripts\python.exe -m pip install -e ".[hardware]"`。
   电脑还必须已有兼容的 VISA backend；安装 PyVISA 不等于安装 VISA backend。
3. 只发现资源：`.venv\Scripts\python.exe scripts\check_ds1102ze_basic.py`。
4. 从输出选择完整 resource，执行只读检查：
   `.venv\Scripts\python.exe scripts\check_ds1102ze_basic.py --resource "<RESOURCE>"`。
5. 核对 IDN、型号、固件及 CH1 设置。任一返回无法解释时立即停止。
6. 经用户确认后，执行一次有恢复动作的 enable read-back：
   `.venv\Scripts\python.exe scripts\check_ds1102ze_basic.py --resource "<RESOURCE>" --verify-write`。
   脚本记录原 enable，设置为 true、验证，再恢复并验证原值。
7. 只有接入安全低压稳定信号并确认共地后，才追加 `--measure` 查询 CH1 frequency/Vpp。
8. 保存结构化输出用于填写主验证记录；不要把未脱敏 serial 提交到 Git。

## 7. Actual DS1102Z-E runtime observation

用户于 2026-09-06 完成真实 Phase 6B manual HIL；随后用同一脚本和稳定低压信号
再次提供结构化输出。Serial 按既定策略脱敏。

| Field | Actual observation |
|---|---|
| VISA resource | `USB0::0x1AB1::0x0517::***9517::INSTR` |
| PyVISA | 1.16.2 |
| VISA backend | IVI；NI-VISA runtime，64-bit Python 可发现 `visa32.dll` / `visa64.dll` |
| Manufacturer / model | `RIGOL TECHNOLOGIES` / `DS1102Z-E` |
| Firmware | `00.06.03.SP2` |
| CH1 settings read | enabled=true、DC、1X、0.05 V/div：PASS |
| MAIN timebase read | 20 us/div：PASS |
| Safe set -> query | PASS |
| Restore -> verification | PASS |
| Stable low-voltage frequency | 10020.04 Hz：PASS |
| Stable low-voltage Vpp | 0.356 V：PASS |

编程手册声明软件版本为 00.06.02，实机为 00.06.03.SP2。Phase 6B 使用的基础命令
未观察到行为冲突；这只是一条 firmware compatibility observation，不推广到 waveform。

另一次没有建立稳定输入前的只读查询返回 frequency=`9.9e37`、Vpp=`0.01`。
`9.9e37` 被记录为此型号/固件的 sentinel-like unavailable observation，并由 Driver
有限拒绝；不声称手册把它定义为所有 measurement item 的通用 sentinel。

结论：**Phase 6B basic communication/configuration/measurement query 已通过真实 HIL**。
这不表示完整 Driver、waveform acquisition、scaling 或工业级可靠性已经验证。

Phase 6B 至此停止，等待评审后才进入 Phase 6C。
