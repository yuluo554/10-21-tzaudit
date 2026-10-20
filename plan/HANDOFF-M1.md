# HANDOFF-M1 · 数据先行

> 上一棒：**M0（出题定稿 + 方法论装订 + 可运行骨架）✅ 2026-10-21**
> 本棒目标：**M1 数据先行** —— 五份真实 IANA 版本入仓 + 金标复算入口可跑。
> 启动命令（用户侧，绝对路径不入库）：`/goal 读取 "<项目根>\plan\HANDOFF-M1.md" 继续完成任务`
> **第一动作**：`py -3.12 tools/check-sprint-layout.py`（必须全绿；红了先修布局）。

---

## 1. 当前进度 + 证据

**已完成（M0）**

| 交付 | 证据 |
|---|---|
| 计划套件 `plan/00–06` | 布局门 `LAYOUT.FILES 10 份齐备` / `LAYOUT.SECTIONS 8 份小节齐备` |
| 方法论装订（`AGENTS.md` + 布局门 + `plan/00` 装订行） | `LAYOUT.BINDING_HEAD PASS`；`LAYOUT.DOC_TOOLS 3 个脚本全部在位` |
| 布局门 10 组变异自证 | `py -3.12 tools/mutate-layout-gate.py` → **10/10 组按预期**（含 V8 反向对照） |
| 可安装骨架 | `py -3.12 -m pip install -e ".[dev]"` → `tzaudit --version` / `--help` 退 0 |
| 契约测试 | `py -3.12 -m pytest -q` → **70 passed**（3.8 通道同样 70 passed）：civil 全量 73414 天对拍 32 项 / 架构分层 2 / 退出码 13 / 零网络 4 / 序列化 7 / 金标形态 3 / zoneinfo 树 9 |
| CLI 冒烟 | `tzaudit --version` → `tzaudit 0.1.0.dev0`；`tzaudit version --zoneinfo <tree> --json` 退 0；未实现子命令退 **5** 且 stderr 说明 |
| `bench/run.py` 分母自证 | 无金标时退 **3** 并打印"缺件: data/_downloads 不存在"，不静默 0 项通过 |

**M1 结束时应有的状态**：`tools/fetch_tzdb.py` 能真下载五版本；`data/tzdb/{2026a..2026e}/provenance.json`
带真实 sha256 与实测 `zones`；`bench/run.py --check` 能解析全量树并断言 `parse_errors == 0`。

## 2. 当前事实 · 状态不变量（下一棒动手前必须知道）

1. **数值口径的唯一真相源 = `data/README.md` §四**。`plan/02`/`plan/03`/README 只引用不复制；
   任何"第二套口径"都会让 `plan/06` X2 风险成真。改口径 = 改 §四 + 改引用 + 决策记录三处。
2. **`plan/01` §1.5 的探针快照数字（598 / 11 / 20 / 201 / 192 / 580）不得进代码常量、不得进 README 首屏、
   不得作断言阈值**。唯一例外：M1 的"零解析错误"与"对拍一致率"是**判据正确性**门槛，且分母以末态回填。
3. **状态副本有四处**（`plan/00` 台账行 / `plan/00` 里程碑表 / `plan/05` 状态表 / `README.md` 路线图），
   布局门逐副本采集、任一不一致即红。翻转状态必须**同一次提交**内改齐四处。
4. **退出码 5（未就绪）是临时的**：`windows`/`diff`/`audit`/`report` 每落地一个，必须在同一提交里
   删掉 `errors.NotImplementedYet` 对应引用、删 `tests/test_exit_codes.py::test_not_ready_exit_code_is_5`
   里那一行、改 `plan/03` §九与 `data/README.md` §4.4。四处少一处 = 幽灵语义复活。
5. **`plan/03` 与实现必须同步**：骨架里 `tzif.parse` / `posix_tz.parse` / `timeline.*` / `windows.*` /
   `diff.*` / `audit.*` 都是 `raise NotImplementedYet`。M2 起逐个替换，**签名不要改**——`tests/test_architecture.py`
   的 `ALLOWED` 表按模块声明依赖面，新增模块必须先加表（门会报"新模块未声明"）。
6. **`tests/test_architecture.py` 的 `ALLOWED` 是依赖方向的唯一真相源**。`report` 只能 import `errors`；
   `timeline` 才能 import `tzif` / `posix_tz` / `zoneinfo_store`。反向 import 会立刻红。
