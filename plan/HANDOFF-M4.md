# HANDOFF-M4 · 版本差异分类 `diff`

> 上一棒：**M3（墙钟窗口）✅ 2026-10-21**
> 本棒目标：**M4 版本差异分类** —— `diff.py` 落地，让 `tzaudit diff --old <A> --new <B>`
> 输出**四类互斥**的变更分类（`history_reinterpreted` / `future_rule` / `abbreviation_only` /
> `alias_only`），判定顺序固定。
> 启动命令（用户侧，绝对路径不入库）：`/goal 读取 "<项目根>\plan\HANDOFF-M4.md" 继续完成任务`
> **第一动作**：`py -3.12 tools/check-sprint-layout.py`（必须全绿；红了先修布局）。

---

## 1. 当前进度 + 证据

**已完成（M0 + M1 + M2 + M3）**

### M3 DoD 逐项实测（14/14；证据可复跑）

| # | DoD 项 | 实测证据 |
|---|---|---|
| 1 | `windows.scan_year` 落地，`Window` 字段与 `plan/03` §五 一致 | `Window.__slots__` = `{type, start_local, end_local, duration_min, residual_sec, offset_before, offset_after, zone, source}`（9 字段，逐个对上） |
| 2 | 双判据复核：GAP 必 0 个、OVERLAP 必 2 个且 offset 不同；不满足即丢弃 | NY 2026 真 GAP `02:00→03:00` 通过复核；**正常时刻**（`2026-07-01 12:00`）谎称 GAP → 被拒（`_verify_candidate` 返回 False） |
| 3 | NY 2026 → GAP `02:00→03:00` + OVERLAP `01:00→02:00`，方向正确 | 实测 `[('GAP','02:00','03:00'), ('OVERLAP','01:00','02:00')]` |
| 4 | **Vancouver 2026 → 零条 OVERLAP** | 实测 `['GAP']`（只有 3 月起跳；11 月不再回拨） |
| 5 | Lord_Howe（30min）/ Chatham（45min）/ Dublin（负 DST）三条金标 | Lord_Howe `[('OVERLAP',30,39600,37800), ('GAP',30,37800,39600)]`；Chatham 偏移含 `45900`(+12:45)；Dublin `[('GAP',60,0,3600), ('OVERLAP',60,3600,0)]` |
| 6 | `--all --year 2026` 跑完；单 zone 错误进 `summary.errors` 不中断 | `zones_scanned=598`、`windows=395`、`errors=0`（约 1.3 s） |
| 7 | 跨年边界不丢窗口（12/31、闰年 2/29） | Almaty 2024 `2024-02-29 23:00→03-01 00:00`；Managua 1996 `1996-12-31 23:00→1997-01-01 00:00`（**转换点在次年**）；Choibalsan 1978 `1978-01-01 00:00→01:00`（**转换点在上一年**） |
| 8 | `EXIT_NOT_READY` 只退役 `windows` 一条 | `windows` 对不存在树 → 3；`diff`/`audit`/`report` → 5（三条仍在骨架期） |
| 9 | `data/fixtures/windows/` 落地，`gen.py --check` 逐字节一致 | 四组 fixture `--check` 全 PASS（`windows` 7 份产物） |
| 10 | `bench/run.py --check --suite windows` 退 0；金标无 `observed_*` | rc=0；五版本金标 `expected` 里 `observed/actual/runtime` 前缀键 = 0 个 |
| 11 | 布局门 + 脱敏门全绿 | 布局门 `结论: 全绿`（10 条判据）；脱敏门 `结论: 全绿`（201 份文本） |
| 12 | 四处状态副本同步翻 M3 ✅ | `plan/00` 台账 + `plan/00` 里程碑表 + `plan/05` 状态表 + `README.md` 路线图，M3 行全含 ✅ |
| 13 | `plan/HANDOFF-M4.md` 已落盘（七节齐） | 七节关键词逐个命中：当前进度 / 当前事实 / 待办 / 既定口径 / 环境坑 / DoD / 命令速查 |
| 14 | `py -3.12` / `py -3.8` 全绿 | 3.12 = **286 passed, 1 skipped**（3005 s / 50 分钟）；3.8 = **286 passed, 1 skipped**（3538 s / 59 分钟） |

### 交付物清单

