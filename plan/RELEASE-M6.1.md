# RELEASE-M6.1 · tzaudit v0.1.1 发布留档

> 两栏纪律（`plan/05` §五）：**§一 tag 前事实**随 tag 树一起发布，只写"结构 + 复验方法"与
> **不含自指的值**；**§二 tag 后追加**在 tag 之后补记（附件 sha256、tag 对象、run 计数只写在这里）。
> 自指的值（附件 sha256 / tag OID / tag 指向的 commit / 本次 push 的 run 数）**不写进 tag 树**——
> 写一次就失效一次。
>
> 版本目标：`v0.1.0` → **`v0.1.1`**（M6.1 二次迭代：D1 变异门 P0 + D2/D5 CI 接纪律 + D3/D4 发布面 + D9 复核锚）。
> `v0.1.0` 的留档见 `plan/RELEASE-M6.md`（**不动**）。

---

## 一、tag 前事实

### 1.1 版本

| 项 | 值 | 复验命令 |
|---|---|---|
| 版本号 | `0.1.1` | `py -3.12 -m tzaudit --version` |
| 三处一致 | `src/tzaudit/__init__.py` / `pyproject.toml` / `README.md` 首屏 | `grep -n '0\.1\.1' src/tzaudit/__init__.py pyproject.toml README.md` |
| Python 底线 | 3.8 | `py -3.8 -m pytest` |

### 1.2 本版改动（相对 `v0.1.0`）

| # | 改动 | 落点 | 类型 |
|---|---|---|---|
| D1 | `tools/mutate-layout-gate.py` 的 V9 靶子改成打 `LAYOUT.RELEASE` 两条独立子判据 + **字节级 no-op 自证** | `tools/mutate-layout-gate.py` | **P0**（门自身 9/10 → 10/10） |
| D2 | CI 加常驻门：干净 checkout 上 `bench/run.py --check` 必须 **rc=3** | `.github/workflows/ci.yml` | P1 |
| D5 | README 首屏据实标注"金标复算在本地 / CI 跑不到"（435 vs 363+72） | `README.md` | P1 |
| D3 | `actions/checkout@v4 → @v7`、`setup-python@v5 → @v7` | `.github/workflows/ci.yml` | P1 |
| D4 | GitHub `description` 非空 + 4 topics | GitHub 元数据（非仓内） | P1 |
| D9 | `data/README.md` 加 tzdata 版本纳入纪律 + `next_review` | `data/README.md` | P2 |
| — | 文档对齐：V9 靶子描述、维护纪律、里程碑 DoD、README 计数 | `plan/00`、`plan/05`、`plan/HANDOFF-M1` | 文档 |

> **范围**：本版**不改判定逻辑**（`src/tzaudit/**` 的 tzif / posix_tz / timeline / windows / diff / audit / report 一字未动）；
> **不动金标与 provenance**（`data/tzdb/**` 的 `provenance.json` sha256 / `NEWS` / `expect*.json` 一字未改）；
> **不动 `data/fixtures/**`**；**不改退出码语义**（0/1/2/3/4；5 已于 M5 退役）。

### 1.3 已执行的验证（本地等价校验）

| # | 验证 | 方法 | 结论 |
|---|---|---|---|
| 1 | 布局门 | `py -3.12 tools/check-sprint-layout.py` | **退 0**（10 条判据全绿） |
| 2 | 脱敏门 | `py -3.12 tools/check-desensitized.py` | **退 0**（4 条规则；扫 224 份文本文件） |
| 3 | **变异门** | `py -3.12 tools/mutate-layout-gate.py` | **退 0，`变异验证: 10/10 组按预期`**（D1 的正面判据） |
| 4 | 全量测试（有数据） | `py -3.12 -m pytest -o addopts=""` | **434 passed, 1 skipped**（1807.24 s ≈ 30 分 07 秒） |
| 5 | 全量测试（CI 等价） | `git archive HEAD` 解包树跑 `pytest -o addopts=""` | **363 passed, 72 skipped**（16.92 s） |
| 6 | 金标复算（有数据） | `py -3.12 bench/run.py --check --suite parse/windows/diff/audit` | **各退 0、`不一致: 0`** |
| 7 | 缺件纪律（无数据） | 干净树 `bench/run.py --check` | **退 3**，点名缺件 + "不是 0 项通过" |
| 8 | CI 实跑 | 本版 push 后 CI 5/5 job success、Node20 注解 0（**run 编号属自指值，只记 §2.2**） | 见 §2.2 |

