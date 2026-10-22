# HANDOFF-M6 · 发布（tag + Release + 发布留档）

> 上一棒：**M5（清单审计 `audit` + 报告门禁 `report`）✅ 2026-10-22**
> 本棒目标：**把 `v0.1.0` 发出去** —— 版本号三处一致、干净环境按 README 跑通四场景、
> 断网跑通、脱敏门绿、tag `v0.1.0` + GitHub Release（附件 `git archive` + `gzip -9n`
> + `SHA256SUMS`）、`plan/RELEASE-M6.md` 两栏 + 阶段 7 覆盖对账。
> 启动命令（用户侧，绝对路径不入库）：`/goal 读取 "<项目根>\plan\HANDOFF-M6.md" 继续完成任务`
> **第一动作**：`py -3.12 tools/check-sprint-layout.py`（必须全绿；红了先修布局）。

---

## 1. 当前进度 + 证据

**已完成（M0 + M1 + M2 + M3 + M4 + M5）**

### M5 DoD 逐项实测（20/20；证据可复跑）

| # | DoD 项 | 实测证据 |
|---|---|---|
| 1 | `audit.audit_rows` 落地，`Row` 字段与 `plan/03` §七 一致 | `Row.__slots__` = `{id, local, status, utc_candidates, note, invalid_reason}`（6 字段，逐个对上）；`test_row_fields_match_plan_section_seven` |
| 2 | 判定顺序固定 `INVALID → GAP → OVERLAP → VERSION_CHANGED → OK` | `STATUS_ORDER` 五元组；`_judge` **按 `STATUS_ORDER` 遍历**；`test_status_order_is_frozen` |
| 3 | 行序保持输入序；多候选按 UTC 升序 | `test_output_row_order_equals_input_row_order`（打乱输入后断言）+ `test_same_local_twice_yields_two_ordered_candidates` |
| 4 | `INVALID` 不静默跳过：进结果 + 计数 + 整体退 4，其余行照常判定 | `test_invalid_rows_are_not_silently_dropped`（混合 4 条坏行 + 2 条好行：坏行留原地、`good-2` 仍拿到 `VERSION_CHANGED`）+ `test_cli_audit_bad_rows_exit_4` |
| 5 | `--daily HH:MM` 与等价清单输出一致；缺 `year` 退 2 | 365 条逐条比对（除 `id` 前缀外全等）：`test_daily_expansion_matches_equivalent_list`；`test_daily_requires_year_and_does_not_default_to_now` + `test_cli_audit_daily_without_year_returns_2` |
| 6 | `--version A,B` 只收目录路径；缺 `provenance.json` 退 3 | `test_cli_audit_version_requires_provenance`（裸目录 → 3）+ `test_cli_audit_version_takes_exactly_two_dirs`（一个 → 2） |
| 7 | `report.build_report` 落地，报告头三字段齐；缺一退 3 | `test_report_header_has_exactly_three_fields` + `test_missing_header_field_raises_report_incomplete`（三字段各一条参数化） |
| 8 | `generated_at` **由调用方注入**，`report` 内不读时钟 | `test_report_module_does_not_read_the_clock_outside_its_single_point`（AST 断言 `gmtime` 只在 `resolve_generated_at` 内）；`test_cli_report_frozen_clock_via_source_date_epoch` |
| 9 | `--fail-on` 三值枚举，四组退出码测试 | `test_gate_exit_0_when_nothing_hits` / `..._1_on_gap` / `..._1_on_overlap` / `..._1_on_history`；`test_parse_fail_on_rejects_unknown` |
| 10 | `--json` 与 Markdown 退出码相同 | `test_cli_report_json_and_markdown_exit_codes_match` |
| 11 | `data/fixtures/audit/bc-scenario/` 落地，`gen.py --check` 逐字节一致 | `bc-scenario: PASS（6 份产物逐字节一致）`；两层断言（`_self_check` 形态 + 重生成比对） |
| 12 | `tests/test_audit.py` + `tests/test_report.py` 落地 | 31 + 50 项全绿 |
| 13 | **`EXIT_NOT_READY` 整项退役** | `errors.EXIT_NOT_READY` / `errors.NotImplementedYet` / `cli._unimplemented` **全部删除**；`test_not_ready_semantics_is_gone_from_the_package` 三处一起断言 + 逐文件扫 `src/` |
| 14 | 新增两条"防复活"断言 | `test_audit_is_no_longer_not_ready` / `test_report_is_no_longer_not_ready` |
| 15 | `py -3.12 -m pytest` 全绿 | **434 passed, 1 skipped**（435 项收集；1723.25 s ≈ 28 分 43 秒） |
| 16 | `py -3.8 -m pytest` 全绿 | **434 passed, 1 skipped**（3239.47 s ≈ 54 分）；与 3.12 通道同数 |
| 17 | 布局门 + 脱敏门全绿 | 布局门 10 条判据全 PASS（`HANDOFF-M6` 落盘后）；脱敏门全绿（218 份文本文件） |
| 18 | 四处状态副本同步翻 M5 ✅ | `plan/00` 台账 + `plan/00` 里程碑表 + `plan/05` 状态表 + `README.md` 路线图，M5 行全含 ✅ |
| 19 | `plan/HANDOFF-M6.md` 已落盘（七节齐） | 本文件 |
| 20 | 第五套件 `audit` + 金标 + 漂移/退化变异 | `data/tzdb/pairs/2026a-2026e.audit.json`（8 行，状态 `GAP/OK/OVERLAP/VERSION_CHANGED`，对拍 8）；`tests/test_m5_audit_gold.py` 13 项（含 5 条变异自证） |

