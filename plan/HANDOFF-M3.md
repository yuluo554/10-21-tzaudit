# HANDOFF-M3 · 墙钟风险窗口 `windows`

> 上一棒：**M2（TZif 双引擎）✅ 2026-10-21**
> 本棒目标：**M3 墙钟窗口** —— `windows.py` 落地，让 `tzaudit windows --zone X --year Y`
> 输出 **GAP / OVERLAP** 墙钟区间，并用双判据复核到"宁漏不误报"。
> 启动命令（用户侧，绝对路径不入库）：`/goal 读取 "<项目根>\plan\HANDOFF-M3.md" 继续完成任务`
> **第一动作**：`py -3.12 tools/check-sprint-layout.py`（必须全绿；红了先修布局）。

---

## 1. 当前进度 + 证据

**已完成（M0 + M1 + M2）**

| 交付 | 证据 |
|---|---|
| 计划套件 `plan/00–06` | 布局门 `LAYOUT.FILES 10 份齐备` / `LAYOUT.SECTIONS 8 份小节齐备` |
| 方法论装订 | `LAYOUT.BINDING_HEAD PASS`；`LAYOUT.DOC_TOOLS 4 个脚本全部在位` |
| 五版本真实数据入仓 | `data/tzdb/{2026a..2026e}/` 各含 `provenance.json` + `NEWS` 首版块 + `leap-seconds.list` + `version` + `expect.json` |
| **TZif 解析器（v1–v4）** | `src/tzaudit/tzif.py`；全量 598 zone × 5 版本 = 2990 次解析零错误 |
| **POSIX TZ 解析器** | `src/tzaudit/posix_tz.py`；`data/README.md` §4.2 全部形态；三条技术坑各一反例 |
| **双引擎合并 + 本地反解** | `src/tzaudit/timeline.py`；`load_timeline` / `resolve_local` / `to_local` / `roundtrip` / `offset_at` / `transition_points` |
| **独立参照实现（扩到 timeline 层）** | `tests/reference.py`：TZif 读取 + POSIX 正则解析 + `datetime` 日历 + **段区间包含式**反解（不 import tzaudit） |
| **timeline 金标（两套件）** | `data/tzdb/<ver>/expect-timeline.json`；`bench/run.py --check` 退 0，两套件各 5 份 |
| **三个 fixture + 生成器** | `data/fixtures/tzif/slim-vs-fat/`、`data/fixtures/tzif/source-vs-wheel/`、`data/fixtures/posix/three-rule-forms/`，各带 `gen.py --check`（逐字节） |
| 契约测试 | `py -3.12 -m pytest` → **230 passed, 1 skipped**（231 项收集）；`py -3.8` 同（3.8 通道无额外 skip） |
| 门 | 布局门绿 / 脱敏门绿（189 份文本） |

**M2 结束时已锁住的状态**：`posix_tz.parse` 解 `data/README.md` §4.2 全部形态；
`timeline.load_timeline(zone, store, window_start, window_end)` 把表段与 tail 段合成一条
`Segment` 序列（无缝、`source ∈ {table, tail}`）；`resolve_local` / `roundtrip` 与参照实现对拍一致
（全 598 zone 转换点邻域 **96680** 点 + 抽样 **767832** 点零不一致）。
`windows` 仍是 `raise NotImplementedYet`（M3 落地）。

## 2. 当前事实 · 状态不变量（下一棒动手前必须知道）

1. **数值口径的唯一真相源 = `data/README.md` §四**。`plan/02`/`plan/03`/README 只引用不复制；
   任何"第二套口径"都会让 `plan/06` X2 风险成真。改口径 = 改 §四 + 改引用 + 决策记录三处。
2. **`plan/01` §1.5 的探针快照数字（598 / 11 / 20 / 201 / 192 / 580）不得进代码常量、不得进
   README 首屏、不得作断言阈值**。唯一例外：M1 的"零解析错误"与"对拍一致率"是**判据正确性**
   门槛，且分母以末态回填。
