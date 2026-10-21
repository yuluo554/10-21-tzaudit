# data · 依据查证、数据源可获取性与数值口径

> 本文件是**数值口径的唯一权威**（§四）。`plan/01` 与代码里的表述均为便于阅读的摘录；若与 §四冲突，**以 §四为准**，并在同一提交内修正摘录。
>
> - **代理实际检索窗口**：**2026-10-19T18:35Z–18:48Z**（`gh api` 检索、竞品 README/源码通读、IANA 发布包下载与 NEWS 核对均发生在此窗口内）
> - **tzdata 事实来源**：**实际下载的 IANA 发布包**（`https://data.iana.org/time-zones/releases/tzdata<ver>.tar.gz`，本次拉到 **2026a / 2026e**）与 PyPI `tzdata` **2026.1 / 2026.5**；`https://data.iana.org/time-zones/tzdb/version` 返回 **2026e**
> - **实测快照性质**：§一.5 的 598 / 11 / 20 / 201 / 192 / 580 / diff 行数等全部为**该窗口内的本机一次性探针快照**，只作可行性证据；**不得进代码常量、不得进 README 首屏、不得作断言阈值**
> - **未计入的检索（如实标注）**：`tzdata pinning check` 与首次的 `timezone test suite tz` 返回 **403 限流**，**不是 0 结果**，不计入空白列（⬜）

---

## 一、依据查证记录（三态：✅ 已核对原文 / ⬜ 软论据或待核对）

### 1.1 竞品与基线工具的边界（✅ 已读源码/官方文档原文，窗口 2026-10-19T18:35Z–18:48Z）

| 编号 | 对象 | 星数 | 结论（要点） | 来源 |
|---|---|---|---|---|
| TZDRIFT-SRC | `prithsk/tzdrift` | **0★**（**2026-10-18 创建**，7KB，单次提交） | **✅ 读了全文，非推测**：核心是 `out[n] = [int((start + dt.timedelta(hours=h)).astimezone(z).utcoffset()...) for h in range(0, hours, step)]`——**按 step 小时采样 UTC 偏移逐点比对**。因此：①输出不了墙钟区间（无本地→UTC 反解）；②看不见历史（`start` 默认 `now()`）；③按文件 SHA1 合并 alias，掩盖"legacy 名字换缩写"；④无 fold 处理。README 质量高，**直接引用 Cal.com 真实 open issue 并做了线上 API 核对** | 仓库源码 + README |
| ZDUMP | tzdata 自带 `zdump` | — | 单 zone 转储（`-v` / `-i` / `-c` / `-t`），**无比较、无 gap/overlap 查询** | 手册 |
| TZDIFF-JS | `jodastephen/tzdiff` | 3★（2013 创建，最后提交 **2024-09-16**） | **停在 tzdb 2024b**；只有文本转储 | 仓库 |
| TZDIFF-BB | `belgianbeer/tzdiff` | 166★ | **并排显示多时区当前时间**——与本题无重叠，**须在文档中明确区分同名不同物** | 仓库 README |
| ZONEINFO | Python `zoneinfo` | — | 单值转换；**实测对不存在的本地时间静默返回假合法 offset**：`2026-03-08 02:30 America/New_York` → `-05:00`，不报错 | 本机实测 |
| PYTZ | `pytz` | — | 单值转换；无审计语义 | 文档 |
| DATEPARSER | `dateparser` | — | **实测** `05/10/2023` → `2023-05-10`（静默按美式）。**仓库地址在检索窗口内返回 404**，故行为改由**官方文档**核实，不引用仓库 README | 官方文档 |
| CONVENIENCE | `pendulum` / `arrow` / `dateutil` | 6677★ / 9050★ / 2640★ | 便利层（人性化 API），**无审计语义** | 仓库 README |
| CHRONO-TZ | `chrono-tz` | 281★ | **编译期嵌入单版本**，无法跨版本比较 | 仓库 |
| TEMPORAL | `temporal`（tc39） | 3703★ | 有 `disambiguation` / `offset` 选项，**能感知 gap/overlap**——但是运行时 API，**不是审计工具**（不产出清单、不做跨版本 diff） | 提案文档 |
| EGGERT-TZ | `eggert/tz` | 1869★ | 数据库与编译器本身，**非审计器** | 仓库 |
| TZDATA-NEWS | tzdata `NEWS` / `tz-link.html` | — | **散文**：不可计算、不可 diff、不可门禁 | 发布包内文件 |

