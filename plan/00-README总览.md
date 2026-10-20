# 00 · README 总览 — 10-21-tzaudit（时区数据版本漂移审计）

> 方法论：`ai-tool-project-sprint`（装订 2026-10-21）｜布局门：`py -3.12 tools/check-sprint-layout.py`｜续接对话第一件事 = 跑它

- **性质**：不参赛项目题 · 发布 GitHub **公开仓库** · 署名 yuluo554
- **定位宣言**："竞品按小时采样 UTC 偏移，只能说'这个时区会错'。我们说三件它做不到的事：**哪个本地墙钟区间根本不存在、哪个出现两次、哪些历史时间戳的 UTC 解释被改写了**。把'时区数据升级'从'祈祷没人踩坑'变成一张可 diff 的清单。"
- **交付形态**：**纯本地 Python CLI**（运行时零网络；tzdata 版本包由用户提供，`--zoneinfo` / `--version` 指向本地目录）。唯一形态，不设备选。
- **发布**：GitHub 公开仓库，v0.1.0（**tag + Release 附产物 + 发布留档**三件套）。
- **检索窗口**：代理实际检索窗口 **2026-10-19T18:35Z–18:48Z**；tzdata 事实来自实际下载的 IANA 发布包（`/tzdb/version` = **2026e**）。
- **状态**：出题定稿（阶段 3）+ 方法论装订与可运行骨架（阶段 0 第零步 + 骨架四件套）。开发从 M1（数据先行）开工。

## 文档索引表

| 文档 | 内容 | 状态 |
|---|---|---|
| `plan/00-README总览.md` | 本文档：索引 / 决策记录 / 弃选项 / 承诺-证据台账 / 提交材料实物表 / 里程碑 | ✅ v1 |
| `plan/01-题目文档.md` | 十段式题目定稿（定位宣言、竞品盲区实测、需求原话、IANA NEWS 原文、实测快照、技术坑、五模块、提交材料、评分、含金量锚点、边界与非目标、招牌动词表） | ✅ v1 |
| `data/README.md` | 依据查证记录（三态 + 检索窗口 + 不可达/限流如实说明）/ 数据源可获取性 / 合成数据纪律 / 数值口径（唯一权威） | ✅ v1 |
| `.gitignore` | Python 标准模板 + tzdata 下载包不入仓（`*.tar.gz`）+ 基准产物目录 | ✅ v1 |
| `plan/02-架构与技术选型.md` | 分层架构（tzif / posix / timeline / 四子命令 / 报告）、依赖方向、确定性纪律、选型与弃选 | ✅ v1（M0） |
| `plan/03-模块详设.md` | 五个子命令接口、数据结构、判定顺序、失败路径、测试点 | ✅ v1（M0） |
| `plan/04-数据计划.md` | 五版本金标口径、fixture 生成器确定性纪律、批量模式规模基线、数据升级流程 | ✅ v1（M0） |
| `plan/05-里程碑与发布.md` | 每里程碑 DoD、已知未验证项、环境事实、风险预案、发布流程 | ✅ v1（M0） |
| `plan/06-交付对标与决策.md` | 题面 §二/§三逐条落位、缺口表、待定决策表、发布前检查清单 | ✅ v1（M0） |
| `plan/HANDOFF-M1.md` | M0 收尾交接单（七节）：M1 待办 / K 口径 / 环境坑 / DoD / 命令速查 | ✅ v1（M0） |
| `plan/RELEASE-M6.md` | 发布留档（tag 时点事实 / tag 后追加事实分栏） | ⬜ 待 M6 |

> 索引状态列随里程碑同步翻转；不得在一处标 ✅ 而在另一处标 ⬜。

## 决策记录表

> 本表同时登记已定案决策与**弃选项**（含弃选理由），后续里程碑不再重复论证。
> **前六条是本题的产品地基，不得在后续文档中被改弱。**