| 交付 | 证据 |
|---|---|
| 计划套件 `plan/00–06` | 布局门 `LAYOUT.FILES 10 份齐备` / `LAYOUT.SECTIONS 8 份小节齐备` |
| 方法论装订 | `LAYOUT.BINDING_HEAD PASS`；`LAYOUT.DOC_TOOLS 4 个脚本全部在位` |
| 五版本真实数据入仓 | `data/tzdb/{2026a..2026e}/` 各含 `provenance.json` + `NEWS` 首版块 + `leap-seconds.list` + `version` + `expect.json` |
| **TZif 解析器（v1–v4）** | `src/tzaudit/tzif.py`；全量 598 zone × 5 版本 = 2990 次解析零错误 |
| **POSIX TZ 解析器** | `src/tzaudit/posix_tz.py`；`data/README.md` §4.2 全部形态；三条技术坑各一反例 |
| **双引擎合并 + 本地反解** | `src/tzaudit/timeline.py`；`load_timeline` / `resolve_local` / `to_local` / `roundtrip` / `offset_at` / `transition_points` / `segment_source_at` |
| **独立参照实现（扩到 timeline 层）** | `tests/reference.py`：TZif 读取 + POSIX 正则解析 + `datetime` 日历 + **段区间包含式**反解（不 import tzaudit） |
| **墙钟窗口 `windows`** | `src/tzaudit/windows.py`：`Window` / `scan_year` / `scan_all` / `scan_tree` + **双判据复核**；已接 `cli.py`（`--zone` / `--all` / `--json`） |
| timeline 金标（两套件） | `data/tzdb/<ver>/expect-timeline.json`；`bench/run.py --check` 退 0，两套件各 5 份 |
| **windows 金标（第三套件）** | `data/tzdb/<ver>/expect-windows.json`；`bench/run.py --check --suite windows` 退 0，5 份；含 `total_windows` 全量分母 + 抽样窗口集合 + 参照对拍 40 点/版本 |
| 四个 fixture + 生成器 | `data/fixtures/tzif/slim-vs-fat/`、`data/fixtures/tzif/source-vs-wheel/`、`data/fixtures/posix/three-rule-forms/`、**`data/fixtures/windows/wall-clock-windows/`**，各带 `gen.py --check`（逐字节） |
| 契约测试 | `py -3.12 -m pytest` → **286 passed, 1 skipped**（287 项收集；M2 的 231 项 + M3 的 56 项）；`py -3.8 -m pytest` 同 |
| 门 | 布局门绿 / 脱敏门绿 |

**M3 结束时已锁住的状态**：`windows.scan_year(zone, year, tl)` 按
"**本地墙钟年份**"归属窗口（不按 UTC 年份），转换点取 `timeline.transition_points`，
候选按 `before/after` 的差得 GAP / OVERLAP，再逐候选**复核**（GAP 必须 0 个候选、
OVERLAP 必须 2 个且 offset 不同），不满足即**丢弃**（宁漏不误报）。
`diff` 仍是 `raise NotImplementedYet`（M4 落地）。

## 2. 当前事实 · 状态不变量（下一棒动手前必须知道）

1. **数值口径的唯一真相源 = `data/README.md` §四**。`plan/02`/`plan/03`/README 只引用不复制；
   任何"第二套口径"都会让 `plan/06` X2 风险成真。改口径 = 改 §四 + 改引用 + 决策记录三处。
2. **`plan/01` §1.5 的探针快照数字（598 / 11 / 20 / 201 / 192 / 580）不得进代码常量、不得进
   README 首屏、不得作断言阈值**。唯一例外：M1 的"零解析错误"与"对拍一致率"是**判据正确性**
   门槛，且分母以末态回填。
   **M3 实测**：2026 年全量 598 zone 扫出 **395 条窗口**（GAP 201 / OVERLAP 194）、
   **201 个 zone** 有窗口、**192 个 zone** 有 OVERLAP；`--all` 耗时约 **1.3 秒**。
   这三个数字是**本项目的实测基准**（可写进 `plan/05` 的 U5 关闭说明），**不得**进代码常量或断言阈值。
3. **状态副本有四处**（`plan/00` 台账行 / `plan/00` 里程碑表 / `plan/05` 状态表 / `README.md` 路线图），
   布局门逐副本采集、任一不一致即红。翻转状态必须**同一次提交**内改齐四处。
   **M2 实测坑**：台账"状态"列若出现 `🟡` 且同一格提到已 ✅ 的里程碑号，`LAYOUT.LEDGER` 立刻红
   （`🟡` 本身是未完成标记）。要么写 `⬜`，要么写 ✅ + 说明，不要混。
