# Phase 6E Measurement Workflow Validation

## Scope

Phase 6E 组合 Phase 6B–6D 已验证的语义能力，建立 provider-neutral application
measurement workflow：

`MeasurementRequest -> MeasurementService -> OscilloscopeInterface / AnalysisEngine -> MeasurementResult`

当前仅支持 channel 1/2 和 `frequency`、`vpp`、`waveform`、`pwm`。本阶段没有 Agent、
LLM、MCP、JLCEDA 联动、Agent-facing runtime adapter、新仪器能力、RAW waveform、FFT、
任意 SCPI 或 VISA resource 暴露。

## Compatibility finding

新的 `MeasurementResult` 独立于 EDA 存在，不要求 document、selection 或 probe target。
现有 EDA `MeasurementContext` 继续表示设计关联上下文，未来可以关联独立测量结果，但
Phase 6E 不把硬件独立测量强制绑定到 EDA。

原 `ArtifactReference` 的语义本身是通用证据引用，但物理位置在 EDA package。Phase 6E
将其提升为共享 Domain value object，并从原 EDA module 兼容导出；没有建立不兼容的
第二个 ArtifactReference。

## Domain and observation semantics

- `MeasurementRequest`：immutable request id、measurement kind、channel 1/2、可选 context id。
- `MeasurementObservation`：value、source、method、observed time、局部 quality、warnings、
  evidence artifact ids。
- source 明确区分 `instrument`、`software_analysis`、`simulated`。
- `MeasurementResult` 使用不同字段保存 instrument 与 software observations；不平均、不
  覆盖，也不把二者自动变成 accuracy pass/fail。
- `MeasurementProvenance` 保存 instrument identity、channel、workflow 时间范围，以及适用
  时的 analysis algorithm name/version。
- `WaveformArtifact` 只保存 reference、点数、时间/电压范围与 acquisition metadata；完整
  time/voltage arrays 只存在于 ArtifactStore。

## Coherence

PWM workflow 中，software Vpp/mean/RMS/frequency/period/duty 均来自同一 waveform，明确
标记为 `same_artifact`。instrument frequency/Vpp 是捕获后的顺序查询，与 software evidence
只能标记为 `sequential_same_session`。当前模型不声称 `same_capture`。

## Partial result and quality

- instrument frequency 或 Vpp 单项失败：保留 waveform 和 software analysis，对应
  observation 为 `unavailable`，overall quality 为 `degraded`。
- waveform capture 失败：software metrics 明确为 `unavailable`，不继续 instrument PWM
  queries，overall quality 为 `failed`。
- waveform 成功但周期证据不足：保留 software Vpp/mean/RMS；frequency/period/duty 为
  unavailable，analysis warning 继续传播，overall quality 为 `degraded`。
- 全部 PWM evidence 可用且 deterministic analysis 为 good：overall quality 为 `good`。

总体 quality 是 evidence 聚合结果，不是简单复制 analysis quality；局部 observation quality
始终保留。底层异常文本不会进入稳定结果。

## Artifact abstraction

`ArtifactStore` 是 provider-neutral outbound port。当前 `InMemoryArtifactStore` 仅供测试和
开发：完整 waveform 存在当前进程内，tool DTO 返回 `memory://` reference 和有限摘要。
它不声称持久化、跨进程可取或具备数据库耐久性。

## Hardware Tool Contract

`protocols/hardware/v1/hardware-tool.schema.json` 定义静态语义 allowlist：

- `hardware.get_status`
- `hardware.measure_frequency`
- `hardware.measure_vpp`
- `hardware.capture_waveform`
- `hardware.measure_pwm`

参数只允许 channel 1/2 和可选 context id。结果是 JSON DTO，不包含 Driver 对象、完整
sample arrays、SCPI、VISA resource 或任意底层调用入口。Schema 同时约束 response operation
必须与 result measurement kind 匹配。本阶段只有 serializer，没有 Agent runtime dispatcher。

## TDD evidence

初始 Red：原有测试继续运行；新增 Phase 6E 测试出现 3 个 import errors 和 3 个 architecture
failures，原因分别为 Artifact/domain/service/tool modules 与 ports 尚未实现。首轮最小实现后，
一个 CH2 provenance test 被 Domain 正确拒绝，因为 Fake 返回错误的 CH1 waveform；修复 Fake
遵守端口语义，没有放宽通道一致性不变量。Tool operation/kind mismatch 测试随后先 Red，
再由 JSON Schema cross-field constraint 修复为 Green。

自动测试覆盖：四类 request、channel validation、software/instrument evidence、same-artifact、
sequential coherence、两类 instrument partial failure、waveform failure、insufficient cycles、
warning/quality/provenance propagation、artifact reference、tool JSON/schema 以及 dependency tests。

## Current validation boundary

Phase 6E 自动测试使用 FakeOscilloscope 和 Phase 6D deterministic analyzer。Phase 6B–6D 的
真实 DS1102Z-E HIL 证据支持底层能力，但 Phase 6E application workflow 本轮没有新增真实 HIL。
当前证据不代表所有 waveform、frequency/duty 范围、长期 Artifact durability 或工业级测量
准确度已经验证。

## Architecture review closeout

Phase 6E architecture review 判定为 **PASS**。批准 MeasurementResult 独立于 EDA、共享
ArtifactReference、instrument/software observation 分离、`sequential_same_session` 不升级为
`same_capture`、partial result semantics，以及不暴露 SCPI/VISA/Driver/full waveform 的 Tool
Contract 边界。

该 PASS 仅由 Domain tests、MeasurementService tests、FakeOscilloscope tests、Tool Schema
tests 和 architecture dependency tests 支持。`MeasurementService` 尚未通过真实 DS1102Z-E
端到端 HIL，因此不得表述为 real MeasurementService workflow validated。