| 日期 | 决策 | 结论与理由 |
|---|---|---|
| 2026-10-20 | **① 最大风险：`prithsk/tzdrift`（0★，2026-10-18 创建，检索前一天）** | 它 7KB、单次提交，但 **README 质量高**（直接引用 Cal.com 真实 open issue 并做了线上 API 核对）。**细分正在被主动认领**。它的形态是 `out[n] = [int((start + timedelta(hours=h)).astimezone(z).utcoffset()) for h in range(0, hours, step)]`——按小时采样 UTC 偏移。因此本题的 **README 第一屏必须打出差异**：*"它告诉你哪个时区会错；我们告诉你哪个墙钟区间不存在、哪些历史时间戳被改写。"* 不得以"更准/更快/更多 zone"作为差异，只能是**功能空间不同**。 |
| 2026-10-20 | **② 三个自修正的技术坑会原样出现在实现里，不许"后来再修"** | ① **POSIX TZ 偏移是西为正**（`EST5` = UTC−5）；② 规则时间 `M3.2.0/2` 里的 `/2` 是**墙钟秒**，不能当偏移去减；③ **`fold=0 ≠ fold=1` 在 gap 里也成立**，单用它判 overlap 会在 gap 上误报（Vancouver 实测踩中）。所以 M2 必须**同时**给两套判据：不存在 ⟺ `roundtrip(local) != local`；二义 ⟺ `roundtrip(local) == local` 且 fold 两值 offset 不同。这三条写进 `plan/03` 的测试点，且每条各配一个反例单测。 |
| 2026-10-20 | **③ slim 格式导致 580/598 zone 依赖 POSIX tail，只 diff 迁移表必漏 Vancouver** | 实测 2026.1 的 Vancouver tail 是 `PST8PDT,M3.2.0,M11.1.0`，2026.5 是 `MST7`——**表里迁移数都是 0，但语义完全不同**。因此 M3 必须在"表相同"之后**再做一次 tail 语义比对**，并把 Vancouver 定为 `future_rule` 的基准用例（`evidence=tail`）。任何"只比转换表"的实现在这一条上会直接失败。 |
| 2026-10-20 | **④ tzdata 事实必须从实际下载的发布包算，不能凭记忆** | 本次没有出现"未取到官方原文"的坑（与 APFS 那次不同），但纪律不变：版本内容（`NEWS` 原文、转换点、tail 字符串）一律来自**实际下载**的 `tzdata<ver>.tar.gz` 或 PyPI wheel；仓库里只入库**解包后的必要文本 + 金标 JSON**，`*.tar.gz` 不入仓（`.gitignore` 已封）。引用时带版本号与来源路径，`data/README.md` §一逐条登记三态。 |
| 2026-10-20 | **⑤ 定位只打"竞品盲区中的三件事"，禁写"空白/首创"** | 三件事：**墙钟窗口（不存在 / 出现两次）**、**历史重解释**、**变更四分类**。措辞必须限定为"竞品盲区中的三件事"——因为 `tzdrift` 0★ 已存在且 README 强，`temporal`（tc39, 3703★）在 API 层面能感知 gap/overlap。宣称"首创/空白"是不诚实且可被一条 issue 打脸。 |
| 2026-10-20 | **⑥ 明确不做 cron 解析器** | `scheduler-mcp` 59★ / `temporal-cortex` 13★ / crontab.guru 已占用户心智。`audit` 只接受**本地时刻清单**或 `--daily HH:MM`，不接受 cron 表达式。这条是**产品边界**，也是与"调度系统"受众的相处方式：本工具审计它们的输入数据，不替代它们。 |
| 2026-10-20 | 数值口径单点定义在 `data/README.md` §四 | gap/overlap 双判据、POSIX tail 解析规则、四类变更定义、退出码语义、`roundtrip` 定义，五项一处定义；plan 与代码只可引用，不得复制。理由：本题结论对"判定顺序"和"fold 用法"极敏感，两处口径必然漂移。 |
| 2026-10-20 | 代理实测快照（598 / 11 / 20 / 201 / 192 / 580 / 342/199/64/37/30）**只作可行性证据** | 全部标注为"检索窗口内本机实测快照"，**不进 README 首屏当卖点、不作代码常量、不作断言阈值**。唯一例外：M1 的"零解析错误"与"与独立参照实现对拍一致"是**判据正确性**门槛（它们验证判据对不对，不是性能指标），且分母以末态实际 zone 数回填，不写死 598。 |
| 2026-10-20 | 薄片优先：M2（墙钟窗口）先于 M3（版本分类） | 墙钟窗口是**竞品物理上做不到**的那一件，也是 README 首屏的差异点；先把它做出来，产品的差异化才成立。版本分类次之，历史重解释再次。若工期紧张，砍的只能是 M4 的批量与 M5 的门禁组合，**不砍 M2**。 |
| 2026-10-20 | 弃选：**C4 日历规则 / 节假日** | `vacanza/holidays` 1958★ 已占位；ISO 周是标准库一行（`date.isocalendar()`）；阴阳历/复活节等需要权威离线源，本仓库无法保证数据来源的可用性（预检①/②过不了）。 |
| 2026-10-20 | 弃选：**cron / RRULE 解析** | 明令避开（见决策⑥），且已有成熟项目占位。写进题面 §六 的"不做"清单，防止后续被"顺手加一下"侵蚀。 |
| 2026-10-20 | 弃选：**按小时采样 UTC 偏移型** | 这正是 `tzdrift`（0★, 2026-10-18）与 `jodastephen/tzdiff`（3★）的形态。原理上：采样不产生墙钟区间（缺反解）、`now()` 起点看不见历史。与之同构=把 0★ 的定位复制一遍，且拿不到差异。 |
| 2026-10-20 | 弃选：**时区转换 CLI / 世界时钟** | 检索同类"时区转换"为红海（28 条结果），属消费级功能，与审计无关，且会把"审计"叙事冲淡成"又一个 tz 工具"。 |
| 2026-10-20 | 弃选：**纯 `zdump` 包装** | `zdump` 只能单 zone 转储（`-v`/`-i`/`-c`/`-t`），无跨版本比较、无 gap/overlap 查询。包一层没有独立价值——真正的价值在**跨版本 + 墙钟语义**。 |
| 2026-10-20 | 弃选：**时间戳格式歧义审计（C2）** | 需求真实（`dateparser` 实测 `05/10/2023` → `2023-05-10` 静默按美式），但**形态弱、易被视作 `dateparser` 的薄封装**，且结论依赖启发式而非可复算数据。列为**第二选择**（若时区方向素材不足时的替代题），不进本题首期。 |
| 2026-10-20 | 弃选：**跨系统时区基准（C3）** | 确定性最强（可对拍多个实现），但**产品感最弱、最易被复制**（本质是比较几个库的输出），且不解决"数据版本变更"这个真问题。列为**第三选择**。 |
| 2026-10-20 | 弃选：**闰秒 / `right` 模式主线** | `hifitime` 552★ / `zeit` 243★ 已覆盖；POSIX 时间本身忽略闰秒；`leap-seconds.list` 最后一条为 2017-01-01（Δ=37s）、文件到期 2027-06-28；2026a 的 `NEWS` 已默认不再安装 `right` 文件。首期只解析不建模，列扩展项。 |
| 2026-10-20 | 弃选：**GUI / 桌面 / Web 形态** | 输出是 Markdown + JSON，供 CI 与终端消费；桌面形态无业务必要，且会引入空壳风险与分发负担（预检⑩/㉕）。 |
| 2026-10-20 | 弃选：**内置"最新 tzdata" / 自动下载** | 会破坏"运行时零网络"红线，也会把审计对象（数据）与工具耦合：用户必须明确指定比较的两棵树，结论才可复算。 |

