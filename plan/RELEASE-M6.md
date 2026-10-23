# RELEASE-M6 · tzaudit v0.1.0 发布留档

> 两栏纪律（`plan/05` §五）：**§一 tag 前事实**随 tag 树一起发布，只写"结构 + 复验方法"与
> **不含自指的值**；**§二 tag 后追加**在 tag 之后补记（附件 sha256、tag 对象、run 计数只写在这里）。
> 自指的值（附件 sha256 / tag OID / tag 指向的 commit / 本次 push 的 run 数）**不写进 tag 树**——
> 写一次就失效一次。

---

## 一、tag 前事实

### 1.1 版本

| 项 | 值 | 复验命令 |
|---|---|---|
| 版本号 | `0.1.0` | `py -3.12 -m tzaudit --version` |
| 三处一致 | `src/tzaudit/__init__.py` / `pyproject.toml` / `README.md` 首屏 | `grep -n '0\.1\.0' src/tzaudit/__init__.py pyproject.toml README.md` |
| Python 底线 | 3.8 | `py -3.8 -m pytest` |

### 1.2 已执行的验证（**本地等价校验**；tag 时点未接远端，CI 待首推验证）

| # | 验证 | 方法 | 结论 |
|---|---|---|---|
| 1 | 干净环境四场景 | `git archive` 导出 → 解包到临时目录 → 新建 venv → 按 `README.md` 逐条敲（含"前置条件"三步 fetch/check/bench） | 全通（见 §1.4 逐条输出） |
| 2 | 断网 | `sitecustomize.py` 打桩 `socket.socket.connect` / `connect_ex` / `create_connection` / `getaddrinfo` / `gethostbyname` 一律抛 `NetworkBlocked`；旁证 `netstat -ano` 采样 | 四个子命令全通、零连接（见 §1.5） |
| 3 | 脱敏门 | `py -3.12 tools/check-desensitized.py` | 退 0（4 条规则，见 §1.6） |
| 4 | 布局门 | `py -3.12 tools/check-sprint-layout.py` | 退 0（10 条判据） |
| 5 | 全量测试 | `py -3.12 -m pytest` / `py -3.8 -m pytest`（串行） | 见 §1.7 |
| 6 | 五套件金标 | `py -3.12 bench/run.py --check` | 退 0，`不一致: 0` |
| 7 | 六组 fixture | 各 `data/fixtures/**/gen.py --check` | 全 PASS |
| 8 | 退出码 5 退役 | `grep -r EXIT_NOT_READY src/` | 空 |

### 1.3 提交身份

| 项 | 值 | 复验命令 |
|---|---|---|
| author / committer 邮箱 | `282769740+yuluo554@users.noreply.github.com` | `git log --format='%ae %ce' \| sort -u` |
| tagger 邮箱 | 同上（`git config user.email`，环境未覆盖 `GIT_COMMITTER_EMAIL`） | `git cat-file -p v0.1.0` |

### 1.4 干净环境四场景（复验方法）