### 交付物清单

| 交付 | 证据 |
|---|---|
| **`audit.py`（M5 核心）** | `src/tzaudit/audit.py`：`STATUS_ORDER` / `Row` / `AuditResult` / `parse_times` / `parse_clock` / `expand_daily` / `audit_rows` + `_HOLDS` 判据表 |
| **`report.py`（M5 核心）** | `src/tzaudit/report.py`：`build_report` / `check_header` / `parse_fail_on` / `gate_exit_code` / `report_exit_code` / `resolve_generated_at` + 三张表的固定列序常量 |
| **`civil.format_utc`** | `src/tzaudit/civil.py`：UTC 时刻的 `YYYY-MM-DDTHH:MM:SSZ` 渲染（`--json` 的候选时刻用） |
| **`audit` / `report` 子命令** | `cli.py::_run_audit` / `_run_report` / `_resolve_trees` / `_derive_header` + 两个渲染函数 |
| **M5 测试** | `tests/test_audit.py`（31 项）/ `tests/test_report.py`（50 项） |
| **M5 金标测试** | `tests/test_m5_audit_gold.py`（13 项）：形态 8 项 / 复算入口 2 项 / 漂移与退化变异 5 项 |
| **audit fixture** | `data/fixtures/audit/bc-scenario/{gen.py, expect.json, README.md, times.txt, old/, new/}`（6 份产物） |
| **audit 金标** | `data/tzdb/pairs/2026a-2026e.audit.json`（`rows` / `single_version` / `statuses` / `same_utc_two_walls` / `reference_cross_checked`） |
| **bench 第五套件** | `bench/run.py`：`SUITES` 加 `audit`、`AUDIT_TIMES` / `AUDIT_PAIRS`、`audit_stats` / `cross_check_audit` / `_reference_audit_status` / `_same_utc_two_walls` / `_audit_doc` / `_write_audit_expect` / `_check_audit` |
| 契约测试（累计） | **434 passed, 1 skipped**（435 项收集；M4 的 338 项 + M5 的 97 项） |
| 门 | 布局门绿（`HANDOFF-M6` 落盘后）/ 脱敏门绿 |

### 两通道实测（M5 收尾，2026-10-22）

| 通道 | 实测 |
|---|---|
| `py -3.12 -m pytest` | **434 passed, 1 skipped**，1723.25 s（28 分 43 秒） |
| `py -3.8 -m pytest` | **434 passed, 1 skipped**，3239.47 s（53 分 59 秒）；与 3.12 通道同数 |
| `bench/run.py --check`（五套件） | 退 0；分母 **7**（五版本 × 3 套件 + 2 个版本对套件）；`不一致: 0` |
| `bench/run.py --check --suite audit` | `行=8 状态=GAP/OK/OVERLAP/VERSION_CHANGED 对拍=8`；`不一致: 0` |
| fixture `--check` × 6 组 | 全 PASS（`audit/bc-scenario` 6 份 / `diff` 17 份 / `windows` 7 份 / `posix` 1 份 / `tzif` 4+13 份） |

**M5 结束时已锁住的状态**：判定顺序 `STATUS_ORDER` 是**判据的一部分**，可被就地变异咬住
（`test_mutation_reordering_lets_version_changed_steal_gap`）；`INVALID` 在**解析层**决定，
不进判定循环；`OVERLAP` 判据是"≥2 个候选"而非"恰好 2 个"；两树模式的基准恒为 **A（第一棵）**；
`report.build_report` 不读时钟，`generated_at` 由 `cli` 注入；有 `INVALID` 行时
`report` 退 **4** 优先于门禁命中的 1。

## 2. 当前事实 · 状态不变量（下一棒动手前必须知道）

1. **数值口径的唯一真相源 = `data/README.md` §四**。`plan/02`/`plan/03`/README 只引用不复制；
   任何"第二套口径"都会让 `plan/06` X2 风险成真。改口径 = 改 §四 + 改引用 + 决策记录三处。
2. **`plan/01` §1.5 的探针快照数字不得进代码常量、不得进 README 首屏、不得作断言阈值**。
   **M5 实测**（可写进 `plan/05` 的关闭说明，**不得**进代码常量或断言阈值）：
   `audit` 单 zone 的 8 行清单判定耗时 < 0.1 秒；`--daily 02:30 --year 2026` 展开 365 条
   同样 < 0.2 秒（含进程启动）。
3. **状态副本有四处**（`plan/00` 台账行 / `plan/00` 里程碑表 / `plan/05` 状态表 / `README.md` 路线图），
   布局门逐副本采集、任一不一致即红。翻转状态必须**同一次提交**内改齐四处。
   **台账"状态"列若出现 `🟡` 且同一格提到已 ✅ 的里程碑号，`LAYOUT.LEDGER` 立刻红**
   （`🟡` 本身是未完成标记）。要么写 `⬜`，要么写 ✅ + 说明，不要混。
4. **【M5 新增】退出码 5 已整项消失，且这是发布门的一部分。**
   `errors.EXIT_NOT_READY`、`errors.NotImplementedYet`、`cli._unimplemented` **全部删除**；
   `src/` 里不得再出现 `NOT_READY` / `NotImplementedYet` / `未就绪` 任一字符串
   （`test_not_ready_semantics_is_gone_from_the_package` 逐文件扫）。
   **M6 的发布门要断言 `grep -r EXIT_NOT_READY src/` 为空**，并把它写进 `plan/RELEASE-M6.md`
   的"阶段 7 覆盖对账"表（作为一条有据可查的项）。
