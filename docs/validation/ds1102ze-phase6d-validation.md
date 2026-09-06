# Phase 6D - Deterministic waveform analysis validation

更新日期：2026-09-06。Phase 6C 基线：
`af20ba0 feat(hardware): add validated DS1102Z-E waveform acquisition`。

本阶段只建立 provider-neutral、无 I/O 的确定性波形分析。当前内容只有 synthetic
自动测试证据；尚未执行真实 DS1102Z-E analysis HIL，尚未提交 Phase 6D。

## Architecture

`Waveform -> analyze_waveform() -> WaveformAnalysisResult`

- Analysis 只依赖 provider-neutral `Waveform`、`InstrumentIdentity` 和共享
  `DutyCycle` value object。
- `DutyCycle` 从 EDA models 提升到 `domain/values.py`；原 EDA import 仍重导出同一类，
  不复制 ratio/percent 语义。
- Analysis 不依赖 Rigol、VISA、SCPI、PyVISA、JLCEDA、Agent、Tool 或 NumPy。
- Driver 不依赖 Analysis。真实对比只存在于开发期 HIL 脚本，不是 MeasurementService。

## Immutable result

`WaveformAnalysisResult` 包含：Vpp、mean、population RMS、可空 frequency/period、
可空 `DutyCycle`、good/degraded/invalid quality、typed warnings、algorithm metadata 与
有限 `WaveformProvenance`。它不返回任意 dict，也不复制大型 sample arrays。

Algorithm metadata 固定记录：名称/版本、threshold/hysteresis strategy 与数值、rising/
falling edge count、实际采用的 period 与 duty sample 数。HIL 或未来 Agent 可以解释结果，
但不能把 metadata 当作测量准确度证明。

## Deterministic algorithms

基础统计：

- `Vpp = max(v) - min(v)`。
- `Mean = arithmetic mean`；实现先按最大绝对值归一化，再用 `math.fsum`，避免不必要溢出。
- `RMS = sqrt(mean(v²))`；同样先归一化，结果为 Python float。
- 空、非有限 waveform 在 Domain boundary 拒绝；有限输入若 span 计算溢出也明确拒绝。

周期分析：

1. 检查时间值 finite、strictly increasing，并验证所有步长及 metadata sample interval
   在 `1e-6` 相对容差（且绝对下限 1 fs）内一致。
2. 幅值必须至少为 `max(4 * voltage_increment, 1e-12 V)`；这是基于量化分辨率的门限，
   不是 TTL 1.65 V 假设。
3. threshold 使用 `midpoint(min,max)`。
4. hysteresis 使用幅值 10% 的对称总带宽，即 midpoint 上下各 5%。
5. 对 Schmitt state transition 做线性 crossing interpolation，分别提取 rising/falling。
6. 使用相邻 rising edges 得到多个 period；至少需要两个完整 period。
7. period 以 median 为中心，只保留相差不超过 10% 的 inlier；inlier 少于两个或少于
   原 period 的 75% 时报告 `unstable_period`，不输出 frequency/period/duty。
8. Duty 使用 `rising -> falling -> next rising` 的完整周期，绝不使用整个窗口中高电平
   sample 比例；对多个 duty ratios 再做 median 聚合。

Clipping 只能是启发式 warning：当至少 20 点、至少 8 个不同电平，且 min/max 各占
至少 5% 时标记 `clipped_signal_suspected`。两电平理想方波不会仅因平台而被误判；该
warning 会把 quality 降为 degraded，但不隐藏仍可计算的指标。

## Quality gates and warnings

支持：`insufficient_samples`、`insufficient_cycles`、`signal_too_small`、
`unstable_period`、`clipped_signal_suspected`、`ambiguous_threshold`、
`no_edges_detected`、`invalid_time_axis`、`nonuniform_sampling`。

- good：frequency 与 duty 都可用，且没有 warning。
- degraded：基础统计可用，但周期证据不足、幅值过小、clipping suspected，或部分周期
  指标不可用。
- invalid：时间轴本身不满足算法前提；Vpp/mean/RMS 仍可作为与时间无关的统计返回。

不会为 DC、噪声、短窗口或不稳定周期强制生成频率。

## TDD evidence and golden tolerances

初始 Red：两个 Analysis test modules import error；Analysis 目录与 HIL 脚本 architecture
tests 各失败一次。实现后发现新测试目录缺少 `__init__.py`，导致统一 discovery 只增加
architecture tests；补齐 package marker 后，全部 golden tests 正式进入统一 runner。
按 Phase 6C 的 1200 点/200 ns 窗口新增 golden 时，最初用 microhertz tolerance 得到
9990.00999 Hz 而失败；原因是边沿在 200 ns sample grid 上量化，不是倍频错误。随后按
`dt / period` 推导为约 20 Hz 上限，测试采用 21 Hz，并保持算法不含 10 kHz 特判。

覆盖场景：10 kHz/30%、1 kHz/50%、DC、constant zero、小幅噪声、noisy square、
非整数周期窗口、phase shifted window、轻微 jitter、严重 period instability、周期不足、
clipped-looking sine、非递增/非均匀时间轴、单点输入及有限数值 span overflow。

容差按 fixture 的采样分辨率设置而不是全局 1%：

- 无噪声且每周期恰好 100 点：线性 crossing 的 frequency 允许 1 microhertz 数值误差；
  duty 允许 1.1 percentage points，相当于略大于一个 sample/period。