> 星数为**检索窗口快照**，会漂移；引用必须带窗口。

### 1.2 需求侧原话（✅ 逐条对照 URL，窗口同上）

| 编号 | 类别 | 原话（节选，未改写） | 来源 |
|---|---|---|---|
| HN-44373189 | 任务因 DST 被跳过 | "I never really took time seriously until one of my cron jobs **skipped execution because of daylight saving**. That was the moment I realized how tricky time actually is."（Raphell, 2025-06-25） | https://news.ycombinator.com/item?id=44373189 |
| HN-44373665 | 避开凌晨任务：可能不跑或跑两次 | "I **avoid running 'daily' cron jobs** or other scheduled tasks around 2am for that reason, they **might not get run or they might get run twice**."（bigiain） | https://news.ycombinator.com/item?id=44373665 |
| HN-45726083 | 调整日的现实代价 | "**Redundantly running cron jobs** are the least of our problems. Daylight savings adjustment day causes surge in deaths and ER visits."（2025-10-27） | https://news.ycombinator.com/item?id=45726083 |
| CAL-30104 | **真实生产事故（open，2026-09-06）** | "British Columbia stopped observing daylight saving on 2026-11-01 and is now permanently UTC−07:00. This landed in tzdb 2026b... **Cal is internally inconsistent about it across its own surfaces.** ... **The reschedule email is the damaging one**: it states the *new* time an hour early, so an attendee is told to arrive at 5:00pm for a session that is actually at 6:00pm." | https://github.com/calcom/cal.diy/issues/30104 |
| AIRFLOW-7999 | 表达式在 DST 后偏移 | "`0 7-8 * * *`" → 实际 "8 AM instead of 7 AM" | https://github.com/apache/airflow/issues/7999 |
| CELERY-10585 | 不应产出不存在的时间 | "**do not produce a datetime that does not exists** (at DST start, when an hour disappears)" | https://github.com/celery/celery/issues/10585 |
| K8S-47202 | 时区绑定导致频繁改任务 | "if I define that CronJob in UTC I will be forced to **update that job from time to time**"（221 reactions） | https://github.com/kubernetes/kubernetes/issues/47202 |

### 1.3 历史重解释实证（✅ 来自**实际下载**的 IANA 发布包 `NEWS` 原文）

| 编号 | 版本 | 原文（节选） | 影响 |
|---|---|---|---|
| IANA-2026E | tzdata **2026e** | "In 1925 Ireland fell back on 09-20 not 10-04" | Europe/Dublin 1925 年秋季回溯日整体位移 |
| IANA-2026D | tzdata **2026d** | "Iran's 1979-05-26 spring forward was at 00:00, not 24:00" | Asia/Tehran 1979 春季前跳的墙钟位置改变 |

### 1.4 版本与包的事实（✅ 实拉）

| 事实 | 值 | 来源 |
|---|---|---|
| 当前 tzdb 版本 | **2026e** | `https://data.iana.org/time-zones/tzdb/version` |
| 已下载源码发布包 | `tzdata2026a.tar.gz`、`tzdata2026e.tar.gz` | `https://data.iana.org/time-zones/releases/` |
| 已核对 PyPI `tzdata` | **2026.1**、**2026.5**（slim 构建 wheel） | PyPI |
| 系统已编译树 | `/usr/share/zoneinfo`（fat 构建） | 本机 |
| 闰秒文件末条 | `leap-seconds.list` 最后一条 **2017-01-01（Δ=37s）**；文件到期 **2027-06-28** | 发布包内文件 |
| `right` 文件默认安装 | **2026a `NEWS` 已默认不再安装 `right` 文件** | 发布包 `NEWS` |

### 1.5 代理实测快照（✅ 本机一次性探针；**快照，非产品指标**）

| 指标 | 快照值 | 用途 |
|---|---|---|
| TZif 解析 | **598 zone 零解析错误** | M2 可行性 |
| 与独立参照实现（PEP 495 语义）对拍 | **20/20 一致** | M2 判据正确性 |
| 2026a→2026e 源码 diff 行数 | `northamerica` **342**、`africa` **199**、`europe` **64**、`southamerica` **37**、`asia` **30** | 变更真实且分布广 |
| `2024–2031` 窗口内变化的 zone | **11 个**（10 个加拿大 + 摩洛哥 2 个，含重叠计数） | M4 规模参照 |
| 全历史任意时刻不同 | **20 个**（含 Europe/Dublin、Asia/Tehran、EST5EDT、MST7MDT） | 历史重解释规模参照 |
| 2026 年有 gap / 有 overlap | **201 / 192**（598 zone 全量） | M3 批量规模参照 |
| slim 依赖 POSIX tail | **580/598 zone** | **关键**：只 diff 转换表会漏变更 |
| Vancouver 2026.1 vs 2026.5 tail | `PST8PDT,M3.2.0,M11.1.0` vs `MST7`，**表里迁移数都是 0 但语义完全不同** | M4 `future_rule` 判据来源 |

