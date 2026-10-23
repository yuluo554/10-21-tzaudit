# tzaudit · 时区数据版本漂移审计

> **v0.1.1** — 本地 CLI，运行时**零网络**、**零第三方依赖**、**零遥测**。
> 状态：**五个子命令全部落地**（`version` / `windows` / `diff` / `audit` / `report`）。
> 交付面含五版本真实 provenance、五套件金标复算入口、TZif 解析器、POSIX tail 解析器、
> 表+tail 合并与本地反解、墙钟窗口、四类版本差异分类、清单审计与报告门禁。

竞品按小时采样 UTC 偏移，只能说"这个时区会错"。我们说三件它做不到的事：

1. **哪个本地墙钟区间根本不存在**（GAP）——`windows` 输出 `start_local` / `end_local` / `duration_min`；
2. **哪个出现两次**（OVERLAP）——同一组字段，外加 `offset_before` / `offset_after`；
3. **哪些历史时间戳的 UTC 解释被改写了**（`history_reinterpreted`）——`diff` 输出 `class` + `evidence`。

把"时区数据升级"从"祈祷没人踩坑"变成**一张可 diff 的清单**。

---

## 为什么需要它

`tzdata` 不是"每季度更新的字典"，而是一份**会改写历史**的数据库。IANA 发布说明里明确写着往回改的句子
（原文见 `plan/01-题目文档.md` §1.4）：

- **2026e**：`In 1925 Ireland fell back on 09-20 not 10-04`
- **2026d**：`Iran's 1979-05-26 spring forward was at 00:00, not 24:00`

升级 tzdata **不会让程序报错**：它让三个月前的日志换一个 UTC 解释，让一张排班表的墙钟落到一个
根本不存在的时刻。所有下游（调度、审计日志、账单、合规留存）在同一刻被重写，而**没有任何测试会失败**。

更麻烦的是：**同一份 tzdata 源码可以编出两种语义不同的二进制**。`slim` 构建把远期规则压进 POSIX TZ 尾巴，
`fat` 构建把规则展开成显式转换表。只比较转换表数量的工具会在两者之间报"没有变化"，而实际行为完全不同
（`America/Vancouver`: `PST8PDT,M3.2.0,M11.1.0` → `MST7`，表内迁移数都是 0）。

本工具做两件事：**双引擎合并**（TZif 表 + POSIX tail）与**墙钟语义判定**（本地→UTC 反解）。

## 安装

```bash
py -3.12 -m pip install -e ".[dev]"      # 开发安装
tzaudit --version                         # tzaudit 0.1.1
tzaudit --help
```

要求 Python ≥ 3.8，无运行时依赖。

## 前置条件：先跑 fetch（金标与审计都要真数据）

工具**运行时不下载任何东西**。但仓库里的金标回归需要**真实的 IANA 版本数据**，
而编译后的 zoneinfo 树体积大、无法文本审查，所以**不入仓**——干净 clone 后必须自己跑一次：

```bash
# 1) 拉五个版本的 IANA 源码包 + PyPI slim wheel（约 4 MB；构建期工具，允许联网）
py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e

# 2) 离线复核：sha256 与 provenance 逐份比对（不联网）
py -3.12 tools/fetch_tzdb.py --check

# 3) 金标复算：全量树逐 zone 解析，parse_errors 必须为 0
py -3.12 bench/run.py --check
```

**没跑第 1 步会怎样**：`bench/run.py --check` **退 3 并点名缺失的版本**，不会静默报"0 项通过"：

```text
缺件: 以下版本没有本地树 data/_downloads/slim/<ver>/：2026a, 2026b, 2026c, 2026d, 2026e
处置: py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e
结论: 环境不满足（exit 3），**不是** 0 项通过
```

> **"0 项通过"与"没扫到"必须可区分**——这条是本项目所有门的共同纪律。

### 金标复算在哪里跑（本地 vs CI，据实标注）

**金标复算是开发机门，CI 上跑不到**——因为 `data/_downloads/` 不入仓（需联网拉约 4 MB），
CI 的干净 checkout 里没有它。所以 CI 上 **72 条金标测试全部 `SKIP`**：