4. **退出码 5（未就绪）是临时的**：`diff`/`audit`/`report` 每落地一个，必须在同一提交里
   删掉 `errors.NotImplementedYet` 对应引用、删 `tests/test_exit_codes.py::test_not_ready_exit_code_is_5`
   里那一行、改 `plan/03` §九与 `data/README.md` §4.4。四处少一处 = 幽灵语义复活。
   **M3 已退役 `windows` 那一条**（`EXIT_NOT_READY` **常量仍在**，因为另外三条还在用）。
   **M4 只退役 `diff` 那一条**，`audit`/`report` 仍在 5。
5. **`plan/03` 与实现必须同步**：M2 已把 §三 / §四 改成 `[M2 已落地]`，M3 已把 §五改成
   `[M3 已落地]` 并登记了两处实现细节差异（本地墙钟年份归属 + `segment_source_at`）。
   M4 落地后同样要改 §六。
6. **`tests/test_architecture.py` 的 `ALLOWED` 是依赖方向的唯一真相源**。
   **`diff` 的依赖面已定**：`{errors, timeline, zoneinfo_store, civil}`（**不能** import
   `posix_tz` / `tzif` / `windows`）。新增模块必须先加表（门会报"新模块未声明"）。
7. **`civil.py` 是唯一允许做日历算术的地方**，且**全整数**（测试扫 `float(` / `round(`）。
   `datetime` 只允许出现在 `tests/` 与 `data/fixtures/*/gen.py` 里，不得进 `src/`。
8. **`generated_at` 是唯一允许读时钟的地方**，落在 `report.build_report`（M5）。其余模块一律不读时钟。
   **`tools/` 与 `data/fixtures/*/gen.py` 不受此限**（构建期工具）。
9. **`serialize.py` 是唯一写盘入口**（`src/` 内）。`bench/run.py` 与 `tools/` 是仓库级脚本，
   各自实现同口径的规范化写盘（`sort_keys` + 2 空格 + LF）；`test_truth_shape.py` 逐份比对。
10. **`.gitignore` 封了 `*.csv`**：fixture 的清单用 `.json`/`.txt` 承载；真实用户清单永不入仓。
11. **`data/tzdb/` 与 `data/fixtures/` 的 `expect*.json` 必须是规范化 JSON**
    （`sort_keys` + 2 空格 + LF 尾），由 `tests/test_truth_shape.py` 断言。
12. **本机 `python` 是商店占位符**，一律 `py -3.12` / `py -3.8`；CI 里才是 `python`。
13. **`posix_tz` 只做语法**，不做日历算术——"规则 → UTC 时刻"在 `timeline`。
    M4 要判 `future_rule` 时**不要**在 `diff` 里重写规则展开：直接读
    `timeline.Timeline.tail`（`PosixTz` 的 `std`/`dst`/`start`/`end` 四元组）比。
14. **`/time` 的两种基准**：起跳按 std 墙钟、回拨按 DST 墙钟（tzcode 语义）。
15. **tail 的正确性靠"解析式求值"**，不靠物化段。`diff` 判 `future_rule` 时若要比较"表外行为"，
    用 `timeline.offset_at` / `transition_points`（走解析式），不要物化段。
16. **`resolve_local` 用"枚举候选 offset + 自洽校验"**（不是 `max/min_offset` 区间法）。
17. **金标候选数必须出现 {0,1,2}**：M2 的 timeline 金标如此；**M3 的 windows 金标同理**——
    `bench/run.py --regen --suite windows` 里有一条硬门槛：抽样集若缺 `GAP` 或 `OVERLAP`
    任一种，**直接拒绝写出**（防"实现只产一种"的退化实现恒绿）。
    M4 的 diff 金标同理：四类若某类在全量树里真的不存在，要**如实记 `null` + 说明**，
    不许编造（`data/README.md` §三 的真值纪律）。
18. **本机无 `zic`**。`data/fixtures/tzif/source-vs-wheel/fat/` 是 `gen.py` 的规则编译器产物。
19. **跑测试不要并发**（`bench/run.py` 会写金标文件，并发读会假红）。
20. **`bench/run.py` 现在有三套件**（`parse` / `timeline` / `windows`），各自一个金标文件
    （`expect.json` / `expect-timeline.json` / `expect-windows.json`）。新增第四套件（如 `diff`）时：
    加 `SUITES` 常量 + `_check_<suite>` + `_<suite>_doc` + 对应的 `_write_*`，并**同时**给金标加漂移变异测试。