7. **`civil.py` 是唯一允许做日历算术的地方**，且**全整数**（测试扫 `float(` / `round(`）。
   `datetime` 只允许出现在 `tests/` 里做交叉证伪，不得进 `src/`（`test_no_network.py` 的时钟扫描会抓 `datetime.now`，
   但不会抓 `datetime.date`——**新增 `datetime` 用法要自觉**）。
8. **`generated_at` 是唯一允许读时钟的地方**，落在 `report.build_report`（M5）。其余模块一律不读时钟。
   测试冻结用 `SOURCE_DATE_EPOCH`。
9. **`serialize.py` 是唯一写盘入口**。禁止在子命令里直接 `open(...,"w")` 写产物——否则 CRLF/BOM/sort_keys 漂移。
10. **`.gitignore` 封了 `*.csv`**：fixture 的清单用 `.json`/`.txt` 承载；真实用户清单永不入仓（隐私红线）。
11. **`data/tzdb/` 与 `data/fixtures/` 的 `expect.json` 必须是规范化 JSON**（`sort_keys` + 2 空格 + LF 尾），
    由 `tests/test_truth_shape.py` 断言；不是规范化就红。
12. **本机 `python` 是商店占位符**，一律 `py -3.12` / `py -3.8`；CI 里才是 `python`。

## 3. 下一棒待办（M1 数据先行）

按顺序做，每步都有可跑的判据：

1. **实现 `tools/fetch_tzdb.py`**（当前退 5）
   - `--versions 2026a,2026b,2026c,2026d,2026e`：下载 `https://data.iana.org/time-zones/releases/tzdata<ver>.tar.gz`
     到 `data/_downloads/`，逐文件重试（≥3 次）+ 超时 + sha256 记录。
   - 解包**只取必要文本**：`NEWS`、`leap-seconds.list`、`version`；写 `data/tzdb/<ver>/provenance.json`
     （字段见 `plan/04` §1.2）。
   - `--check`：不联网，只校验已下载件 sha256 与 provenance 一致。
   - **失败即退 3**（环境不满足），不吞异常、不"跳过版本"。
2. **入仓五份 `provenance.json` + `NEWS` 摘录**
   - `zones` 字段填**实测值**（用 `ZoneinfoStore(slim 树).zones()` 数），不是题面 598。
   - 2026e 的 NEWS 里爱尔兰那句、2026d 的伊朗那句要**逐字保留**（`plan/01` §1.4 引用它们）。
3. **`bench/run.py --regen` 骨架 → 真复算**
   - 读树 → `ZoneinfoStore.zones()` → 逐 zone `tzif.parse`（M2 前可用"只数 zone 数"的降级形态，
     但**必须把"解析尚未实现"显式写进输出**，不许假装跑过）。
   - 生成 `data/tzdb/<ver>/expect.json`（只含输入 + 期望）。
4. **跑通三条命令并留输出**
   - `py -3.12 tools/fetch_tzdb.py --check`
   - `py -3.12 bench/run.py --check`（分母 > 0，退出 0）
   - 干净 clone（无 `data/_downloads`）跑 `--check` → **必须退 3 并点名缺失版本**
5. **README 补"前置条件"一节**（`plan/04` §1.1 已写要求），并验证"干净 clone 按 README 能跑通 fetch"。
6. **状态回写 + 写 `plan/HANDOFF-M2.md` + commit**（收尾顺序见下）。
7. 若 Q1/Q2/Q4 决策已由用户拍板，按答复调整 `plan/03` §一 / `plan/04` §一 的实现口径。

## 4. 既定口径清单（K 编号；动了会打挂测试）