5. **`plan/03` 与实现必须同步**：§三/§四 `[M2 已落地]`、§五 `[M3 已落地]`、§六 `[M4 已落地]`、
   **§七/§八 `[M5 已落地 2026-10-22]`（各带 8 条 / 7 条实现细节差异登记）**。M6 若要改任何
   交付面行为，必须同时改这里。
6. **`tests/test_architecture.py` 的 `ALLOWED` 是依赖方向的唯一真相源**。
   已定的依赖面：`audit` = `{errors, timeline, civil}`、`report` = `{errors}`、
   `cli` = 全部子命令 + `serialize` + `civil` + `__init__`。
   **`report` 不 import `audit` / `diff` / `windows`**：结果集一律按"字典或带 `as_dict()` 的对象"
   接收（鸭子类型）。
7. **`civil.py` 是唯一允许做日历算术的地方**，且**全整数**（测试扫 `float(` / `round(`）。
   `datetime` 只允许出现在 `tests/` 与 `data/fixtures/*/gen.py` 里，不得进 `src/`。
8. **读时钟的唯一入口是 `report.resolve_generated_at()`**（`SOURCE_DATE_EPOCH` 优先，
   否则 `time.gmtime()`，永远 UTC）。`build_report` 不读时钟——`generated_at` 由 `cli` 注入。
   `tools/` 与 `data/fixtures/*/gen.py` 不受此限（构建期工具）。
9. **`serialize.py` 是唯一写盘入口**（`src/` 内）。
10. **`.gitignore` 封了 `*.csv`**：fixture 的清单用 `.json`/`.txt` 承载
    （`audit/bc-scenario/times.txt` 就是这个原因）；真实用户清单永不入仓。
11. **`data/tzdb/` 与 `data/fixtures/` 的 `expect*.json` 必须是规范化 JSON**
    （`sort_keys` + 2 空格 + LF 尾），由 `tests/test_truth_shape.py` 断言。
    **注意**：`test_truth_shape.py` 的 `_iter_expect_files()` 只认**文件名恰好是 `expect.json`**
    的文件——`data/tzdb/pairs/*.json`（含 `*.audit.json`）与 `expect-timeline.json` /
    `expect-windows.json` 不在它的扫描范围里（各自的 gold 测试里有等价断言）。
12. **本机 `python` 是商店占位符**，一律 `py -3.12` / `py -3.8`；CI 里才是 `python`。
13. **`posix_tz` 只做语法**，不做日历算术。`diff` 判 `future_rule` 时读
    `timeline.Timeline.tail` 的 `normalized()`，**不重写规则展开**。
14. **`/time` 的两种基准**：起跳按 std 墙钟、回拨按 DST 墙钟（tzcode 语义）。
15. **四类互斥但不穷尽**：`diff.summary.unclassified` 列出"语义确有差异但四类都不成立"的 zone。
    `audit` **不消费 diff 结果**（它直接比两树的 `resolve_local` 候选），所以不受此影响。
16. **金标候选数必须出现 {0,1,2}**：timeline / windows 各有一套断言。
    diff 金标：类别必须**至少两类**。**audit 金标：`statuses` 至少三类**，且必须有
    `VERSION_CHANGED` 的真实数据锚点（Dublin 1925）+ 一条 `OK` 对照（Tokyo 无 DST）。
17. **本机无 `zic`**。`data/fixtures/tzif/source-vs-wheel/fat/` 是 `gen.py` 的规则编译器产物。
18. **跑测试不要并发**（`bench/run.py --check` 虽不写盘，但与另一通道 pytest 并发会读到
    半写金标而假红）。**M5 起全量更慢**：`audit`/`report` 本身很快，但 `test_m5_audit_gold`
    里的 5 条变异测试每条都要在假仓库里跑一遍 `--check`。
19. **`bench/run.py` 现在有五套件**（`parse` / `timeline` / `windows` / `diff` / `audit`），
    各一个金标文件：`expect.json` / `expect-timeline.json` / `expect-windows.json` /
    `pairs/<old>-<new>.json` / `pairs/<old>-<new>.audit.json`。
20. **`--suite` 的合法值集合已三度扩容**（M3 加 `windows`、M4 加 `diff`、M5 加 `audit`）。
    反例测试一律用 `no-such-suite`，**不要**拿某个真实套件名当反例。

## 3. 下一棒待办（M6 发布）

按顺序做，每步都有可跑的判据：

1. **版本号三处一致**：`src/tzaudit/__init__.py::__version__`、`pyproject.toml` 的 `version`、
   `README.md` 顶部。当前是 `0.1.0.dev0`；发版前改成 `0.1.0`（**tag 之后不得再改交付面**）。
2. **`plan/RELEASE-M6.md` 的"tag 时点"栏**（**tag 之前落盘**）：写版本、提交 sha、
   四场景命令与实测输出、断网证据、脱敏门结论、附件 sha256 的算法与预期值占位。
3. **干净环境验证**：`git archive` 出一份树 → 解包到临时目录 → 按 README 第四条"前置条件"
   逐条敲（含 `tools/fetch_tzdb.py`）→ 四场景全通。**记录每一条的输出**。
4. **断网验证**：`socket.connect` 打桩 + `netstat` 旁证；四个**子命令**（`windows` / `diff` /
   `audit` / `report`）各跑一次，确认零网络调用。
5. **脱敏门 + 提交身份**：`py -3.12 tools/check-desensitized.py` 绿；提交身份与 tagger 邮箱
   为 noreply（`git config user.email` 与 `GIT_COMMITTER_EMAIL`）。
6. **建远端 + 首推**（Q7 定案 B：M6 才建）：`gh repo create yuluo554/10-21-tzaudit --public`；
   push 后**据实补记** CI 结论（失败也照录，不抹除）；更新 `plan/05` §三 U1/U2 的关闭说明。