## 3. 下一棒待办（M4 版本差异分类）

按顺序做，每步都有可跑的判据：

1. **实现 `src/tzaudit/diff.py`**
   - `diff_trees(old_store, new_store, window=None, zone=None) -> DiffResult`
   - `Change(zone, class_, window, before, after, evidence, note)`（`plan/03` §六）。
   - **判定顺序固定**（`data/README.md` §4.3）：`history_reinterpreted` → `future_rule` →
     `abbreviation_only` → `alias_only`，**取第一条成立者**，同一 zone 只输出一条。
   - `history_reinterpreted`：在 `window`（默认 = 两树共有历史的交集）内存在**任一** UTC 时刻，
     两树的 `to_local` 不同 → 成立。`evidence` = `table` / `tail`（差异来自哪段）。
   - `future_rule`：**先比 tail 的规范化结构**（`std/dst/start/end` 四元组），再比表尾之后的展开；
     **表相同但 tail 不同必须落这里**（Vancouver 2026.1→2026.5：`PST8PDT,M3.2.0,M11.1.0` → `MST7`）。
   - `abbreviation_only`：所有转换点 `utc/offset` 相同，仅 `abbr` 不同 → `evidence=abbr`。
   - `alias_only`：zone 在 link 集合中新增/消失，且**无任何 offset/规则差异** → `evidence=link`。
   - **link 识别**：判据 = `st_size` 相同 + 内容 sha256 相同（`zoneinfo_store.links()` 已实现）；
     **不能用"文件名像 link"推断**（Windows 解包会丢符号链接）。
2. **接线 `cli.py`**：`diff` 子命令落地 → **同一提交里**退役 `EXIT_NOT_READY` 的 `diff` 那一条
   （删 `cli._unimplemented` 对 `diff` 的分派、删 `test_exit_codes.py` 里 `diff` 那行、
   改 `plan/03` §九与 `data/README.md` §4.4）。**注意**：`audit`/`report` 两条仍在 5。
3. **落地 `tests/test_diff.py`**（`plan/03` §六 测试点）：
   - Vancouver（构造 slim fixture）→ `future_rule` + `evidence=tail`；**断言 `class` 不是 `alias_only`**。
   - Dublin 1925 / Tehran 1979（真实数据 fixture）→ `history_reinterpreted`。
   - 仅缩写变化（构造）→ `abbreviation_only`，且 `history_reinterpreted` 与 `future_rule` 均不成立。
   - 四类互斥：同一 zone 只输出一条；构造"同时有 abbr 与 tail 差异"的 fixture → 必须落 `future_rule`。
   - **判定顺序变异**：把顺序改成 `future_rule` 优先 → 第 2 条测试必须红（变异验证写进测试注释）。
4. **落地 `data/fixtures/diff/`**：生成器 + `expect.json` + `README.md`（`plan/04` §三 硬纪律：
   `--check` 两层断言、禁 random / 禁时钟 / 写盘归一）。至少两组：
   `vancouver-tail/`（表相同、tail 不同 → `future_rule`）与 `bc-2026b/`（BC 永久 UTC−7）。
5. **`bench/run.py` 加第四套件 `diff`**：金标存"两版本对的变更名单"（`plan/04` §二 已定口径：
   `data/tzdb/pairs/2026a-2026e.json` 的 `window_changed` / `all_history_changed` 两个名单）。
   **仍然只存输入与期望**，不得出现 `observed_*`。
   **必须**给这条判据加漂移变异测试（M1 教训：新判据先想好"改哪一行会让它红"）。
   **名单不写死条数**（`plan/04` §二 真值纪律第 3 条）：断言用**集合相等**。
6. **状态回写 + 写 `plan/HANDOFF-M5.md` + commit**（收尾顺序见下）。

> **M4 不要做的事**：不要碰 `audit`/`report`（M5）、不要把 `EXIT_NOT_READY` **整项**删掉
> （只退役 `diff` 那一条；其余两条还在用）、不要改 `timeline` 的接口签名。

## 4. 既定口径清单（K 编号；动了会打挂测试）