| 条件 | 全量测试 | 说明 |
|---|---|---|
| **本地**（已跑 `fetch_tzdb.py`，有 `data/_downloads`） | **435 collected → 434 passed + 1 skipped** | 那 1 skip = `tests/test_timeline.py`「本机无 `zic`，fat 真实树不可得」（语义等价已由 `data/fixtures/tzif/slim-vs-fat` 覆盖） |
| **CI 等价**（无 `data/_downloads`） | **363 passed + 72 skipped** | 与 `plan/RELEASE-M6.md` §1.7 登记**逐字一致**（363 / 72 = 435 − 72） |

⇒ **判据 `435 = 363 + 72`**：CI 的绿只证明 363 条；剩下 72 条金标**只在本地跑过**。
自己复验两条件：

```bash
# (a) CI 等价条件：git archive 解出的树不含 gitignored 的 data/_downloads
git archive HEAD | tar x -C /tmp/tzaudit-ci && cd /tmp/tzaudit-ci
py -3.12 -m pip install -e ".[dev]" && py -3.12 -m pytest -o addopts=""     # 363 passed, 72 skipped

# (b) 本地金标条件（先跑 fet，见上）——CI 里那 72 条在这跑
py -3.12 bench/run.py --check --suite parse      # 逐套件，rc=0；全量 --check 需 30–50 分钟
```

CI 里另有一条**常驻门**守住本项目最核心的纪律：干净 checkout 上 `bench/run.py --check`
**必须退 3**（点名缺件、明写"不是 0 项通过"），**绝不静默报"0 项通过"**。

产出落在 `data/_downloads/`（已 gitignore）：

| 路径 | 内容 | 入仓？ |
| --- | --- | --- |
| `data/_downloads/tzdata<ver>.tar.gz` | IANA 源码发布包 | ❌ |
| `data/_downloads/iana/<ver>/` | 解包后的 `NEWS` / `leap-seconds.list` / `version` | ❌（摘录入仓） |
| `data/_downloads/tzdata-<pypi>.whl` | PyPI wheel（slim 构建） | ❌ |
| `data/_downloads/slim/<ver>/` | 解 wheel 得到的 slim zoneinfo 树（金标与审计的输入） | ❌ |
| `data/tzdb/<ver>/provenance.json` | 版本 + kind + URL + sha256 + **实测 zones** | ✅ |
| `data/tzdb/<ver>/NEWS` | 该版本发布说明的**首版块**逐字摘录 | ✅ |
| `data/tzdb/<ver>/expect.json` | 金标（只含输入 + 期望） | ✅ |

### 自己准备两棵 zoneinfo 树（不用 fetch 也能审计）

工具本身只认"一个含 TZif 文件的目录"，来源不限：

```bash
# A) PyPI tzdata wheel（slim 构建）
py -3.12 -m pip download tzdata==2026.1 -d data/_downloads
py -3.12 -c "import zipfile,glob; zipfile.ZipFile(sorted(glob.glob('data/_downloads/tzdata-2026.1*.whl'))[0]).extractall('data/_downloads/2026.1')"

# B) 系统已编译树（fat 构建）
tzaudit version --zoneinfo /usr/share/zoneinfo --json
```

## 四个最小复现场景

> 四条场景都已落地，各由 `tests/` 锁定（见 `plan/05` 的 DoD）。
> 退出码：`0` 成功 / `1` 门禁命中 / `2` 用法错误 / `3` 环境不满足 / `4` 输入无效
> （口径单点在 `data/README.md` §4.4）。**不再有"功能未就绪（5）"**。

### 1. 墙钟窗口（GAP / OVERLAP）✅ 已可用

```bash
tzaudit windows --zone America/New_York --year 2026 --zoneinfo <tree>
```

```text
GAP      2026-03-08 02:00 → 03:00  (60min)  -05:00 → -04:00  America/New_York  source=tail
OVERLAP  2026-11-01 01:00 → 02:00  (60min)  -04:00 → -05:00  America/New_York  source=tail
```