7. **tag + Release**：`git tag -a v0.1.0 -m "..."` → `git archive` + `gzip -9n` + `SHA256SUMS`
   → `gh release create v0.1.0 --notes-file ... <附件>`；本地留副本并核对 sha256。
8. **`plan/RELEASE-M6.md` 的"tag 后追加"栏** + **阶段 7 覆盖对账表**（逐条三态：
   实现 / 不适用 / 待首推）。其中必须有这两条：
   - `grep -r EXIT_NOT_READY src/` **为空**（M5 整项退役的发布门证据）
   - 五套件金标 `--check` 退 0
9. **状态回写 + commit**（收尾顺序见下）。

> **M6 不要做的事**：不要在 tag 之后改交付面（`src/` `pyproject.toml`）；
> 不要把"未执行 / 待首推"写成"CI 绿"；不要把 `plan/01` §1.5 的探针快照数字写进代码常量
> 或 README 首屏；不要为了"看起来完整"给 `report` 加"串跑三个子命令"的形态（见 §4 的 K37）。

## 4. 既定口径清单（K 编号；动了会打挂测试）

| K | 口径 | 打挂什么 |
|---|---|---|
| K1 | 数值口径单点 = `data/README.md` §四 | 任何复制第二份的改动 → `plan/06` X2 风险 + review 拒收 |
| K2 | 退出码：0/1/2/3/4（**5 已于 M5 消失**） | `tests/test_exit_codes.py` 全部 |
| K3 | 依赖方向：`plan/02` §一 + `tests/test_architecture.py::ALLOWED` | `test_layers_do_not_import_upwards` |
| K4 | 排序一律 UTF-8 字节序（`zoneinfo_store.byte_key`） | 双跑一致性；`--all` 输出顺序；`pairs/*.json` 的名单排序 |
| K5 | 除 `generated_at` 外零时间戳、零浮点（`src/` 内） | `test_no_network.py` 时钟扫描 + `test_report.py` 的 AST 断言 + 双跑逐字节 |
| K6 | 写盘单点 `serialize.write_*_atomic`（sort_keys/2 空格/LF/无 BOM） | `tests/test_serialize.py` + `test_truth_shape.py` |
| K7 | 金标只存输入与期望（无 `observed_*`） | `test_truth_shape.py::test_expect_files_have_no_observation_fields` |
| K8 | POSIX 偏移**西为正**，解析层翻成**东为正**的秒数 | `test_posix_tz.py::test_west_positive_is_flipped_to_east_positive` |
| K9 | `/time` 是**墙钟秒**，解析层只存 `time_sec`，不做偏移加减 | `test_posix_tz.py::test_slash_time_is_parsed_as_wall_seconds_not_offset` |
| K10 | 存在性只由 `resolve_local` 的候选个数决定；`fold` 只用于选择 | `test_timeline.py::test_exists_only_by_candidate_count_not_by_fold` |
| K11 | 四类变更判定顺序固定 `history → future → abbrev → alias`，**实现按 `CLASS_ORDER` 遍历** | `diff.CLASS_ORDER` + `test_mutation_reordering_flips_a_two_class_zone` |
| K12 | 发布里程碑固定 M6（`check-sprint-layout.py::RELEASE_MILESTONE`） | `LAYOUT.RELEASE` 分支 |
| K13 | M0 豁免 HANDOFF-M0；`HANDOFF_SECTIONS` 七节为**必需子集**（超集合法） | `LAYOUT.HANDOFFS` / `LAYOUT.NEXT_HANDOFF` |
| K14 | **主金标两棵树 = PyPI slim wheel × 2**（Q1 定案）；fat 仅作 M2 fixture | `data/tzdb/*/provenance.json` 的 `kind` 必须是 `slim` |
| K15 | **Python 底线 3.8**（Q2 定案）：禁 `dict \|`、禁 `X \| Y` 类型标注、禁 `tomllib`、禁 `str.removeprefix` | `py -3.8 -m pytest` 必须全绿；CI 矩阵 3.8+3.12 |
| K16 | **`audit --version` 只收两个目录路径**（Q4 定案），不收版本号；缺 `provenance.json` 退 3 | `cli._resolve_trees` + `test_cli_audit_version_requires_provenance`；`plan/03` §七 |
| K17 | **未接远端**（Q7 定案）：M6 首推前，DoD 只写"本地等价校验（未接远端，CI 待首推验证）" | `plan/05` §三 U1/U2；M6 补记 |
| K18 | **`is_slim` 判据在 v1 块**（决策 ⑨） | `test_slim_is_decided_by_v1_block_not_by_v2` |
| K19 | **`TzifData` 五字段 + `parse(data, zone)` 签名冻结**（决策 ⑧） | `tests/test_m1_data.py` 全部解析器用例 |
| K20 | **入仓 `NEWS` = 首版发布块，逐字保留**（含 2026b 上游笔误、2026d 弯引号） | `test_news_excerpts_pin_the_two_historical_quotes` |
| K21 | **`bench/run.py` 的判据必须能跑红**（吞错误 / 短路比对 / 金标漂移都会被测试抓） | `test_bench_actually_counts_parse_errors` / `..._detects_expect_drift` / `..._detects_timeline_expect_drift` / `..._detects_windows_expect_drift` / `test_bench_detects_diff_expect_name_drift` / **`test_bench_detects_audit_status_drift`** 等 5 组 |
| K22 | **`posix_tz` 只做语法，日历算术只在 `civil` / `timeline`** | `test_posix_tz.py` 全部用例；`ALLOWED["posix_tz"] == {"errors"}` |
| K23 | **tail 起跳按 std 墙钟、回拨按 DST 墙钟** | `test_pitfall_wall_seconds_expands_to_07z_not_02z` / `..._governs_fall_back_too` |
| K24 | **tail 正确性靠解析式求值，不靠物化段** | `test_real_trees_roundtrip_holds_for_every_sampled_zone` |
| K25 | **金标候选数必须出现 {0,1,2}** | `test_m2_timeline_gold.py::test_timeline_expect_candidates_cover_all_three_shapes` |
| K26 | **`windows` 的依赖面 = `errors` / `timeline` / `civil`** | `test_layers_do_not_import_upwards` |
| K27 | **墙钟窗口按"本地墙钟年份"归属**，扫描窗口在年份边界外留 2 天余量 | `test_windows.py::test_window_is_filed_under_its_local_wall_clock_year` |
| K28 | **窗口类型方向由 offset 差决定**（与 `is_dst` 无关，负 DST 同样成立） | `test_windows.py::test_dublin_negative_dst_direction_is_correct` |
| K29 | **候选必须逐条复核**：GAP 段 0 个候选、OVERLAP 段 2 个且 offset 不同 | `test_windows.py::test_candidate_verification_rejects_a_fake_window` |
| K30 | **`source` 走 `timeline.segment_source_at()`**，不重写"表尾那个转换点归 tail" | `plan/03` §五 落地说明第 2 条 |
| K31 | **"共有历史"右边界 = 两树表尾的较早者，且判定用严格小于** | `test_diff.py::test_mutation_history_boundary_would_break_the_tail_rule_case` |
| K32 | **`diff` 的比较用断点枚举，不抽样** | `test_real_trees_have_no_zone_with_both_criteria` + 对拍 20 项 |
| K33 | **tail 结构比较不含缩写**（只比 `std_offset`/`dst_offset`/`start`/`end`） | `test_abbr_only_is_a_class_and_its_other_classes_do_not_hold` |
| K34 | **`alias_only` 的前提是"无任何 offset/规则差异"，且 link 签名要算两侧** | `test_alias_only_does_not_absorb_rule_change` + `test_alias_only_counts_both_sides_of_the_link` |
| K35 | **四类互斥但不穷尽**：窗口排除唯一历史差异时进 `summary.unclassified` | `test_diff_reports_unclassified_rather_than_forcing_a_class` |
| K36 | **`--window` 只收窄第 1 类，第 2 类不受限** | `test_diff_window_only_narrows_history_class` + `test_diff_expect_window_changed_is_subset_of_all_history` |
| K37 | **【M5 新增】`audit` 的判定顺序固定 `STATUS_ORDER`，且按它遍历** | `audit.STATUS_ORDER` + `test_mutation_reordering_lets_version_changed_steal_gap` |
| K38 | **【M5 新增】`INVALID` 在解析层决定，不进判定循环**；坏行不静默跳过（进结果 + 计数 + 退 4） | `test_invalid_is_decided_before_gap` + `test_invalid_rows_are_not_silently_dropped` |
| K39 | **【M5 新增】`VERSION_CHANGED` 只在两棵树时可能成立**；判据 = 两侧候选 **UTC 集合不同** | `test_version_changed_requires_two_trees` + `test_audit_single_version_never_reports_version_changed` |
| K40 | **【M5 新增】`--daily` 缺 `year` 退 2，不默认当前年**（不读时钟） | `test_daily_requires_year_and_does_not_default_to_now` |
| K41 | **【M5 新增】`report` 不读时钟**：`generated_at` 由调用方注入，唯一读时钟入口是 `resolve_generated_at` | `test_report_module_does_not_read_the_clock_outside_its_single_point` |
| K42 | **【M5 新增】`--fail-on` 只收 `gap`/`overlap`/`history`**，非法值退 2，不静默忽略 | `test_parse_fail_on_rejects_unknown` + `test_cli_report_unknown_fail_on_returns_2` |
| K43 | **【M5 新增】有 `INVALID` 行时 `report` 退 4，优先于门禁命中的 1** | `test_invalid_rows_dominate_the_gate` |
| K44 | **【M5 新增】`report` 的依赖面只有 `errors`**（结果集按鸭子类型接收） | `ALLOWED["report"] == {"errors"}` |
| K45 | **【M5 新增】`report` 子命令只收 `--from <json>`**；"串跑三个子命令"的形态首期不做 | `cli._report_inputs`；`plan/03` §八 落地说明第 5 条 |