> **纪律**：以上数字**一律不得**成为代码常量、README 卖点或断言阈值（唯一例外是"零解析错误"与"对拍一致"这两条**判据正确性**门槛，且其分母以末态实际 zone 数回填，不写死 598）。

### 1.6 技术坑（✅ 代理踩过并修正；实现必须原样包含）

| 编号 | 坑 | 正确做法 |
|---|---|---|
| PITFALL-WEST | **POSIX TZ 偏移是"西为正"**：`EST5` = UTC−5、`MST7` = UTC−7 | 解析时 `utc_offset = -sign * value`；反例单测：对称时区看不出错的场景要专门构造 |
| PITFALL-WALLSEC | 规则时间 `M3.2.0/2` 的 `/2` 是**墙钟秒** | 先求"本地那天的那一刻"，再做一次本地→UTC 解析；**不得**把它当偏移去加减 |
| PITFALL-FOLD-GAP | **`fold=0 ≠ fold=1` 在 gap 里也成立** | 单看 fold offset 不同会**在 gap 上误报 overlap**（Vancouver 实测踩中）。必须两套判据并存（见 §四.1） |

### 1.7 开源空白检索（⬜ 软论据：`gh api` 检索式 + total_count，窗口 2026-10-19T18:35Z–18:48Z）

| 检索式 | total_count | 头部 / 有效头部 |
|---|---|---|
| `tzdata diff timezone` | 2 | `hygt/tz-diff` 0★、`tzdrift` 0★ |
| `tzif parser` | 8 | zig-tzif 9★、tzif-parser 4★ |
| `timezone drift` | 16 | CronScheduler 68★（调度库，非审计） |
| `tzdiff` | 6 | belgianbeer 166★（并排显示）、jodastephen 3★（停 2024b） |
| `dst transition audit` | 1 | 0★ |
| `posix tz string parser` | 1 | 0★ |
| **`tzdata comparison tool`** | **0** | — |
| **`timezone database diff tool`** | **0** | — |
| **`timezone migration checker`** | **0** | — |
| **`iana tzdata monitor`** | **0** | — |
| **`dst test data generator`** | **0** | — |
| `tzdata pinning check` | — | **403 限流，未计入** |
| `timezone test suite tz`（首次） | — | **403 限流，未计入** |

> **判定（⬜ 软论据，非市场调查）**：**墙钟窗口 + 历史重解释 + 变更分类三件事竞品都没做。**
> 但**不得**写成"空白/首创"——`tzdrift` 0★ 已存在（2026-10-18 创建）且 README 强；`temporal`（3703★）在 API 层面能感知 gap/overlap。措辞固定为"**竞品盲区中的三件事**"。

---

## 二、数据源可获取性记录

| 数据源 | 状态 | 获取路径 | 实测结果与阻断说明 |
|---|---|---|---|
| IANA 源码发布包 | ✅ **已获取** | `https://data.iana.org/time-zones/releases/tzdata<ver>.tar.gz` | 实拉到 **2026a**、**2026e**；`/tzdb/version` = 2026e。包体**不入仓**（`.gitignore` 封 `*.tar.gz`），只入解包后的必要文本（`NEWS`、`leap-seconds.list`）+ 金标 JSON |
| PyPI `tzdata` wheel（slim） | ✅ **已获取** | `pypi.org/project/tzdata/` | 核对 **2026.1 / 2026.5**；wheel 内 `tzdata/zoneinfo/**` 是 slim 构建（含 POSIX tail） |
| 系统 `/usr/share/zoneinfo`（fat） | ✅ **已获取** | 本机路径 | 已编译树，作为 fat 构建的对照组 |
| 2026b / 2026c / 2026d | ✅ **已获取** | 同 releases 路径 | M1 需五个版本齐全（`data/tzdb/{2026a..2026e}/`）；`provenance.json` 逐版本记 URL + sha256 |
| 第三方"时区事故数据集" | ⬜ **未采用** | — | 未找到可直连、许可清晰的公开事故时间戳数据集；**不编造**，改用 §三 的合成清单 |
| GitHub 检索 API | ⚠️ **部分受限** | `gh api search/repositories` | 两个检索式 **403 限流**（`tzdata pinning check`、首次 `timezone test suite tz`），如实标注，不计入空白列 |
| `dateparser` 仓库 | ⚠️ **404** | — | 检索窗口内仓库地址 404；行为改用**官方文档**核实，不引用其 README |