3. **状态副本有四处**（`plan/00` 台账行 / `plan/00` 里程碑表 / `plan/05` 状态表 / `README.md` 路线图），
   布局门逐副本采集、任一不一致即红。翻转状态必须**同一次提交**内改齐四处。
   **M2 实测坑**：台账"状态"列若出现 `🟡` 且同一格提到已 ✅ 的里程碑号，`LAYOUT.LEDGER` 立刻红
   （`🟡` 本身是未完成标记）。要么写 `⬜`，要么写 ✅ + 说明，不要混。
4. **退出码 5（未就绪）是临时的**：`windows`/`diff`/`audit`/`report` 每落地一个，必须在同一提交里
   删掉 `errors.NotImplementedYet` 对应引用、删 `tests/test_exit_codes.py::test_not_ready_exit_code_is_5`
   里那一行、改 `plan/03` §九与 `data/README.md` §4.4。四处少一处 = 幽灵语义复活。
   **M3 只退役 `windows` 那一行**，其余三个子命令仍在 5。
5. **`plan/03` 与实现必须同步**：M2 已把 §三 / §四 改成 `[M2 已落地]` 并登记了三处实现细节差异
   （表覆盖 `[首个, 最后一个)`、窗口只影响物化、候选 offset 枚举法）。M3 落地后同样要改 §五。
6. **`tests/test_architecture.py` 的 `ALLOWED` 是依赖方向的唯一真相源**。`windows` 只能 import
   `errors` / `timeline` / `civil`（**不能** import `posix_tz` / `tzif` / `zoneinfo_store`）。
   新增模块必须先加表（门会报"新模块未声明"）。
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
13. **【M2 新增】`posix_tz` 只做语法**，不做日历算术——"规则 → UTC 时刻"在 `timeline`
    （`timeline._rule_local_epoch` / `timeline._year_transitions`）。M3 **不要**在 `windows` 里
    重写一遍规则展开：直接用 `timeline.transition_points` + `offset_at`。
14. **【M2 新增】`/time` 的两种基准**：`timeline._year_transitions` 里，**起跳按 std 墙钟**、
    **回拨按 DST 墙钟**（tzcode 语义）。改这条会让 `test_pitfall_wall_seconds_*` 立刻红。
15. **【M2 新增】tail 的正确性靠"解析式求值"，不靠物化段**：`to_local` / `resolve_local` 对
    `utc >= table_end_utc` 走 `_tail_state_at`（按年展开 + 跨年 ±1 年）。物化段只提供
    `source="tail"` 证据。**不要**改成"只查物化段"——窗口外的 UTC 会算错。
16. **【M2 新增】`resolve_local` 用"枚举候选 offset + 自洽校验"**（不是 `max/min_offset` 区间法）。
    两者等价，但枚举法在 tail 生效区不需要维护 `max/min`（那里没有物化段）。
17. **【M2 新增】金标候选数必须出现 {0,1,2}**：只用均匀网格抽样时实测集合 = `{1}`
    （gap/overlap 等于没验）。`bench/run.py` 因此另加 `TIMELINE_TRANSITION_PROBES` 个
    从转换点反推的探测时刻。**M3 的 `windows` 金标同样要能覆盖 gap 与 overlap 两种**。
18. **【M2 新增】本机无 `zic`**（实测 2026-10-21）。`data/fixtures/tzif/source-vs-wheel/fat/`
    是 `gen.py` 的规则编译器产物，**不是** `zic` 产物；README 里已如实标注 `known_deviation`。
    `tests/test_timeline.py::test_slim_and_fat_semantics_on_real_data` 因此 skip（写明理由）。
19. **【M2 新增】`test_m1_data.py::test_bench_check_passes_with_real_trees` 断言的是全量输出**。
    若同时有别的进程在跑 `bench/run.py`（并发），可能读到半写文件而假红——**跑测试不要并发**。
