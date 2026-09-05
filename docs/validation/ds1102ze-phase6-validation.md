# Phase 6A - DS1102Z-E hardware audit and validation record

审计日期：2026-09-06。被审计基线：`6e2bb74 feat(jlceda): add guarded remote highlight`。
本轮只完成 Phase 6A，新增审计文档；没有实现 6B-6F，未执行仪器发现、连接或控制。

## 1. Evidence and manual identity

| 证据 | 已核实内容 |
|---|---|
| Programming Guide | 用户提供的 `C:/Users/Administrator/Desktop/新建文件夹/DS1000ZE_ProgrammingGuide_EN.pdf`；2020-04；PGA27101-1110；218 页；声明软件版本 00.06.02 |
| Programming Guide SHA-256 | `4ef912f294e7d18c4c8dd7a67c7e6858a6f69de0dfb18dc5b355f00a82080823` |
| User Guide | 用户提供的 `C:/Users/Administrator/Desktop/新建文件夹/DS1000Z-E_UserGuide_CN.pdf`；2022-02；UGA27003-1110；声明软件版本 00.06.02 |
| User Guide SHA-256 | `2a9ca69fbc145ee90d4c59e83737d3f6e4059953ef6a117a2c387ff7059f2e6e` |
| 型号适用性 | 编程手册 PDF 第 4 页明确包括 DS1102Z-E（100 MHz、2 模拟通道），正文以 DS1202Z-E 为例 |
| 阅读方式 | 提取相关完整命令页；另外渲染核对 PDF 190、195、198 页的 Figure 2-1/2-2、BYTE 电压公式与 preamble 字段 |
| 版本限制 | 上述是用户提供并在本轮核对的官方手册版本，不宣称是当前厂商最新发布；00.06.02 也不是已查询的实机固件 |

## 2. Current hardware architecture and files

当前仓库没有 `hardware/` 子系统。检查了受版本控制的文件、`src/`、`scripts/`、
`tests/` 与 `pyproject.toml`；本结论不包含仓库外可能存在的实验脚本或未提供的旧工程。

| 能力层 | 当前文件 / 状态 | 分类 |
|---|---|---|
| Communication / VISA | 不存在；项目依赖只有 jsonschema、websockets；当前 .venv 也没有 pyvisa | 缺失 |
| SCPI Session | 不存在；现有 integrations/jlceda/transport 是认证 WebSocket，仅服务 EDA | 缺失，不能复用其报文/会话为 SCPI |
| Oscilloscope Interface | 不存在；application/ports/eda_interface.py 只定义 EDA port | 缺失 |
| DS1102Z-E Driver | 不存在；未发现官方命令发送、IDN 解析或参数映射代码 | 缺失 |
| Waveform model / parser / scaling | 不存在；没有波形数组、preamble parser 或 binary block parser | 缺失 |
| Deterministic Analysis | 不存在；没有真实波形频率、Vpp、PWM duty 算法 | 缺失 |
| MeasurementService | 不存在 | 缺失 |
| Real/Fake Hardware Tool | 不存在 | 缺失 |
| DutyCycle、ArtifactReference | domain/eda/models.py 中已有 immutable value objects 和单元测试 | 可复用业务语义，跨域位置需在后续评审 |
| MeasurementContext | domain/eda/models.py 中已有，但必填 document/selection/probe_target，results 是标量键值对 | EDA 上下文，不能直接充当独立硬件 MeasurementResult |
| ProbeConnectionConfirmation | 已有模型与测试；包含 EDA snapshot / probe_target 关联 | 不是实际完成了接线，也不适合为独立硬件测试伪造 EDA 对象 |

相关现有文件：

- `src/ai_instrument_assistant/domain/eda/models.py`
- `src/ai_instrument_assistant/application/ports/eda_interface.py`
- `src/ai_instrument_assistant/integrations/jlceda/transport/gateway.py`
- `tests/unit/domain/eda/test_models.py`
- `tests/architecture/test_eda_dependency_boundaries.py`
- `scripts/run_contract_tests.py`、`pyproject.toml`

拟定依赖链（尚未实现）：

`HardwareTool -> MeasurementService -> OscilloscopeInterface <- DS1102ZEDriver -> ScpiSession -> VisaTransport`

Service 调用独立 Analysis 模块。仪器身份、Waveform、MeasurementRequest/Result
属于 provider-neutral hardware/measurement Domain；Driver 不导入 Tool schema。
ScpiSession 负责串行 query/response 和一般 block framing，VisaTransport 只负责字节 I/O。
并发请求须覆盖整个配置/采集事务的互斥，不能只锁单次 write。

## 3. Official command matrix

