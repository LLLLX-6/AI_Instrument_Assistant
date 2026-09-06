# Phase 6C - DS1102Z-E waveform acquisition automatic validation

更新日期：2026-09-06。Phase 6B 基线：
`a3c8619 feat(hardware): add validated DS1102Z-E basic driver`。

本记录严格区分自动测试与真实硬件观察。Phase 6C 先完成自动化实现和
recorded/fake 验证，随后由用户在真实 DS1102Z-E 上完成第一轮波形下载。
真实输出证明当前受控 NORM/BYTE 路径能够完成并形成有限 `Waveform`；没有被脚本
直接观察或输出的底层细节仍不得推定为已验证。

## Implemented scope

- 通用 IEEE 488.2 definite-length block parser：支持 `#<N><length><payload>`，
  `N=1..9`；拒绝 `#0`、非十进制长度、截断与应用长度上限之外的声明。
- 明确尾部策略：只接受无尾部、LF 或 CRLF；不对二进制 payload 使用 `strip()`。
- provider-neutral immutable `Waveform`，包含显式 X/Y 缩放元数据、时间轴、电压值、
  仪器身份、采集时间和请求闭区间。
- DS1000Z-E 十字段 preamble parser，以及已核对的 BYTE 电压公式：
  `(code - yorigin - yreference) * yincrement`。
- DS1102Z-E 第一条采集切片固定为单通道、`NORM`、`BYTE`、`START=1`、
  `STOP=1200`。不实现 RAW、MAX、WORD、ASCII、分块或多通道采集。
- 采集事务会读取 waveform source/mode/format/start/stop；只修改不符合目标的项，
  每次修改都回读验证，完成或失败后按逆序 best-effort 恢复并再次验证。
- `ScpiSession.query_raw()` 将 DATA 命令与 binary read 保持在同一串行锁内。
- HIL 脚本只调用语义端口，输出有限摘要与前 8 个样本，不输出全部数组、不暴露
  原始 SCPI、不进行 frequency/duty 软件分析。

## Deliberate constraints

1. 本阶段不调用 `:STOP`/`:RUN`，不改变采集运行状态；NORM 只读取屏幕波形。
2. `XREFerence` 只接受手册核实的 0，`YREFerence` 只接受 127；出现其他值即报告
   metadata incompatibility，不套用其他型号公式。
3. `START != 1` 的时间轴语义没有在当前垂直切片中推广，因此明确拒绝。
4. 通用 block parser 允许空 payload，但 Domain Waveform 至少需要一点；协议 framing
   与领域不变量保持分层。
5. `observed_voltage_span` 只是 HIL 摘要的 `max-min` 观察值，不是 Phase 6D Analysis
   Engine 的 Vpp 算法结果。

## TDD evidence

第一轮 Red：基础测试产生 4 个 import error 与 2 个 port assertion failure，分别确认
binary parser、Waveform model、Rigol preamble/scaling、waveform errors 和
`capture_waveform` port 尚不存在。

第二轮 Red：6 个 Driver tests 因 `DS1102ZEDriver` 尚未实现抽象方法
`capture_waveform` 而失败。随后实现最小 NORM/BYTE 路径。

第三个针对性 Red：模拟设置命令回读失败时，测试证明原状态没有进入恢复队列；实现将
恢复登记移动到状态写入之前，保证任何状态写入尝试后都会执行恢复流程。

自动测试覆盖：

- `#1`、`#2`、`#9`、262144-byte generic payload、空 payload、LF/CRLF；
- 非法 width、length、截断、额外尾部与应用级上限；
- 十字段 preamble、未知 enum、非数字、非法 point count；
- synthetic negative/zero/positive scaling，避免 uint8 下溢；
- payload/request/preamble 长度一致性；
- 1200 点 capture、无状态变化路径、修改并逆序恢复、异常恢复；
- transport disconnect 不被误分类为 waveform decode error；
- Domain / communication / driver / port 的依赖方向。

完整统一 runner 结果：Python 193 项、TypeScript shared contract 14 项、
TypeScript extension/runtime/architecture 70 项，全部通过。独立 strict TypeScript
typecheck 通过。`npm run build` 在正常文件权限下通过；受限执行沙箱中的第一次构建因
esbuild 无权读取既有入口目录而失败，该结果属于执行环境限制，不是源码编译失败。
这些自动结果不能替代下面的真实 HIL。

## Phase 6B actual observation retained

用户已真实确认：DS1102Z-E 固件 `00.06.03.SP2`，PyVISA 1.16.2 + IVI/NI-VISA，
基础连接/配置/恢复通过；安全低压输入下 instrument query 为 10020.04 Hz、0.356 Vpp。
资源标识在文档中只保留掩码形式 `USB0::0x1AB1::0x0517::***9517::INSTR`。
这些只证明 Phase 6B，不证明 Phase 6C waveform capture。

## Actual manual HIL

用户于 2026-09-06 在安全低压、共地前提下运行语义级 waveform HIL 脚本，执行完成且
没有报告 framing、metadata、长度、非有限值、连接或恢复异常。

| 字段 | Actual observation |
|---|---|
| Instrument | RIGOL TECHNOLOGIES DS1102Z-E；firmware `00.06.03.SP2` |
| VISA resource | `USB0::0x1AB1::0x0517::***9517::INSTR` |
| Channel / mode | CH1；实现固定 NORM/BYTE |
| Point count | 1200 |
| Sample interval | 200 ns |
| Time origin | -120 us |
| Derived screen span | 1199 intervals = 239.8 us；首末点约 -120 us 至 +119.8 us |
| Voltage range | minimum -0.340 V；maximum +0.008 V |
| Observed voltage span | 0.348 V |
| Finite samples | PASS |
| First samples | -0.316 V 至 -0.332 V 的低电平附近样本；只保留有限摘要，不保存 console raw dump |

时间窗口与 Phase 6B 的 20 us/div、12 格屏幕范围（约 240 us）一致。0.348 V 的 waveform
span 与 Phase 6B 独立 instrument query 的 0.356 Vpp 相差 0.008 V（约 2.25%）；两者
并非同一原子记录，且本阶段没有建立准确度阈值，因此只记录为量级与缩放结果相互一致，
不把它升级为软件 Vpp 算法验收。

### What this HIL proves

- 真实固件接受当前 source/mode/format/start/stop/preamble/data 序列；
- binary response 落在当前 parser 接受的 definite-length framing 与尾部策略内；
- 声明长度、preamble points 和请求区间最终一致为 1200 点；
- 当前 X/Y metadata 通过受控约束，缩放结果全部有限；
- 语义 Driver、SCPI session、VISA transport 与真实设备可以完成一轮端到端采集。

### Still not directly observed

- 脚本没有输出 raw framing，因此不能声称实际 header 一定为 `#9`，也不能区分无尾部、
  LF 或 CRLF；只知道实际响应被当前严格 parser 接受。
- 输出没有列出 raw 十字段 preamble，只能确认它通过了解析及当前 NORM/BYTE、
  XREF=0、YREF=127 约束。
- 输出没有展示 capture 前后 waveform 设置，不能把自动恢复测试等同为真实仪器上的
  可见 restore 证据；本轮只确认没有抛出 restoration failure。
- 未验证 CH2、RAW、MAX、WORD、ASCII、分块、`START != 1`、长内存读取或多通道。
- 未实现或验证 software frequency/duty/Vpp Analysis Engine。

Phase 6C 的首条真实垂直切片判定为 **PASS with bounded observations**。当前仍不创建
Phase 6C commit，等待 closeout 授权；不进入 Phase 6D。
