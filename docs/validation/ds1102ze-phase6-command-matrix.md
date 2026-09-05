# Phase 6A - DS1102Z-E Manual-to-Driver command matrix

审计日期：2026-09-06。状态：供评审；下列 Driver 方法均为拟定接口，尚未实现或连接实机。

依据为用户提供的 `DS1000ZE_ProgrammingGuide_EN.pdf`：2020-04，
PGA27101-1110，声明软件版本 00.06.02。手册正文以 DS1202Z-E 举例，
适用型号表同时包含 DS1102Z-E。表中页码使用印刷页码，括号内为 PDF 的 1-based 页序。
完整文件指纹和审计范围见 [validation record](ds1102ze-phase6-validation.md)。

大小写表示手册的 SCPI 缩写规则，不是两个不同命令。`<n>` 本阶段仅 1/2。
S = set，Q = query；S 命令没有测量返回值，通信成功不证明后置条件成立。
每组配置应做指定 Q 的 read-back；无法达到请求值时报告 InstrumentStateError。
下列范围来自手册，初版 Driver 可以选择明确的更小支持集合。

## Identity、通道、时基与测量

| 官方命令（S/Q 形式） | 参数范围 / 返回格式 | 前置条件与状态影响 | 拟定 Driver 方法 | 手册 |
|---|---|---|---|---|
| Q `*IDN?` | 四个逗号分隔字段：厂商、型号、序列号、软件版本；手册厂商为 `RIGOL TECHNOLOGIES` | 连接后首先查询；不修改设置；型号必须确认为 DS1102Z-E，不能只看 VISA resource 名称 | `identify()` | 2-70 (86) |
| S `:CHANnel<n>:DISPlay <bool>`；Q `:CHANnel<n>:DISPlay?` | S: ON/OFF/1/0；Q: 1/0 | S 开关通道，会影响采样资源分配；本阶段测量前明确启用目标通道 | `set_channel_enabled()` / `get_channel_enabled()` | 2-9 (25) |
| S `:CHANnel<n>:COUPling <coupling>`；Q `:CHANnel<n>:COUPling?` | AC/DC/GND；Q 返回同一枚举 | S 改变信号耦合；PWM 基线使用 DC 并回读 | `set_channel_coupling()` / `get_channel_coupling()` | 2-9 (25) |
| S `:CHANnel<n>:PROBe <atten>`；Q `:CHANnel<n>:PROBe?` | 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000；Q 为科学计数法 | S 改变显示比例和 scale 范围；不能改变物理探头开关；先确定比例再验证 scale | `set_probe_ratio()` / `get_probe_ratio()` | 2-13 (29) |
| S `:CHANnel<n>:SCALe <scale>`；Q `:CHANnel<n>:SCALe?` | 1X: 0.001-10 V/div；10X: 0.01-100 V/div；Q 为科学计数法 | 范围依赖 probe；VERNier OFF 时为 1-2-5 档；S 改变垂直设置 | `set_channel_scale()` / `get_channel_scale()` | 2-13 (29) |
| Q `:CHANnel<n>:VERNier?`（S 形式 `<bool>` 暂不开放） | Q: 1/0 | 查询微调状态以判定合法 scale；拟定初版仅支持 OFF，遇 ON 明确拒绝该配置流程 | `read_channel_settings()` | 2-14 (30) |
| Q `:CHANnel<n>:UNITs?`（S 形式 `<units>` 暂不开放） | Q: VOLT/WATT/AMP/UNKN；S 枚举 VOLTage/WATT/AMPere/UNKNown | 检查换算单位；基线要求 VOLT，不把其他单位标记为 vpp_v | `read_channel_settings()` | 2-14 (30) |
| S `:TIMebase[:MAIN]:SCALe <scale>`；Q `:TIMebase[:MAIN]:SCALe?` | YT: 2 ns/div-50 s/div，1-2-5；ROLL: 100 ms/div-50 s/div，1-2-5；Q 科学计数法 | S 修改时基；具体模型/固件需回读验证；Driver 显式发送 MAIN 路径 | `set_timebase_scale()` / `get_timebase_scale()` | 2-121 (137) |
| Q `:TIMebase:MODE?`（S `<mode>` 暂不开放） | MAIN/XY/ROLL | 不改状态；第一条垂直切片要求 MAIN，避免直接把 YT 时基范围用于 XY/ROLL | `read_acquisition_settings()` | 2-122 (138) |
| Q `:MEASure:ITEM? FREQuency,CHANnel<n>` | FREQuency 为手册 item；响应为科学计数法，含义为 Hz | 显式指定 source；不依赖全局 `:MEASure:SOURce`；需要可测波形。Q 不主动启用屏幕测量项 | `measure_frequency()` | 2-97、2-108 (113、124) |
| Q `:MEASure:ITEM? VPP,CHANnel<n>` | VPP 为最大值与最小值差；响应为科学计数法；本切片在 VOLT 单位下解释为 V | 同上；与 software Vpp 比较时必须记录采样窗口和设置 | `measure_vpp()` | 2-99、2-108 (115、124) |
| 对照说明：S `:MEASure:ITEM <item>,CHANnel<n>` | 手册有 37 个 item；本阶段不做全量封装 | S 启用相应测量项，会改变测量显示状态；不能把 S 当作上面 Q 的同义词 | 暂不开放；屏幕测量项由人工设置 | 2-108 (124) |
| Q `:MEASure:SETup:MID?`（S `<value>` 暂不开放） | Q 整数 6-94，默认 50，表示幅度百分比 | 只记录仪器时间测量阈值；不擅自修改，与软件阈值一起保存 | `read_measurement_settings()` | 2-104 (120) |