| K | 口径 | 打挂什么 |
|---|---|---|
| K1 | 数值口径单点 = `data/README.md` §四 | 任何复制第二份的改动 → `plan/06` X2 风险 + review 拒收 |
| K2 | 退出码：0/1/2/3/4/5（5 为临时） | `tests/test_exit_codes.py` 全部 14 项 |
| K3 | 依赖方向：`plan/02` §一 + `tests/test_architecture.py::ALLOWED` | `test_layers_do_not_import_upwards` |
| K4 | 排序一律 UTF-8 字节序（`zoneinfo_store.byte_key`） | 双跑一致性；`--all` 输出顺序 |
| K5 | 除 `generated_at` 外零时间戳、零浮点（`src/` 内） | `test_no_network.py` 时钟扫描 + 双跑逐字节 |
| K6 | 写盘单点 `serialize.write_*_atomic`（sort_keys/2 空格/LF/无 BOM） | `tests/test_serialize.py` + `test_truth_shape.py` |
| K7 | 金标只存输入与期望（无 `observed_*`） | `test_truth_shape.py::test_expect_files_have_no_observation_fields` |
| K8 | POSIX 偏移**西为正**，解析层翻成**东为正**的秒数 | `test_posix_tz.py::test_west_positive_is_flipped_to_east_positive` |
| K9 | `/time` 是**墙钟秒**，解析层只存 `time_sec`，不做偏移加减 | `test_posix_tz.py::test_slash_time_is_parsed_as_wall_seconds_not_offset` |
| K10 | 存在性只由 `resolve_local` 的候选个数决定；`fold` 只用于选择 | `test_timeline.py::test_exists_only_by_candidate_count_not_by_fold` + Vancouver 反例 |
| K11 | 四类变更判定顺序固定 `history → future → abbrev → alias` | `diff.CLASS_ORDER`（M4 建立） |
| K12 | 发布里程碑固定 M6（`check-sprint-layout.py::RELEASE_MILESTONE`） | `LAYOUT.RELEASE` 分支 |
| K13 | M0 豁免 HANDOFF-M0；`HANDOFF_SECTIONS` 七节为**必需子集**（超集合法） | `LAYOUT.HANDOFFS` / `LAYOUT.NEXT_HANDOFF` |
| K14 | **主金标两棵树 = PyPI slim wheel × 2**（Q1 定案）；fat 仅作 M2 fixture | `data/tzdb/*/provenance.json` 的 `kind` 必须是 `slim` |
| K15 | **Python 底线 3.8**（Q2 定案）：禁 `dict \|`、禁 `X \| Y` 类型标注、禁 `tomllib`、禁 `str.removeprefix` | `py -3.8 -m pytest` 必须全绿；CI 矩阵 3.8+3.12 |
| K16 | **`audit --version` 只收两个目录路径**（Q4 定案），不收版本号 | `cli.py` 的 `--version` 帮助文本；`plan/03` §七 |
| K17 | **未接远端**（Q7 定案）：DoD 只写"本地等价校验（未接远端，CI 待首推验证）" | `plan/05` §三 U1/U2；M6 补记 |
| K18 | **`is_slim` 判据在 v1 块**（决策 ⑨） | `test_slim_is_decided_by_v1_block_not_by_v2` |
| K19 | **`TzifData` 五字段 + `parse(data, zone)` 签名冻结**（决策 ⑧） | `tests/test_m1_data.py` 全部解析器用例 |
| K20 | **入仓 `NEWS` = 首版发布块，逐字保留**（含 2026b 上游笔误、2026d 弯引号） | `test_news_excerpts_pin_the_two_historical_quotes` |
| K21 | **`bench/run.py` 的判据必须能跑红**（吞错误 / 短路比对 / 金标漂移都会被测试抓） | `test_bench_actually_counts_parse_errors` / `test_bench_detects_expect_drift` / `test_bench_detects_timeline_expect_drift` / **`test_bench_detects_windows_expect_drift`** |
| K22 | **`posix_tz` 只做语法，日历算术只在 `civil` / `timeline`** | `test_posix_tz.py` 全部用例；`ALLOWED["posix_tz"] == {"errors"}` |
| K23 | **tail 起跳按 std 墙钟、回拨按 DST 墙钟** | `test_pitfall_wall_seconds_expands_to_07z_not_02z` / `..._governs_fall_back_too` |
| K24 | **tail 正确性靠解析式求值，不靠物化段** | `test_real_trees_roundtrip_holds_for_every_sampled_zone`（窗口外也要对） |
| K25 | **金标候选数必须出现 {0,1,2}** | `test_m2_timeline_gold.py::test_timeline_expect_candidates_cover_all_three_shapes` |
| K26 | **`windows` 的依赖面 = `errors` / `timeline` / `civil`**（不得 import `tzif`/`posix_tz`） | `test_layers_do_not_import_upwards` |
| K27 | **【M3 新增】墙钟窗口按"本地墙钟年份"归属**，扫描窗口在年份边界外留 2 天余量 | `test_windows.py::test_window_is_filed_under_its_local_wall_clock_year`（Almaty 2024-02-29 → 03-01） |
| K28 | **【M3 新增】窗口类型方向由 offset 差决定**：`after > before` = GAP、`after < before` = OVERLAP（与 `is_dst` 无关，负 DST 同样成立） | `test_windows.py::test_dublin_negative_dst_direction_is_correct` |
| K29 | **【M3 新增】候选必须逐条复核**：GAP 段 0 个候选、OVERLAP 段 2 个且 offset 不同；不满足即丢弃 | `test_windows.py::test_candidate_verification_rejects_a_fake_window` |
| K30 | **【M3 新增】`source` 走 `timeline.segment_source_at()`**，不重写"表尾那个转换点归 tail"的规则 | `plan/03` §五 落地说明第 2 条 |

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
| **TZif v2 的两个头都带版本字节** | 合成 fixture 首版把 v1 头写成 `\0` → 解析器判"footer 不是以换行开头" | 实测 2026e 树确认：第一头与第二头都是 `'2'`；fixture 照此构造 |
| **`abbrind` 指向的是字符串表字节偏移，不是类型序号** | 合成 fixture 写 `abbrind=4` → 取到空串 | 第二个缩写从 5 开始；写 fixture 时按字节偏移算 |
| **`pytest` 的 `tmp_path` 造"假仓库"必须跑副本** | 首版用真 `bench/run.py` + `cwd=fake` → 它按 `__file__` 推 ROOT，仍读真仓库 | 复制脚本到假仓库再跑 |
| **`bench/run.py` 认版本看 `provenance.json`** | 假仓库只建 `tzdb/<ver>/` 目录、不写 provenance → `入仓版本: （无）` | 假仓库必须写 `provenance.json` |
| **上游 `2026b` 的 NEWS 头写成 `Release 2026a`** | 实际下载包原文如此 | 原样入仓；测试对 2026b 豁免；**不代改上游** |
| **`retrieved` 取本地日历日不是 UTC 日** | 首版用 `gmtime()` → 记成 2026-10-20 | 改 `localtime()`；`SOURCE_DATE_EPOCH` 存在时读它 |
| **v1 块的转换时刻是 32 位有符号** | 构造 fat fixture 写 2037 年的时间 → `struct.error` | v1 块只放 `[-2^31, 2^31-1]` 内的点；M2 已修 |
| **本机无 `zic`** | `shutil.which('zic')` → `None`；无 `/usr/share/zoneinfo` | fat 树只能自建（`data/fixtures/tzif/source-vs-wheel/gen.py`） |
| **IANA 源码的 `RULES` 字段可以是固定 save** | Dublin 的 `1:00` 不是 ruleset 名 → 编译器报"未知 ruleset" | 不是已知 ruleset 就按偏移解析 |
| **IANA `UNTIL` 的时间基准是"当时生效的偏移"** | Vancouver `2026 Nov 1 2:00` 用 std 偏移换算 → 差 1 小时 | 迭代到不动点；且**严格早于** UNTIL 的最后一条规则才算 |
| **IANA 的 `A/B` 缩写是"左标准、右 DST"** | Dublin `IST/GMT` 配负 DST：看起来"反了"，其实正是 zic 语义 | `_abbr` 按 `is_dst` 选边 |
| **`2:45s` 这类 `s` 后缀不能丢** | Chatham 规则全是 `2:45s` | `_rule_wall_epoch` 原样带出 `kind` |
| **规则年份区间不得借出端点外的年** | 首版用 `from - 1` 起算 → 2000-only 的规则算进 1999 | `range(max(from, lo), min(to, hi) + 1)` |
| **`pytest` 全量很慢** | 287 项：3.12 实测 **3005 s（50 分钟）**、3.8 实测 **2342 s（39 分钟）** | 两通道各跑一次 ≈ 1.5 小时；**必须串行**（并发会读到半写金标而假红）；改代码后先跑受影响文件 |
| **台账状态格混 `🟡` + ✅ 里程碑号会红** | `LAYOUT.LEDGER` 把 `🟡` 当未完成标记 | 见 §2 第 3 条 |
| **【M3 新增】合成 fixture 的"表尾偏移"必须与 tail 在表尾处的偏移一致** | 合成 `Zone/AbbrevOnly` 若把只换缩写的转换点放在**夏天**，表说 EST、tail 说 EDT → 交界处造出一条**假窗口** | 实测 2026e 等五版本 553 个带 tail 的 zone **零不变量违例**；fixture 把该点放在冬季（1/15） |
| **【M3 新增】`bench/run.py` 的 `--suite` 取值集合已变** | `windows` 从"未知套件"变成第三套件 → 两条旧测试（`test_bench_rejects_unknown_suite`）假红 | 已改成 `no-such-suite`；M4 加第四套件时**不要再拿 `windows` 当反例** |
| **【M3 新增】长跑 `pytest` 偶发 Windows 访问冲突** | 一次全量跑在 `ast.py` 里崩（`access violation`），分文件跑全绿 | 疑似长时间运行的资源问题；**分文件跑**并复跑确认，不当成代码缺陷 |
| **【M3 新增】两个通道的 pytest **不能并发**，也不许与 `bench/run.py` 并发** | 本次实测：3.12 全量在跑时又起了 3.8 全量 + 一次 `bench/run.py --check` → 3.8 侧 **4 个用例假红**（3 个是金标文件被并发写读到半成品，1 个是子进程 `No module named tzaudit`） | **串行跑**；单独复跑那 4 个用例全绿。`bench/run.py --check` 也会写金标（`--check` 不写，但 `--regen` 写）——**并发时读到半写文件必假红** |
| **【M3 新增】子进程调 CLI 的测试不能依赖"包已安装"** | 本机只给 3.12 通道装了 `tzaudit`（`pip install -e .`），3.8 通道没装 → `python -m tzaudit` 在 3.8 下 `No module named tzaudit` | 测试里给子进程设 `PYTHONPATH=<repo>/src`，**不依赖安装状态**（CI 里两种状态都可能） |

