# fixture · BC 场景（同一 UTC 两版本两墙钟）

> 一句话：**注入了"官方放弃 DST、永久停在夏令时"的省级立法形态** —— 同一本地墙钟在
> 两棵树下映射到相差一小时的 UTC；并用两条行锚住 `audit` 的判定顺序。

## 注入了什么

一个 zone（`Zone/Bc`）的两棵树，`old/` 与 `new/`：

| | 旧树 `old/`（标签 `2026a`） | 新树 `new/`（标签 `2026b`） |
|---|---|---|
| 表内历史 | 1970 → 2025-11 的完整季节转换（`PST`/`PDT`） | 1970 → **2025-03**（停在最后一次起跳，此后再不回拨） |
| tail | `PST8PDT,M3.2.0,M11.1.0` | `MST7`（永久 −7，即"停在夏令时"） |
| 表尾自洽 | 表尾 `PST`(−8) 与 tail 的 std(−8) 一致 | 表尾 `PDT`(−7) 与 tail 的 −7 一致 |

**两棵树各自自洽**：表尾那个转换点的偏移与 tail 在该点的偏移一致。这是 `plan/04` 的
反例纪律——树不自洽时造出来的"窗口 / 差异"是假的（M4 踩过：表说 EST、tail 说 EDT）。

## 为什么需要它

`plan/03` §七 的五条测试点里有两条只能靠它咬住：

1. **`VERSION_CHANGED` 的判据** = 同一本地墙钟在两棵树下的 **UTC 不同**。
   `bc-version-changed`（2026-12-15 12:00）在旧树下是 `20:00Z`（−8）、
   在新树下是 `19:00Z`（−7）—— 相差一小时。
   同一件事的 **UTC 视角**：`19:00Z` 在旧树下是 `11:00` 墙钟、在新树下是 `12:00` 墙钟。
   这就是 Cal.com #30104 事故"同一时刻在两个版本的墙钟不一样"的复现口径。
2. **判定顺序**：`bc-gap`（2026-03-08 02:30）在旧树是 GAP、在新树**存在**；
   `bc-overlap`（2026-11-01 01:30）在旧树 2 个候选、新树 1 个。
   按 `INVALID → GAP → OVERLAP → VERSION_CHANGED → OK` 必须分别报 **GAP** / **OVERLAP**；
   把 `VERSION_CHANGED` 提前就翻成 `VERSION_CHANGED`。这是顺序变异唯一的真锚点。

## 期望值怎么来的

**不调产品代码**。每条期望由"注入了什么"手算：偏移是输入常量
（旧树冬 −8 / 夏 −7，新树恒 −7），`UTC = 墙钟 − 偏移`，
日历换算用 `_support._epoch`（生成期用 `datetime`，与产品侧的自研整数算法不是同一份代码）。

## 产物

```text
gen.py              生成器（--check 重生成到临时目录并逐字节比对 + 自检形态）
expect.json         金标（只存输入 + 期望，无 observed_*）
times.txt           清单（4 行，顺序即期望输出行序）
old/provenance.json 旧树元信息（version=2026a；`audit --version` 要求每棵树都带）
old/Zone/Bc         旧树 TZif
new/provenance.json 新树元信息（version=2026b）
new/Zone/Bc         新树 TZif
```

## 重建

```bash
py -3.12 data/fixtures/audit/bc-scenario/gen.py            # 写产物
py -3.12 data/fixtures/audit/bc-scenario/gen.py --check    # 两层断言：形态 + 逐字节
```

`--check` 的两层断言（`plan/04` §三 第 2 条）：① `build()` 写完后立刻 `_self_check`
（TZif 魔数 / provenance 必备键 / 期望覆盖四种状态）；② 重生成到临时目录后与入仓件逐字节比对。
只做 ② 会在"生成器被改坏但两次坏成一样"时仍绿。