```bash
# 0) 从 tag 树导出（tag 之后用 tag 名；发布前用 git write-tree 的 tree 对象）
git archive --format=tar --prefix=tzaudit/ v0.1.0 | tar -x -C /tmp/clean-env
cd /tmp/clean-env/tzaudit
py -3.12 -m venv .venv && ./.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

| 场景 | 命令（`<tree>` = `data/_downloads/slim/2026e`） | 期望 |
|---|---|---|
| 前置 1 | `py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e` | 退 0，五版本各 598 zone |
| 前置 2 | `py -3.12 tools/fetch_tzdb.py --check` | 退 0，10 份下载件 sha256 一致 |
| 前置 3 | `py -3.12 bench/run.py --check` | 退 0，`不一致: 0` |
| 1 | `tzaudit windows --zone America/New_York --year 2026 --zoneinfo <tree>` | GAP `2026-03-08 02:00:00 → 03:00:00` + OVERLAP `2026-11-01 01:00:00 → 02:00:00`，退 0 |
| 1b | `tzaudit windows --all --year 2026 --zoneinfo <tree> --json` | 退 0，`summary.errors == []` |
| 2 | `tzaudit diff --old <a> --new <e> --json` | 退 0，598 zone 比较、24 条变更 |
| 2b | `tzaudit diff ... --window 2000-2030 --json` / `--zone America/Vancouver` | 退 0；Vancouver 落 `future_rule`（`evidence=tail`） |
| 3 | `tzaudit audit --times times.csv --zone America/New_York --zoneinfo <tree> --json` | 退 0；`INVALID=0 GAP=1 OVERLAP=1 OK=1` |
| 3b | `tzaudit audit --times times.csv --zone America/Vancouver --version <a>,<e> --json` | 退 0；`VERSION_CHANGED=1`（两版候选 20:00Z vs 19:00Z） |
| 3c | `tzaudit audit --daily 02:30 --year 2026 --zone America/New_York --zoneinfo <tree> --json` | 退 0；365 行 |
| 3d | 同上但**缺** `--year` | 退 **2**（不默认当前年） |
| 4 | `tzaudit report --from result.json --zoneinfo <tree> --format md --fail-on gap,overlap,history` | 报告头三字段齐；命中 → 退 **1** |
| 4b | 同上 `--format json --fail-on overlap` | 与 Markdown **同退出码**（1） |
| 4c | 结果集缺报告头来源（无 `--zoneinfo`/`--version` 且结果集无 header） | 退 **3** |

> 清单格式：两列 `id,local_time`、**无表头**；一行一个时间戳也可（自动 `line-001`）。
> 表头会被算作 `INVALID`（整体退 4）——这是"坏行不静默跳过"的直接后果，README 已注明。

### 1.5 断网证据（复验方法）

```bash
# 打桩：任何连接/解析都抛 NetworkBlocked
mkdir -p /tmp/netguard
cat > /tmp/netguard/sitecustomize.py <<'EOF'
import socket
class NetworkBlocked(RuntimeError): pass
def _boom(*a, **k):
    raise NetworkBlocked("network access attempted: %r %r" % (a, k))
socket.socket.connect = _boom
socket.socket.connect_ex = _boom
socket.create_connection = _boom
socket.getaddrinfo = _boom
socket.gethostbyname = _boom
EOF
PYTHONPATH=/tmp/netguard <python> -c "import socket; socket.create_connection(('data.iana.org',443))"
# → NetworkBlocked（打桩生效的正向证据）