### M3 变异验证记录（6 组；就地变异 → 目标变红 → 还原复绿）

| # | 变异（改哪一行） | 期望命中的判据 | 实测 |
|---|---|---|---|
| M3-V1 | `bench/run.py`：`_check_windows` 里 `for key in WINDOWS_KEYS:` 下的比对加 `False and` 短路 | `test_bench_detects_windows_expect_drift` | ✅ 变红（漂移被吞 → 门恒绿 → 漂移测试红），还原复绿 |
| M3-V2 | `bench/run.py`：`windows_stats` 里 `total_windows += count` → `+= count + 1` | `bench/run.py --check --suite windows` 退非 0（`total_windows 漂移`） | ✅ 变红，还原复绿 |
| M3-V3 | `windows._verify_candidate`：函数体开头 `return True`（跳过复核） | `test_candidate_verification_rejects_a_fake_window` | ✅ 变红（正常时刻被判成 GAP），还原复绿 |
| M3-V4 | `windows._scan`：删掉 `if civil.local_naive_from_epoch(start_local)[0] != year: continue`（去掉年份归属过滤） | `test_window_is_filed_under_its_local_wall_clock_year` + 两条 `not_lost` | ✅ 变红，还原复绿 |
| M3-V5 | `windows._YEAR_MARGIN_SEC`：`2 * 86400` → `0`（年份边界余量归零） | 两条 `not_lost`（跨年窗口整个丢掉） | ✅ 变红，还原复绿 |
| M3-V6 | `windows._scan`：`GAP` 与 `OVERLAP` 两个分支互换（方向反了） | `test_new_york_2026_..._correct_direction` + `test_dublin_negative_dst_direction_is_correct` | ✅ 变红，还原复绿 |