20. **【M2 新增】`bench/run.py` 现在有两套件**（`parse` / `timeline`），各自一个金标文件。
    `--suite` 只选一个；缺省跑全部。新增第三套件（如 `windows`）时：加 `SUITES` 常量 +
    `_check_<suite>` + `_<suite>_doc` + 对应的 `_write_*`，并**同时**给金标加漂移变异测试。

## 3. 下一棒待办（M3 墙钟窗口）

按顺序做，每步都有可跑的判据：

1. **实现 `src/tzaudit/windows.py`**
   - `scan_year(zone, year, tl)` → `list[Window]`；`Window(type, start_local, end_local,
     duration_min, residual_sec, offset_before, offset_after, zone, source)`（`plan/03` §五）。
   - 取该年覆盖的转换点：`timeline.transition_points(tl, year_start, year_end)`。
   - 对每个转换点：`before = timeline.offset_at(t_i - 1, tl)`、`after = timeline.offset_at(t_i, tl)`。
     - `after > before` → 候选 GAP `[t_i + before, t_i + after)`。
     - `after < before` → 候选 OVERLAP `[t_i + after, t_i + before)`。
   - **逐候选复核双判据**：段内取首/中/末三点（长度 < 3 分钟则逐秒）跑 `resolve_local`：
     GAP 段必须 `len==0`；OVERLAP 段必须 `len==2` 且两 offset 不同。任一不满足 → **丢弃候选**。
   - 输出排序：`start_local` 升序 → 同起点 `type` 字典序（`GAP` < `OVERLAP`）。
   - `duration_min = (end - start) // 60`；`residual_sec = (end - start) % 60`（不并进分钟）。
2. **`--all` 模式**：遍历 `store.zones()`（字节序），单 zone 异常 → 该 zone 记 `error` 进
   `summary.errors`，**不中断整批**；有 error 时退 3。
3. **接线 `cli.py`**：`windows` 子命令落地 → **同一提交里**退役 `EXIT_NOT_READY` 的 `windows` 那一条
   （删 `cli._unimplemented` 对 windows 的分派、删 `test_exit_codes.py` 里 windows 那行、
   改 `plan/03` §九与 `data/README.md` §4.4）。**注意**：`diff`/`audit`/`report` 三条仍在 5。
4. **落地 `tests/test_windows.py`**（`plan/03` §五 测试点）：
   - NY 2026 → 恰好两条：GAP `02:00→03:00`、OVERLAP `01:00→02:00`，方向正确，`source=table`。
   - **Vancouver 2026 → 零条**（只按 fold 判 overlap 的实现会在这里报一条）。
   - `Australia/Lord_Howe 2026`（30 分钟）→ 两条，`duration_min=30`；
     `Pacific/Chatham 2026` → 两条，偏移含 45 分钟。
   - `--all --year 2026` 跑完不抛异常，`summary.zones` 与扫描数一致。
   - 同一 zone 双跑逐字节一致（忽略 `generated_at`）。
5. **落地 `data/fixtures/windows/`**：生成器 + `expect.json` + `README.md`（`plan/04` §三 硬纪律：
   `--check` 两层断言、禁 random / 禁时钟 / 写盘归一）。
6. **`bench/run.py` 加第三套件 `windows`**：金标存"抽样 zone 在抽样年份的窗口集合"
   （`plan/04` §二 已定口径）。**仍然只存输入与期望**，不得出现 `observed_*`。
   **必须**给这条判据加漂移变异测试（M1 教训：新判据先想好"改哪一行会让它红"）。
7. **状态回写 + 写 `plan/HANDOFF-M4.md` + commit**（收尾顺序见下）。