# 四个子命令各跑一次（windows / diff / audit / report），再跑 version
PYTHONPATH=/tmp/netguard <python> -m tzaudit windows ... --json > /dev/null   # 退 0
PYTHONPATH=/tmp/netguard <python> -m tzaudit diff ... --json > /dev/null      # 退 0
PYTHONPATH=/tmp/netguard <python> -m tzaudit audit ... --json > /dev/null     # 退 0
PYTHONPATH=/tmp/netguard <python> -m tzaudit report ... --fail-on overlap     # 退 1（门禁命中，非网络错）
```

旁证：在子进程存活期间反复采样 `netstat -ano`，统计属于该 PID 的 `ESTABLISHED`/`SYN_SENT` 行数。

### 1.6 脱敏门

`py -3.12 tools/check-desensitized.py` 退 0：4 条规则（盘符绝对路径 / MSYS 用户路径 / 本机用户名 /
回环代理端口），扫全仓文本文件，豁免仅限脚本自身与 `.git/`。

### 1.7 测试与金标

| 通道 | 命令 | 实测（2026-10-22，本机） |
|---|---|---|
| 3.12 | `py -3.12 -m pytest` | **434 passed, 1 skipped**（2872.15 s ≈ 47 分 52 秒） |
| 3.8 | `py -3.8 -m pytest` | **434 passed, 1 skipped**（2980.50 s ≈ 49 分 40 秒）；与 3.12 同数 |
| 金标 | `py -3.12 bench/run.py --check` | 退 0，分母 **7**，`不一致: 0` |
| CI 等价（无 `data/_downloads`） | `py -3.12` / `py -3.8 -m pytest` | **363 passed, 72 skipped** ×2 通道，均退 0 |

> `-q` 已在 `addopts`，**不要**再传 `-q`（会变 `-qq` 而不打印汇总行）。
> **必须串行**：`bench/run.py --check` 与 pytest 并发会读到半写金标而假红；
> 跑测试期间也不得切换提交 / stash / 还原工作树（见 `plan/HANDOFF-M6.md` §5）。

### 1.8 交付形态

| 项 | 内容 |
|---|---|
| 附件 | `git archive --format=tar --prefix=<name>/ v0.1.0 \| gzip -9n` + `SHA256SUMS` |
| 复验方法 | `sha256sum -c SHA256SUMS`；`gh release download` 回下载后 `cmp`；解包树与 `git archive` 树共有文件逐字节比对 |
| 本地副本 | `RELEASE-M6.md` §二 记录文件名与 sha256 |

---

## 二、tag 后追加

> 本节写于 tag 之后，**不随 tag 树发布**（tag 树里只有 §一）。
> 自指的值（tag OID、指向的 commit、附件 sha256、run 编号）只出现在这里。

### 2.0 tag 与 Release

| 项 | 值 |
|---|---|
| tag | `v0.1.0`（annotated） |
| tag 对象 OID | `e770c42efbef9f3e5562746cdfcbb92191e3e16b` |
| tag 指向的 commit | `d05fb8d83e243df07f9154854cdd1da10c839591` |
| tagger | `yuluo554 <282769740+yuluo554@users.noreply.github.com>` |
| Release URL | https://github.com/yuluo554/10-21-tzaudit/releases/tag/v0.1.0 |
| 仓库 | https://github.com/yuluo554/10-21-tzaudit （public） |

### 2.1 附件与复核

| 项 | 值 |
|---|---|
| 附件 1 | `10-21-tzaudit-v0.1.0.tar.gz`（369728 B） |
| 附件 2 | `SHA256SUMS`（94 B） |
| sha256 | `55d2d7c6e063954bc2fbef876d3631040e805cc9711b0d701379e9ecbc501fad` |
| 构建命令 | `git archive --format=tar --prefix=10-21-tzaudit-0.1.0/ v0.1.0 \| gzip -9n` |
| `gzip -9n` 确定性 | 同一条命令重建两次 → `cmp` 逐字节一致 |
| 本地副本 | 仓库外 `dist-release/`（不入仓；**不写进 `.gitignore` 之外的位置**） |
| 回下载 `cmp` | `gh release download v0.1.0` 取回两份附件 → 与本地副本 `cmp` **逐字节一致**；`sha256sum -c SHA256SUMS` → **OK** |
| 解包树 vs `git archive` 树 | 附件解包 **160** 份 / tag 树 **160** 份；**共有且逐字节相等 160**、内容不同 **0**、仅附件侧 **0**、仅 tag 树侧 **0** |
| tag 后提交集合 | `git diff --name-only v0.1.0..HEAD` = `plan/00`、`plan/05`、`plan/06`、`plan/RELEASE-M6.md`、`.gitignore` —— **全部非交付面**（`src/` 与 `pyproject.toml` 零改动） |
| tag 树内含留档 | `git cat-file -e v0.1.0:plan/RELEASE-M6.md` → 通过 |

### 2.2 CI 实跑结论（逐条配对；失败轮次照录，不抹除）

**口径**：本表登记到 `v0.1.0` 发布链路上的**关键轮次**。tag 之后只有 `plan/` 文档的
收尾提交，**每一轮都实测为 success**（同样是 5/5 job：`layout + desensitization gates` +
`pytest {ubuntu,windows} × {3.8,3.12}`）；它们不改交付面，故不逐轮登记条数
（条数随文档修订滚动，写死必失效）。

| run | 事件 | 分支 / tag | head sha | 结论 | 说明 |
|---|---|---|---|---|---|
| #1 | push | `main` | `f06d9e8` | **failure** | 首推即红：4 个 pytest 矩阵全红，`layout + desensitization gates` 绿 |
| #2 | push | `main` | `d05fb8d` | **success** | 修 CI 红因后重推；5/5 job success |
| #3 | push | `v0.1.0`（tag） | `d05fb8d` | **success** | tag run；5/5 job success |
| #4 | push | `main` | `35b0d43` | **success** | tag 后留档提交（附件副本移出版本控制）；5/5 job success |
| #5 | push | `main` | `f3c9758` | **success** | 留档修正（G5 改写 + 提交集合实测）；5/5 job success |
| #6 | push | `main` | `a63e13f` | **success** | 收尾（CI 轮次配对补记）；5/5 job success |

> 复验命令：`gh api repos/yuluo554/10-21-tzaudit/actions/runs --jq '.workflow_runs[] |
> "\(.run_number)\t\(.event)\t\(.head_branch)\t\(.head_sha[0:7])\t\(.conclusion)"'`