> **M3 的极性教训（新增，比 M2 的"瞄错列"更进一步）**：
>
> 1. **"门级变异"与"行为级变异"要用不同的跑法**。改 `bench/run.py` 的**判据**时，
>    必须跑**真实仓库的** `bench/run.py --check`（对着**入仓**金标）——
>    跑"漂移测试"是**错的**：那个测试会**用被变异的代码重新生成金标**，
>    于是"期望与实现同源"、门照样绿（引擎自证）。
>    反过来，改 `src/` 的**实现**时，要跑**行为测试**（不是 bench）。
>    首版把 V1 的跑法搞反了，测出来"rc=0"——正是这个坑的现场。
> 2. **变异靶子要"瞄得准"**：M3-V4 的初版靶子（删年份过滤）在**当年的时间线**上
>    不咬人（`Asia/Almaty` 2024 的窗口起点在年内，不靠余量），
>    换成"转换点在年外"的两条真例（`America/Managua` 1996 / `Asia/Choibalsan` 1978）才咬住。
>    **判据的锚点必须选在"该判据唯一会失效"的地方。**
> 3. **合成 fixture 里"自相矛盾的树"会造出假阳性**：第一次把"只换缩写"的陷阱转换点
>    放在**夏天**，结果表说 EST、tail 说 EDT，交界处凭空多出一条 GAP——
>    差点被当成"实现的 bug"写进结论。正解：**先验证树自洽**
>    （表尾偏移 == tail 在表尾处的偏移），再拿它做反例。
>    这条已写进 §5 的坑表。