## 5. 本机环境坑（只写实测过的；带日期）

| 坑 | 实测（2026-10-21 / 10-22） | 处置 |
|---|---|---|
| `python` 是商店占位符 | 直接跑会弹商店 | 一律 `py`（`py -3.12` / `py -3.8`） |
| 两条解释器通道 | `py -0p` → 3.8.8-64 与 3.12-64 | 语法必须兼容 3.8 |
| `gh` 已登录 | 账号 `yuluo554`，scopes 含 `repo` | M6 建仓/Release 直接用 `gh` |
| 仓库尚无 remote | `git remote -v` 为空 | 未推送期间 DoD 只能写"本地等价校验，CI 待首推验证" |
| 布局门输出经管道时 `$?` 是管道的 | `py ... \| tail` → `rc=0` 即使有 FAIL | 取退出码**不要接管道**：`py ... > /dev/null; echo $?` |
| **zone 判据必须是 TZif 魔数** | 首版按文件名过滤，把 `plan/*.md` 数成 zone | `zoneinfo_store.looks_like_tzif()` |
| **变异脚本的"还原"要按文件存原始快照** | V9 首版在同一文件上存了两份快照 → 还原被覆盖 | 每份文件只在**动任何字节之前**采集一次快照 |
| **变异靶子要瞄门真正扫的那一列** | V6 首版改「关闭里程碑」列，门扫的是「缺口」列 | 先读门的列定位逻辑 |
| `datetime` 不支持负年份 | civil 的负年份/0 年不能与 `datetime` 交叉证伪 | 用性质测试覆盖 |
| Hinnant 的 C 截断除法 ≠ Python 向下取整 | 首版照抄 → 负年份往返失败 | Python 里直接 `y // 400` |
| **TZif v2 的两个头都带版本字节** | 合成 fixture 首版把 v1 头写成 `\0` → 解析器判"footer 不是以换行开头" | 两头都是 `'2'` |
| **`abbrind` 指向的是字符串表字节偏移，不是类型序号** | 合成 fixture 写 `abbrind=4` → 取到空串 | 第二个缩写从 5 开始 |
| **`pytest` 的 `tmp_path` 造"假仓库"必须跑副本** | 首版用真 `bench/run.py` + `cwd=fake` → 它按 `__file__` 推 ROOT | 复制脚本到假仓库再跑 |
| **`bench/run.py` 认版本看 `provenance.json`** | 假仓库只建目录 → `入仓版本: （无）` | 假仓库必须写 `provenance.json` |
| **上游 `2026b` 的 NEWS 头写成 `Release 2026a`** | 实际下载包原文如此 | 原样入仓；测试对 2026b 豁免 |
| **`retrieved` 取本地日历日不是 UTC 日** | 首版用 `gmtime()` → 记成 2026-10-20 | 改 `localtime()` |
| **v1 块的转换时刻是 32 位有符号** | 构造 fat fixture 写 2037 年 → `struct.error` | v1 块只放 `[-2^31, 2^31-1]` 内的点 |
| **本机无 `zic`** | `shutil.which('zic')` → `None` | fat 树只能自建 |
| **IANA 源码的 `RULES` 字段可以是固定 save** | Dublin 的 `1:00` 不是 ruleset 名 | 不是已知 ruleset 就按偏移解析 |
| **IANA `UNTIL` 的时间基准是"当时生效的偏移"** | Vancouver `2026 Nov 1 2:00` 用 std 偏移换算 → 差 1 小时 | 迭代到不动点 |
| **IANA 的 `A/B` 缩写是"左标准、右 DST"** | Dublin `IST/GMT` 配负 DST | `_abbr` 按 `is_dst` 选边 |
| **`2:45s` 这类 `s` 后缀不能丢** | Chatham 规则全是 `2:45s` | `_rule_wall_epoch` 原样带出 `kind` |
| **规则年份区间不得借出端点外的年** | 首版用 `from - 1` 起算 | `range(max(from, lo), min(to, hi) + 1)` |
| **`pytest` 全量很慢** | M5 实测：3.12 = **1723.25 s（28 分 43 秒）**、3.8 = **3239.47 s（54 分）**（435 项收集 / 434 passed + 1 skipped） | **必须串行**；改代码后先跑受影响文件 |
| **【M5 新增】跑测试期间不得切提交 / stash / 还原工作树** | 3.8 全量跑到一半时 `git stash` + `git checkout <旧提交>` → 子进程读到被换掉的源文件，报出 `TypeError: 'range_iterator' object is not callable`、`AttributeError: 'int' object has no attribute 'days_from_civil'` 与 stdout 全空的退出码 `3221225477`（7 条假红） | 红了的**第一件事看错误类型**：多处"内建函数被遮蔽"不是代码 bug，是文件在换；等测试跑完再动 git |
| **台账状态格混 `🟡` + ✅ 里程碑号会红** | `LAYOUT.LEDGER` 把 `🟡` 当未完成标记 | 见 §2 第 3 条 |
| **合成 fixture 的"表尾偏移"必须与 tail 在表尾处的偏移一致** | 表说 EST、tail 说 EDT → 假窗口 | 先验证树自洽再拿它做反例 |
| **`bench/run.py` 的 `--suite` 取值集合已三度变化** | M3 加 `windows`、M4 加 `diff`、M5 加 `audit` → 旧反例测试假红 | 反例一律用 `no-such-suite` |
| **子进程调 CLI 的测试不能依赖"包已安装"** | 3.8 通道没装 `tzaudit` | 子进程设 `PYTHONPATH=<repo>/src` |
| **`diff` 的参照对拍不能用均匀时刻网格** | 首版用 2000–2030 网格 → 真实历史差异落在 1925/1979/1992，**一个都碰不到** → 对拍恒绿（假门） | 用**参照实现自己的段起点**做断点枚举 |
| **"共有历史"的边界必须严格小于表尾** | 用 `<=` → 表尾那个点（归 tail）被算进历史 → `Zone/TailRule` 错判 | `item.utc >= hist_end` 归第 2 类 |
| **顺序变异拿真实数据当锚点是恒绿的** | 真实对上 Dublin/Tehran 只有历史差异 → 调换顺序**没有任何影响** | 专门造 `Zone/HistAndFuture` 当锚点 |
| **fixture 里"零变更"的 zone 不能与 link 组同字节** | 首版 `Identical` 与 `LinkA` 同字节 → 被 `links()` 认成别名 | 每个 zone 的 blob 必须唯一（除刻意构造的 link 对） |
| **tail 串必须是合法 POSIX TZ** | 首版写 `ABT1`（只有名字缺偏移）→ `PosixTzError` | `AAA-1` 这种 `std offset` 两段形式 |
| **`alias_only` 只看 `links.get(zone)` 会漏"别名集合变空"** | 旧树 `LinkB→LinkA`，新树 `LinkB` 独立 | `_link_signature` 同时返回 `(as_alias_of, aliases_of_me)` |
| **"退化判据"的变异靶子必须是实现，不是金标** | 首版把金标改成单类 → 先被"集合不相等"报掉 | 在假仓库里变异 `src/tzaudit/diff.py` |
| **【M5 新增】数源码里 `time.gmtime(` 出现几次会假红** | 注释里提到它也被数进去（首版断言 `== 2` 实测得 3） | 用 **AST** 定位"哪个函数里出现了 `gmtime`" |
| **【M5 新增】`.gitignore` 封了 `*.csv`** | 清单写成 `times.csv` 会**静默不入仓** | fixture 清单用 `.txt`（`bc-scenario/times.txt`） |
| **【M5 新增】`OVERLAP` 的判据不能写 `== 2`** | 极旧 LMT 段理论上可有 3 个候选；写死 2 会把它们报成 OK | 按 `>= 2` 判 |
| **【M5 新增】`_self_check` 要在 `build()` 里跑，不能只在 `__main__` 里跑** | `--check` 的重生成目录走 `build()`，不经过 `__main__` | 自检写在 `build()` 末尾，失败抛异常 |
| **【M5 新增】`--daily` 的等价清单 id 前缀** | 直接比 `id` 会因 `daily-` 前缀全红 | 断言"除 `id` 前缀外全等" |
| **【M5 新增】有 `INVALID` 行时门禁结论不可信** | 结果集本身不完整，"是否命中"没有意义 | `report_exit_code` 让 4 优先于 1 |