**#1 的红因（据实记录）**：`tests/test_audit.py::test_invalid_is_decided_before_gap` 在缺
`data/_downloads/slim` 时退回到 `bc-scenario` 的旧树，却仍按 `America/New_York` 取 zone ——
该 fixture 树里只有 `Zone/Bc`。本地因为有 slim 树（跑过 `fetch_tzdb`）而恒绿，CI 是干净 clone
（没有 downloads）所以四矩阵全红。修法：按树选 zone（有真实树用 `America/New_York`，
无真实树用 `Zone/Bc`，后者在 `2026-03-08 02:30` 同样有 GAP 段），断言不变。
**教训**：本地有 `data/_downloads` 会掩盖"无数据环境"的分支——CI 等价环境必须本地复现过。
修复后本地无 `data/_downloads` 复现：3.12 = 363 passed / 72 skipped，3.8 = 363 passed / 72 skipped。

### 阶段 7 覆盖对账

> 三态：**实现**（tag 树里有实物且可复验）/ **不适用**（本轮明确不做，附理由）/ **待首推**（本地无法验证）。
> 三态行数必须 ≥ 3（`tools/check-sprint-layout.py::LAYOUT.RELEASE` 断言）。

| # | 阶段 7 项 | 三态 | 证据 / 复验 |
|---|---|---|---|
| 1 | 版本号三处一致（`0.1.0`） | 实现 | §1.1；`git show v0.1.0:src/tzaudit/__init__.py` 与 `pyproject.toml` 均为 `0.1.0` |
| 2 | 干净环境四场景 | 实现 | §1.4（`git archive` 解包树 + 新建 venv 逐条实跑） |
| 3 | 断网跑通四子命令 | 实现 | §1.5（`socket` 五入口打桩；`netstat -ano` 逐 PID 采样零连接） |
| 4 | 脱敏门绿 | 实现 | §1.6（4 条规则；CI run #2/#3 的 `layout + desensitization gates` job 亦绿） |
| 5 | 退出码 5 整项退役 | 实现 | `grep -r EXIT_NOT_READY src/` **为空**（M5 退役的发布门证据） |
| 6 | 五套件金标 `--check` 退 0 | 实现 | `py -3.12 bench/run.py --check` → 退 0、`不一致: 0`（分母 7） |
| 7 | 六组 fixture 生成器 `--check` | 实现 | 六组全 PASS（`audit` 6 / `diff` 17 / `windows` 7 / `slim-vs-fat` 4 / `source-vs-wheel` 13 / `posix` 1 份产物） |
| 8 | 发布三件套（tag / Release 附件 / 留档） | 实现 | §2.0 + §2.1 |
| 9 | CI 实跑与跨平台（4 矩阵 × 2 OS） | 实现 | §2.2：run #2 / #3 全绿，含 `ubuntu-latest` 与 `windows-latest` × `3.8` / `3.12` |
| 10 | 首推失败轮次留档 | 实现 | §2.2：run #1 红因与修法逐条记录，未抹除 |

