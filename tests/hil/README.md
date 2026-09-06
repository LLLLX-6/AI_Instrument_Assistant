# DS1102Z-E HIL tests

此目录只记录需要用户明确接线和操作的真实硬件测试，不进入默认 CI。

Phase 6B 使用 `scripts/check_ds1102ze_basic.py`。默认读取身份和设置；
只有显式传入 `--verify-write` 才会写入通道 enable 状态并恢复原值，
只有明确接入安全低压信号并传入 `--measure` 才会查询 frequency/Vpp。

禁止连接市电或高压，外部信号必须先确认安全电压和共地。
