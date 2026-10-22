# HANDOFF-M5 · 清单审计 `audit` + 报告门禁 `report`

> 上一棒：**M4（版本差异分类）✅ 2026-10-21**
> 本棒目标：**M5 清单审计与报告门禁** —— `audit.py` 与 `report.py` 落地，让
> `tzaudit audit --times <file> --zone <name>` 逐条判定墙钟状态，
> `tzaudit report` 输出带三字段报告头的 Markdown/JSON 并支持 `--fail-on` 门禁，
> **两条子命令同时退役退出码 5**（退役后 `EXIT_NOT_READY` **整项删除**）。
> 启动命令（用户侧，绝对路径不入库）：`/goal 读取 "<项目根>\plan\HANDOFF-M5.md" 继续完成任务`
> **第一动作**：`py -3.12 tools/check-sprint-layout.py`（必须全绿；红了先修布局）。

---

## 1. 当前进度 + 证据

**已完成（M0 + M1 + M2 + M3 + M4）**

### M4 DoD 逐项实测（16/16；证据可复跑）

| # | DoD 项 | 实测证据 |
|---|---|---|
| 1 | `diff.diff_trees` 落地，`Change` 字段与 `plan/03` §六 一致 | `Change.__slots__` = `{zone, class_, window, before, after, evidence, note}`（7 字段，逐个对上）；`test_change_fields_match_plan_section_six` |
| 2 | 四类判定**顺序固定**（`CLASS_ORDER`），同一 zone 只输出一条 | `CLASS_ORDER = (history_reinterpreted, future_rule, abbreviation_only, alias_only)`；`_classify` **按 `CLASS_ORDER` 遍历**；`test_one_record_per_zone_at_most` + `test_diff_expect_one_record_per_zone` |
| 3 | `history_reinterpreted`：窗口内任一 UTC 时刻两树 `to_local` 不同 → 成立 | **断点枚举**（两树段起点并集，非抽样）→ 精确覆盖；真实树实测 Bogota `@1992-05-02` |
| 4 | `future_rule`：表相同但 tail 不同 → **必须**落这里 | Vancouver 真实树 `future_rule` + `evidence=tail`，`before=tail=PST8PDT,M3.2.0,M11.1.0` / `after=tail=MST7`；`test_vancouver_is_not_alias_only` |
| 5 | `abbreviation_only`：转换点 `utc/offset` 全同，仅 `abbr` 不同 | `Zone/AbbrOnly`：`abbr=AAA → abbr=BBB`，`evidence=abbr` |
| 6 | `alias_only`：仅 link 集合变化（sha256 判据），**不得**吸收规则变化 | `Zone/LinkB` 旧树是 link、新树改规则 → `future_rule`；`Zone/LinkA` 别名集合变空 → `alias_only`；`_link_signature` 两侧都算 |
| 7 | 判定顺序变异测试：调换顺序 → 必红 | 把 `future_rule` 提前 → `Zone/HistAndFuture` 从 `history_reinterpreted` 翻成 `future_rule`；还原复绿（`test_mutation_reordering_flips_a_two_class_zone`） |
| 8 | Dublin 1925 / Tehran 1979 → `history_reinterpreted`（真实数据） | Dublin `@1925-09-20 02:00Z`、Tehran `@1979-05-25 20:30Z`，均 `evidence=table` |
| 9 | `data/fixtures/diff/` 落地，`gen.py --check` 逐字节一致 | `gen.py --check` → **PASS（17 份产物逐字节一致）**；七种形态齐 |
| 10 | `bench/run.py --check --suite diff` 退 0；金标无 `observed_*`；名单**集合相等** | rc=0；`data/tzdb/pairs/2026a-2026e.json`；`all_history_changed` 24 条 / `window_changed` 15 条，集合相等断言；4 条漂移变异测试全红 |
| 11 | `py -3.12 -m pytest` 全绿（含新增 M4 测试） | **338 passed, 1 skipped**（339 项收集；1878.87 s ≈ 31 分钟） |
| 12 | `py -3.8 -m pytest` 全绿（底线解释器） | **338 passed, 1 skipped**（2302.04 s ≈ 38 分钟）；与 3.12 通道同数 |
| 13 | 布局门 + 脱敏门全绿 | 布局门 10 条判据全 PASS（`HANDOFF-M5` 落盘后）；脱敏门全绿 |
| 14 | `EXIT_NOT_READY` 只退役 `diff` 一条（`audit`/`report` 仍退 5） | `test_not_ready_exit_code_is_5` 只剩 2 条 argv；新增 `test_diff_is_no_longer_not_ready` |
| 15 | 四处状态副本同步翻 M4 ✅ | `plan/00` 台账 + `plan/00` 里程碑表 + `plan/05` 状态表 + `README.md` 路线图，M4 行全含 ✅ |
| 16 | `plan/HANDOFF-M5.md` 已落盘（七节齐） | 本文件；七节关键词逐个命中 |