### 1.4 变异门 V9 修正的证据链（D1，本版重点）

**失效形态**：V9 旧靶子是"把**尚未完成**的 M6 篡改成 ✅ 但不建 `RELEASE-M6.md`"。M6 完成后三处副本本
就是 ✅ ⇒ `.replace("⬜","✅")` 退化为 **no-op** ⇒ 变异未改字节 ⇒ `LAYOUT.RELEASE` 不红 ⇒
`FAIL V9`（rc=1），而四处文档仍写 `10/10`。

**修正**：
- 靶子改成与里程碑状态**无关**的两条独立子判据（`plan/RELEASE-M6.md` 的「阶段 7 覆盖对账」标题 +
  「## 二、tag 后追加」两栏标记），永远有效；
- 脚本加**字节级自证** `repo_fingerprint()`：任一组的替换/删除若是 no-op，该组报
  `FAIL（靶子已失效）`，而不是被静默记成"按预期"。

**负控（已实测）**：
1. 把 V9 换成一个真 no-op 的靶子 → 脚本报 `FAIL V9 靶子已失效（变异是 no-op，没有改变任何字节）`，rc=1；
2. 把门的 `two_cols` 判据削弱成对「tag 后追加」四字不敏感 → V9 的"明细须同现 `两栏:False`"断言失败
   （证伪：两条子判据**各自**都能被咬住）。

### 1.5 断网证据

本版**未改 `src/`**（判定逻辑与零网络纪律一字未动），故不重跑断网打桩；
`v0.1.0` 的断网证据见 `plan/RELEASE-M6.md` §1.5（`socket` 五入口打桩 + `netstat` 旁证）。
本版 CI 的 CLI 冒烟（`--help` / `--version`）与四矩阵 `pytest` 仍在跑。

### 1.6 脱敏门

`py -3.12 tools/check-desensitized.py` 退 0：4 条规则（盘符绝对路径 / MSYS 用户路径 / 本机用户名 /
回环代理端口），扫全仓文本文件，豁免仅限脚本自身与 `.git/`。

> **本版新增**：`SKIP_DIRS` 加入 `update/`（迭代交接物目录，含本机路径，已 gitignore；与既有
> `.venv` / `bench/out` 同族处理）。这是 `.gitignore` 与门的口径**成对**调整，不是削弱规则。

### 1.7 测试与金标

| 通道 | 命令 | 实测（2026-10-23，本机） |
|---|---|---|
| 3.12 有数据 | `py -3.12 -m pytest -o addopts=""` | **434 passed, 1 skipped**（1807.24 s） |
| CI 等价（无 `data/_downloads`） | `git archive HEAD` 解包树 `pytest -o addopts=""` | **363 passed, 72 skipped**（16.92 s） |

> 总数 **435 collected** = 363（CI 可跑）+ 72（金标，CI skip）。
> CI 上无 `data/_downloads`（不入仓、需联网拉约 4 MB）⇒ 72 条金标测试全部 `SKIP`。
> **这条差异已在 README 首屏据实标注**（D5）。
> ⚠ `addopts = "-q"` 已在 `pyproject.toml`，验收**必须** `-o addopts=""`（否则 `-q` 叠加成 `-qq` 吞掉汇总行）。

### 1.8 交付形态

| 项 | 内容 |
|---|---|
| 附件 | `git archive --format=tar --prefix=<name>/ v0.1.1 \| gzip -9n` + `SHA256SUMS` |
| 复验方法 | `sha256sum -c SHA256SUMS`；`gh release download` 回下载后 `cmp`；解包树与 `git archive` 树共有文件逐字节比对 |
| 本地副本 | `dist-release/`（不入仓，已 gitignore） |