## 6. DoD 逐项 checklist（M4）

- [ ] `diff.diff_trees` 落地，`Change` 字段与 `plan/03` §六 一致
- [ ] 四类判定**顺序固定**（`CLASS_ORDER` 常量），同一 zone 只输出一条
- [ ] `history_reinterpreted`：窗口内任一 UTC 时刻两树 `to_local` 不同 → 成立
- [ ] `future_rule`：表相同但 tail 不同 → **必须**落这里（Vancouver 2026.1→2026.5）
- [ ] `abbreviation_only`：转换点 `utc/offset` 全同，仅 `abbr` 不同
- [ ] `alias_only`：仅 link 集合变化（sha256 判据），**不得**吸收规则变化
- [ ] 判定顺序变异测试：调换顺序 → 必红
- [ ] Dublin 1925 / Tehran 1979 → `history_reinterpreted`（真实数据）
- [ ] `data/fixtures/diff/` 落地，`gen.py --check` 逐字节一致
- [ ] `bench/run.py --check --suite diff` 退 0；金标无 `observed_*`；名单**集合相等**（不写死条数）
- [ ] `py -3.12 -m pytest` 全绿（含新增 M4 测试）
- [ ] `py -3.8 -m pytest` 全绿（底线解释器）
- [ ] 布局门 + 脱敏门全绿
- [ ] `EXIT_NOT_READY` 只退役 `diff` 一条（常量仍在，`audit`/`report` 仍退 5）
- [ ] 四处状态副本同步翻 M4 ✅
- [ ] `plan/HANDOFF-M5.md` 已落盘（七节齐）

> 未推送期间**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。

## 7. 关键命令速查

```bash
# 门
py -3.12 tools/check-sprint-layout.py            # 布局门
py -3.12 tools/check-desensitized.py             # 脱敏门

# 测试（两个通道都跑；**必须串行**，并发会读到半写金标而假红）
# 注意：pyproject 的 addopts 已是 "-q"；再传 -q 会变成 -qq，**不打印汇总行**
py -3.12 -m pytest
py -3.8  -m pytest

# 单文件（改完先跑受影响的那几个）
py -3.12 -m pytest tests/test_diff.py -q
py -3.12 -m pytest tests/test_windows.py -q
py -3.12 -m pytest tests/test_timeline.py -q

# 数据（干净 clone 先跑这一条）
py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e
py -3.12 tools/fetch_tzdb.py --check
py -3.12 tools/fetch_tzdb.py --materialize

# 金标
py -3.12 bench/run.py --check
py -3.12 bench/run.py --check --suite parse
py -3.12 bench/run.py --check --suite timeline
py -3.12 bench/run.py --check --suite windows
py -3.12 bench/run.py --regen
py -3.12 bench/run.py --regen --suite timeline
py -3.12 bench/run.py --regen --suite windows

# fixture 重建
py -3.12 data/fixtures/tzif/slim-vs-fat/gen.py --check
py -3.12 data/fixtures/tzif/source-vs-wheel/gen.py --check
py -3.12 data/fixtures/posix/three-rule-forms/gen.py --check
py -3.12 data/fixtures/windows/gen.py --check

# 安装与 CLI 冒烟
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m tzaudit --help
py -3.12 -m tzaudit --version
py -3.12 -m tzaudit windows --zone America/New_York --year 2026 --zoneinfo data/_downloads/slim/2026e
py -3.12 -m tzaudit windows --all --year 2026 --zoneinfo data/_downloads/slim/2026e --json

# 取退出码（别接管道）
py -3.12 tools/check-sprint-layout.py > /dev/null; echo "layout rc=$?"
```

### 收尾顺序（硬约束，不得裁量）

```
DoD 逐项验证 → 四处状态副本回写 → 写 plan/HANDOFF-M5.md → git add -A → commit →（有远端则 push 等 CI）
```

未推送期间 DoD 里**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。