> **M3 不要做的事**：不要碰 `diff`/`audit`/`report`（M4/M5）、不要把 `EXIT_NOT_READY` **整项**删掉
> （只退役 `windows` 那一条；其余三条还在用）、不要改 `timeline` 的接口签名。

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
| K8 | POSIX 偏移**西为正**，解析层翻成**东为正**的秒数 | `test_posix_tz.py::test_west_positive_is_flipped_to_east_positive` |
| K9 | `/time` 是**墙钟秒**，解析层只存 `time_sec`，不做偏移加减 | `test_posix_tz.py::test_slash_time_is_parsed_as_wall_seconds_not_offset` |
| K10 | 存在性只由 `resolve_local` 的候选个数决定；`fold` 只用于选择 | `test_timeline.py::test_exists_only_by_candidate_count_not_by_fold` + Vancouver 反例（M3） |
| K11 | 四类变更判定顺序固定 `history → future → abbrev → alias` | `diff.CLASS_ORDER`（已是常量） |
| K12 | 发布里程碑固定 M6（`check-sprint-layout.py::RELEASE_MILESTONE`） | `LAYOUT.RELEASE` 分支 |
| K13 | M0 豁免 HANDOFF-M0；`HANDOFF_SECTIONS` 七节为**必需子集**（超集合法） | `LAYOUT.HANDOFFS` / `LAYOUT.NEXT_HANDOFF` |
| K14 | **主金标两棵树 = PyPI slim wheel × 2**（Q1 定案）；fat 仅作 M2 fixture | `data/tzdb/*/provenance.json` 的 `kind` 必须是 `slim` |
| K15 | **Python 底线 3.8**（Q2 定案）：禁 `dict \|`、禁 `X \| Y` 类型标注、禁 `tomllib`、禁 `str.removeprefix` | `py -3.8 -m pytest` 必须全绿；CI 矩阵 3.8+3.12 |
| K16 | **`audit --version` 只收两个目录路径**（Q4 定案），不收版本号 | `cli.py` 的 `--version` 帮助文本；`plan/03` §七 |
| K17 | **未接远端**（Q7 定案）：DoD 只写"本地等价校验（未接远端，CI 待首推验证）" | `plan/05` §三 U1/U2；M6 补记 |
| K18 | **`is_slim` 判据在 v1 块**（决策 ⑨） | `test_slim_is_decided_by_v1_block_not_v2`；挪到 v2 块即红 |
| K19 | **`TzifData` 五字段 + `parse(data, zone)` 签名冻结**（决策 ⑧） | `tests/test_m1_data.py` 全部解析器用例 |
| K20 | **入仓 `NEWS` = 首版发布块，逐字保留**（含 2026b 上游笔误、2026d 弯引号） | `test_news_excerpts_pin_the_two_historical_quotes` |
| K21 | **`bench/run.py` 的判据必须能跑红**（吞错误 / 短路比对 / 金标漂移都会被测试抓） | `test_bench_actually_counts_parse_errors` / `test_bench_detects_expect_drift` / `test_bench_detects_timeline_expect_drift` |
| K22 | **【M2 新增】`posix_tz` 只做语法，日历算术只在 `civil` / `timeline`** | `test_posix_tz.py` 全部用例；`ALLOWED["posix_tz"] == {"errors"}` |
| K23 | **【M2 新增】tail 起跳按 std 墙钟、回拨按 DST 墙钟** | `test_pitfall_wall_seconds_expands_to_07z_not_02z` / `..._governs_fall_back_too` |
| K24 | **【M2 新增】tail 正确性靠解析式求值，不靠物化段** | `test_real_trees_roundtrip_holds_for_every_sampled_zone`（窗口外也要对） |
| K25 | **【M2 新增】金标候选数必须出现 {0,1,2}** | `test_m2_timeline_gold.py::test_timeline_expect_candidates_cover_all_three_shapes` |
| K26 | **【M2 新增】`windows` 的依赖面 = `errors` / `timeline` / `civil`**（不得 import `tzif`/`posix_tz`） | `test_layers_do_not_import_upwards` |

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
| **`pytest` 的 `tmp_path` 造"假仓库"必须跑副本** | 首版用真 `bench/run.py` + `cwd=fake` → 它按 `__file__` 推 ROOT，仍读真仓库 | 复制脚本到假仓库再跑 |
| **`bench/run.py` 认版本看 `provenance.json`** | 假仓库只建 `tzdb/<ver>/` 目录、不写 provenance → `入仓版本: （无）` | 假仓库必须写 `provenance.json` |
| **上游 `2026b` 的 NEWS 头写成 `Release 2026a`** | 实际下载包原文如此 | 原样入仓；测试对 2026b 豁免；**不代改上游** |
| **`retrieved` 取本地日历日不是 UTC 日** | 首版用 `gmtime()` → 记成 2026-10-20 | 改 `localtime()`；`SOURCE_DATE_EPOCH` 存在时读它 |
| **v1 块的转换时刻是 32 位有符号** | 构造 fat fixture 写 2037 年的时间 → `struct.error: 'i' format requires ...` | v1 块只放 `[-2^31, 2^31-1]` 内的点（真实 zic 也这么切）；M2 已修 |
| **本机无 `zic`** | `shutil.which('zic')` → `None`；无 `/usr/share/zoneinfo` | fat 树只能自建（`data/fixtures/tzif/source-vs-wheel/gen.py`），README 标注 `known_deviation` |
| **IANA 源码的 `RULES` 字段可以是固定 save** | Dublin 的 `1:00` 不是 ruleset 名 → 编译器报"未知 ruleset" | 不是已知 ruleset 就按偏移解析 |
| **IANA `UNTIL` 的时间基准是"当时生效的偏移"** | Vancouver `2026 Nov 1 2:00` 用 std 偏移换算 → 差 1 小时（那时 DST 仍生效） | 迭代到不动点；且**严格早于** UNTIL 的最后一条规则才算（同刻的回拨不算） |
| **IANA 的 `A/B` 缩写是"左标准、右 DST"** | Dublin `IST/GMT` 配负 DST：看起来"反了"，其实正是 zic 语义 | `_abbr` 按 `is_dst` 选边；写反会让 2.1M 采样点全红 |
| **`2:45s` 这类 `s` 后缀不能丢** | Chatham 规则全是 `2:45s`（标准时基准）；当墙钟处理会让回拨偏 1 小时 | `_rule_wall_epoch` 原样带出 `kind` |
| **规则年份区间不得借出端点外的年** | 首版用 `from - 1` 起算 → 2000-only 的规则算进 1999 | `range(max(from, lo), min(to, hi) + 1)` |
| **`pytest` 全量很慢** | 231 项：3.12 实测 1653–2486s；3.8 实测 3360s | 两通道各跑一次 ≈ 1 小时；**别并发跑**（会读到半写金标而假红）；改代码后先跑受影响文件 |
| **台账状态格混 `🟡` + ✅ 里程碑号会红** | `LAYOUT.LEDGER` 把 `🟡` 当未完成标记 | 见 §2 第 3 条 |