> ⚠ **产物名 = `10-21-tzaudit-v0.1.1.tar.gz`**（带**目录名前缀 + `v` 前缀**），
> **不是** setuptools 规范化形态（`tzaudit-0.1.1.tar.gz`）。与同批 `tripwire` 相反，**别套用它的规则**。

---

## 二、tag 后追加

> 本节写于 tag 之后，**不随 tag 树发布**（tag 树里只有 §一）。
> 自指的值（tag OID、指向的 commit、附件 sha256、run 编号）只出现在这里。

### 2.0 tag 与 Release

| 项 | 值 |
|---|---|
| tag | `v0.1.1`（annotated） |
| tag 对象 OID | `e2d34972fd1bfb2c1956f22fe253cbb5ddaf2514` |
| 指向 commit | `5593424fd31dd86f1e79e44bf43cb69412062769`（= `main` HEAD） |
| tag 消息 | `tzaudit v0.1.1：M6.1 二次迭代（变异门 V9 靶子失效修复 + CI 缺件纪律 + 发布面补全）` |
| tagger | `yuluo554 <282769740+yuluo554@users.noreply.github.com>` |
| Release | `v0.1.1`，**draft=false / prerelease=false / latest=true** |
| Release URL | <https://github.com/yuluo554/10-21-tzaudit/releases/tag/v0.1.1> |
| tag 后提交 | **仅留档追加**（`plan/RELEASE-M6.1.md` §二；不写死滚动条数——见 `plan/RELEASE-M6.md` §2.2 口径）；`v0.1.1` 之后的提交**不改交付面** |
| `v0.1.0` | **未动**（annotated `e770c42e` → `d05fb8d` 保持原样） |
| 复验命令 | `git rev-parse v0.1.1 v0.1.1^{commit}`；`curl -s https://api.github.com/repos/yuluo554/10-21-tzaudit/releases/latest` |

### 2.1 附件与复核

| 项 | 值 |
|---|---|
| 附件 1 | `10-21-tzaudit-v0.1.1.tar.gz`（378253 B） |
| 附件 2 | `SHA256SUMS`（94 B） |
| 附件 1 sha256 | `afd3b6c8213d09ae3aacbca4761d5647574f3925e5d5ba75c16c1e42456b88eb` |
| 附件 2 sha256 | `4a057e9b1e1e9f389d6962e7bae8cc437c93a1e583df4b439c2f7bd72fa6ee36` |
| 构建命令 | `git archive --format=tar --prefix=10-21-tzaudit-0.1.1/ v0.1.1 \| gzip -9n` |
| `gzip -9n` 确定性 | 同一条命令重建两次 → `cmp` 逐字节一致 |
| 本地副本 | 仓库外 `dist-release/`（不入仓，已 gitignore） |
| 匿名下载 | `curl -sL` 两份附件（**不带 token**）→ `sha256sum -c SHA256SUMS` → **OK**；HTTP **200** |
| 三方一致 | 本地构建 sha256 = 匿名下载 sha256 = GitHub API `digest`（`sha256:afd3b6c8…`） |
| 解包树版本 | `pyproject.toml:7` = `0.1.1`、`src/tzaudit/__init__.py:7` = `0.1.1` |
| 解包树门 | 解包后 `check-sprint-layout.py` / `check-desensitized.py` 均**退 0** |
| tag 树内文件 | **161** 份（`git ls-tree -r v0.1.1 --name-only`）；附件条目 210（161 文件 + 49 目录） |
| `git diff --name-only v0.1.0..v0.1.1` | `ci.yml` / `.gitignore` / `AGENTS.md` / `README.md` / `data/README.md` / `plan/00` / `plan/05` / `plan/06` / `plan/HANDOFF-M1.md` / `plan/RELEASE-M6.md` / `plan/RELEASE-M6.1.md` / `pyproject.toml` / `src/tzaudit/__init__.py` / `tools/check-desensitized.py` / `tools/mutate-layout-gate.py`（15 项；**交付面只有版本号 2 处 + 两个门脚本**，判定逻辑 `src/tzaudit/**` 未动） |