### 交付物清单

| 交付 | 证据 |
|---|---|
| **`diff.py`（M4 核心）** | `src/tzaudit/diff.py`：`CLASS_ORDER` / `Change` / `DiffResult` / `diff_trees` / `parse_window` + 断点枚举 + link 双侧签名 |
| **`diff` 子命令** | `cli.py::_run_diff` + `_render_diff`（`--old` / `--new` / `--window` / `--zone` / `--json`） |
| **M4 测试** | `tests/test_diff.py`（35 项）：契约 / fixture 七形态 / 真实数据 / 2 组顺序与边界变异 / CLI 5 项 |
| **M4 金标测试** | `tests/test_m4_diff_gold.py`（16 项）：形态 9 项 / 复算入口 3 项 / 4 条漂移与退化变异 |
| **diff fixture** | `data/fixtures/diff/{gen.py, expect.json, README.md, old/, new/}`（17 份产物，七种形态） |
| **diff 金标** | `data/tzdb/pairs/2026a-2026e.json`（`window_changed` / `all_history_changed` / `changes[]` / `unclassified`） |
| **bench 第四套件** | `bench/run.py`：`SUITES` 加 `diff`、`diff_stats` / `cross_check_diff` / `_reference_classify_diff` / `_diff_doc` / `_write_diff_expect` / `_check_diff` |
| 契约测试（累计） | `338 passed, 1 skipped`（339 项收集；M3 的 287 项 + M4 的 51 项） |
| 门 | 布局门绿 / 脱敏门绿 |

### 两通道实测（M4 收尾，2026-10-21）

| 通道 | 实测 |
|---|---|
| `py -3.12 -m pytest` | **338 passed, 1 skipped**，1878.87 s（31 分 19 秒） |
| `py -3.8 -m pytest` | **338 passed, 1 skipped**，2302.04 s（38 分 22 秒） |
| `bench/run.py --check`（四套件） | 退 0；分母 6（五版本 × 3 套件 + 1 个版本对）；`不一致: 0` |
| `bench/run.py --check --suite diff` | 退 0；`比较=598 变更=24 窗口内=15 对拍=20` |
| fixture `--check` × 5 组 | 全 PASS（`diff` 17 份 / `windows` 7 份 / `posix` 1 份 / `tzif` 4+13 份） |

**M4 结束时已锁住的状态**：`diff_trees` 的四类判定**按 `CLASS_ORDER` 遍历**
（顺序是判据的一部分，可被变异测试锚住）；"共有历史"的右边界 = 两树表尾的**较早者**，
且判定用**严格小于**（表尾那个点归 tail）；`alias_only` 在进入前会再跑一次
**不看 window** 的全区间扫描，确认"真的没有任何 offset/规则差异"；
四类互斥但**不穷尽**——窗口排除唯一历史差异时，zone 进 `summary.unclassified` 如实报告。
`audit` / `report` 仍是 `raise NotImplementedYet`（M5 落地）。

## 2. 当前事实 · 状态不变量（下一棒动手前必须知道）

1. **数值口径的唯一真相源 = `data/README.md` §四**。`plan/02`/`plan/03`/README 只引用不复制；
   任何"第二套口径"都会让 `plan/06` X2 风险成真。改口径 = 改 §四 + 改引用 + 决策记录三处。