### M2 变异验证记录（5 组；在临时副本上执行，不污染工作树）

| # | 变异（改哪一行） | 期望命中的判据 | 实测 |
|---|---|---|---|
| M2-V1 | `posix_tz.parse`：`std = (-west, std_abbr)` → `(west, std_abbr)`（不翻符号） | `test_west_positive_is_flipped_to_east_positive` | ✅ 变红（29 failed），还原复绿 |
| M2-V2 | `timeline._year_transitions`：`start_local - tail.std[0]` → `- tail.dst[0]`（起跳按 DST 换算） | `test_pitfall_wall_seconds_expands_to_07z_not_02z` | ✅ 变红（17 failed），还原复绿 |
| M2-V3 | `timeline.resolve_local`：删掉 `if to_local(utc, timeline) != local: continue`（自洽校验） | `test_ny_2026_gap_and_overlap_counts` / `test_exists_only_by_candidate_count_not_by_fold` | ✅ 变红——**GAP 变成 2 个候选**，正是 M3 双判据要防的形态 |
| M2-V4 | `bench/run.py`：`for key in TIMELINE_KEYS:` 下的比对加 `False and` 短路 | `test_bench_detects_timeline_expect_drift` | ✅ 变红（`--check` 退非 0），还原复绿 |
| M2-V5 | `timeline.load_timeline`：最后一个转换点不再 `continue`（表段延伸到无穷） | `test_table_segments_cover_transitions_and_tail_takes_over` | ✅ 变红（段之间有缝），还原复绿 |