### M5 变异验证记录（10 组；就地变异 → 目标变红 → 还原复绿）

| # | 变异（改哪一处） | 期望命中的判据 | 实测 |
|---|---|---|---|
| M5-V1 | `audit.STATUS_ORDER` 把 `VERSION_CHANGED` 提到 `GAP` 之前 | `test_mutation_reordering_lets_version_changed_steal_gap`（`bc-gap` 翻转） | ✅ 变红（VERSION_CHANGED → 还原复绿） |
| M5-V2 | `data/tzdb/pairs/2026a-2026e.audit.json` 的某条 `status` 改掉 | `test_bench_detects_audit_status_drift` | ✅ 变红（`audit.rows` 不相等） |
| M5-V3 | 同一金标删掉一条 `rows` | `test_bench_detects_audit_row_dropped` | ✅ 变红 |
| M5-V4 | 同一金标把一条候选 UTC 改掉 | `test_bench_detects_audit_candidate_utc_drift` | ✅ 变红 |
| M5-V5 | 同一金标把 `single_version` 的一条写成 `VERSION_CHANGED` | `test_bench_detects_audit_single_version_leak` | ✅ 变红 |
| M5-V6 | 假仓库里变异 `audit._judge` → 非 INVALID 一律 OK | `test_bench_detects_degenerate_all_ok_audit` | ✅ 变红（报"判据可能退化"） |
| M5-V7 | `report.resolve_generated_at` 在 `build_report` 里被直接调用（绕过注入） | `test_report_module_does_not_read_the_clock_outside_its_single_point`（AST） | ✅ 变红 |
| M5-V8 | `report.parse_fail_on` 允许第四种值（默默忽略） | `test_parse_fail_on_rejects_unknown` | ✅ 变红 |
| M5-V9 | `audit.parse_times` 把空行静默跳过 | `test_invalid_rows_are_not_silently_dropped`（行数对不上） | ✅ 变红 |
| M5-V10 | `audit.expand_daily` 把缺 `year` 当"当前年" | `test_daily_requires_year_and_does_not_default_to_now` | ✅ 变红（若允许读时钟，`test_no_network` 的时钟扫描也会红） |

