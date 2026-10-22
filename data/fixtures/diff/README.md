# fixture · diff/change-classes

**注入了什么**：两组"旧树 / 新树"（`old/` 与 `new/`），每个 zone 注入一种版本漂移形态。
每棵树都是**合成 slim 形态**（v1 块压扁 + POSIX tail 承载当年语义），与真实 slim 树同形。

| zone | 注入的形态 | 期望分类 | `evidence` |
|---|---|---|---|
| `Zone/TailRule` | 表**逐字节相同**，仅 tail `PST8PDT,M3.2.0,M11.1.0` → `MST7`（真实 2026.1→2026.5 的 Vancouver） | `future_rule` | `tail` |
| `Zone/BcPermanent` | 旧树 2026 起继续 DST；新树表内多一条 2026-11-01 永久 UTC−7，tail 收成 `MST7` | `future_rule` | `tail` |
| `Zone/AbbrOnly` | 同一转换点、同一 offset，缩写 `AAA` → `BBB`；**两树均无 tail** | `abbreviation_only` | `abbr` |
| `Zone/AbbrAndTail` | **同时**改缩写（`AAA`→`BBB`）与 tail（`AAA-1`→`BBB-2`，offset 也变） | `future_rule` | `tail` |
| `Zone/LinkB` | 旧树与 `LinkA` 逐字节相同（互为 link）；新树改成独立 tail `LBK-5` | `future_rule` | `tail` |
| `Zone/LinkA` | 与旧树 `LinkB` 逐字节相同；新树里 `LinkB` 独立出去 → 别名集合变空 | `alias_only` | `link` |
| `Zone/Identical` | 两树**逐字节相同** | **零变更**（不产出记录） | — |

## 为什么需要它

`plan/03` §六 的五条测试点必须能被**独立复核**，而真实树的金标只有"20 个 zone 变了"这个总量：

1. **`future_rule` 的判据锚点必须是"表相同、只有 tail 变"**（`Zone/TailRule`）。
   没有这条，"实现直接比整份文件字节"也能全绿——那等于没判语义。
2. **四类互斥 + 判定顺序**需要一条"同时命中两类"的反证（`Zone/AbbrAndTail`）：
   缩写与 tail 同时变时必须落 `future_rule`。顺序若被调换，这条立刻红。
3. **零变更必须零记录**（`Zone/Identical`）——防"每个 zone 都报一条"的退化实现。
4. **`alias_only` 不得吸收规则变化**（`Zone/LinkB`）——防"两份副本就把规则差异吞掉"。
5. **`alias_only` 的两侧都要算**（`Zone/LinkA`）：旧树里 `LinkB → LinkA`（`LinkA` 是规范名、
   有别名挂在名下），新树里 `LinkB` 独立 → `LinkA` 的**别名集合**从 `("Zone/LinkB",)`
   变空。只看 `links.get(zone)` 会判成"没变化"。

## 金标的推导方式（不调产品代码）

`gen.py` 的期望值**直接由"注入了什么"手写**：形态 → 类别是 `data/README.md` §4.3 的定义，
不需要复算。树本身用 `data/fixtures/_support.py` 的 `build_tzif` 从手写类型表与 tail 串构造
（`_support` 是生成期工具，与产品侧自研的 `civil` 整数算法**不是同一份代码**）。

`expect.json` 的 `expected.changes[]` 逐条给出 `zone` / `class` / `evidence` / `note`；
`expected.not_changes[]` 列出**必须不产出记录**的 zone。
`tests/test_diff.py::test_diff_fixture_gold_matches_implementation` 逐条比对实现结果。

## 断言口径

- **同一 zone 只出现一条**（四类互斥）——测试断言 `changes` 里的 zone 无重复。
- `expected.class_order` 记录判定顺序常量，测试断言 `diff.CLASS_ORDER` 与它一致。
- 金标里**没有** `observed_*` 字段（`tests/test_truth_shape.py` 常驻守门）。

## 重建

```bash
py -3.12 data/fixtures/diff/gen.py           # 写产物
py -3.12 data/fixtures/diff/gen.py --check   # 重生成到临时目录并逐字节比对
```

`--check` 做**两层断言**（`plan/04` §三 硬纪律）：① 入仓产物自身在位；② 重生成到临时目录
与入仓件**逐字节**比对。只做 ① 会在生成器被改坏时仍绿。

## 生成期的两个坑（实测 2026-10-21）

1. **tail 串必须是合法 POSIX TZ**（`std offset` 两段）。首版写成 `ABT1`（只有名字、缺偏移）
   → `posix_tz.parse` 直接抛 `PosixTzError`，fixture 生成期就炸。
2. **每个 zone 的 blob 必须互不相同**（除刻意构造的 link 组）。首版让 `Identical` 与
   `LinkA` 用了同一份字节，结果 `links()` 把 `Identical` 也认成 `LinkA` 的别名，
   "零变更"的期望被"link 关系变化"顶掉。