2. **`plan/01` §1.5 的探针快照数字不得进代码常量、不得进 README 首屏、不得作断言阈值**。
   **M4 实测**（可写进 `plan/05` 的关闭说明，**不得**进代码常量或断言阈值）：
   2026a→2026e 全历史 **24 条**变更（history 11 / future 9 / alias 4 / abbrev 0），
   `--window 2000-2030` 下 **15 条**；598 个 zone 全量比较耗时约 **0.5 秒**。
3. **状态副本有四处**（`plan/00` 台账行 / `plan/00` 里程碑表 / `plan/05` 状态表 / `README.md` 路线图），
   布局门逐副本采集、任一不一致即红。翻转状态必须**同一次提交**内改齐四处。
   **台账"状态"列若出现 `🟡` 且同一格提到已 ✅ 的里程碑号，`LAYOUT.LEDGER` 立刻红**
   （`🟡` 本身是未完成标记）。要么写 `⬜`，要么写 ✅ + 说明，不要混。
4. **退出码 5 是临时的，且是"逐条退役"**。`diff` 已在 M4 退役（`cli` 不再分派、
   `test_exit_codes.py` 删掉那一行、`plan/03` §九 与 `data/README.md` §4.4 同步）。
   **M5 要同时退役 `audit` 与 `report` 两条** —— 两条都落地后，
   `EXIT_NOT_READY` **整项删除**：删常量 `errors.EXIT_NOT_READY`、删 `NotImplementedYet` 类、
   删 `cli._unimplemented`、删 `test_exit_codes.py::test_not_ready_exit_code_is_5` 整个函数、
   改 `plan/03` §九 与 `data/README.md` §4.4 的"临时语义"整段。
   `data/README.md` §4.4 已写明"M6 之前必须全部退役，M6 的发布门断言它已从 `src/` 消失"。
5. **`plan/03` 与实现必须同步**：§三/§四 `[M2 已落地]`、§五 `[M3 已落地]`、
   §六 `[M4 已落地]`（含 7 条实现细节差异登记）。M5 落地后同样改 §七 / §八。
6. **`tests/test_architecture.py` 的 `ALLOWED` 是依赖方向的唯一真相源**。
   已定的依赖面：`audit` = `{errors, timeline, diff, civil}`、`report` = `{errors}`。
   **`report` 若要读 JSON 结果集，只能从 `cli` 或经参数传入**（`report` 不许 import `audit`/`diff`，
   否则 M5 要改 `ALLOWED` 并在 `plan/02` §一 登记）。
7. **`civil.py` 是唯一允许做日历算术的地方**，且**全整数**（测试扫 `float(` / `round(`）。
   `datetime` 只允许出现在 `tests/` 与 `data/fixtures/*/gen.py` 里，不得进 `src/`。
8. **`generated_at` 是唯一允许读时钟的地方**，落在 `report.build_report`（M5）。
   其余模块一律不读时钟。`tools/` 与 `data/fixtures/*/gen.py` 不受此限（构建期工具）。
   **`report` 的 `generated_at` 必须能由调用方注入**（测试要固定值），
   不能写成"函数内直接 `datetime.now()` 无处替换"。
9. **`serialize.py` 是唯一写盘入口**（`src/` 内）。
10. **`.gitignore` 封了 `*.csv`**：fixture 的清单用 `.json`/`.txt` 承载；真实用户清单永不入仓。
11. **`data/tzdb/` 与 `data/fixtures/` 的 `expect*.json` 必须是规范化 JSON**
    （`sort_keys` + 2 空格 + LF 尾），由 `tests/test_truth_shape.py` 断言。
    **注意**：`test_truth_shape.py` 的 `_iter_expect_files()` 只认**文件名恰好是 `expect.json`**
    的文件——`data/tzdb/pairs/*.json` 与 `expect-timeline.json` / `expect-windows.json`
    不在它的扫描范围里（各自的 gold 测试里有等价断言）。
12. **本机 `python` 是商店占位符**，一律 `py -3.12` / `py -3.8`；CI 里才是 `python`。
13. **`posix_tz` 只做语法**，不做日历算术。`diff` 判 `future_rule` 时读
    `timeline.Timeline.tail` 的 `normalized()`，**不重写规则展开**。