- noisy/jittered 10 kHz：frequency 允许 100 Hz，对应 1 us crossing uncertainty；duty
  允许 2.1 percentage points，对应两个独立 edge 各约一个 sample 的最坏离散误差。
- Phase 6C 1200 点/200 ns 窗口：frequency 允许 21 Hz，来自一个 200 ns edge step 对
  100 us period 的误差传播；duty 允许 0.3 percentage points。
- clipped 1 kHz：允许 20 Hz，覆盖 10 us sample resolution 与迟滞 crossing 偏移。

完整统一 runner 结果：Python 216 项、TypeScript shared contract 14 项、TypeScript
extension/runtime/architecture 70 项，全部通过。没有保存或提交真实 waveform 数组：
Phase 6C 只产生了有限 console 摘要，无法建立诚实的 recorded regression fixture。

## Pending real analysis HIL

在安全低压 PWM、确认共地后运行：

```powershell
.venv\Scripts\python.exe scripts\check_ds1102ze_analysis.py --resource "<exact discovered VISA resource>" --channel 1
```

脚本顺序执行 waveform capture、software analysis、instrument frequency/Vpp query，输出
side-by-side observation。它明确声明这些不是同一原子记录，不设置任意 `<1%` 自动通过
标准。需要人工关注：frequency 数量级、duty 与信号设计、Vpp 量级、edge counts、quality
与 warnings。真实结果返回前不提交 Phase 6D，不进入 MeasurementService 或 Hardware Tool。

## Actual real analysis HIL and stop condition

用户于 2026-09-06 在同一安全低压 CH1 场景完成真实 analysis HIL。有限实际结果：

| Metric | Instrument | Software |
|---|---:|---:|
| Frequency | 10000.0 Hz | 10000.0 Hz |
| Vpp / voltage span | 0.352 V | 0.360 V |
| Period | — | 100 us |
| Mean | — | -0.1118367 V |
| RMS | — | 0.1871507 V |
| Duty | 未查询 | 69.99984% |

Waveform 仍为 1200 点、200 ns、239.8 us。软件检测 3 个 rising edges、2 个 falling
edges，采用 2 个完整 period 和 2 个 duty ratios；quality=`good`、warnings 为空。
frequency 没有出现 5 kHz/20 kHz 倍频错误。软件 Vpp 与随后 instrument query 相差
0.008 V（约 2.27%），两者不是同一原子记录，因此只记为量级一致。

Duty 触发停止条件：设计/信号口头预期为约 30%，软件按“电压高于动态中点的持续时间”
得到约 70%，两者互为补数。当前 waveform 大致在 -0.34 V 与 0 V 之间，mean 约
-0.112 V；这些数据与“负电平约占 30%，较高电平约占 70%”相容。因此现有证据没有
证明 edge detector 算错，更可能是以下尚未确认的语义之一：

- 信号本身为 active-low，所谓 30% 指低有效脉宽；
- 示波器 CH1 inversion 或源端反相改变了可见极性；
- 外部源所配置的 polarity/duty 定义与“高电平 duty”不同。

不得把 70% 自动翻转为 30%，也不得按已知目标硬编码。`quality=good` 当前只表示算法对
观测波形得到稳定、内部一致的 edge evidence，不表示它符合设计期望。

Phase 6D 判定为 **HIL stopped: polarity/active-level semantics unresolved**。保持代码和
自动测试不变，不提交 Phase 6D，不进入下一阶段。下一步需要独立确认：屏幕上正脉宽/
负脉宽或 duty 读数、CH1 invert 状态，以及信号源期望是 active-high 30% 还是
active-low 30%。

### Follow-up: physical connection issue confirmed

用户随后确认探头与参考地接反。该物理接线错误可以解释实测高电平 duty 约 70% 与
预期约 30% 互为补数：反相后的电压波形改变了“高于动态中点”的持续时间，但没有改变
周期。因此前一次结果保留为有效的故障观测，不作为算法缺陷，也不作为 Phase 6D HIL
通过证据。

必须在断开被测信号并安全纠正连接后重新执行相同 HIL。重新测量前仍保持 Phase 6D
未提交、停止状态；不得用软件自动翻转占空比来补偿物理接线错误。

### Corrected-connection HIL result

用户安全纠正连接后，于 2026-09-06 使用相同仪器、CH1 和分析脚本完成复测：

| Metric | Instrument | Software |
|---|---:|---:|
| Frequency | 10020.04 Hz | 10006.7755 Hz |
| Vpp / voltage span | 0.424 V | 0.416 V |
| Period | — | 99.9323 us |
| Mean | — | -0.2245 V |
| RMS | — | 0.2700417 V |
| High-level duty | 未查询 | 29.95514% |

Waveform 为 1200 点、200 ns sample interval、239.8 us time span。软件检测到 3 个
rising edges、2 个 falling edges，采用 2 个完整 periods 和 2 个 duty ratios；
quality=`good`、warnings 为空。频率没有 5 kHz/20 kHz 倍频或半频现象，占空比与
约 30% high-level PWM 的设计语义一致。

仪器查询与软件分析是顺序观测，不是同一原子记录：frequency 相差约 13.26 Hz，Vpp
相差 0.008 V。这里只记录两者量级和行为一致，不建立任意准确度合格阈值。

判定：**Phase 6D real waveform-analysis HIL PASS with bounded observations**。首次 70%
结果保留为错误物理接线下的有效故障证据；纠正接线后的结果证明无需翻转算法输出或
硬编码 10 kHz/30%。