见 [完整命令矩阵](ds1102ze-phase6-command-matrix.md)：记录了本切片所需 S/Q 形式、参数范围、
响应类型、前置条件、状态副作用、拟定 Driver 方法与印刷/PDF 页码。
这些方法名是计划，不代表已有可调用实现。

## 4. Manual vs current implementation findings

| Finding | 现状、风险与建议 |
|---|---|
| H-01：没有旧 Driver | 无“已实现且可信”或“已实现但未验证”的硬件代码，也无可证实的旧 Driver/手册冲突。6B 实际是从零实现最小 contract，而非修复不存在的 Driver |
| H-02：模型名称不等于硬件实现 | MeasurementContext 的 tests 只证明 EDA 不变量。为真实结果填入假 document/selection 会破坏独立硬件边界。最小新增硬件结果模型；DutyCycle/ArtifactReference 可经后续评审提取到共享 domain 并保留原 import re-export，避免复制定义 |
| H-03：手册示例不等于规格 | SRATe? 示例为 2e9，所附用户手册简介写模拟通道实时采样率 1 GSa/s。示例值不能被当成 DS1102Z-E 上限或实机事实；型号能力与固件须实测记录 |
| H-04：状态依赖不能省略 | scale 依赖 probe 与 vernier；timebase 依赖 MAIN/ROLL；RAW 必须 STOP；MATH 不在首版范围。参数校验不能只做正数检查 |
| H-05：查询也可消耗状态 | `:SYSTem:ERRor[:NEXT]?` 会删除一条错误。仅关键配置序列后有界检查；保留证据，不以清空错误模拟成功 |
| H-06：文档漂移 | 根 README 仍描述 5B.2b；旧 V0.2 constraints 的排除项属于历史阶段。不能据此宣称当前已实现或永久禁用硬件；本轮只登记，不顺带改写 EDA 文档 |

没有发现已存在的硬件代码处于错误层；当前风险是未来把硬件职责塞入 EDA Domain/transport。
若后续提供仓库外旧 Driver，应单独纳入矩阵审核，不能默认其结果兼容。

## 5. Waveform acquisition audit

当前没有 acquisition 实现或实机证据。已确认的手册事实：

- NORMal 是屏幕波形，读取点范围 1-1200；其点间隔为 TimeScale/100。
- RAW 为内存波形，仅 STOP 可读，读取过程中不得操作示波器；其点间隔为 1/SampleRate。
- MAX 随运行状态切换屏幕/内存语义，第一条链建议不支持。
- BYTE 每点 1 byte，单条 DATA? 最多 250000 点。大于此数需使用不同 STARt/STOP 的连续闭区间分块，每块都有独立 header。
- WORD 占两字节但只有低 8 位有效；ASCII 已是实际电压。首版只实现 BYTE，显式拒绝其余格式。

建议 6C 先提供明确点预算的 RAW BYTE 读取；请求部分内存时返回原始 memory point count、
requested start/stop 和实际 point_count，不默默把整段请求裁剪成“成功”。
若请求全部且超过单块上限，要么实现连续分块，要么明确拒绝超出当前支持范围。

拟定序列：校验完整请求/身份 -> 读取相关设置 -> 明确取得采集状态 -> STOP 并有限时等待 STOP
-> source/mode/format/range 配置和回读 -> preamble -> DATA block -> 长度/状态/元数据核验
-> 标准 Waveform。需要新数据时，必须定义新采集/触发完成条件；单独 STOP 不证明波形是新的。
初版采集后的 RUN/STOP 状态必须在请求策略和结果 metadata 中说明，不隐式恢复后宣称已保持采集记录。
录制/回放关闭、触发源与输入匹配可作为首轮 HIL 的显式人工前置条件；不为此增加完整录制或触发 Driver。

屏幕 A、仪器 query B、软件 C 应尽量比较同一冻结记录。记录 acquisition mode、MID 阈值、
probe、coupling、scale、时基及各读数时间；不能声称多条 SCPI 是原子的同一帧事务。

## 6. Binary block parser audit

当前 parser 与 parser tests 都缺失。手册 2-178 描述该设备为 `#9` 加 9 位 payload 字节数；
2-179 的 11-byte header 是这一编码的实例。通用 parser 应按 `#<N><length><payload>` 读取，
测试 N=1..9，并在实机侧记录 header 形态；支持可变 N 不与 #9 的设备描述冲突。

6C 待实现 contract：

