# HANDOFF-M2 · TZif 双引擎（表 + POSIX tail）

> 上一棒：**M1（数据先行）✅ 2026-10-21**
> 本棒目标：**M2 TZif 双引擎** —— `posix_tz.py` + `timeline.py` 落地，
> 让"表段 + POSIX tail"合成一条时间线，并给出 `resolve_local` / `to_local` / `roundtrip`。
> 启动命令（用户侧，绝对路径不入库）：`/goal 读取 "<项目根>\plan\HANDOFF-M2.md" 继续完成任务`
> **第一动作**：`py -3.12 tools/check-sprint-layout.py`（必须全绿；红了先修布局）。

---

## 1. 当前进度 + 证据

**已完成（M0 + M1）**

| 交付 | 证据 |
|---|---|
| 计划套件 `plan/00–06` | 布局门 `LAYOUT.FILES 10 份齐备` / `LAYOUT.SECTIONS 8 份小节齐备` |
| 方法论装订 | `LAYOUT.BINDING_HEAD PASS`；`LAYOUT.DOC_TOOLS 4 个脚本全部在位` |
| 布局门 10 组变异自证 | `py -3.12 tools/mutate-layout-gate.py` → 10/10 组按预期（M0 记录见 `HANDOFF-M1` §5） |
| **五版本真实数据入仓** | `data/tzdb/{2026a..2026e}/` 各含 `provenance.json` + `NEWS` 首版块 + `leap-seconds.list` + `version` + `expect.json` |
| **`tools/fetch_tzdb.py` 真下载** | `--versions ...` → 5 个 IANA 包 + 5 个 PyPI wheel，逐个 sha256；`--check` → `PASS（10 份下载件 sha256 与 provenance 一致）` 退 0 |
| **`bench/run.py --check` 真复算** | 退 0，分母 5，`parse_errors=0`，**五版本各 598 zone**；双跑 `expect.json` 逐字节一致 |
| **TZif 解析器（M1 前移）** | `src/tzaudit/tzif.py` 落地 v1–v4；全量 2990 次解析零错误 |
| **独立参照对拍** | `tests/reference.py`（不 import tzaudit）；每版本抽样 20 + 2026e **全量 598 zone** 与生产实现逐条一致 |
| 契约测试 | `py -3.12 -m pytest -q` → **125 passed**；`py -3.8` → **125 passed**（3.8 通道无 skip） |
| 门 | 布局门绿 / 脱敏门绿（169 份文本） |

**M2 结束时应有的状态**：`posix_tz.parse` 能解 `data/README.md` §4.2 的全部形态；
`timeline.load_timeline(zone, store)` 把表段与 tail 段合成一条 `Segment` 序列；
`resolve_local` / `roundtrip` 与参照实现对拍一致；`windows` 尚未实现（M3），
但 `timeline` 的接口已被测试锁住。

## 2. 当前事实 · 状态不变量（下一棒动手前必须知道）

1. **数值口径的唯一真相源 = `data/README.md` §四**。`plan/02`/`plan/03`/README 只引用不复制；
   任何"第二套口径"都会让 `plan/06` X2 风险成真。改口径 = 改 §四 + 改引用 + 决策记录三处。
2. **`plan/01` §1.5 的探针快照数字（598 / 11 / 20 / 201 / 192 / 580）不得进代码常量、不得进 README 首屏、
   不得作断言阈值**。唯一例外：M1 的"零解析错误"与"对拍一致率"是**判据正确性**门槛，且分母以末态回填。
   → **M1 已按此回填：598 来自实测 `ZoneinfoStore(...).zones()`，不是抄题面。**
3. **状态副本有四处**（`plan/00` 台账行 / `plan/00` 里程碑表 / `plan/05` 状态表 / `README.md` 路线图），
   布局门逐副本采集、任一不一致即红。翻转状态必须**同一次提交**内改齐四处。
4. **退出码 5（未就绪）是临时的**：`windows`/`diff`/`audit`/`report` 每落地一个，必须在同一提交里
   删掉 `errors.NotImplementedYet` 对应引用、删 `tests/test_exit_codes.py::test_not_ready_exit_code_is_5`
   里那一行、改 `plan/03` §九与 `data/README.md` §4.4。四处少一处 = 幽灵语义复活。