```bash
tzaudit windows --all --year 2026 --zoneinfo <tree> --json
```

`--json` 输出 `{"year", "zones", "windows", "summary"}`；`summary.zones_scanned` 是实际扫描的
zone 数，`summary.errors` 是单 zone 失败清单（有错退 3，不中断整批）。

### 2. 版本差异（四类互斥）— ✅ M4 已落地

```bash
tzaudit diff --old <tree-2026a> --new <tree-2026e> --json
tzaudit diff --old <tree-2026a> --new <tree-2026e> --window 2000-2030
tzaudit diff --old <tree-2026a> --new <tree-2026e> --zone America/Vancouver
```

```json
{"changes": [{"zone": "America/Vancouver", "class": "future_rule",
              "evidence": "tail", "before": "tail=PST8PDT,M3.2.0,M11.1.0",
              "after": "tail=MST7", "window": null}],
 "summary": {"zones_compared": 598, "changes": 24,
             "classes": {"history_reinterpreted": 11, "future_rule": 9,
                         "abbreviation_only": 0, "alias_only": 4},
             "unclassified": [], "zone_set_equal": true}}
```

类别的判定顺序固定：`history_reinterpreted` → `future_rule` → `abbreviation_only` → `alias_only`
（口径见 `data/README.md` §4.3），同一 zone 只输出一条。`--window` **只影响第 1 类**
（历史重解释），第 2 类（表外规则）不受窗口限制——这是为什么 `--window 2000-2030`
不会让 Vancouver 消失。

四类互斥但**不穷尽**：窗口把唯一的历史差异排除后，某些 zone 四类都不成立，
它们进 `summary.unclassified` 如实列出，**不**被塞进 `alias_only` 当垃圾桶。

### 3. 清单审计（不接 cron 表达式）✅ 已可用

```bash
printf 'case-001,2026-03-08 02:30\ncase-002,2026-11-01 01:30\ncase-003,2026-06-01 12:00\n' > times.csv
tzaudit audit --times times.csv --zone America/New_York --zoneinfo <tree> --json
```

> 清单是**两列 `id,local_time`、无表头**；一行一个时间戳也可以（自动 `line-001`）。
> `INVALID` 行不静默跳过，所以写表头会被当成坏行（整体退 4）——这是有意的。

```text
case-001  GAP      2026-03-08 02:30:00  —                         0 个 UTC 候选（该墙钟不存在）
case-002  OVERLAP  2026-11-01 01:30:00  05:30Z, 06:30Z             2 个 UTC 候选（偏移差 3600s）
case-003  OK       2026-06-01 12:00:00  16:00Z
```

```bash
# 同一清单在两棵树下对照：VERSION_CHANGED = 同一本地时刻 UTC 解释不同
tzaudit audit --times times.csv --zone America/Vancouver \
    --version <tree-2026a>,<tree-2026e>

# 按天展开（等价于一份"每天同一时刻"的清单；缺 --year 退 2，不读时钟）
tzaudit audit --daily 02:30 --year 2026 --zone America/New_York --zoneinfo <tree>
```

判定顺序固定 `INVALID → GAP → OVERLAP → VERSION_CHANGED → OK`；行序保持输入序；
`INVALID` 行不静默跳过（进结果 + 计数 + 整体退 4）。

### 4. 报告与 CI 门禁 ✅ 已可用

先用任一子命令的 `--json` 落一份结果集，再生成报告：

```bash
tzaudit windows --all --year 2026 --zoneinfo <tree> --json > result.json
tzaudit report --from result.json --zoneinfo <tree> --format md --fail-on gap,overlap,history
tzaudit report --from result.json --format json --zoneinfo <tree> --fail-on overlap
```

报告头**固定三字段**：

```text
# tzaudit 报告

- data_version: 2026e
- zones_covered: 598
- generated_at: 2026-10-22T10:09:35Z
```

