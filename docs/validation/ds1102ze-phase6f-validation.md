# Phase 6F Real MeasurementService HIL

## Status

**Automatic support: PASS. Real DS1102Z-E MeasurementService HIL: PASS with bounded observations.**

Phase 6F 不增加测量能力或算法，只验证真实组合：

`PyVisaTransport -> DS1102ZEDriver -> MeasurementService -> deterministic analysis / ArtifactStore -> MeasurementResult`

## Composition root

`ai_instrument_assistant.bootstrap.hardware` 是本阶段唯一新增的 concrete wiring boundary。它
构造 PyVisaTransport、DS1102ZEDriver、DeterministicWaveformAnalysisEngine、
InMemoryArtifactStore 和 MeasurementService，并由小型 context-managed `MeasurementRuntime`
管理 connect/disconnect。没有引入 DI framework。

业务 `MeasurementService` 仍只依赖 OscilloscopeInterface、WaveformAnalysisEngine 和
ArtifactStore，不依赖 Rigol、VISA、SCPI、JLCEDA 或 Agent。

## Automatic evidence

Recorded VISA integration test 使用真实 DS1102ZEDriver、真实 deterministic analyzer、真实
MeasurementService 和 InMemoryArtifactStore，确认：

- RIGOL identity 进入 status/provenance；
- PWM software/instrument observations 均进入 MeasurementResult，source 不混淆；
- waveform read 先于 instrument frequency query，frequency query 先于 Vpp query；
- software evidence 为 `same_artifact`；
- instrument/software 为 `sequential_same_session`；
- ArtifactReference 能在当前进程取回完整 waveform，channel/point count/sample interval/
  acquisition mode/captured time 与 Result metadata 一致；
- 有限 Tool DTO 通过 Hardware Tool JSON Schema，且不包含完整 sample arrays。

受控 fault-injection wrapper（不拔 USB）确认：frequency query 失败和 Vpp query 失败仍保留
waveform/software evidence、总体为 degraded；waveform capture 失败不会伪造 software
frequency/duty/Vpp，总体为 failed。

## HIL script

`scripts/check_measurement_service.py` 通过 composition root 获取 runtime，所有 status 和
measurement 业务调用只经过 MeasurementService。它不导入 Driver/PyVISA，不直接调用
driver measurement methods，不发 SCPI，也不实现 analysis。

一次运行依次执行 status、frequency、Vpp、waveform、PWM，并打印有限 JSON。输出包含脱敏
identity、ArtifactReference/metadata、instrument/software observations、quality、warnings、
coherence、provenance、Artifact round-trip verification 和真实 workflow order，不打印完整
waveform arrays 或底层对象。每个结果在打印前通过 Hardware Tool Schema。

真实 HIL 命令：

```powershell
.venv\Scripts\python.exe scripts\check_measurement_service.py --resource "USB0::0x1AB1::0x0517::DS1ZE243409517::INSTR" --channel 1
```

安全前提：仅使用安全低压 PWM，确认公共地，不探测市电或高压。InMemoryArtifactStore 仅在
当前进程可取，不持久、不跨进程、不耐久。

## Acceptance boundary

自动结构检查会要求 waveform/PWM Artifact round-trip 成功、结果不为 failed、PWM overall
quality 为 good，并输出 `ready_for_manual_review`。它不比较 instrument/software 误差，不建立
统一 accuracy threshold，也不能替代人工确认真实值、来源、coherence 与 provenance。

真实 HIL 输出返回前，不得声明 real MeasurementService workflow validated，不提交 Phase 6F，
不进入 Hardware Tool runtime、Agent、LLM、MCP 或 JLCEDA 联动。

## Actual real HIL observation

用户于 2026-09-06 使用真实 RIGOL DS1102Z-E（firmware `00.06.03.SP2`）和安全低压
CH1 PWM 完成 MeasurementService HIL。序列号按既有策略显示为 `***9517`。

独立 Service results：

| Scenario | Actual result |
|---|---|
| Status | identity/provenance present; Tool Schema accepted |
| Frequency | instrument `10000.0 Hz`, source=`instrument`, quality=`good` |
| Vpp | instrument `0.424 V`, source=`instrument`, quality=`good` |
| Waveform | 1200 points, 200 ns interval, normal acquisition, quality=`good` |

独立 waveform result 使用 artifact `1fed4cb8-6293-4972-891a-4aa778fa8cb6`，时间范围
`-120.4 us` 至 `119.4 us`，电压范围 `-0.384 V` 至 `0.036 V`。Artifact 在当前进程内
回读成功，channel、point count、sample interval、acquisition mode 和 capture metadata
与 Result 一致。

真实 PWM workflow result：

| Evidence | Value |
|---|---:|
| Instrument frequency | 10000.0 Hz |
| Instrument Vpp | 0.424 V |
| Software frequency | 10006.68233 Hz |
| Software period | 99.93322 us |
| Software high-level duty | 29.94510% |
| Software Vpp | 0.420 V |
| Software mean | -0.2240167 V |
| Software RMS | 0.2694676 V |

PWM overall quality=`good`、warnings=`[]`，algorithm=`aia.threshold_edges/1.0.0`。全部六项
software observations 引用同一个 PWM artifact
`f9d95387-df22-4283-a53a-1573dc837ff3`；instrument observations 没有伪造 waveform
artifact evidence。coherence 为 software `same_artifact`、cross-source
`sequential_same_session`。实际 timestamps 与实现顺序一致：capture/analysis 在 instrument
frequency/Vpp observations 之前，最终 provenance 覆盖完整 workflow。

两个 Artifact round-trip 均为 `verified=true` 且
`metadata_matches_stored_waveform=true`。脚本输出 `hil_acceptance=ready_for_manual_review`，
人工复核以上来源、coherence、provenance 和 artifact evidence 后，Phase 6F 判定为
**PASS with real MeasurementService end-to-end evidence**。

该结论只覆盖此台设备、当前 firmware、CH1、安全低压约 10 kHz/30% PWM、NORM/BYTE
1200-point screen waveform 和当前顺序 workflow。两次 capture 对应不同 Artifact，符合独立
measurement 语义。instrument queries 与 PWM artifact 不是原子/同时观测；数值没有用于建立
统一 accuracy threshold。InMemoryArtifactStore 仍仅为 process-local、non-durable。
