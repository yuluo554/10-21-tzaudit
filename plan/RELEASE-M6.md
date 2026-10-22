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

| 通道 | 命令 | 期望 |
|---|---|---|
| 3.12 | `py -3.12 -m pytest` | 全绿（`-q` 已在 `addopts`，**不要**再传 `-q`） |
| 3.8 | `py -3.8 -m pytest` | 全绿，与 3.12 同数 |
| 金标 | `py -3.12 bench/run.py --check` | 退 0，分母 > 0，`不一致: 0` |

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

（tag 与 Release 完成后补记：tag 对象 OID、tag 指向的 commit、附件文件名与 sha256、Release URL、
CI run 结论、阶段 7 覆盖对账。）

### 2.1 附件与复核

| 项 | 值 |
|---|---|
| 附件 | 待补记 |
| sha256 | 待补记 |
| 回下载 `cmp` | 待补记 |
| 解包树 vs `git archive` 树 | 待补记 |
| tag 后提交集合是否 ⊆ 非交付面 | 待补记 |

### 2.2 CI 实跑结论

| 事件 | run | 结论 |
|---|---|---|
| 首推 `main` | 待补记 | 待补记 |
| `v*` tag | 待补记 | 待补记 |

### 阶段 7 覆盖对账

> 三态：**实现**（tag 树里有实物且可复验）/ **不适用**（本轮明确不做，附理由）/ **待首推**（本地无法验证）。
> 三态行数必须 ≥ 3（`tools/check-sprint-layout.py::LAYOUT.RELEASE` 断言）。

| # | 阶段 7 项 | 三态 | 证据 / 复验 |
|---|---|---|---|
| 1 | 版本号三处一致（`0.1.0`） | 实现 | §1.1 |
| 2 | 干净环境四场景 | 实现 | §1.4 |
| 3 | 断网跑通四子命令 | 实现 | §1.5 |
| 4 | 脱敏门绿 | 实现 | §1.6 |
| 5 | 退出码 5 整项退役 | 实现 | `grep -r EXIT_NOT_READY src/` **为空**（M5 退役的发布门证据） |
| 6 | 五套件金标 `--check` 退 0 | 实现 | `py -3.12 bench/run.py --check` → 退 0、`不一致: 0` |
| 7 | 发布三件套（tag / Release 附件 / 留档） | 实现 | §2.1 |
| 8 | CI 实跑与跨平台 | 待首推 | §2.2 |