`data_version` / `zones_covered` 的**输入侧来源**是 `--zoneinfo <tree>`（单树）或
`--version <A>,<B>`（两树）；结果集里自带 `data_version` 时也可以不传。
缺任一字段 → 退 3。`--fail-on` 只看结果集，不看人读文本；`--json` 与 Markdown 的退出码相同。
`generated_at` 是唯一的时间戳，可被 `SOURCE_DATE_EPOCH` 冻结以便逐字节比对。

```bash
# 清单审计的结果集可以直接进报告（`audit --json` 自带 versions，无需再传 --version）
tzaudit audit --times times.csv --zone America/New_York --zoneinfo <tree> --json > result.json
tzaudit report --from result.json --format md --fail-on overlap
```

## 输出字段

| 字段 | 含义 | 出现于 |
|---|---|---|
| `type` | `GAP` / `OVERLAP` | `windows[]` |
| `start_local` / `end_local` | 本地墙钟区间（无偏移后缀） | `windows[]` |
| `duration_min` / `residual_sec` | 整分钟 + 秒级残差（不四舍五入） | `windows[]` |
| `offset_before` / `offset_after` | 转换前后偏移（东为正，`+HH:MM`） | `windows[]` |
| `source` | `table` / `tail`（判定依据的引擎） | `windows[]` `changes[]` |
| `class` | `history_reinterpreted` / `future_rule` / `abbreviation_only` / `alias_only` | `changes[]` |
| `evidence` | `table` / `tail` / `abbr` / `link` | `changes[]` |
| `status` | `GAP` / `OVERLAP` / `VERSION_CHANGED` / `OK` / `INVALID` | `rows[]` |
| `data_version` / `zones_covered` / `generated_at` | 报告头三字段（缺一即不合规） | 报告根 |

## 已知边界（如实标注）

- **首期只做两版本对**（A↔B），不做 A→B→C 链。
- **`--fail-on` 只有三选**：`gap` / `overlap` / `history`。
- **不做 cron 解析器**：`audit` 只接受本地时刻清单或 `--daily HH:MM`（避开 crontab.guru 一类已占位工具）。
- **不做时区转换 / 世界时钟 / 纯 zdump 包装**。
- **闰秒 / `right` 模式非主线**：只解析 `leap-seconds.list`，不建模、不比较。
- **不内置"最新 tzdata"、不自动下载、不联网**：版本目录由用户提供，结论才可复算。
- **报告不写绝对路径 / 主机名 / 用户名**。
- `diff` 的分类是"在给定两棵树与给定判定顺序下的结论"，不是"事实真相"——报告同时输出 `evidence` 与该口径。

## 仓库结构

```text
src/tzaudit/       解析层（tzif / posix_tz）→ 语义层（timeline）→ 子命令 → 报告
tests/             契约 / 架构 / 确定性 / 各模块
bench/run.py       金标复算入口
data/README.md     数值口径唯一权威（§四）
data/tzdb/         五版本 provenance + NEWS 摘录 + 金标（M1 起）
data/fixtures/     合成 fixture + 生成器（M2 起）
tools/             布局门 / 脱敏门 / 数据抓取
plan/              计划、里程碑、交接单、发布留档
```

## 开发

```bash
py -3.12 -m pytest -q                              # 全量测试
py -3.8  -m pytest -q                              # 底线解释器（语法必须兼容）
py -3.12 tools/check-sprint-layout.py              # 方法论布局门
py -3.12 tools/check-desensitized.py               # 脱敏门
```

## 路线图

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 出题定稿 + 方法论装订 + 可运行骨架 | ✅ 已完成（2026-10-21） |
| M1 | 数据先行：五版本 provenance + 金标复算入口 | ✅ 已完成（2026-10-21） |
| M2 | TZif 双引擎（表 + POSIX tail） | ✅ 已完成（2026-10-21） |
| M3 | 墙钟窗口 `windows`（含 `--all`） | ✅ 已完成（2026-10-21） |
| M4 | 版本差异分类 `diff` | ✅ 已完成（2026-10-21） |
| M5 | 清单审计 `audit` + 报告门禁 | ✅ 已完成（2026-10-22） |
| M6 | 发布：tag + Release + 发布留档 | ✅ 已完成（2026-10-22） |

## 许可

MIT