`SCALe` 章节只对 1X/10X 给出明确端点；首版可只支持这两种 probe ratio。
其他 attenuation 虽是官方合法值，也不能在未验证边界前按猜测扩展 Driver scale 范围。
配置数值 read-back 容差用于浮点/序列化误差，与 HIL 的测量准确度判据是两回事。

## Acquisition、错误诊断

| 官方命令 | 参数 / 返回格式 | 前置条件与状态影响 | 拟定 Driver 方法 | 手册 |
|---|---|---|---|---|
| S `:RUN` | 无参数、无对应 RUN? | 开始采集；录制/回放时无效。需用触发状态确认，不能把 write 完成当作开始了新记录 | `run()` | 2-2 (18) |
| S `:STOP` | 无参数、无对应 STOP? | 停止采集；录制/回放时无效；RAW 前等待触发状态 STOP | `stop()` | 2-2 (18) |
| S `:SINGle` | 无参数 | 等待一次满足条件的触发后停止；写入后可能仍 WAIT；录制/回放时无效 | `single()`（场景确实需要才开放） | 2-3 (19) |
| Q `:TRIGger:STATus?` | TD/WAIT/RUN/AUTO/STOP | 不修改配置；用于有 deadline 的状态轮询；STOP 不等于刚刚完成了一次新采集 | `get_acquisition_state()` | 2-124 (140) |
| Q `:ACQuire:SRATe?` | 科学计数法，Sa/s | 读取 ADC 采样率；与 NORMal 导出点间隔分别保存 | `read_acquisition_settings()` | 2-6 (22) |
| Q `:ACQuire:TYPE?`（S `<type>` 暂不开放） | NORM/AVER/PEAK/HRES | 读取采集模式；初版质量基线选 NORM，其他模式先报告不支持或显式质量限制 | `read_acquisition_settings()` | 2-5 至 2-6 (21-22) |
| Q `:ACQuire:MDEPth?`（S `<mdep>` 暂不开放） | 整数或 AUTO；单通道可设 AUTO/12000/120000/1200000/12000000/24000000；双通道 AUTO/6000/60000/600000/6000000/12000000 | 查询不改变状态；AUTO 不能当整数。实际导出点数还要结合 preamble 和读取区间 | `read_acquisition_settings()` | 2-5 (21) |
| Q `:SYSTem:ERRor[:NEXT]?` | 整数错误码 + 逗号 + ASCII 错误内容（示例为带引号字符串） | **查询会删除一条系统错误记录**；开发/HIL 模式在关键配置后有界读取，保存错误；手册该页未给出队列空时完整响应 | `check_errors()` | 2-116 (132) |
| Q `*OPC?`（可选，不作为触发完成凭据） | 手册描述完成返回 1，否则 0 | 仅是操作完成查询；不能替代 `:TRIGger:STATus?` 或证明信号/波形已更新 | 可选内部同步；非首版必需 | 2-70 (86) |

不采用 `*RST`、`:AUToscale` 作为隐式连接初始化；它们会改变超出指定配置的状态。
手册未在 `:MEASure:ITEM?` 一节规定无效结果 sentinel，不能把其他命令的 `9.9E37`
示例移植为该命令的官方规范。真实空输入/不可测返回格式及 error queue 空响应需在 HIL 记录。

## Waveform