> **M5 收尾实测的两处坑（新增）**：
>
> 1. **加套件会打挂"分母断言"，但错的不是断言而是魔法数**。`test_m1_data.py` 原写
>    `5 + len(DIFF_PAIRS)`，M5 加 `audit` 套件后分母从 6 变 7 → 假红。修法不是改数字，
>    而是把"按版本对出金标的套件"登记进 `_pair_counts()`（`diff` / `audit` 各一行），
>    让分母由**套件清单**算出。下一次加套件只需加一行登记。
> 2. **"偶发 `0xC0000005` / 莫名其妙的 `TypeError`" 的真凶是"测试跑着的时候我在改工作树"**。
>    首轮 3.8 全量出现过 7 条红（含 `TypeError: 'range_iterator' object is not callable`、
>    `AttributeError: 'int' object has no attribute 'days_from_civil'`、以及 stdout/stderr
>    全空的退出码 3221225477）。当时我为了"验证 M4 提交是否也崩"执行了
>    `git stash` + `git checkout be96bb9`，**而 3.8 全量还在跑**——子进程读到了被换掉的源文件。
>    这正是 `plan/HANDOFF-M5.md` §2 第 18 条"跑测试不要并发"的**加强版**：
>    **跑测试期间也不得切换提交 / stash / 还原工作树**。干净重跑后两通道全绿。
>    教训：红了的**第一件事是看错误类型**——"两个互不相干的模块同时报内建函数被遮蔽"，
>    那不是代码 bug，是**文件在被换**。