5. **`plan/03` 与实现必须同步**：`posix_tz.parse` / `timeline.*` / `windows.*` / `diff.*` / `audit.*`
   仍是 `raise NotImplementedYet`。M2 起逐个替换，**签名不要改**——`tests/test_architecture.py`
   的 `ALLOWED` 表按模块声明依赖面，新增模块必须先加表（门会报"新模块未声明"）。
6. **`tests/test_architecture.py` 的 `ALLOWED` 是依赖方向的唯一真相源**。`report` 只能 import `errors`；
   `timeline` 才能 import `tzif` / `posix_tz` / `zoneinfo_store` / `civil`。反向 import 会立刻红。
7. **`civil.py` 是唯一允许做日历算术的地方**，且**全整数**（测试扫 `float(` / `round(`）。
   `datetime` 只允许出现在 `tests/` 里做交叉证伪，不得进 `src/`。
8. **`generated_at` 是唯一允许读时钟的地方**，落在 `report.build_report`（M5）。其余模块一律不读时钟。
   测试冻结用 `SOURCE_DATE_EPOCH`。**`tools/` 不受此限**（构建期工具，`fetch_tzdb.py` 读时钟取 `retrieved`）。
9. **`serialize.py` 是唯一写盘入口**（`src/` 内）。`bench/run.py` 与 `tools/` 是仓库级脚本，
   各自实现了同口径的规范化写盘（`sort_keys` + 2 空格 + LF）；**口径必须一致**，
   `test_truth_shape.py` 会逐份比对 `expect.json` 是否等于 `serialize.dumps_json` 的输出。
10. **`.gitignore` 封了 `*.csv`**：fixture 的清单用 `.json`/`.txt` 承载；真实用户清单永不入仓（隐私红线）。
11. **`data/tzdb/` 与 `data/fixtures/` 的 `expect.json` 必须是规范化 JSON**（`sort_keys` + 2 空格 + LF 尾），
    由 `tests/test_truth_shape.py` 断言；不是规范化就红。
12. **本机 `python` 是商店占位符**，一律 `py -3.12` / `py -3.8`；CI 里才是 `python`。
13. **【M1 新增】TZif 解析器已在 M1 落地**（`tzif.parse`），`TzifData` 五字段未变。
    M2 **不要重写它**；`is_slim` 判据在 **v1 块**（见 `plan/00` 决策 ⑨），挪到 v2 块会让
    `test_slim_is_decided_by_v1_block_not_v2` 立刻红。
14. **【M1 新增】`bench/run.py` 的两条判据已被变异证伪过**：
    "吞掉 `errors.append`" 与 "短路 `expected != stats` 比对" 都会让
    `test_bench_actually_counts_parse_errors` / `test_bench_detects_expect_drift` 变红。
    **改 `bench/run.py` 后必须重跑这两条**，否则很容易把判据改回假门。
15. **【M1 新增】依赖真实树的用例在无 `data/_downloads/slim` 时 skip（9 条）**，
    不是假绿。CI 首次跑时这些会 skip——这是预期，不是失败。
16. **【M1 新增】上游 `2026b` 的 `NEWS` 头误写成 `Release 2026a`**（原文如此）。
    `test_news_excerpt_is_only_the_latest_release_block` 对 2026b 显式豁免；
    **不要"顺手修正"上游数据**，那会让入仓件与发布包 sha256 对不上。
17. **【M1 新增】`2026d` 的伊朗句用 U+2019 弯引号**（`Iran’s`），`plan/01` 引用时写的是直引号。
    金标按**原文**断言（`test_news_excerpts_pin_the_two_historical_quotes`）。
    文档侧若要对齐，改文档不改数据。

## 3. 下一棒待办（M2 TZif 双引擎）

按顺序做，每步都有可跑的判据：

1. **实现 `src/tzaudit/posix_tz.py`**
   - 按 `data/README.md` §4.2 逐条：缩写（`<+1245>` 优先）、偏移（**西为正** → 翻成东为正）、
     `Jn` / `n` / `Mm.w.d` 三类规则、`/time` 为**墙钟秒**、缺省 dst offset = std + 1h、无逗号段 = 无 DST。
   - **反例单测**（三条技术坑各一条，`plan/03` §三 测试点）：
     `EST5` → `-18000`；`M3.2.0/2` 在 NY 上展开得 `07:00Z`（不是 `02:00Z`）；
     `MST7` → `dst is None`。