| 官方命令（S/Q 形式） | 参数范围 / 返回格式 | 前置条件与状态影响 | 拟定 Driver 方法 | 手册 |
|---|---|---|---|---|
| S `:WAVeform:SOURce <source>`；Q `:WAVeform:SOURce?` | CHANnel1/CHANnel2/MATH；Q CHAN1/CHAN2/MATH；首版仅 CH1/CH2 | S 改变下载源；必须与请求 channel 一致 | `capture_waveform()` 内部 source 配置/回读 | 2-175 (191) |
| S `:WAVeform:MODE <mode>`；Q `:WAVeform:MODE?` | NORMal/MAXimum/RAW；Q NORM/MAX/RAW | S 改变导出模式；RAW 只在 STOP 读取，读取中不得操作示波器；MAX 的含义随 RUN/STOP 改变，首版不选 MAX | `capture_waveform()` 内部 mode 配置/回读 | 2-175 至 2-176 (191-192) |
| S `:WAVeform:FORMat <format>`；Q `:WAVeform:FORMat?` | BYTE/WORD/ASCii；Q BYTE/WORD/ASC；首版仅 BYTE | S 改变编码；BYTE 每点 1 byte；WORD 每点 2 bytes 但只有低 8 位有效，不能称作 16 位 ADC 精度 | `capture_waveform()` 内部 format 配置/回读 | 2-176 (192) |
| S `:WAVeform:STARt <sta>`；Q `:WAVeform:STARt?` | 1-based；NORM 1-1200；RAW 1-当前最大存储深度；Q 整数 | S 改变读取区间；与 STOP 为闭区间；MAX 的表述与状态相关，不纳入首版 | `capture_waveform()` 内部范围检查/回读 | 2-181 (197) |
| S `:WAVeform:STOP <stop>`；Q `:WAVeform:STOP?` | 与 STARt 相同；Q 整数；默认 1200 | S 改变读取区间，**不是**停止采集的 `:STOP`；必须 stop >= start | `capture_waveform()` 内部范围检查/回读 | 2-182 (198) |
| Q `:WAVeform:DATA?` | BYTE/WORD 为 definite-length block；该机手册写为 `#9` + 9 位字节长度 + payload | 先 source/mode/format/range；RAW 必须 STOP；BYTE 单请求 <=250000 点，WORD <=125000，ASCII <=15625；Q 不配置仪器 | `capture_waveform()` / 内部 `read_waveform_block()` | 2-176 至 2-179 (192-195) |
| Q `:WAVeform:PREamble?` | 10 个逗号分隔参数，见下 | 查询当前 waveform source/mode 下元数据；和 DATA 必须在同一次受控采集状态下读取 | 内部 `read_waveform_preamble()` | 2-182 至 2-183 (198-199) |
| Q `:WAVeform:XINCrement?` | 科学计数法；CH1/CH2 为秒；NORM=TimeScale/100，RAW=1/SampleRate | 不改状态；必须读取而不是猜测。MAX 按 RUN/STOP 切换定义 | 内部 preamble 交叉核验 | 2-179 (195) |
| Q `:WAVeform:XORigin?` | 科学计数法；NORM 屏幕起始时间，RAW 内存波形起始时间，单位 s | 与当前 source/mode 绑定 | 同上 | 2-180 (196) |
| Q `:WAVeform:XREFerence?` | 手册说明返回 0，表示第一点 | 不能用 1-based STARt 直接代替；若返回非零，记录兼容性差异后暂停该路径 | 同上 | 2-180 (196) |
| Q `:WAVeform:YINCrement?` | 科学计数法，单位随通道幅度单位；NORM=VerticalScale/25 | RAW 与采集时/当前 vertical scale 有关，必须查询；不要硬套屏幕公式 | 同上 | 2-180 (196) |
| Q `:WAVeform:YORigin?` | 整数，编码空间的垂直偏移；NORM=VerticalOffset/YINCrement | 不是直接以 V 为单位的加法偏置；RAW 定义依赖仪器状态 | 同上 | 2-181 (197) |
| Q `:WAVeform:YREFerence?` | 手册说明返回 127 | 仍解析查询值/保存实际值；实机与文档不同应报告，不能静默硬编码 128 | 同上 | 2-181 (197) |

Preamble 顺序严格为：

`format, type, points, count, xincrement, xorigin, xreference, yincrement, yorigin, yreference`

`format` 为 0 BYTE / 1 WORD / 2 ASC；`type` 为 0 NORM / 1 MAX / 2 RAW，
并非 `:ACQuire:TYPE?` 的采集模式。`points` 为 1-24000000 的整数；
`count` 为平均模式的平均次数，否则 1。partial read 的 payload 点数按请求闭区间计算，
不能在未确认语义前强行让它等于整份 preamble 的 points。

矩阵之外的 API 不是已批准实现清单。六个单独的 X/Y query 可以用于开发/HIL 的 preamble
交叉验证；正常路径可只读取一次 preamble，避免每一点/每个块重复全部查询。
