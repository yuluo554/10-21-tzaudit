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

*（本版发布后补记）*

### 2.1 附件与复核

*（本版发布后补记）*

### 2.2 CI 实跑结论

*（本版 push 后补记；含 run 编号、5/5 或 6/6 job 结论、Node20 注解计数）*

### 2.3 阶段 7 覆盖对账（M6.1）

*（本版发布后补记）*