2. **实现 `src/tzaudit/timeline.py`**
   - `load_timeline(zone, store)` → `tzif.parse` + `posix_tz.parse(footer)` → 合并成 `Segment` 序列。
   - 表段：每个转换点 `[t_i, t_{i+1})` 一个 `Segment(source="table")`。
   - 表尾之后：从 `max(table_end, window_start)` 起按 tail **逐年展开**，上限 = 请求窗口末端 + 1 年
     （`plan/05` R2：漏最后一年 / 无限循环是本里程碑的主要风险）。
   - **展开起点可早于 1970**（slim 树的历史区间也可能靠 tail）。
   - `resolve_local` / `to_local` / `roundtrip` 按 `plan/03` §4.2 的 O(log n) 算法。
3. **`tests/reference.py` 扩到 timeline 层**
   - 现在它只做 TZif 字节读取。M2 需要**独立实现** `resolve_local` 语义
     （用 `datetime` + 手工 offset 表，**不共享生产代码**）。
   - 对拍：`roundtrip(resolve_local(l)) == l` 对 fixture 全量逐行成立。
4. **`tests/test_posix_tz.py` / `tests/test_timeline.py` / `tests/test_slim_fat.py` 落地**
   - `test_timeline.py`：双向对拍 + 参照实现对拍（≥20 zone，含三种特殊形态）。
   - `test_slim_fat.py`：fat 从 IANA 源码包自建（**只作 fixture**），与 slim 做**重叠区间**语义比对
     （Q1 定案：不要求版本号相同）。
5. **`bench/run.py --regen` 扩到 timeline 套件**
   - 金标加"抽样 zone 的转换点数"与"抽样 zone 的 tail 展开点数"（`plan/04` §二 已定口径）。
   - **仍然只存输入与期望**，不得出现 `observed_*`（`test_truth_shape.py` 守）。
6. **状态回写 + 写 `plan/HANDOFF-M3.md` + commit**（收尾顺序见下）。

> **M2 不要做的事**：不要实现 `windows`（M3）、不要碰 `diff`/`audit`/`report`（M4/M5）、
> 不要把 `EXIT_NOT_READY` 退役（那是 `windows` 落地时才做的整项退役）。

## 4. 既定口径清单（K 编号；动了会打挂测试）

| K | 口径 | 打挂什么 |
|---|---|---|
| K1 | 数值口径单点 = `data/README.md` §四 | 任何复制第二份的改动 → `plan/06` X2 风险 + review 拒收 |
| K2 | 退出码：0/1/2/3/4/5（5 为临时） | `tests/test_exit_codes.py` 全部 13 项 |
| K3 | 依赖方向：`plan/02` §一 + `tests/test_architecture.py::ALLOWED` | `test_layers_do_not_import_upwards` |
| K4 | 排序一律 UTF-8 字节序（`zoneinfo_store.byte_key`） | 双跑一致性；`--all` 输出顺序 |
| K5 | 除 `generated_at` 外零时间戳、零浮点（`src/` 内） | `test_no_network.py` 时钟扫描 + 双跑逐字节 |
| K6 | 写盘单点 `serialize.write_*_atomic`（sort_keys/2 空格/LF/无 BOM） | `tests/test_serialize.py` + `test_truth_shape.py` |
| K7 | 金标只存输入与期望（无 `observed_*`） | `test_truth_shape.py::test_expect_files_have_no_observation_fields` |
| K8 | POSIX 偏移**西为正**，解析层翻成**东为正**的秒数 | `plan/03` §三 反例单测（M2 落地） |
| K9 | `/time` 是**墙钟秒**，解析层只存 `time_sec`，不做偏移加减 | `plan/03` §三 测试点 3（M2 落地） |
| K10 | 存在性只由 `resolve_local` 的候选个数决定；`fold` 只用于选择 | `plan/03` §四 + Vancouver 反例（M3） |
| K11 | 四类变更判定顺序固定 `history → future → abbrev → alias` | `diff.CLASS_ORDER`（已是常量） |
| K12 | 发布里程碑固定 M6（`check-sprint-layout.py::RELEASE_MILESTONE`） | `LAYOUT.RELEASE` 分支 |
| K13 | M0 豁免 HANDOFF-M0；`HANDOFF_SECTIONS` 七节为**必需子集**（超集合法） | `LAYOUT.HANDOFFS` / `LAYOUT.NEXT_HANDOFF` |
| K14 | **主金标两棵树 = PyPI slim wheel × 2**（Q1 定案）；fat 仅作 M2 fixture | `data/tzdb/*/provenance.json` 的 `kind` 必须是 `slim` |
| K15 | **Python 底线 3.8**（Q2 定案）：禁 `dict \|`、禁 `X \| Y` 类型标注、禁 `tomllib`、禁 `str.removeprefix` | `py -3.8 -m pytest` 必须全绿；CI 矩阵 3.8+3.12 |
| K16 | **`audit --version` 只收两个目录路径**（Q4 定案），不收版本号 | `cli.py` 的 `--version` 帮助文本；`plan/03` §七 |
| K17 | **未接远端**（Q7 定案）：DoD 只写"本地等价校验（未接远端，CI 待首推验证）" | `plan/05` §三 U1/U2；M6 补记 |
| K18 | **【M1 新增】`is_slim` 判据在 v1 块**（决策 ⑨） | `test_slim_is_decided_by_v1_block_not_v2`；挪到 v2 块即红 |
| K19 | **【M1 新增】`TzifData` 五字段 + `parse(data, zone)` 签名冻结**（决策 ⑧） | `tests/test_m1_data.py` 全部解析器用例 |
| K20 | **【M1 新增】入仓 `NEWS` = 首版发布块，逐字保留**（含 2026b 上游笔误、2026d 弯引号） | `test_news_excerpts_pin_the_two_historical_quotes` / `test_news_excerpt_is_only_the_latest_release_block` |
| K21 | **【M1 新增】`bench/run.py` 的两条判据必须能跑红**（吞错误 / 短路比对都会被测试抓） | `test_bench_actually_counts_parse_errors` / `test_bench_detects_expect_drift` |