14. **`/time` 的两种基准**：起跳按 std 墙钟、回拨按 DST 墙钟（tzcode 语义）。
15. **四类互斥但不穷尽**（M4 新增）：`summary.unclassified` 列出"语义确有差异但四类都不成立"
    的 zone。M5 的 `audit` 若要消费 diff 结果，**不得**把 `unclassified` 当"无变更"。
16. **金标候选数必须出现 {0,1,2}**：timeline / windows 各有一套断言。
    **diff 金标同理**：类别必须**至少两类**——`--regen` 缺类拒绝写出、`--check` 报"判据可能退化"。
17. **本机无 `zic`**。`data/fixtures/tzif/source-vs-wheel/fat/` 是 `gen.py` 的规则编译器产物。
18. **跑测试不要并发**（`bench/run.py --check` 虽不写盘，但与另一通道 pytest 并发会读到
   半写金标而假红）。
19. **`bench/run.py` 现在有四套件**（`parse` / `timeline` / `windows` / `diff`），
    各一个金标文件：`expect.json` / `expect-timeline.json` / `expect-windows.json` /
    `pairs/<old>-<new>.json`。M5 若要第五套件（如 `audit`）：
    加 `SUITES` 常量 + `_check_<suite>` + `_<suite>_doc` + `_write_*`，并**同时**给金标加漂移变异测试。
20. **`--suite` 的合法值集合已两度扩容**（M3 加 `windows`、M4 加 `diff`）。
    反例测试一律用 `no-such-suite`，**不要**拿某个真实套件名当反例。

## 3. 下一棒待办（M5 清单审计 + 报告门禁）

按顺序做，每步都有可跑的判据：

1. **实现 `src/tzaudit/audit.py`**
   - `audit_rows(rows, zone, versions=(A,B)|None) -> AuditResult`；
     `Row(id, local, status, utc_candidates, note, invalid_reason)`（`plan/03` §七）。
   - 判定顺序固定：`INVALID`（解析失败）→ `GAP` → `OVERLAP` → `VERSION_CHANGED` → `OK`。
   - **行序保持输入序**；同一时刻多候选按 UTC 升序。
   - `VERSION_CHANGED` 只在 `--version A,B` 给定时可能成立（两版本 `resolve_local` 的 UTC 集合不同）。
   - `INVALID` 行**不静默跳过**：进结果 + 计数；有 `INVALID` 时整体退 4（`data/README.md` §4.4）。
   - `--daily HH:MM` 展开为 `year` 范围内每天一条；**缺年即退 2，不默认当前年**（不读时钟）。
   - `--version A,B` 的 A/B 是**目录路径**（K16/Q4），必须存在且带 `provenance.json`，否则退 3。
2. **实现 `src/tzaudit/report.py`**
   - `build_report(results, data_version, zones_covered, generated_at) -> (md, doc)`；
     `gate_exit_code(doc, fail_on: set[str]) -> int`（`plan/03` §八）。
   - **报告头三字段**（`data/README.md` §4.5）：`data_version` / `zones_covered` / `generated_at`，
     缺任一 → 退 3（`ReportIncomplete`）。`generated_at` **由调用方注入**（测试固定值）。
   - `--fail-on` 枚举**固定三值** `gap` / `overlap` / `history`（可逗号组合），**不存在第四种**。
   - `--json` 与 Markdown 的退出码必须相同。
3. **接线 `cli.py`**：`audit` / `report` 分派落地 → **同一提交里**退役**两条**退出码 5
   （删 `cli._unimplemented` 整个函数、删 `NotImplementedYet` 类与 `errors.EXIT_NOT_READY` 常量、
   删 `test_exit_codes.py::test_not_ready_exit_code_is_5` 整个函数、
   改 `plan/03` §九 与 `data/README.md` §4.4）。**退役后 `src/` 里不得再有"未就绪"语义。**
   新增两条防复活断言（仿 `test_diff_is_no_longer_not_ready`）。
