# AI Instrument Assistant

AI Instrument Assistant 是一个以 Python 为核心的电子设计与仪器测量项目。系统通过明确的接口和安全边界，把 EDA 中的电路设计信息、真实仪器测量结果与 AI 辅助分析连接起来。

目前经过真实设备验证的仪器是 **Rigol DS1102Z-E 示波器**。仓库包含嘉立创 EDA 只读集成、元狸图 MCP 只读适配器、DeepSeek Harness 集成、确定性测量分析与证据处理，以及 RE-001 RC 低通实验的有限垂直切片。

项目仍处于工程验证阶段。真实运行记录只证明文档中注明的设备、接线、操作和工作流；不代表通用仪器兼容、自动实验或工业计量认证。

## 系统架构

```text
设计侧：嘉立创 EDA / 元狸图 MCP → EDA Adapter → EDAInterface → 设计证据 ┐
                                                                     ├→ 确定性关联与比较
测量侧：Rigol → VISA / SCPI → Driver → 测量服务 → 测量证据 ──────────┘          ↓
                                                            Grounding → Egress → 结果

执行控制：用户请求 → Harness 选择语义工具 ───────┐
          可信工作流 → Scope + Physical Policy ─┴→ 授权门 → Hardware IPC → 测量服务
```

系统采用 Ports and Adapters：Python Domain 与 Application 层只依赖与厂商无关的接口；嘉立创 EDA、元狸图、DeepSeek Harness、VISA/SCPI 和 Rigol 的细节分别留在适配器、通信层或驱动层。跨语言消息结构以 [`protocols/`](protocols/) 下的版本化 JSON Schema 为准；认证、会话、关联与重放规则由协议状态逻辑处理。

### 主要子系统

| 子系统 | 当前实现 |
| --- | --- |
| EDA | 与厂商无关的设计模型和 `EDAInterface`；嘉立创 TypeScript 扩展；元狸图 MCP 只读适配器；Python Application Host |
| 仪器 | VISA 通信、SCPI 会话、DS1102Z-E 驱动、示波器接口、波形模型及确定性分析 |
| Hardware Tool | `get_status`、`measure_frequency`、`measure_vpp`、`capture_waveform`、`measure_pwm` 五个受限语义操作 |
| 安全控制 | `TrustedOperationScope`、独立的 Physical Policy、物理接线确认、单次调用预算和认证 IPC |
| 证据与输出 | 设计与测量来源分离、确定性交叉引用与比较、Grounding 和 Egress 检查 |

## 已验证范围

- **Phase 8：完成。** 建立设计证据与测量证据的确定性关联、受限的工程比较和结构化结果发布。
- **Phase 8.5A：完成。** 建立 Python Application Host、会话与工作流状态、一次性 Challenge 等基础能力。
- **Phase 8.5B：有限集成，暂时关闭。** 嘉立创扩展的启动、Provider/Interactive 连接、状态、手动刷新及只读 EDA 路径已保留；在已评审的嘉立创 3.x 运行时中，自动读取当前 UI 选择仍不够可靠。
- **RE-001 核心端到端证明：完成。** 用户请求能够经过可信确认、受控的真实测量、确定性分析和证据约束的结果发布。该验证证明的是对话式实验数据流，**不是** RC 滤波器物理性能验证。

当前**没有证明**自动生成或修改 EDA 设计、可靠地从嘉立创当前 UI 选择自动绑定探针、自动控制信号发生器、频率扫描、截止频率搜索、因果诊断或通用实验室自动化。具体阶段和真实验证结论见 [阶段状态](docs/architecture/PHASE_STATUS.md) 与 [验证记录](docs/validation/)。

## 安全边界

- AI 选择工具不等于获得工具执行权限；自然语言和模型参数不能创建或扩大可信授权。
- 真实测量需要语义操作授权与独立的物理安全确认。EDA 选择不能代替探头接线确认。
- 系统不向模型开放原始 SCPI、通用硬件执行器或任意 JavaScript 执行。
- 授权拒绝时不发送 Hardware IPC，也不产生硬件副作用；失败后不自动重试或重新测量。
- 大型波形数据通过不透明的 `ArtifactReference` 引用，不直接进入模型侧工具结果。
- 设计目标、仪器事实、软件分析和模拟证据保留各自的来源，不互相冒充。