## 5. 本机环境坑（只写实测过的；带日期）

| 坑 | 实测（2026-10-21） | 处置 |
|---|---|---|
| `python` 是商店占位符 | 直接跑会弹商店 | 一律 `py`（`py -3.12` / `py -3.8`） |
| 两条解释器通道 | `py -0p` → 3.8.8-64 与 3.12-64；pytest 7.4.4 / 8.4.2 | 语法必须兼容 3.8 |
| `curl` 可用、IANA 可达 | `data.iana.org/time-zones/tzdb/version` → `200`，body = `2026e` | 下载走 `urllib`；**CLI 运行期不许联网**，只有 `tools/` 可以 |
| `gh` 已登录 | 账号 `yuluo554`，scopes 含 `repo` | M6 建仓/Release 直接用 `gh` |
| 仓库尚无 remote | `git remote -v` 为空 | 未推送期间 DoD 只能写"本地等价校验，CI 待首推验证" |
| 布局门输出经管道时 `$?` 是管道的 | `py ... \| tail` → `rc=0` 即使有 FAIL | 取退出码**不要接管道**：`py ... > /dev/null; echo $?` |
| **zone 判据必须是 TZif 魔数** | 首版按文件名过滤，把 `plan/*.md` 数成 zone（报 27 个） | `zoneinfo_store.looks_like_tzif()`；回归 `test_text_files_are_not_counted_as_zones` |
| **变异脚本的"还原"要按文件存原始快照** | V9 首版在同一文件上存了两份快照 → 还原被覆盖 | 每份文件只在**动任何字节之前**采集一次快照 |
| **变异靶子要瞄门真正扫的那一列** | V6 首版改「关闭里程碑」列，门扫的是「缺口」列 | 先读门的列定位逻辑，再决定改哪一格 |
| `datetime` 不支持负年份 | civil 的负年份/0 年不能与 `datetime` 交叉证伪 | 用性质测试覆盖 |
| Hinnant 的 C 截断除法 ≠ Python 向下取整 | 首版照抄 `(y if y>=0 else y-399)//400` → 负年份往返失败 | Python 里直接 `y // 400` |
| **TZif v2 的两个头都带版本字节** | 合成 fixture 首版把 v1 头写成 `\0` → 解析器判"footer 不是以换行开头"（偏移错 44 字节） | 实测 2026e 树确认：第一头与第二头都是 `'2'`；fixture 照此构造 |
| **`abbrind` 指向的是字符串表字节偏移，不是类型序号** | 合成 fixture 写 `abbrind=4`（`"CEST\0CET\0"` 的 NUL 位置）→ 取到空串 | 第二个缩写从 5 开始；写 fixture 时按字节偏移算 |
| **`pytest` 的 `tmp_path` 造"假仓库"必须跑副本** | 首版用真 `bench/run.py` + `cwd=fake` → 它按 `__file__` 推 ROOT，仍读真仓库 | 复制脚本到假仓库再跑（它按自身位置推 ROOT） |
| **`bench/run.py` 认版本看 `provenance.json`** | 假仓库只建 `tzdb/<ver>/` 目录、不写 provenance → `入仓版本: （无）` | 假仓库必须写 `provenance.json`（`_tzdb_versions()` 的判据） |
| **上游 `2026b` 的 NEWS 头写成 `Release 2026a`** | 实际下载包原文如此 | 原样入仓；测试对 2026b 豁免；**不代改上游** |
| **`retrieved` 取本地日历日不是 UTC 日** | 首版用 `gmtime()` → 记成 2026-10-20，而项目日历日是 2026-10-21 | 改 `localtime()`；`SOURCE_DATE_EPOCH` 存在时读它 |