- 验证 #、N 为 1..9、length 各字节为十进制数字及应用级最大长度，拒绝 #0 indefinite block。
- 按长度跨多次底层 read 收满数据，不能依赖一次 VISA read 或 payload 内的换行。
- 先解析 framing，再交给 Rigol BYTE decoder；Rigol 点数与 scaling 不进入 VISA transport。
- 截断 header/payload、非法字符、超限长度要明确失败；空 payload 对通用 framing 的处理与 Waveform 必须至少一点的不变量分开。
- 尾部终止符策略由传输 contract 明确；本手册该段未保证 LF/CRLF。不得使用 `.strip()` 修剪 binary payload；未约定的额外字节拒绝，残留数据使会话失步时不能直接再发下一条 query。

## 7. Scaling audit

当前没有旧 scaling 代码。已从手册 2-179 原文和渲染页面确认 BYTE 电压公式：

`V[i] = (unsigned_byte[i] - YORigin - YREFerence) * YINCrement`

减法前转为有符号数值类型，避免 uint8 下溢。YORigin 是编码空间偏移，不是电压加法项；
不能使用别的仪器常见的 `(code-yref)*yinc+yorigin`。不再次乘 probe ratio，避免重复缩放；
同时保存实际 probe 和完整 preamble，并用 HIL 验证最终单位。

手册 2-180 说明 XREFerence 返回 0，XORigin 为首点时间，XINCrement 为相邻间隔。
因此从首点开始、0-based 的时间轴为 `t[i] = XORigin + i * XINCrement`。
这是依据字段定义得出的表达式，手册没有单独印出这一整条通用公式。
从 1-based STARt=s 读取部分区间时，拟用全记录索引 `s-1+i`；需在 6C/HIL 以重叠区间
验证 XORigin 是否仍对应全记录首点。若实际返回与此解释不一致，暂停并报告。
若 XREFerence 非 0，不推广未确认的其他设备公式。

六个参数使用实际 preamble/query；不要把 127、VerticalScale/25、TimeScale/100 硬编码为所有模式。
必须区分 `sample_interval = XINCrement` 与 `instrument_sample_rate = ACQuire:SRATe?`，
尤其 NORMal 导出不能按 ADC 采样率生成时间轴。

拟定 synthetic tests（当前尚未编写/运行）：

- bytes=[122,132,142]，yorigin=5、yreference=127、yincrement=0.02，预期 V=[-0.2,0,0.2]。
- xorigin=-2e-6、xincrement=1e-6、xreference=0、STARt=1，预期 t=[-2e-6,-1e-6,0]。
- 分块区间、非零 yorigin、负电压、首末点及 probe read-back 同时覆盖，不能只测零偏移例子。
- preamble 严格 10 字段；正确区分 waveform type 与 acquisition type；实际 payload 长度与请求区间匹配。

## 8. Existing tests and current reliability classification

本轮通过现有统一测试入口重新验证：Python 126，TypeScript shared contract 14，
TypeScript runtime/architecture 70，全部通过（含严格 TypeScript typechecks）。
这些是 EDA/基础设施结果；硬件专项测试数为 0，HIL 为未执行。

已有可复用测试包括 DutyCycle ratio/percent 和边界、ArtifactReference、
MeasurementContext 禁止内嵌大数据、Python AST 依赖检查以及测试 runner。
现有 EDA architecture tests 只扫描 EDA domain/port 等指定路径，不会自动保护未来 hardware 层。

| 待覆盖 contract | 当前 | 计划阶段 |
|---|---|---|
| discover/connect/close、IDN、错误型号、timeout、断连/communication error | 无 | 6B |
| 非法 channel/scale 在 I/O 前拒绝；正确通道/时基命令；配置回读 | 无 | 6B |
| instrument frequency/Vpp response；无效值与错误分类 | 无 | 6B，6F 补 recorded evidence |
| source/mode/format/range 顺序、binary block、preamble、scaling | 无 | 6C |
| 多周期 frequency/duty、Vpp；弱信号、欠采样、削顶、周期不稳 | 无 | 6D |
| MeasurementService、结构化结果、Tool 不泄漏 raw SCPI/Resource、模拟来源标记 | 无 | 6E / HIL 后 Tool 门控 |
| 硬件层依赖方向及实际 known-signal 三方比较 | 无 | 6B 起建立边界；6F 验证实机 |

## 9. Reliability risks and explicit unknowns

1. 未获取实际 IDN、固件、VISA backend/driver 或物理连接；不得把手册版本或虚构 IDN 当作观测值。
2. 手册未在 ITEM? 段定义所有 invalid measurement 响应；必须拒绝无法解释的结果并记录，不能总返回数值。
3. error queue 空响应及 binary terminator/分片行为需要实际会话证据；存在超时后读取边界失步风险。
4. 通道配置、采集与下载存在状态耦合；前置参数验证要在整次配置的第一次写入前完成，后置条件须回读。
5. 输入源 nominal 10 kHz/30%/3.3 V 不是已测真值；阈值、量化、周期数、信号噪声及窗口不同都会影响对比。
6. 当前 DutyCycle/ArtifactReference 的 EDA 目录位置会妨碍独立硬件复用，须做最小共享模型调整评审，不能复制两套语义。
7. 开发顺序存在文本冲突：第十二节要求 Driver/HIL 完成后才建立 Tool；第十五节把 Tool 放在 HIL 之前。下列计划提出解决方案，需本次评审确认。