完整约束见 [架构不变量](docs/architecture/ARCHITECTURE_INVARIANTS.md)。

## 仓库结构

```text
src/ai_instrument_assistant/
  domain/          与厂商无关的领域模型
  application/     用例、接口、Application Host 和工作流
  communication/   通信与会话抽象
  drivers/         仪器驱动
  hardware/        Hardware Tool 运行与策略集成
  integrations/    嘉立创、元狸图、DeepSeek 等适配器
  analysis/        确定性信号与证据分析

extensions/
  jlceda/           嘉立创 TypeScript 扩展
  deepseek-harness/ DeepSeek Harness 集成

protocols/          跨语言 JSON Schema 协议
tests/              Python 单元、集成、契约和架构测试
docs/               架构决策与验证记录
scripts/            测试入口及需单独授权的真实验证脚本
```

## 本地准备

需要 Python **3.11 或更新版本**、Node.js **24 或更新版本**及 npm。以下命令在 Windows PowerShell 中执行：

```powershell
git clone https://github.com/LLLLX-6/AI_Instrument_Assistant.git
cd AI_Instrument_Assistant

py -3 --version  # 确认版本不低于 3.11
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
npm ci
```

仅在需要真实 VISA 仪器时安装可选依赖，并配置兼容的 VISA 后端：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[hardware]"
```

普通安装和测试不会提供真实 EDA、模型或仪器的访问凭据。真实外部操作需要单独的本地配置和相应的可信授权。

### 运行测试与构建

Python 与嘉立创扩展的离线测试可分别运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm run test:jlceda
```

完整测试和构建还需要一份**单独的、已编译的官方 DeepSeek Harness 源码检出目录**。当前集成只接受提交 `d347e703908d0406b7a7ef80e3a0e594d86b2215`；Harness 所需包必须已生成 `lib/index.js`。按[官方开发说明](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/development.md)准备该目录后，在当前 PowerShell 会话中设置：

```powershell
$env:DEEPSEEK_HARNESS_DEV_ROOT = 'C:\path\to\deepseek-harness'
git -C $env:DEEPSEEK_HARNESS_DEV_ROOT rev-parse HEAD
# 上一行必须返回 d347e703908d0406b7a7ef80e3a0e594d86b2215
```

然后运行完整离线回归与构建：

```powershell
.\.venv\Scripts\python.exe scripts\run_contract_tests.py
npm run build
```

也可以单独运行 Harness 测试：

```powershell
npm run test:harness
```

缺少 `DEEPSEEK_HARNESS_DEV_ROOT` 或目录未编译时，完整测试会在 Harness 准备阶段停止；这不表示 Python 或嘉立创测试失败。

普通测试使用 Fake、合成数据或记录的有限样例。以 `validate_`、`check_` 等命名的真实验证脚本可能访问外部系统；运行前应先阅读脚本和对应验证文档。

## 本地连接边界

| 默认端口 | 用途 |
| --- | --- |
| `127.0.0.1:49624` | 嘉立创 EDA Provider 协议 |
| `127.0.0.1:49625` | Harness 与 Hardware Backend 的认证 IPC |
| `127.0.0.1:49626` | 交互界面与 Application Host 协议 |

三条连接分别管理凭据、会话和消息关联，不能作为同一权限边界使用。

## 文档入口

- [项目上下文](CODEX.md)
- [项目架构基线](docs/architecture/PROJECT_BASELINE.md)
- [架构不变量](docs/architecture/ARCHITECTURE_INVARIANTS.md)
- [阶段状态](docs/architecture/PHASE_STATUS.md)
- [版本化协议](protocols/)
- [真实验证记录](docs/validation/)

历史上未通过的验证记录会保留；后续修复或通过验证不会改写先前结果。

仓库目前没有 `LICENSE` 文件。团队使用、复制或再分发代码的规则请与仓库所有者确认。