4. **落地 `tests/test_audit.py`**（`plan/03` §七 测试点 5 条）：
   - 四类各一条：`GAP`（`2026-03-08 02:30` NY）、`OVERLAP`（`2026-11-01 01:30` NY）、
     `VERSION_CHANGED`（BC 场景）、`OK`。
   - BC 场景：同一 UTC 在 2026a / 2026b 下两个不同墙钟（`data/fixtures/audit/bc-scenario/`）。
   - `--daily 02:30` 与等价清单输出逐字节一致（除 `id` 前缀）。
   - CSV 坏行（缺列、时间非法、空行）→ `INVALID` + 计数 + 退 4，且**其余行照常判定**。
   - 输出行序 == 输入行序（打乱输入后断言）。
5. **落地 `tests/test_report.py`**（`plan/03` §八 测试点）：
   - 头三字段缺一 → 退 3。
   - `--fail-on` 四组退出码（无命中 / gap / overlap / history）。
   - `--json` 与 Markdown 退出码相同。
   - 双跑逐字节一致（`generated_at` 注入同一固定值）。
6. **落地 `data/fixtures/audit/bc-scenario/`**：生成器 + `expect.json` + `README.md`
   （`plan/04` §三 硬纪律：`--check` 两层断言、禁 random / 禁时钟 / 写盘归一）。
   注入：同一 UTC 在两版本下映射到两个不同墙钟（相差一小时）。
7. **`bench/run.py` 加第五套件 `audit`**（可选，但**若加就必须同时加漂移变异测试**）：
   金标存"清单逐条判定"的期望（`status` + `utc_candidates`）。
   **仍然只存输入与期望**，不得出现 `observed_*`。
8. **状态回写 + 写 `plan/HANDOFF-M6.md` + commit**（收尾顺序见下）。
   **注意**：M5 之后 `EXIT_NOT_READY` 整项消失，`plan/HANDOFF-M6.md` 的 §2 必须记明这一点，
   并提示 M6 的发布门要断言 `grep -r EXIT_NOT_READY src/` 为空。

> **M5 不要做的事**：不要碰 `windows` / `diff` 的接口签名；
> 不要在 `report` 里读时钟（`generated_at` 必须注入）；
> 不要让 `report` import `audit` / `diff`（会改依赖方向）；
> 不要把 `--daily` 的缺省年取成"当前年"（本项目不读时钟）。

## 4. 既定口径清单（K 编号；动了会打挂测试）