> **运行时零网络**：CLI 不下载任何东西。用户在本地提供 zoneinfo 树或解包后的 tzdata 目录（`--zoneinfo` / `--version`）。

---

## 三、合成数据纪律

1. **测试清单一律用假业务场景**，不含任何真实用户日志：
   - CSV 形如 `id,local_time`，id 用 `case-001` 这类序号，时间用**构造**的 `2026-03-08 02:30` / `2026-11-01 01:30` 等边界时刻；
   - 不出现真实企业名、主机名、账号、会话 id；不出现任何真实日志的复制片段。
2. **假值白名单登记**（凡出现以下形态，均视为合成，不是真实数据）：
   - 业务 id：`case-\d{3}`、`demo-\d{3}`、`bc-2026-\d{3}`；
   - 客户名：`Acme Demo`、`Example Tenant`（**仅出现在 fixture 的 `README.md` 说明里，不写进提交身份/邮箱**）；
   - 时区清单：只用 IANA 标准 zone 名，不自造 zone 名（自造会掩盖解析错误）。
3. **金标来源纪律**：
   - `windows` / `diff` 的金标来自**实际下载的 tzdata 版本**（可溯源到 `provenance.json` 的 sha256），不是手写推测值；
   - `audit` 的金标是**合成清单 + 真实版本树**的组合：清单是假的，版本数据是真的。
4. **不入仓**：任何真实日志、真实用户时间戳、真实客户 CSV；仓库不接受"脱敏后的真实日志"（脱敏不可验证）。

---

## 四、数值口径（唯一权威）

> 本节 5 项一处定义；`plan/01`、代码注释与 README 只可引用，**不得复制第二份口径**。

### 4.1 gap / overlap 双判据（M2 / M4 共用）

记 `resolve_local(local, zone)` 返回该本地墙钟时刻对应的 UTC 候选集合；`roundtrip(local)` = 把 `resolve_local` 的结果转回本地墙钟（`fold` 按 PEP 495）。

| 判定 | 定义 | 说明 |
|---|---|---|
| **GAP（不存在）** | `roundtrip(local) != local` | 该墙钟在时间线上没有对应点 |
| **OVERLAP（二义）** | `roundtrip(local) == local` **且** `utcoffset(fold=0) != utcoffset(fold=1)` | 两个 fold 都合法且 offset 不同 |
| **OK（唯一）** | `roundtrip(local) == local` **且** 两个 fold 的 offset 相同 | |
| **禁止** | 仅用 `fold=0 != fold=1` 判 OVERLAP | **在 gap 上同样成立**，会误报（Vancouver 实测踩中） |

- 窗口输出时长以**整分钟**给 `duration_min`；不足 1 分钟的秒级残差写 `residual_sec`（不四舍五入成 60）。
- 窗口排序：`start_local` 升序 → 同起点按 `type` 字典序（`GAP` < `OVERLAP`）。
- 判定顺序：**先判 GAP，再判 OVERLAP**；两者互斥，不允许同时为真。

### 4.2 POSIX TZ tail 解析规则（M2 唯一的 tail 口径）

语法：`std offset [dst [offset] [,start[/time],end[/time]]]`

| 项 | 规则 |
|---|---|
| 偏移符号 | **西为正**：`EST5` → UTC−5；`MST7` → UTC−7；`<+1245>-12:45` → UTC+12:45 |
| 偏移格式 | `[+-]hh[:mm[:ss]]`，小时可 1–3 位 |
| start/end 形式 | `Jn`（1–365，**跳过 2/29**）／`n`（0–365，**含 2/29**）／`Mm.w.d`（月/第 w 周/星期 d，`w=5` 表示最后一个） |
| `/time` 后缀 | **墙钟秒**（可带符号，可为负/超 24h）；**不得**当偏移去减（见 §1.6 PITFALL-WALLSEC） |
| 缺省 `dst offset` | 缺省为 `std offset − 1 小时`（即 DST 比标准时快 1h） |
| 缺省 `start/end` | 无逗号段时，表示**无 DST**（如 `MST7`） |
| 生效边界 | 转换表覆盖到的时间范围内用表；之后用 tail 展开；两者交界以**更晚的显式转换点**为界，并记录 `source: table\|tail` |