## 10. Proposed minimal Phase 6B-6F plan

所有内容仍待本轮评审；按小步 Red -> Green 实施，遇实际冲突按用户停止条件暂停。

| 阶段 | 最小交付与边界 | 退出证据 |
|---|---|---|
| 6B | 新增 VisaTransport、串行 ScpiSession、OscilloscopeInterface、DS1102ZEDriver 的 identity/基本配置/instrument query；FakeTransport/RecordedSession 先行。最小新增 InstrumentIdentity 和结构化错误；PyVISA 只在 transport 层 | 模型识别、非法参数零 SCPI、read-back mismatch、timeout/断连等失败路径及 import architecture tests；尚不声称实机验证 |
| 6C | BYTE definite-length parser、preamble parser、紧凑时间轴+电压/ArtifactReference Waveform；明确 RAW STOP、点预算与分块策略 | 手册溯源、头部变长/分片/截断/额外字节、非零 offset synthetic scaling、区间一致性测试 |
| 6D | 纯函数 Vpp；多个同极性边沿估计周期，使用阈值/必要的迟滞与插值、最少周期/边沿数；完整周期 high_time/period 求 duty | 已知周期、30% PWM、无周期/常值、小幅度、低采样、噪声/不稳定周期测试；无依据则结果字段为空，提供 quality/warnings |
| 6E | MeasurementService + 独立 MeasurementRequest/Result 的设计/实现；保存 instrument/software 两份读数、差值、设置、来源与 artifact，不覆盖为单一“真值”。在本阶段评审拟定 Hardware Tool 的类型 contract，但先不发布 Real/Fake Tool 实现 | 用 Fake scope 完成 service 场景、失败/部分结果/后置状态测试；不依赖 JLCEDA、不返回 Resource/raw bytes/arbitrary dict |
| 6F | 用户接线确认后，先通过 Driver/Service 的显式 CLI 做真实 HIL；A 屏幕读数、B SCPI query、C software；结果通过评审后再完成 Real/Fake HardwareTool 实现并使用同一语义 contract，Fake 标记 simulated | 型号/固件/VISA/来源/设置/波形证据及误差可解释，建立有依据的验收标准；Tool contract tests 与来源隔离测试 |

此门控建议优先遵守“先 Driver/HIL 后 Tool”的要求。6E 前置 contract review 并不表示发布
Hardware Tool；如果评审坚持 Tool 在 6E 完整实现，需要先明确修改第十二节的顺序要求。
Tool 最终只包含 get_instrument_status、measure_frequency、capture_waveform、measure_pwm
等静态语义方法，不提供 send_scpi。Fake 与 Real 返回同一种结构且来源可辨。

分析建议只计算 Vpp/frequency/duty；mean/RMS 仅有明确复用时加入。
DutyCycle 沿用 ratio 0..1；至少处理 insufficient_cycles、signal_too_small、
clipping_suspected、unstable_period、insufficient_samples，必要时单指标不可用，
而非因为 frequency 不可用就伪造 Vpp 或把全部数据丢弃。

## 11. HIL evidence placeholders and review stop

| HIL 字段 | 当前事实 |
|---|---|
| Tested model / IDN / firmware | 未连接、未查询 |
| VISA backend / version / resource | 未安装项目级 PyVISA；VISA backend 未探查，不声称不存在 |
| Physical connection / probe ratio | 未确认；候选为 STM32 PWM -> CH1，STM32 GND -> scope GND，实际探头挡位须与仪器配置匹配 |
| Signal source | STM32F103C8T6 是用户建议，当前尚未确认实际源 |
| Expected frequency / duty / levels | 候选 10 kHz / 0.30 / 约 3.3 V；未验证源时钟与实际值 |
| Scope settings / sample rate / point count | 未测 |
| A: screen measurement | 未测 |
| B: instrument query | 未测 |
| C: software analysis | 未测 |
| Deviations / acceptance criteria | 未建立；先记录观测误差，结合正式规格、源稳定性与算法分辨率决定，不能任意设定 1% |
| Unresolved limitations | 上述固件、无效值、终止符、部分区间时间轴和窗口对应关系需 HIL 确认 |

本轮只新增此审计记录与命令矩阵；未修改 EDA 功能、依赖或实现代码，未创建提交。
至此停止 Phase 6A，等待架构和手册审计评审。