| K | 口径 | 打挂什么 |
|---|---|---|
| K1 | 数值口径单点 = `data/README.md` §四 | 任何复制第二份的改动 → `plan/06` X2 风险 + review 拒收 |
| K2 | 退出码：0/1/2/3/4/5（5 为临时） | `tests/test_exit_codes.py` 全部 11 项 |
| K3 | 依赖方向：`plan/02` §一 + `tests/test_architecture.py::ALLOWED` | `test_layers_do_not_import_upwards` |
| K4 | 排序一律 UTF-8 字节序（`zoneinfo_store.byte_key`） | 双跑一致性；`--all` 输出顺序 |
| K5 | 除 `generated_at` 外零时间戳、零浮点 | `test_no_network.py` 时钟扫描 + 双跑逐字节 |
| K6 | 写盘单点 `serialize.write_*_atomic`（sort_keys/2 空格/LF/无 BOM） | `tests/test_serialize.py` + `test_truth_shape.py` |
| K7 | 金标只存输入与期望（无 `observed_*`） | `test_truth_shape.py::test_expect_files_have_no_observation_fields` |
| K8 | POSIX 偏移**西为正**，解析层翻成**东为正**的秒数 | `plan/03` §三 反例单测（M2） |
| K9 | `/time` 是**墙钟秒**，解析层只存 `time_sec`，不做偏移加减 | `plan/03` §三 测试点 3（M2） |
| K10 | 存在性只由 `resolve_local` 的候选个数决定；`fold` 只用于选择 | `plan/03` §四 + Vancouver 反例（M3） |
| K11 | 四类变更判定顺序固定 `history → future → abbr → alias` | `diff.CLASS_ORDER`（已是常量） |
| K12 | 发布里程碑固定 M6（`check-sprint-layout.py::RELEASE_MILESTONE`） | `LAYOUT.RELEASE` 分支 |
| K13 | M0 豁免 HANDOFF-M0；`HANDOFF_SECTIONS` 七节为**必需子集**（超集合法） | `LAYOUT.HANDOFFS` / `LAYOUT.NEXT_HANDOFF` |

## 5. 本机环境坑（只写实测过的；带日期）

| 坑 | 实测（2026-10-21） | 处置 |
|---|---|---|
| `python` 是商店占位符 | 直接跑会弹商店 | 一律 `py`（`py -3.12` / `py -3.8`） |
| 两条解释器通道 | `py -0p` → 3.8.8-64 与 3.12-64；pytest 7.4.4 / 8.4.2 | 语法必须兼容 3.8（不能用 `:=` 之外的 3.9+ 特性，如 `dict \|`） |
| `curl` 可用、IANA 可达 | `curl https://data.iana.org/time-zones/tzdb/version` → `200`，body = `2026e` | 下载走 `urllib`/`curl` 均可；**记住 CLI 运行期不许联网**，只有 `tools/` 可以 |
| `gh` 已登录 | `gh auth status` → 账号 `yuluo554`，scopes 含 `repo` | M6 建仓/Release 直接用 `gh` |
| 仓库尚无 remote | `git remote -v` 为空 | 未推送期间 DoD 只能写"本地等价校验，CI 待首推验证" |
| `git log` 中文在 Git Bash 里可能显示乱码 | 仅显示问题，hash 与 `git status` 可信 | 验收中文文件走 `py -3.12 -X utf8` 读，不用 `sed`/`grep` 肉眼判 |
| 布局门输出经管道时 `$?` 是管道的 | `py ... \| tail` → `rc=0` 即使有 FAIL | 取退出码**不要接管道**：`py ... > /dev/null; echo $?` |
| **zone 判据必须是 TZif 魔数，不是文件名** | `tzaudit version --zoneinfo .` 首版报 **27 个 zone**（把 `plan/*.md`、`README`、`NEWS` 数成了 zone） | 已修：`zoneinfo_store.looks_like_tzif()` 读前 4 字节；回归 `tests/test_zoneinfo_store.py::test_text_files_are_not_counted_as_zones` |
| **变异脚本的"还原"要按文件存一份原始快照** | V9 首版在同一文件上存了两份快照（第二份是改后内容）→ 还原被覆盖 → "还原后未复绿" | 每份文件只在**动任何字节之前**采集一次快照 |
| **变异靶子要瞄门真正扫的那一列** | V6 首版改「关闭里程碑」列，门扫的是「缺口」列 → 门没红（靶子瞄错，不是假门） | 先读门的列定位逻辑，再决定改哪一格 |
| `datetime` 不支持负年份 | civil 的负年份/0 年不能与 `datetime` 交叉证伪 | 用性质测试（往返 + 逐日单调）覆盖，见 `test_civil.py::test_negative_years_via_arithmetic_properties` |
| Hinnant 算法的 C 截断除法 ≠ Python 向下取整 | 首版照抄 `(y if y>=0 else y-399)//400` → 负年份往返失败 | Python 里直接 `y // 400`（向下取整天然正确） |

### M0 变异验证记录（10 组；`py -3.12 tools/mutate-layout-gate.py` → 10/10 按预期）

在临时副本上执行（不污染工作树）。每组做四件事：改坏 → 断言门 rc=1 且 FAIL 里出现**预期判据 ID**
（防"恰好别处红了"也算通过）→ 还原 → 断言复绿。脚本对每次替换做三连断言（marker 存在 / 已变 / 还原字节一致）。

