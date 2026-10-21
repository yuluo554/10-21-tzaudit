# fixture · windows/wall-clock-windows

**注入了什么**：一棵**合成** zoneinfo 树（6 个 zone），每个 zone 注入一种墙钟形态。
树用 **slim 形态**（v1 块压扁 + POSIX tail 承载当年语义），与真实 slim 树同形。

| zone | 注入的形态 | 期望窗口（2026） |
|---|---|---|
| `Zone/Standard` | 美式 DST（整小时） | GAP `02:00→03:00` + OVERLAP `01:00→02:00` |
| `Zone/HalfHour` | 30 分钟 DST（Lord_Howe 式）+ 南半球顺序 | OVERLAP `01:30→02:00` + GAP `02:00→02:30`，各 30 分钟 |
| `Zone/QuarterHour` | +12:45 非整点（Chatham 式） | OVERLAP `02:45→03:45` + GAP `02:45→03:45`，偏移含 45 分钟 |
| `Zone/NegativeDst` | 负 DST（Dublin 式：冬季 offset=0 / 夏季 +3600） | GAP `01:00→02:00` + OVERLAP `01:00→02:00`，方向仍按 offset 差 |
| `Zone/NoDst` | 无 DST（`MST7`） | **零条** |
| `Zone/AbbrevOnly` | **陷阱**：额外一个"offset 不变、只换缩写"的表内转换点 | 与 `Zone/Standard` 相同（**不得**多报一条） |

## 为什么需要它

`plan/03` §五 的三条反例必须能被**独立复核**，而真实树的金标只有"NY 2026 两条"这一条最直观：

1. **GAP 与 OVERLAP 的方向不能反**——合成树里每种形态各自独立，方向钉死在金标里。
2. **30 分钟 / 45 分钟**这类非整点形态：真实树能验，但**金标必须自带**一份，
   否则"只验了 NY"的退化实现也能全绿。
3. **零窗口的 zone 必须真的零窗口**（`Zone/NoDst`）——防"不扫描直接返回空"这种假绿。
4. **只换缩写不是窗口**（`Zone/AbbrevOnly`）——防"看到转换点就报一条"。

## 金标的推导方式（不调产品代码）

`gen.py` 用 `data/fixtures/_support.py` 的**段区间包含式**（`wall_candidates`）**独立推导**：

- 转换 UTC 由手写的规则表算出（`_support.year_transitions`，用 `datetime` 做日历，
  与产品侧自研整数算法 `civil.py` **不是同一份代码**）；
- 墙钟区间 = `[utc + before, utc + after)`；
- 区间内逐秒跑 `wall_candidates`：GAP 必须 0 个候选、OVERLAP 必须 2 个 → 不满足就丢弃。

产品实现走的是**另一条推理路径**（枚举全部候选 offset + 自洽校验）。
两条路径同时对，结果才相等——这就是"防引擎自证"。

## 断言口径

`expect.json` 的 `expected.windows[]` 逐条给出 `type` / `start_local` / `end_local` /
`duration_min` / `residual_sec` / `offset_before` / `offset_after`，
`tests/test_windows.py::test_windows_fixture_gold_matches_implementation` 逐条比对实现结果。

**注意**：金标里的 `source` 字段**不在** `expect.json` 中（它由"窗口来自表还是 tail"决定，
而合成树里恒为 `tail`，锁它没有信息量）。实现结果的 `source` 由
`tests/test_windows.py::test_window_records_the_engine_it_came_from` 单独断言。

## 重建

```bash
py -3.12 data/fixtures/windows/gen.py           # 写产物
py -3.12 data/fixtures/windows/gen.py --check   # 重生成到临时目录并逐字节比对
```

`--check` 做**两层断言**（`plan/04` §三 硬纪律）：① 入仓产物自身在位；② 重生成到临时目录
与入仓件**逐字节**比对。只做 ① 会在生成器被改坏时仍绿。
