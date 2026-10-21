# fixture · tzif/slim-vs-fat

**注入了什么**：同一套规则（`EST5EDT,M3.2.0/2,M11.1.0/2`）的三种 TZif 编码。

| 文件 | 形态 | 表内转换点 |
|---|---|---|
| `fat.tzif` | fat 构建：v1 块也带全表，显式表覆盖 1970–2035 | 132 |
| `slim.tzif` | slim 构建：v1 块压扁为空表，显式表只到 1987 | 36 |
| `tail_only.tzif` | 极端 slim：表为空，语义**全在** footer | 0 |

**为什么需要它**：slim 树里大量 zone 的语义靠 POSIX tail 承载（表里看不到）。只读表的实现会把
这三者判成"三个完全不同的 zone"，从而在 M4 的 `diff` 里漏掉 tail 变化（Vancouver 就是这个形态）。

**断言口径**（Q1 定案）：**重叠区间**（`overlap_start`–`overlap_end`，即 1970–2036）内，
三者的 `to_local` / `resolve_local` 逐点一致。**不要求**版本号相同，也不比对重叠区间之外
（slim 的 tail 在表尾之前不生效，那一段的行为差异是**真实存在**的）。

**金标**：`expect.json` 的 `candidates` 逐条给出 8 个抽样本地时刻的 UTC 候选数
（0 = GAP / 1 = OK / 2 = OVERLAP），由 `gen.py` 用段区间包含式**独立**推导，不调产品代码。

重建：`py -3.12 data/fixtures/tzif/slim-vs-fat/gen.py --check`