| K | 口径 | 打挂什么 |
|---|---|---|
| K1 | 数值口径单点 = `data/README.md` §四 | 任何复制第二份的改动 → `plan/06` X2 风险 + review 拒收 |
| K2 | 退出码：0/1/2/3/4/5（**5 在 M5 后消失**） | `tests/test_exit_codes.py` 全部 14 项 |
| K3 | 依赖方向：`plan/02` §一 + `tests/test_architecture.py::ALLOWED` | `test_layers_do_not_import_upwards` |
| K4 | 排序一律 UTF-8 字节序（`zoneinfo_store.byte_key`） | 双跑一致性；`--all` 输出顺序；`pairs/*.json` 的名单排序 |
| K5 | 除 `generated_at` 外零时间戳、零浮点（`src/` 内） | `test_no_network.py` 时钟扫描 + 双跑逐字节 |
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
| K16 | **`audit --version` 只收两个目录路径**（Q4 定案），不收版本号 | `cli.py` 的 `--version` 帮助文本；`plan/03` §七 |
| K17 | **未接远端**（Q7 定案）：DoD 只写"本地等价校验（未接远端，CI 待首推验证）" | `plan/05` §三 U1/U2；M6 补记 |
| K18 | **`is_slim` 判据在 v1 块**（决策 ⑨） | `test_slim_is_decided_by_v1_block_not_by_v2` |
| K19 | **`TzifData` 五字段 + `parse(data, zone)` 签名冻结**（决策 ⑧） | `tests/test_m1_data.py` 全部解析器用例 |
| K20 | **入仓 `NEWS` = 首版发布块，逐字保留**（含 2026b 上游笔误、2026d 弯引号） | `test_news_excerpts_pin_the_two_historical_quotes` |
| K21 | **`bench/run.py` 的判据必须能跑红**（吞错误 / 短路比对 / 金标漂移都会被测试抓） | `test_bench_actually_counts_parse_errors` / `..._detects_expect_drift` / `..._detects_timeline_expect_drift` / `..._detects_windows_expect_drift` / **`test_bench_detects_diff_expect_name_drift`** 等 4 条 |
| K22 | **`posix_tz` 只做语法，日历算术只在 `civil` / `timeline`** | `test_posix_tz.py` 全部用例；`ALLOWED["posix_tz"] == {"errors"}` |
| K23 | **tail 起跳按 std 墙钟、回拨按 DST 墙钟** | `test_pitfall_wall_seconds_expands_to_07z_not_02z` / `..._governs_fall_back_too` |
| K24 | **tail 正确性靠解析式求值，不靠物化段** | `test_real_trees_roundtrip_holds_for_every_sampled_zone` |
| K25 | **金标候选数必须出现 {0,1,2}** | `test_m2_timeline_gold.py::test_timeline_expect_candidates_cover_all_three_shapes` |
| K26 | **`windows` 的依赖面 = `errors` / `timeline` / `civil`** | `test_layers_do_not_import_upwards` |
| K27 | **墙钟窗口按"本地墙钟年份"归属**，扫描窗口在年份边界外留 2 天余量 | `test_windows.py::test_window_is_filed_under_its_local_wall_clock_year` |
| K28 | **窗口类型方向由 offset 差决定**（与 `is_dst` 无关，负 DST 同样成立） | `test_windows.py::test_dublin_negative_dst_direction_is_correct` |
| K29 | **候选必须逐条复核**：GAP 段 0 个候选、OVERLAP 段 2 个且 offset 不同 | `test_windows.py::test_candidate_verification_rejects_a_fake_window` |
| K30 | **`source` 走 `timeline.segment_source_at()`**，不重写"表尾那个转换点归 tail" | `plan/03` §五 落地说明第 2 条 |
| K31 | **【M4 新增】"共有历史"右边界 = 两树表尾的较早者，且判定用严格小于**（表尾那个点归 tail） | `test_diff.py::test_mutation_history_boundary_would_break_the_tail_rule_case`（放宽边界 → `Zone/TailRule` 翻成 history） |
| K32 | **【M4 新增】`diff` 的比较用断点枚举，不抽样**（两树 state 是分段常量） | `test_real_trees_have_no_zone_with_both_criteria` + 对拍 20 项 |
| K33 | **【M4 新增】tail 结构比较不含缩写**（只比 `std_offset`/`dst_offset`/`start`/`end`） | `test_abbr_only_is_a_class_and_its_other_classes_do_not_hold` |
| K34 | **【M4 新增】`alias_only` 的前提是"无任何 offset/规则差异"，且 link 签名要算两侧** | `test_alias_only_does_not_absorb_rule_change` + `test_alias_only_counts_both_sides_of_the_link` |
| K35 | **【M4 新增】四类互斥但不穷尽**：窗口排除唯一历史差异时进 `summary.unclassified` | `test_diff_reports_unclassified_rather_than_forcing_a_class` |
| K36 | **【M4 新增】`--window` 只收窄第 1 类，第 2 类不受限** | `test_diff_window_only_narrows_history_class` + `test_diff_expect_window_changed_is_subset_of_all_history` |

## 5. 本机环境坑（只写实测过的；带日期）