### M1 变异验证记录（4 组；在临时副本上执行，不污染工作树）

| # | 变异 | 期望命中的判据 | 实测 |
|---|---|---|---|
| M1-V1 | `is_slim` 判据从 v1 块挪到 v2 块 | `test_slim_is_decided_by_v1_block_not_v2` | ✅ 变红（rc=1），还原复绿 |
| M1-V2 | `bench/run.py` 的 `errors.append(...)` 改成 `pass` | `test_bench_actually_counts_parse_errors` | ✅ 变红，还原复绿 |
| M1-V3 | `bench/run.py` 缺件分支 `return EXIT_ENV` 改成 `EXIT_OK` | `test_bench_reports_missing_versions_instead_of_passing` | ✅ 变红，还原复绿 |
| M1-V4 | `bench/run.py` 的 `if expected.get(key) != stats[key]` 加 `False and` 短路 | `test_bench_detects_expect_drift` | ✅ 变红，还原复绿 |

> **V2/V4 是补做出来的**：首轮只跑 V1/V3，V2/V4 **全绿**——说明这两条判据当时是假门。
> 补了两条"变异自证"用例（造一棵含坏 zone 的假树 / 造一份期望值漂移的金标）后才变红。
> **教训**：新判据必须**先想好"改哪一行会让它红"**，再写测试；跑一遍变异是唯一能证伪的方式。

## 6. DoD 逐项 checklist（M2）

- [ ] `posix_tz.parse` 覆盖 §4.2 全部形态；三条反例单测各一条
- [ ] `timeline.load_timeline` 合并表段 + tail 段；tail 展开上限 = 窗口末端 + 1 年
- [ ] `resolve_local` / `to_local` / `roundtrip` 与参照实现对拍一致（≥20 zone，含三种特殊形态）
- [ ] `tests/reference.py` 扩到 timeline 层（仍不 import tzaudit）
- [ ] slim / fat **重叠区间**语义等价（fat 从源码包自建，只作 fixture）
- [ ] `bench/run.py --regen` 加入 timeline 套件金标；`--check` 仍退 0
- [ ] `py -3.12 -m pytest -q` 全绿（含新增 M2 测试）
- [ ] `py -3.8 -m pytest -q` 全绿（底线解释器）
- [ ] 布局门 + 脱敏门全绿
- [ ] 四处状态副本同步翻 M2 ✅
- [ ] `plan/HANDOFF-M3.md` 已落盘（七节齐）

> 未推送期间**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。

## 7. 关键命令速查

```bash
# 门
py -3.12 tools/check-sprint-layout.py            # 布局门
py -3.12 tools/check-desensitized.py             # 脱敏门

# 测试（两个通道都跑）
py -3.12 -m pytest -q
py -3.8  -m pytest -q

# 数据（M1 已落地；干净 clone 先跑这一条）
py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e
py -3.12 tools/fetch_tzdb.py --check
py -3.12 tools/fetch_tzdb.py --materialize       # 从下载缓存重建 data/tzdb/<ver>/

# 金标
py -3.12 bench/run.py --check
py -3.12 bench/run.py --check --suite parse
py -3.12 bench/run.py --regen

# 安装与 CLI 冒烟
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m tzaudit --help
py -3.12 -m tzaudit --version
py -3.12 -m tzaudit version --zoneinfo data/_downloads/slim/2026e --json

# 取退出码（别接管道）
py -3.12 tools/check-sprint-layout.py > /dev/null; echo "layout rc=$?"
```

### 收尾顺序（硬约束，不得裁量）

```
DoD 逐项验证 → 四处状态副本回写 → 写 plan/HANDOFF-M3.md → git add -A → commit →（有远端则 push 等 CI）
```

未推送期间 DoD 里**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。