### 2.2 CI 实跑结论

| run | 事件 | 分支 / tag | head sha | 结论 | 说明 |
|---|---|---|---|---|---|
| #9 | push | `main` | `c7dd967` | **success** | M6.1 主要改动（D1/D2/D3/D5）；5/5 job success；**含 D2 新增的 `Bench discipline` 步骤 ×4 矩阵全 success** |
| #10 | push | `v0.1.1`（tag） | `5593424` | **success** | tag run；5/5 job success |
| #11 | push | `main` | `98908be` | **success** | tag 后留档追加（`RELEASE-M6.1.md` §二）；5/5 job success |

> 复验命令：`gh api repos/yuluo554/10-21-tzaudit/actions/runs --jq '.workflow_runs[] |
> "\(.run_number)\t\(.event)\t\(.head_branch)\t\(.head_sha[0:7])\t\(.conclusion)"'`

**注解**：Node20 弃用注解 **0 条**（`checkout@v4`/`setup-python@v5 → @v7`，D3 生效）；
`ubuntu-latest` → Ubuntu 26 迁移 notice **3 条**（GitHub 侧排期，非本仓可控；见 `plan/RELEASE-M6.md` §2.3）。

### 2.3 阶段 7 覆盖对账（M6.1）

> 三态：**实现**（tag 树里有实物且可复验）/ **不适用**（本轮明确不做，附理由）/ **待首推**（本地无法验证）。

| # | 阶段 7 项 | 三态 | 证据 / 复验 |
|---|---|---|---|
| 1 | 版本号三处一致（`0.1.1`） | 实现 | §1.1；`git show v0.1.1:pyproject.toml` 与 `src/tzaudit/__init__.py` 均 `0.1.1`；README 首屏 `v0.1.1` |
| 2 | 变异门恢复 10/10（D1） | 实现 | §1.4；本地 `tools/mutate-layout-gate.py` → `10/10 组按预期` rc=0；两组负控实测 |
| 3 | 脱敏门绿（含 `update/` 跳过） | 实现 | §1.6；本地退 0；tag 树解包后退 0 |
| 4 | 布局门绿（10 条判据） | 实现 | §1.3；本地退 0；tag 树解包后退 0 |
| 5 | CI 接「缺件退 3」常驻门（D2） | 实现 | §2.2 run #9/#10：`Bench discipline` 步骤在 4 个 pytest 矩阵全 success |
| 6 | README 据实标注金标在本地/CI 差异（D5） | 实现 | §1.7；README 首屏「金标复算在哪里跑」表（435 vs 363+72） |
| 7 | actions 升 v7 + Node20 注解清零（D3） | 实现 | §2.2；注解计数 **0** |
| 8 | GitHub description + topics（D4） | 实现 | `gh repo view --json description,repositoryTopics` → description 非空 + 4 topics |
| 9 | tzdata 版本纳入纪律 + next_review（D9） | 实现 | `data/README.md` §2.1（`next_review: 2026-11-30`） |
| 10 | 发布三件套（tag / Release 附件 / 留档） | 实现 | §2.0 + §2.1 |
| 11 | 金标在 CI 跑 | **不适用** | CI 上无 `data/_downloads`（不入仓，需联网拉约 4 MB）⇒ 72 条金标测试全部 `SKIP`；这是**有意的口径**（体积 + 联网 + URL 失效风险），已在 README 与 §1.7 登记，并以「缺件必退 3」常驻门兜住纪律（DEC-2 乙+丙案） |
| 12 | 变异门进 CI | **本轮不做** | 本迭代只把「缺件退 3」进 CI；变异门仍在开发机跑（`.github/workflows/ci.yml` 无 `mutate-layout-gate` 步骤）。用户 DEC-2 选项均针对金标，未授权加变异 job —— **留作下一轮候选** |