| 坑 | 实测（2026-10-21） | 处置 |
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
| **`pytest` 全量很慢** | M4 实测：3.12 = **1878.87 s（31 分）**、3.8 = **2302.04 s（38 分）**（339 项） | **必须串行**；改代码后先跑受影响文件 |
| **台账状态格混 `🟡` + ✅ 里程碑号会红** | `LAYOUT.LEDGER` 把 `🟡` 当未完成标记 | 见 §2 第 3 条 |
| **合成 fixture 的"表尾偏移"必须与 tail 在表尾处的偏移一致** | 表说 EST、tail 说 EDT → 假窗口 | 先验证树自洽再拿它做反例 |
| **`bench/run.py` 的 `--suite` 取值集合已三度变化** | M3 加 `windows`、M4 加 `diff` → 旧反例测试假红 | 反例一律用 `no-such-suite` |
| **子进程调 CLI 的测试不能依赖"包已安装"** | 3.8 通道没装 `tzaudit` | 子进程设 `PYTHONPATH=<repo>/src` |
| **【M4 新增】`diff` 的参照对拍不能用均匀时刻网格** | 首版用 2000–2030 网格 → 真实历史差异落在 1925/1979/1992，**一个都碰不到** → 对拍恒绿（假门） | 用**参照实现自己的段起点**做断点枚举 |
| **【M4 新增】"共有历史"的边界必须严格小于表尾** | 用 `<=` → 表尾那个点（归 tail）被算进历史 → `Zone/TailRule` 错判成 `history_reinterpreted` | `item.utc >= hist_end` 归第 2 类 |
| **【M4 新增】顺序变异拿真实数据当锚点是恒绿的** | 真实对上 Dublin/Tehran 只有历史差异、Casablanca/Vancouver 只有表外差异 → 调换顺序**没有任何影响** | 专门造 `Zone/HistAndFuture`（两类同时成立）当锚点 |
| **【M4 新增】fixture 里"零变更"的 zone 不能与 link 组同字节** | 首版 `Identical` 与 `LinkA` 同字节 → 被 `links()` 认成别名 → "零变更"期望被"link 关系变化"顶掉 | 每个 zone 的 blob 必须唯一（除刻意构造的 link 对） |
| **【M4 新增】tail 串必须是合法 POSIX TZ** | 首版写 `ABT1`（只有名字缺偏移）→ `PosixTzError`，fixture 生成期就炸 | `AAA-1` 这种 `std offset` 两段形式 |
| **【M4 新增】`alias_only` 只看 `links.get(zone)` 会漏"别名集合变空"** | 旧树 `LinkB→LinkA`，新树 `LinkB` 独立 → `LinkA` 两侧 `links.get()` 都是 `None` | `_link_signature` 同时返回 `(as_alias_of, aliases_of_me)` |
| **【M4 新增】"退化判据"的变异靶子必须是实现，不是金标** | 首版把金标改成单类 → 先被"集合不相等"报掉，测不到退化判据 | 在假仓库里变异 `src/tzaudit/diff.py`（追加遮蔽定义） |

### M4 变异验证记录（6 组；就地变异 → 目标变红 → 还原复绿）

| # | 变异（改哪一处） | 期望命中的判据 | 实测 |
|---|---|---|---|
| M4-V1 | 调换 `diff.CLASS_ORDER`：`future_rule` 提到 `history_reinterpreted` 之前 | `test_mutation_reordering_flips_a_two_class_zone`（`Zone/HistAndFuture` 翻转） | ✅ 变红（future → 还原复绿） |
| M4-V2 | `diff._history_end` 返回 `(1 << 62)`（共有历史右边界推到无穷远） | `test_mutation_history_boundary_would_break_the_tail_rule_case` | ✅ 变红（`Zone/TailRule` 落 history） |
| M4-V3 | `data/tzdb/pairs/2026a-2026e.json` 的 `all_history_changed` 删一个 zone | `test_bench_detects_diff_expect_name_drift` | ✅ 变红（`--check` 退非 0，报"不相等"） |
| M4-V4 | 同一金标把一条 `changes[].class` 改掉 | `test_bench_detects_diff_expect_class_drift` | ✅ 变红 |
| M4-V5 | 同一金标把 `zones_compared` +1 | `test_bench_detects_diff_expect_count_drift` | ✅ 变红 |
| M4-V6 | 假仓库里变异 `diff.diff_trees` → 只产 `future_rule` | `test_bench_detects_degenerate_single_class_diff` | ✅ 变红（报"判据可能退化"） |