| # | 变异 | 期望命中的判据 |
|---|---|---|
| V1 | 删 `AGENTS.md` | `LAYOUT.FILES` |
| V2 | 删 `plan/03-模块详设.md` | `LAYOUT.FILES` |
| V3 | 删 `plan/00` 顶部装订行（整行移除，不留残句） | `LAYOUT.BINDING_HEAD` |
| V4 | 把 `plan/05` 里 M0 的 ✅ 改成 ⬜（与其余三处不一致） | `LAYOUT.STATUS` |
| V5 | 删 `plan/HANDOFF-M1.md`（下一棒交接单） | `LAYOUT.NEXT_HANDOFF` |
| V6 | 在 `plan/06` 缺口表的某行写 "M0" | `LAYOUT.GAPS` |
| V7 | 把 `plan/00` 台账里某条 ✅ 行改成 `⬜ 待 M0` | `LAYOUT.LEDGER` |
| V8 | 把 `plan/00` 台账某行改成 `⬜ 待 M6`（M6 未完成）→ 应**绿**（反向对照：未完成里程碑不算违规） | `LAYOUT.LEDGER` 保持 PASS |
| V9 | 把 `plan/00` 里程碑表里 M6 改成 ✅ 但不建 `plan/RELEASE-M6.md` | `LAYOUT.RELEASE` |
| V10 | 在 `plan/02` 里新增一行引用一个不存在的 `tools/` + 脚本名（形如 `tools/` + `check-nothing.py`） | `LAYOUT.DOC_TOOLS` |

> **V10 自身踩过一次坑（已修正）**：最初把示例写成完整的 `tools/` + 脚本名字面路径，结果**本表自己**
> 被 `LAYOUT.DOC_TOOLS` 的扫描面抓成"文档点名但不存在的工具"→ 门变红。这正是 skill 的
> "门读人写文档时，为读者写的样例行会被当成真值登记"条。处置 = **文档侧改写**（不在表里写可匹配的
> 路径形态），而不是放宽判据——放宽就少了一条真防线。

> **V8 是反向对照**（不是"多一个绿"）：它证明 `LAYOUT.LEDGER` 不会把"待 M6"误判成违规——
> 只说"未完成标记 + 已 ✅ 里程碑号"才红。没有这条，"台账判据是不是在无脑全红"无从判断。

## 6. DoD 逐项 checklist（M1）

- [ ] `tools/fetch_tzdb.py` 能真下载五版本并写 provenance（`--check` 可离线复核）
- [ ] `data/tzdb/{2026a..2026e}/provenance.json` 齐，字段含 `version/kind/source_url/sha256/retrieved/zones`
- [ ] 五版本 `NEWS` 摘录入仓，2026e 爱尔兰 / 2026d 伊朗两句逐字存在
- [ ] `bench/run.py --check` 退 0，且**打印分母 > 0**
- [ ] 干净 clone（无 `data/_downloads`）跑 `--check` → 退 3 并点名缺件
- [ ] README「前置条件」一节落地，且按 README 能跑通
- [ ] `py -3.12 -m pytest -q` 全绿（含新增 M1 测试）
- [ ] `py -3.8 -m pytest -q` 全绿（底线解释器）
- [ ] 布局门 + 脱敏门全绿
- [ ] 四处状态副本同步翻 M1 ✅
- [ ] `plan/HANDOFF-M2.md` 已落盘（七节齐）

## 7. 关键命令速查

```bash
# 门
py -3.12 tools/check-sprint-layout.py            # 布局门
py -3.12 tools/check-desensitized.py             # 脱敏门

# 测试（两个通道都跑）
py -3.12 -m pytest -q
py -3.8  -m pytest -q

# 安装与 CLI 冒烟
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m tzaudit --help
py -3.12 -m tzaudit --version
py -3.12 -m tzaudit version --zoneinfo <tree> --json

# 数据（M1）
py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e
py -3.12 tools/fetch_tzdb.py --check
py -3.12 bench/run.py --check
py -3.12 bench/run.py --check --suite parse

# 取退出码（别接管道）
py -3.12 tools/check-sprint-layout.py > /dev/null; echo "layout rc=$?"
```

### 收尾顺序（硬约束，不得裁量）

```
DoD 逐项验证 → 四处状态副本回写 → 写 plan/HANDOFF-M2.md → git add -A → commit →（有远端则 push 等 CI）
```

未推送期间 DoD 里**不许写"CI 绿"**，只写"本地等价校验（未接远端，CI 待首推验证）"。