## 弃选项汇总（速查）

| 弃选项 | 一句话理由 | 去向 |
|---|---|---|
| 日历规则 / 节假日 | holidays 1958★ 已占 + 缺权威离线源 | 不做 |
| cron / RRULE 解析 | 明令避开，已有心智占位 | 不做（`--daily` 只展开时刻） |
| 按小时采样偏移 | 已被 tzdrift / jodastephen tzdiff 占，原理上做不出墙钟 | 不做 |
| 时区转换 CLI / 世界时钟 | 红海（28 结果）+ 消费级 | 不做 |
| 纯 zdump 包装 | 无独立价值，缺跨版本与墙钟语义 | 不做 |
| 时间戳格式歧义审计（C2） | 需求真但形态弱、易被视作 dateparser 薄封装 | 第二选择（不本题） |
| 跨系统时区基准（C3） | 确定性最强但产品感最弱、最易复制 | 第三选择 |
| 闰秒 / `right` 主线 | hifitime / zeit 已覆盖，POSIX 忽略闰秒 | 二期，只解析不建模 |
| GUI / 桌面 / Web | 无业务必要，空壳与分发风险 | 永不 |
| 内置最新 tzdata / 自动下载 | 破坏零网络红线 + 结论不可复算 | 永不 |
| 云分析 / 上传清单 / 遥测 | 隐私红线：日志时间戳即生产数据 | 永不 |

## 承诺-证据台账

> 全项目只此一份；其他文档只可引用，不得复制。状态列随里程碑同步翻转。