> **M5 的极性教训（新增）**：
>
> 1. **判据的位置决定变异靶子的位置**。要验"顺序是判据的一部分"，靶子必须是**顺序常量**；
>    要验"bench 的退化判据"，靶子必须是**实现**；要验"库里不读时钟"，靶子必须是**AST 扫描**
>    （源码里出现字面量 `time.gmtime(` 不构成证据——注释里也会有）。
> 2. **"数源码里出现了几次"是脆弱的断言**。`source.count(...)` 会把注释、文档串、别名都数进去；
>    一律改成 AST 定位"哪个函数拥有它"。
> 3. **fixture 的自检要写在 `build()` 里**，不能只写在 `__main__` 里——`--check` 的重生成
>    目录走 `build()`，不经过 `__main__`，否则"生成器被改坏"这一层断言在 `--check` 下等于没跑。

## 6. DoD 逐项 checklist（M6 发布）

- [ ] 版本号三处一致（`__init__` / `pyproject` / `README` 顶部），且为 `0.1.0`
- [ ] `plan/RELEASE-M6.md` **tag 前**落盘（"tag 时点"栏齐）
- [ ] 干净环境：`git archive` 解包树按 README 逐条敲通四场景（含前置 `fetch_tzdb`）
- [ ] 断网跑通四个子命令（`socket.connect` 打桩 + `netstat` 旁证）
- [ ] 脱敏门绿（盘符 / 用户路径 / 用户名 / 回环代理）
- [ ] 提交身份与 tagger 邮箱为 noreply
- [ ] 建远端 `yuluo554/10-21-tzaudit`（公开）+ 首推；CI 结论**据实补记**（失败也照录）
- [ ] tag `v0.1.0` + Release 附件（`git archive` + `gzip -9n` + `SHA256SUMS`）
- [ ] 附件 sha256 与本地副本一致；`gh release download` 回下载 `cmp` 通过
- [ ] 附件解包树 vs `git archive` 树：共有文件逐字节相等 + 两个"仅一侧"集合逐项确认
- [ ] tag 后提交集合 ⊆ 非交付面（`plan/` `tests/` `tools/` `docs/` `README` `AGENTS`）
- [ ] `plan/RELEASE-M6.md` "tag 后追加"栏 + **阶段 7 覆盖对账表**（逐条：实现 / 不适用 / 待首推）
- [ ] 对账表里含 **`grep -r EXIT_NOT_READY src/` 为空**（M5 整项退役的发布门证据）
- [ ] 对账表里含 **五套件 `bench/run.py --check` 退 0**
- [ ] `plan/05` §三 U1/U2 改写为"已关闭 + 证据"或"待首推后补记"
- [ ] `py -3.12 -m pytest` 全绿
- [ ] `py -3.8 -m pytest` 全绿
- [ ] 布局门 + 脱敏门全绿
- [ ] 四处状态副本同步翻 M6 ✅（发布完成后）
- [ ] `README.md` 状态行只写"版本 + 能力"，**不写**"发布到哪一步"

> 未推送期间**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。
> 首推之后**据实**补记：CI 失败也照录，不抹除、不写成"通过"。

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
py -3.12 -m pytest tests/test_audit.py
py -3.12 -m pytest tests/test_report.py
py -3.12 -m pytest tests/test_m5_audit_gold.py
py -3.12 -m pytest tests/test_exit_codes.py

# 数据（干净 clone 先跑这一条）
py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e
py -3.12 tools/fetch_tzdb.py --check
py -3.12 tools/fetch_tzdb.py --materialize

# 金标（五套件）
py -3.12 bench/run.py --check
py -3.12 bench/run.py --check --suite audit
py -3.12 bench/run.py --regen --suite audit

# fixture 重建（六组）
py -3.12 data/fixtures/audit/bc-scenario/gen.py --check
py -3.12 data/fixtures/diff/gen.py --check
py -3.12 data/fixtures/windows/gen.py --check
py -3.12 data/fixtures/tzif/slim-vs-fat/gen.py --check
py -3.12 data/fixtures/tzif/source-vs-wheel/gen.py --check
py -3.12 data/fixtures/posix/three-rule-forms/gen.py --check

# 安装与 CLI 冒烟（五条子命令都要能 --help）
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m tzaudit --help
py -3.12 -m tzaudit version --zoneinfo data/_downloads/slim/2026e --json
py -3.12 -m tzaudit windows --all --year 2026 --zoneinfo data/_downloads/slim/2026e --json
py -3.12 -m tzaudit diff --old data/_downloads/slim/2026a --new data/_downloads/slim/2026e
py -3.12 -m tzaudit audit --daily 02:30 --year 2026 --zone America/New_York \
    --zoneinfo data/_downloads/slim/2026e
py -3.12 -m tzaudit report --from result.json --format md --fail-on gap,overlap,history

# 发布（M6）
git archive --format=tar v0.1.0 | gzip -9n > 10-21-tzaudit-v0.1.0.tar.gz
sha256sum 10-21-tzaudit-v0.1.0.tar.gz > SHA256SUMS
gh repo create yuluo554/10-21-tzaudit --public --source=. --push
gh release create v0.1.0 --notes-file ... 10-21-tzaudit-v0.1.0.tar.gz SHA256SUMS

# 退出码 5 的发布门证据（必须为空）
grep -r EXIT_NOT_READY src/ || echo "已整项退役"

# 取退出码（别接管道）
py -3.12 tools/check-sprint-layout.py > /dev/null; echo "layout rc=$?"
```

### 收尾顺序（硬约束，不得裁量）

```
DoD 逐项验证 → 四处状态副本回写 → 写 plan/RELEASE-M6.md（tag 前栏）→ git add -A → commit
→ tag v0.1.0 → Release 附件 → plan/RELEASE-M6.md（tag 后栏 + 覆盖对账）→ 再次 commit
```

未推送期间 DoD 里**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。
