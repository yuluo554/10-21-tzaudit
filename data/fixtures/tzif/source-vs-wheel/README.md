# fixture · tzif/source-vs-wheel

**注入了什么**：**同一个 tzdata 版本（2026e）** 的两种构建形态，各 6 个 zone：

| 目录 | 来源 | 形态 |
|---|---|---|
| `fat/` | `data/_downloads/tzdata2026e.tar.gz` 的 `Rule`/`Zone` 行**编译** | 显式表覆盖 1900–2037，**无 footer**，不依赖 tail |
| `slim/` | `data/_downloads/slim/2026e`（PyPI wheel）**原样拷贝** | 表只到 2020 前后，语义靠 footer |

6 个 zone 覆盖 `plan/03` §二 的三种特殊形态 + 两个 tail-only 形态：
`America/New_York`、`America/Vancouver`（表内零迁移）、`Europe/Dublin`（负 DST）、
`Australia/Lord_Howe`（30 分钟）、`Pacific/Chatham`（+12:45）、`Asia/Tehran`（固定偏移）。

**为什么需要它**：主金标两棵树都是 slim（Q1 定案）。若没有"fat 与 slim 语义等价"的证据，
"slim 依赖 POSIX tail"就只是断言。本 fixture 的 fat 侧由 IANA 规则**独立编译**、
slim 侧由上游 wheel 提供 —— 两条独立来源，重叠区间内逐点比对。

**已知偏差（如实标注）**：本机**无 `zic`**（实测 2026-10-21）。fat 树由 `gen.py` 的规则编译器
生成，**不是** `zic` 的产物。编译器只覆盖这 6 个 zone 用到的形态（`%s` / `%z` / `A/B` 三种缩写、
`w`/`s`/`u` 三种时间基准、`lastSun` / `Sun>=n` / 数字日），遇到不认识的行直接报错——不猜。

**断言口径**：重叠区间（`overlap_start`–`overlap_end`，1990–2030）内，两棵树的
`(offset, abbr, is_dst)` 逐小时一致。实测 6 zone × 350640 小时 = **2103840 个采样点零差异**。

重建：`py -3.12 data/fixtures/tzif/source-vs-wheel/gen.py --check`