| 承诺项 | 素材来源 | 交付物内可达性 | 核验方式 | 状态 |
|---|---|---|---|---|
| TZif 四版本（v1–v4）解析 | IANA 发布包 + PyPI wheel（✅ 已实测可获取） | `tzif.py` → `tzaudit windows --zone` | 本地树全量 zone **零解析错误**；分母以末态回填 | ⬜ 待 M2 |
| slim / fat 两种构建语义等价 | 2026a/2026e 源码包与 wheel（✅） | `timeline.py` 的 `source: table\|tail` | 同版本 slim 与 fat 对同一 zone 语义一致 | ⬜ 待 M2 |
| 与独立参照实现对拍 | PEP 495 `fold` 语义（✅ 标准） | `timeline.py` 的 `roundtrip` | 对拍一致（数量以末态回填，不写死 20/20） | ⬜ 待 M2 |
| 本地→UTC 反解（竞品缺失的那一步） | 时间线结构（✅） | `timeline.resolve_local()` | gap / overlap 双向用例各至少一条 | ⬜ 待 M2 |
| **GAP 墙钟区间** | 2026 年真实数据（✅ 实测有 gap 的 zone 存在） | `windows` 的 `type=GAP` | America/New_York 2026 `02:00→03:00` | ⬜ 待 M3 |
| **OVERLAP 墙钟区间** | 同上（✅） | `windows` 的 `type=OVERLAP` | 同 zone `01:00→02:00` | ⬜ 待 M3 |
| 双判据（防 gap/overlap 互误报） | `data/README.md` §四单点定义 | `windows` 判定函数 | **Vancouver 2026 零误报**（反例单测） | ⬜ 待 M3 |
| POSIX tail 解析（三类规则 + `/time`） | 2026e 源码包 tail 字符串（✅） | `posix_tz.py` | `Jn` / `n` / `Mm.w.d` 各一条；`/time` 为墙钟秒的断言 | ⬜ 待 M2 |
| 负 DST / 30 分钟 / 非整点 | Dublin / Lord_Howe / Chatham（✅ 真实 zone） | `windows` + `diff` | 三个 zone 各一条 fixture 金标 | ⬜ 待 M3 |
| 四类变更互斥分类 | 2026a–2026e（✅） | `diff` 的 `changes[class]` | 判定顺序固定；Vancouver 为 `future_rule` + `evidence=tail` | ⬜ 待 M4 |
| **历史重解释可被 diff 出来** | IANA `NEWS` 原文 2026e / 2026d（✅） | `diff` 的 `history_reinterpreted` | Dublin(1925) / Tehran(1979) 金标 | ⬜ 待 M4 |
| 窗口内变化 zone 清单 | 五个真实版本（✅） | `diff --window` 输出 | 与金标名单一致（名单以末态回填，不写死 11） | ⬜ 待 M4 |
| alias 不吸收真实变化 | slim 的 link 集合（✅） | `diff` 的 `alias_only` | "legacy 名字换缩写"用例不得落进 alias_only | ⬜ 待 M4 |
| 清单审计四类判定 | 合成清单（见 `data/README.md` §三） | `audit` 的 `GAP/OVERLAP/VERSION_CHANGED/OK` | 四类各至少一条；`INVALID` 不静默跳过 | ⬜ 待 M5 |
| **BC 场景：同一 UTC 两版本两墙钟** | Cal.com #30104 原话（✅） | `audit --version A,B` 的对照 | 构造用例复现"相差一小时"的墙钟偏移 | ⬜ 待 M5 |
| `--daily HH:MM` 与清单等价 | — | `audit` | 两者输出一致 | ⬜ 待 M5 |
| 报告头三字段 | — | `report` 的 `data_version/zones_covered/generated_at` | 缺任一字段即测试失败 | ⬜ 待 M5 |
| `--fail-on` 门禁语义 | `data/README.md` §四单点定义 | `report` 退出码 | 四组退出码测试（无命中/gap/overlap/history） | ⬜ 待 M5 |
| 五版本金标可复算 | 2026a–2026e（✅ 实拉） | `bench/run.py` → `data/tzdb/*/expect.json` | 干净环境重跑一致 | ⬜ 待 M1 |
| fixture 可重建 | 生成脚本固定输入 | `data/fixtures/**/gen.py` | `--check` 重生成逐字节一致 | ⬜ 待 M2–M5 |
| 零网络 / 零遥测 | — | 全部子命令 | 断网跑通；代码内无 HTTP 客户端 | ⬜ 待 M6 |
| README 四场景复现 | — | `README.md` | 干净 clone 按 README 跑通 | ⬜ 待 M6 |
| 发布三件套 | — | tag / Release 附产物 / `plan/RELEASE-M6.md` | tag 树内含留档；Release 有附件 + 本地副本 + sha256 | ⬜ 待 M6 |

## 提交材料实物表（plan/01 §三 逐项落位）

> 每一项都要能在 M6 指着一个具体文件说"就是它"；指不出的项现在删，不留成无主承诺。