> **M4 的极性教训（新增）**：
>
> 1. **"判据的锚点必须选在该判据唯一会失效的地方"**——M3 已说过一次，M4 又踩中一次：
>    顺序变异拿 Dublin 当锚点是**恒绿**的（Dublin 根本没有第 2 类候选）。
>    造一个"两类同时成立"的 fixture zone 才咬得住。
> 2. **对拍的抽样范围必须覆盖差异本身**。用 2000–2030 的均匀网格对拍 1925 年的差异，
>    等于没对拍。凡"抽样对拍"，先问"被抽的区间能不能碰到差异"。
> 3. **变异靶子要对准判据所在的那一层**。要验"bench 的退化判据"，靶子必须是
>    **实现**（改 `src/`）；改金标会先被别的判据（集合相等）拦掉。

## 6. DoD 逐项 checklist（M5）

- [ ] `audit.audit_rows` 落地，`Row` 字段与 `plan/03` §七 一致
- [ ] 判定顺序固定 `INVALID → GAP → OVERLAP → VERSION_CHANGED → OK`
- [ ] 行序保持输入序；多候选按 UTC 升序
- [ ] `INVALID` 不静默跳过：进结果 + 计数 + 整体退 4，其余行照常判定
- [ ] `--daily HH:MM` 与等价清单输出一致；缺 `year` 退 2（不读时钟）
- [ ] `--version A,B` 只收目录路径；缺 `provenance.json` 退 3（K16）
- [ ] `report.build_report` 落地，报告头三字段齐；缺一退 3
- [ ] `generated_at` **由调用方注入**，`report` 内不读时钟
- [ ] `--fail-on` 三值枚举（gap/overlap/history），四组退出码测试
- [ ] `--json` 与 Markdown 退出码相同
- [ ] `data/fixtures/audit/bc-scenario/` 落地，`gen.py --check` 逐字节一致
- [ ] `tests/test_audit.py` + `tests/test_report.py` 落地（`plan/03` §七/§八 测试点全过）
- [ ] **`EXIT_NOT_READY` 整项退役**（常量 + 类 + `_unimplemented` + 测试函数 + 两处文档）
- [ ] 新增两条"防复活"断言（`audit` / `report` 不再退 5）
- [ ] `py -3.12 -m pytest` 全绿（含新增 M5 测试）
- [ ] `py -3.8 -m pytest` 全绿（底线解释器）
- [ ] 布局门 + 脱敏门全绿
- [ ] 四处状态副本同步翻 M5 ✅
- [ ] `plan/HANDOFF-M6.md` 已落盘（七节齐，且记明 `EXIT_NOT_READY` 已整项消失）

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
py -3.12 -m pytest tests/test_audit.py -q
py -3.12 -m pytest tests/test_report.py -q
py -3.12 -m pytest tests/test_diff.py -q
py -3.12 -m pytest tests/test_exit_codes.py -q

# 数据（干净 clone 先跑这一条）
py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e
py -3.12 tools/fetch_tzdb.py --check
py -3.12 tools/fetch_tzdb.py --materialize

# 金标
py -3.12 bench/run.py --check
py -3.12 bench/run.py --check --suite diff
py -3.12 bench/run.py --regen --suite diff

# fixture 重建
py -3.12 data/fixtures/diff/gen.py --check
py -3.12 data/fixtures/windows/gen.py --check
py -3.12 data/fixtures/tzif/slim-vs-fat/gen.py --check
py -3.12 data/fixtures/tzif/source-vs-wheel/gen.py --check
py -3.12 data/fixtures/posix/three-rule-forms/gen.py --check

# 安装与 CLI 冒烟
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m tzaudit --help
py -3.12 -m tzaudit diff --old data/_downloads/slim/2026a --new data/_downloads/slim/2026e
py -3.12 -m tzaudit diff --old data/_downloads/slim/2026a --new data/_downloads/slim/2026e --json
py -3.12 -m tzaudit diff --old data/_downloads/slim/2026a --new data/_downloads/slim/2026e --window 2000-2030
py -3.12 -m tzaudit windows --all --year 2026 --zoneinfo data/_downloads/slim/2026e --json

# 取退出码（别接管道）
py -3.12 tools/check-sprint-layout.py > /dev/null; echo "layout rc=$?"
```

### 收尾顺序（硬约束，不得裁量）

```
DoD 逐项验证 → 四处状态副本回写 → 写 plan/HANDOFF-M6.md → git add -A → commit →（有远端则 push 等 CI）
```

未推送期间 DoD 里**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。