### 4.3 四类变更定义（M4 `diff`，互斥，判定顺序固定）

| 顺序 | 类别 | 定义 | `evidence` 取值 |
|---|---|---|---|
| 1 | `history_reinterpreted` | **过去时刻**（两树共有历史的交集内）的墙钟↔UTC 映射发生变化 | `table` / `tail` |
| 2 | `future_rule` | 转换表**之外**的行为变化：远期规则或 POSIX tail 字符串语义不同 | `tail` / `table` |
| 3 | `abbreviation_only` | 转换点与 offset 全同，仅缩写/命名不同（如 `EST`→`EDT` 的命名调整） | `abbr` |
| 4 | `alias_only` | 仅 link/alias 集合变化；**不得**用于吸收任何 offset 或规则变化 | `link` |

- **取第一条成立的类别**；同一 zone 只输出一条分类记录（多个证据时取顺序最靠前者）。
- **关键约束**：转换表相同但 tail 不同 → 必然落 `future_rule`（Vancouver：表内迁移数皆 0，tail 由 `PST8PDT,M3.2.0,M11.1.0` 变 `MST7`）。
- `--window <开始年>-<结束年>` 只影响第 1 类的判定区间；第 2 类始终按"表外 + tail"判定，不受窗口限制。
- 输出顺序：`zone` 字节序；同 zone 只有一条。

### 4.4 退出码（`report` / 全部子命令共用，一处定义）

| 码 | 语义 | 触发 |
|---|---|---|
| `0` | 成功且门禁未命中 | 无 `--fail-on` 命中项 |
| `1` | 门禁命中 | `--fail-on` 指定的类别在结果集中出现 |
| `2` | 用法错误 | 参数缺失/互斥/非法枚举（含传 cron 表达式） |
| `3` | 环境不满足 | zoneinfo 路径不存在、版本目录缺 `provenance.json`、TZif 损坏 |
| `4` | 输入数据无效 | 清单 CSV 无法解析的行超过一行（逐行记 `INVALID`，但整体仍按 4 退出） |
| `5` | **功能未就绪（骨架期临时语义）** | 子命令的解析层尚未实现（M0 骨架期）。**每落地一个子命令即整项退役**：删常量 `errors.EXIT_NOT_READY` → 删 `cli._unimplemented` 对应分支 → 删 `tests/test_exit_codes.py` 对应断言 → 改本节与 `plan/03` §九 → 决策记录留一行。**四处少一处 = 幽灵语义复活。**<br>**M3 进度**：`windows` 已落地并退出该语义（2026-10-21）；`diff` / `audit` / `report` 三条**仍在 5**（M4/M5 各自退役）。 |

- `--fail-on` 枚举固定为 `gap`、`overlap`、`history`（可逗号组合）；**不存在第四种**。
- 退出码只看结果集，不看人读文本；`--json` 与 Markdown 的退出码必须相同。
- 退出码 `5` **不进入任何发布态口径**：M6 之前必须全部退役，M6 的发布门断言它已从 `src/` 消失。

### 4.5 报告头三字段（M5，缺一即不合规）

| 字段 | 含义 | 缺省行为 |
|---|---|---|
| `data_version` | 参与比较的 tzdata 版本（A、B 两棵树的版本标签） | 缺失 → 退出码 3 |
| `zones_covered` | 本次实际解析的 zone 数（分母，末态回填） | 缺失 → 退出码 3 |
| `generated_at` | 生成时间（UTC，ISO 8601） | 唯一允许的时间戳；其余输出不得含时间戳 |

### 4.6 `roundtrip` 定义（与 PEP 495 `fold` 语义一致）

```
roundtrip(local, zone):
    utc_candidates = resolve_local(local, zone)      # 0 个 → GAP
    return [ to_local(u, zone) for u in utc_candidates ]
```

- `resolve_local` 返回 **0 个** UTC → GAP；返回 **2 个** → OVERLAP；返回 **1 个** → OK。
- `fold` 只是**选择**（PEP 495），**不是**存在性判据；存在性只由 `roundtrip` 的结果数决定。