| 承诺项 | 应存在的文件路径 | 由哪个里程碑产出 | 用哪条命令核对 |
|---|---|---|---|
| 可安装 CLI 入口 | `pyproject.toml`（`[project.scripts] tzaudit`）+ `src/tzaudit/cli.py` | M1 | `pip install -e . && tzaudit --help` |
| 五个子命令实现 | `src/tzaudit/{tzif,posix_tz,timeline,windows,diff,audit,report}.py` | M2–M5 | `tzaudit <sub> --help` × 4（+ `report`） |
| 五版本金标回归 | `data/tzdb/{2026a..2026e}/expect.json` + `bench/run.py` | M1（拉包）→ M4（金标） | `python bench/run.py --check` |
| fixture 集 | `data/fixtures/{tzif,posix,windows,diff,audit}/{gen.py,expect.json,README.md}` | M2–M5 | `git ls-files data/fixtures`；生成器 `--check` |
| 测试 | `tests/test_*.py` | M2–M5 | `pytest -q` |
| README.md | `README.md`（四场景 + 字段说明 + 已知边界） | M6 | 干净 clone 按 README 跑通 |
| 发布留档 | `plan/RELEASE-M6.md`（两栏：tag 时点 / tag 后追加） | M6 | `git cat-file -e v0.1.0:plan/RELEASE-M6.md` |

> 招牌动词表（能力名词 → 交付态命令 → 断言基准）见 `plan/01-题目文档.md` §二，全项目只此一份。

## 里程碑

| 里程碑 | 内容 | 出口门 | 状态 |
|---|---|---|---|
| M0 | 出题定稿 + 方法论装订 + 可运行骨架 | `plan/00–06` 齐；`AGENTS.md` + `tools/check-sprint-layout.py` + `plan/00` 装订行；布局门 10 组变异 10/10 按预期；`tzaudit --help` / `--version` 退 0；`pytest` 70 项两通道全绿；脱敏门绿 | ✅ 已完成（2026-10-21） |
| **M1** | **数据先行** | 下载 **2026a–2026e 五个真实版本**（tar.gz 不入仓，只入解包后的必要文本）；`data/tzdb/<ver>/provenance.json` 记录来源 URL + sha256 + 版本号；`bench/run.py --check` 可跑 | ⬜ 下一步 |
| M2 | **TZif 双引擎** | `tzif.py` + `posix_tz.py` + `timeline.py`；本地树全量 zone 零解析错误；与独立参照实现对拍一致；slim/fat 语义等价；三条技术坑各一反面单测 | ⬜ |
| M3 | **墙钟窗口表 `windows`** | America/New_York 2026 两窗口方向正确；**Vancouver 2026 零误报**；负 DST / 30 分钟 / 非整点三 zone 金标；`--all --year` 可跑完 | ⬜ |
| M4 | **版本差异分类 `diff`** | 四类互斥且顺序固定；Vancouver → `future_rule`（`evidence=tail`）；Dublin 1925 / Tehran 1979 → `history_reinterpreted`；2026a↔2026e 名单与金标一致 | ⬜ |
| M5 | **清单审计 `audit` + 报告门禁** | 四类判定各一条；BC 场景"同一 UTC 两版本两墙钟"复现；报告头三字段；`--fail-on` 四组退出码测试 | ⬜ |
| M6 | 发布 | **git tag（`v0.1.0`）+ GitHub Release（附产物：手工源码包，本地留副本 + sha256）+ 发布留档 `plan/RELEASE-M6.md`（tag 前落盘、tag 后分栏追加）**；干净环境按 README 跑通四场景；断网跑通；提交面脱敏（含 tag tagger 邮箱）；发布 GitHub **公开仓库** | ⬜ |

> **M6 DoD 口径 = A）"Release 附产物"**：至少 1 个手工上传附件（`git archive` + `gzip -9n` + `SHA256SUMS`），本地留副本并记录 sha256。里程碑表的 DoD 列**只能加不能减**；要减必须在决策记录留一行理由。

## 台账与里程碑维护纪律

- 台账状态列在对应里程碑完成的**同一次提交**里翻转，不得滞后。
- 任何一条承诺若在开发中被砍，必须在决策记录表新增一行说明理由，并**同步删除题面对应措辞**；不得只改台账不改题面。
- 里程碑出口门只能加强，不得为了让里程碑"看起来完成"而改弱（尤其 M6 的"附产物"三个字）。
- 实测快照数字（598 / 11 / 20 / 201 / 192 / 580）**不得**进入代码常数、README 首屏或断言阈值；金标回归以 `data/tzdb/*/expect.json` 为准。