> **V4 的坑（已实测）**：`bench/run.py` 里有**两处** `if expected.get(key) != stats[key]:`
> （parse 与 timeline 各一处）。只改第一处会命中 parse 那条判据，timeline 那条仍绿——
> 变异靶子必须瞄**目标套件那一行**。这与 M1 的 V6 教训（改错列）是同一类。

> **教训（沿用 M1）**：新判据必须**先想好"改哪一行会让它红"**，再写测试；跑一遍变异是唯一能证伪的方式。
> M2 的 V3 尤其值得记：自洽校验那行看起来"多余"（候选 offset 都是从段表来的），
> 删掉后 gap 会变成"1 个候选"——而这正是 M3 双判据要防的那类错误。

## 6. DoD 逐项 checklist（M3）

- [ ] `windows.scan_year` 落地，`Window` 字段与 `plan/03` §五 一致
- [ ] 双判据复核：GAP 段 `resolve_local` 必 0 个、OVERLAP 段必 2 个且 offset 不同；不满足即丢弃
- [ ] NY 2026 → GAP `02:00→03:00` + OVERLAP `01:00→02:00`，`source=table`
- [ ] **Vancouver 2026 → 零条**（反例单测，能跑红）
- [ ] Lord_Howe（30 分钟）/ Chatham（45 分钟）/ Dublin（负 DST）三条金标
- [ ] `--all --year 2026` 跑完；单 zone 错误进 `summary.errors` 不中断
- [ ] 跨年边界不丢窗口（12/31、闰年 2/29）
- [ ] `EXIT_NOT_READY` 只退役 `windows` 一条（常量仍在，`diff`/`audit`/`report` 仍退 5）
- [ ] `data/fixtures/windows/` 落地，`gen.py --check` 逐字节一致
- [ ] `bench/run.py --check --suite windows` 退 0；金标无 `observed_*`
- [ ] `py -3.12 -m pytest` 全绿（含新增 M3 测试）
- [ ] `py -3.8 -m pytest` 全绿（底线解释器）
- [ ] 布局门 + 脱敏门全绿
- [ ] 四处状态副本同步翻 M3 ✅
- [ ] `plan/HANDOFF-M4.md` 已落盘（七节齐）

> 未推送期间**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。

## 7. 关键命令速查

```bash
# 门
py -3.12 tools/check-sprint-layout.py            # 布局门
py -3.12 tools/check-desensitized.py             # 脱敏门

# 测试（两个通道都跑；单次 30–55 分钟，别并发）
# 注意：pyproject 的 addopts 已是 "-q"；再传 -q 会变成 -qq，**不打印汇总行**
py -3.12 -m pytest
py -3.8  -m pytest

# 单文件（改完先跑受影响的那几个）
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
py -3.12 bench/run.py --regen
py -3.12 bench/run.py --regen --suite timeline

# fixture 重建
py -3.12 data/fixtures/tzif/slim-vs-fat/gen.py --check
py -3.12 data/fixtures/tzif/source-vs-wheel/gen.py --check
py -3.12 data/fixtures/posix/three-rule-forms/gen.py --check

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
DoD 逐项验证 → 四处状态副本回写 → 写 plan/HANDOFF-M4.md → git add -A → commit →（有远端则 push 等 CI）
```

未推送期间 DoD 里**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。
