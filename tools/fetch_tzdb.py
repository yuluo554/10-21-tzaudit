#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""tzdata 版本包获取器（**构建期**工具；运行期零网络指的是 CLI，不是本脚本）。

产出（全部落在 ``--out``，默认 ``data/_downloads``，已 gitignore）：

  <out>/tzdata<ver>.tar.gz         IANA 源码发布包（不入仓）
  <out>/iana/<ver>/NEWS            解包后的必要文本（M1 入仓到 data/tzdb/<ver>/）
  <out>/iana/<ver>/leap-seconds.list
  <out>/iana/<ver>/version
  <out>/tzdata-<pypi>.whl          PyPI wheel（不入仓）
  <out>/slim/<ver>/                解 wheel 的 ``tzdata/zoneinfo/**`` → slim 树
  <out>/slim/<ver>/provenance.json 该树的 provenance（kind=slim）
  <out>/iana/<ver>/provenance.json IANA 源码包的 provenance（kind=source）

**为什么两个 kind 各自一份 provenance**：``plan/04`` §1.2 要求 ``sha256`` 是**下载包**的
（不是解包树的），而 ``kind`` 决定 ``is_slim`` 语义。金标用的两棵树是 slim（Q1 定案），
所以入仓的 ``data/tzdb/<ver>/provenance.json`` 记 **slim wheel** 的 sha256，并把 IANA 源码包
的 sha256 一起记进 ``source_sha256``，两个来源都可复现。

用法：

  py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e
  py -3.12 tools/fetch_tzdb.py --materialize   # 把入仓件写进 data/tzdb/<ver>/（不联网）
  py -3.12 tools/fetch_tzdb.py --check         # 不联网，只复核已下载件

**失败即退 3**（环境不满足）：不吞异常、不"跳过版本"、不把缺件当成成功。

入仓边界（`plan/04` §一 D1/D2）：``data/tzdb/<ver>/`` 只放**元数据 + 必要文本**——
``provenance.json`` / ``NEWS``（**首版发布块逐字摘录**）/ ``leap-seconds.list`` / ``version``。
编译后的 zoneinfo 树体积大、不可文本审查，留在 ``data/_downloads/slim/<ver>/``（已 gitignore）。
"""

from __future__ import print_function

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import time
import zipfile

EXIT_OK = 0
EXIT_ENV = 3
EXIT_USAGE = 2

BASE_URL = "https://data.iana.org/time-zones/releases"
PYPI_JSON = "https://pypi.org/pypi/tzdata/%s/json"
REQUIRED_TEXT = ("NEWS", "leap-seconds.list", "version")

#: 默认五个版本（与 `plan/04` §一 D1 一致）
DEFAULT_VERSIONS = "2026a,2026b,2026c,2026d,2026e"

#: 单文件重试次数与退避（秒）。**逐文件重试**，不是整批重来。
RETRIES = 3
BACKOFF_SEC = 2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZDB_DIR = os.path.join(ROOT, "data", "tzdb")


# ---------------------------------------------------------------- 基础工具


def sha256_file(path):
    digest = hashlib.sha256()
    with io.open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _download(url, dest, timeout, retries=RETRIES):
    """逐文件下载 + 重试 + 超时。返回 ``(sha256, size)``。

    失败抛 ``RuntimeError``——**不吞异常**（调用方统一退 3）。
    """
    # 延迟 import：本脚本是构建期工具，但把它挂在模块顶部会让"零网络"审计
    # 误以为 src/ 里有网络客户端。保持 import 就近，src/ 仍然零网络。
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    last = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "tzaudit-fetch/0.1"})
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 构建期工具
                data = resp.read()
            tmp = dest + ".part"
            with io.open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            return hashlib.sha256(data).hexdigest(), len(data)
        except (HTTPError, URLError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(BACKOFF_SEC * attempt)
    raise RuntimeError("下载失败（%d 次重试后）: %s -> %s" % (retries, url, last))


# ---------------------------------------------------------------- IANA 源码包


def fetch_source(version, out_dir, timeout):
    """下载 + 解包 IANA 源码包的**必要文本**，写 provenance。"""
    release_dir = os.path.join(out_dir, "iana", version)
    if not os.path.isdir(release_dir):
        os.makedirs(release_dir)

    url = "%s/tzdata%s.tar.gz" % (BASE_URL, version)
    tarball = os.path.join(out_dir, "tzdata%s.tar.gz" % version)
    digest, size = _download(url, tarball, timeout)
    print("  源码包 %s  sha256=%s  %d B" % (os.path.basename(tarball), digest, size))

    # 只取必要文本：其余源文件（africa/europe/...）不入仓也不解。
    with tarfile.open(tarball, "r:gz") as tar:
        members = {}
        for member in tar.getmembers():
            name = os.path.basename(member.name)
            if name in REQUIRED_TEXT and member.isfile():
                members[name] = member
        missing = [n for n in REQUIRED_TEXT if n not in members]
        if missing:
            raise RuntimeError("源码包缺必要文件: %s（%s）" % (", ".join(missing), url))
        for name, member in sorted(members.items()):
            src = tar.extractfile(member)
            target = os.path.join(release_dir, name)
            with io.open(target, "wb") as fh:
                fh.write(src.read())

    declared = io.open(os.path.join(release_dir, "version"), "r", encoding="utf-8").read().strip()
    if declared != version:
        raise RuntimeError("源码包 version 文件是 %r，请求的是 %r" % (declared, version))

    provenance = {
        "version": version,
        "kind": "source",
        "source_url": url,
        "sha256": digest,
        "retrieved": _today(),
        "zones": 0,  # 源码包不是 zoneinfo 树；zones 由 slim 树实测回填
        "notes": "IANA tzdata source release; only NEWS/leap-seconds.list/version extracted",
    }
    with io.open(os.path.join(release_dir, "provenance.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return provenance


# ---------------------------------------------------------------- PyPI slim 树


def _pypi_release(pypi_version, timeout):
    """查 PyPI 的 wheel 记录 → ``(filename, url, sha256)``。"""
    from urllib.request import urlopen

    with urlopen(PYPI_JSON % pypi_version, timeout=timeout) as resp:  # noqa: S310
        doc = json.loads(resp.read().decode("utf-8"))
    for entry in doc.get("urls", []):
        if entry["filename"].endswith(".whl"):
            return entry["filename"], entry["url"], entry["digests"]["sha256"]
    raise RuntimeError("PyPI %s 没有 wheel" % pypi_version)


def _wheel_iana_version(whl_path):
    """从 wheel 的 ``tzdata/__init__.py`` 读 ``IANA_VERSION``（wheel 自带映射，不靠猜）。"""
    with zipfile.ZipFile(whl_path) as zf:
        text = zf.read("tzdata/__init__.py").decode("utf-8")
    for line in text.split("\n"):
        if line.startswith("IANA_VERSION"):
            return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("wheel 里找不到 IANA_VERSION: %s" % whl_path)


def fetch_slim(pypi_version, out_dir, timeout, source_sha256=None, source_url=None):
    """下载 wheel → 解出 ``tzdata/zoneinfo/**`` 成 slim 树 → 写 provenance。

    ``source_sha256`` / ``source_url`` 是**同一 IANA 版本**的源码包凭据。两者一起写进
    slim 树的 provenance——这样"这棵被金标引用的树"能同时回答"哪个 wheel 编的"
    与"对应哪份 IANA 源码"，而 ``sha256`` 字段本身仍严格是**下载包（wheel）**的。
    """
    filename, url, expected = _pypi_release(pypi_version, timeout)
    whl = os.path.join(out_dir, filename)
    digest, size = _download(url, whl, timeout)
    if digest != expected:
        raise RuntimeError("wheel sha256 与 PyPI 记录不符: %s" % filename)
    print("  wheel %s  sha256=%s  %d B" % (filename, digest, size))

    iana_version = _wheel_iana_version(whl)
    tree = os.path.join(out_dir, "slim", iana_version)
    if os.path.isdir(tree):
        shutil.rmtree(tree)
    os.makedirs(tree)

    prefix = "tzdata/zoneinfo/"
    with zipfile.ZipFile(whl) as zf:
        for name in zf.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            rel_path = name[len(prefix):]
            if not rel_path:
                continue
            target = os.path.join(tree, *rel_path.split("/"))
            parent = os.path.dirname(target)
            if not os.path.isdir(parent):
                os.makedirs(parent)
            with io.open(target, "wb") as fh:
                fh.write(zf.read(name))

    zones = _count_zones(tree)
    provenance = {
        "version": iana_version,
        "kind": "slim",
        "source_url": url,
        "sha256": digest,
        "retrieved": _today(),
        "zones": zones,
        "notes": "slim wheel from PyPI tzdata %s" % pypi_version,
        "pypi_version": pypi_version,
    }
    if source_sha256:
        provenance["source_sha256"] = source_sha256
    if source_url:
        provenance["source_url_iana"] = source_url
    with io.open(os.path.join(tree, "provenance.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print("  slim 树 %s: %d zone" % (iana_version, zones))
    return provenance


def _count_zones(tree):
    """实测 zone 数 —— 判据是 **TZif 魔数**，不是文件名（`plan/04` §1.2 的"实测回填"）。"""
    count = 0
    for dirpath, dirnames, filenames in os.walk(tree):
        rel = os.path.relpath(dirpath, tree)
        dirnames[:] = [d for d in dirnames if d not in ("posix", "right", "__pycache__")]
        if rel != "." and rel.split(os.sep)[0] in ("posix", "right"):
            continue
        for name in filenames:
            if name in ("provenance.json",):
                continue
            path = os.path.join(dirpath, name)
            try:
                with io.open(path, "rb") as fh:
                    if fh.read(4) == b"TZif":
                        count += 1
            except (IOError, OSError):
                continue
    return count


# ---------------------------------------------------------------- 离线复核


def check_all(out_dir):
    """**不联网**：复核已下载件的 sha256 与 provenance 一致。

    恒返回 ``(ok, problems, checked, versions)``——**四种返回同一个形状**，
    免得调用方按分支解包（少一种形状就少一处"某个分支没解对"）。
    """
    problems = []
    iana_root = os.path.join(out_dir, "iana")
    slim_root = os.path.join(out_dir, "slim")

    if not os.path.isdir(iana_root):
        return False, ["缺件: %s 不存在（先跑 --versions 下载）" % rel(iana_root)], 0, []

    versions = sorted(d for d in os.listdir(iana_root)
                      if os.path.isdir(os.path.join(iana_root, d)))
    if not versions:
        return False, ["缺件: %s 下没有任何版本目录" % rel(iana_root)], 0, []

    checked = 0
    for version in versions:
        prov_path = os.path.join(iana_root, version, "provenance.json")
        if not os.path.isfile(prov_path):
            problems.append("%s: 缺 provenance.json" % version)
            continue
        prov = json.loads(io.open(prov_path, "r", encoding="utf-8").read())
        tarball = os.path.join(out_dir, "tzdata%s.tar.gz" % version)
        if not os.path.isfile(tarball):
            problems.append("%s: 缺源码包 %s" % (version, rel(tarball)))
        else:
            actual = sha256_file(tarball)
            if actual != prov.get("sha256"):
                problems.append("%s: 源码包 sha256 不符（prov=%s 实际=%s）"
                                % (version, prov.get("sha256"), actual))
            else:
                checked += 1
        for name in REQUIRED_TEXT:
            if not os.path.isfile(os.path.join(iana_root, version, name)):
                problems.append("%s: 缺解包文本 %s" % (version, name))

    # slim 树（金标用的那两棵）
    if not os.path.isdir(slim_root):
        problems.append("缺件: %s 不存在（slim 树未解）" % rel(slim_root))
    else:
        slim_versions = sorted(d for d in os.listdir(slim_root)
                               if os.path.isdir(os.path.join(slim_root, d)))
        if not slim_versions:
            problems.append("缺件: %s 下没有 slim 树" % rel(slim_root))
        for version in slim_versions:
            prov_path = os.path.join(slim_root, version, "provenance.json")
            if not os.path.isfile(prov_path):
                problems.append("slim/%s: 缺 provenance.json" % version)
                continue
            prov = json.loads(io.open(prov_path, "r", encoding="utf-8").read())
            if prov.get("kind") != "slim":
                problems.append("slim/%s: kind=%r（应为 slim）" % (version, prov.get("kind")))
            wheel = os.path.join(out_dir, "tzdata-%s-py2.py3-none-any.whl" % prov.get("pypi_version"))
            if not os.path.isfile(wheel):
                problems.append("slim/%s: 缺 wheel %s" % (version, rel(wheel)))
            else:
                actual = sha256_file(wheel)
                if actual != prov.get("sha256"):
                    problems.append("slim/%s: wheel sha256 不符" % version)
                else:
                    checked += 1
            measured = _count_zones(os.path.join(slim_root, version))
            if measured != prov.get("zones"):
                problems.append("slim/%s: zones 漂移（prov=%s 实测=%d）"
                                % (version, prov.get("zones"), measured))

    return (not problems), problems, checked, versions


def _today():
    """取"抓取当天"（本地日历日）。

    ``SOURCE_DATE_EPOCH`` 存在时读它（可复现构建），否则读本地时钟——
    这是**构建期**工具，不违反"运行期零网络/零时钟"（那条只约束 ``src/``）。
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.strip().isdigit():
        return time.strftime("%Y-%m-%d", time.gmtime(int(epoch.strip())))
    return time.strftime("%Y-%m-%d", time.localtime())


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


# ---------------------------------------------------------------- 入仓（data/tzdb/）


def _first_release_block(news_text):
    """取 NEWS 里**最新一版**的发布块（首个 ``Release <ver>`` 到下一个 Release 之前）。

    逐字保留（含原文缩进与 Unicode 弯引号）——`plan/01` §1.4 直接引用这些句子。
    """
    lines = news_text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.startswith("Release ")]
    if not starts:
        return ""
    begin = starts[0]
    end = starts[1] if len(starts) > 1 else len(lines)
    return "\n".join(lines[begin:end]).rstrip("\n") + "\n"


def materialize(out_dir, tzdb_dir):
    """把 ``data/_downloads`` 里的已下载件整理成**入仓形态**（不联网）。

    写 ``<tzdb>/<ver>/{provenance.json,NEWS,leap-seconds.list,version}``。
    返回 ``(ok, problems)``——缺任何一个版本都算缺件，**不静默跳过**。
    """
    problems = []
    iana_root = os.path.join(out_dir, "iana")
    slim_root = os.path.join(out_dir, "slim")
    if not os.path.isdir(iana_root):
        return False, ["缺件: %s 不存在（先跑 --versions 下载）" % rel(iana_root)]

    versions = sorted(d for d in os.listdir(iana_root)
                      if os.path.isdir(os.path.join(iana_root, d)))
    if not versions:
        return False, ["缺件: %s 下没有任何版本目录" % rel(iana_root)]

    if not os.path.isdir(tzdb_dir):
        os.makedirs(tzdb_dir)

    for version in versions:
        src_dir = os.path.join(iana_root, version)
        dst_dir = os.path.join(tzdb_dir, version)
        if not os.path.isdir(dst_dir):
            os.makedirs(dst_dir)

        # 1) NEWS 只留首版发布块（完整 260KB NEWS 每版本都入仓等于五份重复历史）
        news_src = os.path.join(src_dir, "NEWS")
        if not os.path.isfile(news_src):
            problems.append("%s: 缺 NEWS" % version)
            continue
        news_text = io.open(news_src, "r", encoding="utf-8").read()
        block = _first_release_block(news_text)
        if not block:
            problems.append("%s: NEWS 里找不到 Release 块" % version)
            continue
        _write_text(os.path.join(dst_dir, "NEWS"), block)

        # 2) leap-seconds.list / version 原样
        for name in ("leap-seconds.list", "version"):
            src = os.path.join(src_dir, name)
            if not os.path.isfile(src):
                problems.append("%s: 缺 %s" % (version, name))
                continue
            _write_text(os.path.join(dst_dir, name),
                        io.open(src, "r", encoding="utf-8").read())

        # 3) provenance：以 **slim 树**那份为准（金标引用的就是它），补 source 侧凭据
        slim_prov = os.path.join(slim_root, version, "provenance.json")
        source_prov = os.path.join(src_dir, "provenance.json")
        if not os.path.isfile(slim_prov):
            problems.append("%s: 缺 slim provenance（%s）" % (version, rel(slim_prov)))
            continue
        prov = json.loads(io.open(slim_prov, "r", encoding="utf-8").read())
        if os.path.isfile(source_prov):
            source = json.loads(io.open(source_prov, "r", encoding="utf-8").read())
            prov.setdefault("source_sha256", source.get("sha256"))
            prov.setdefault("source_url_iana", source.get("source_url"))
        if prov.get("kind") != "slim":
            problems.append("%s: provenance kind=%r（应为 slim）" % (version, prov.get("kind")))
        _write_json(os.path.join(dst_dir, "provenance.json"), prov)
        print("  入仓 %s: kind=%s zones=%s" % (version, prov.get("kind"), prov.get("zones")))

    return (not problems), problems


def _write_text(path, text):
    """规范化文本写盘（LF + 结尾换行 + 无 BOM）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _write_json(path, obj):
    """规范化 JSON 写盘（sort_keys + 2 空格 + LF 尾）——与 ``serialize.dumps_json`` 同口径。"""
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


# ---------------------------------------------------------------- CLI


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fetch_tzdb.py",
        description="下载 IANA tzdata 发布包与 PyPI slim wheel，并记录 provenance（构建期工具）",
    )
    parser.add_argument("--versions", default=DEFAULT_VERSIONS,
                        help="逗号分隔的 IANA 版本号（默认 %s）" % DEFAULT_VERSIONS)
    parser.add_argument("--pypi", default=None,
                        help="逗号分隔的 PyPI tzdata 版本（默认按 IANA 版本自推 2026.1..2026.5）")
    parser.add_argument("--out", default="data/_downloads", help="输出目录（默认 data/_downloads）")
    parser.add_argument("--check", action="store_true",
                        help="只校验已下载件的 sha256 与 provenance，不联网")
    parser.add_argument("--materialize", action="store_true",
                        help="把已下载件整理成入仓形态 data/tzdb/<ver>/（不联网）")
    parser.add_argument("--tzdb", default="data/tzdb", help="入仓目录（默认 data/tzdb）")
    parser.add_argument("--timeout", type=int, default=60, help="单文件超时秒数（默认 60）")
    return parser


def _pypi_for(iana_version, overrides):
    """IANA ``2026a`` → PyPI ``2026.1``（``a`` = 当年第 0 个，见 tzdata 包的换算说明）。"""
    if iana_version in overrides:
        return overrides[iana_version]
    letter = iana_version[-1]
    if not letter.isalpha() or letter.lower() < "a" or letter.lower() > "z":
        return None
    year = iana_version[:4]
    return "%s.%d" % (year, ord(letter.lower()) - ord("a") + 1)


def main(argv=None):
    args = build_parser().parse_args(argv)
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    if not versions:
        sys.stderr.write("fetch_tzdb: --versions 不能为空\n")
        return EXIT_USAGE

    out_dir = args.out
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(ROOT, out_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    if args.materialize:
        tzdb_dir = args.tzdb
        if not os.path.isabs(tzdb_dir):
            tzdb_dir = os.path.join(ROOT, tzdb_dir)
        print("fetch_tzdb --materialize: 整理入仓件到 %s" % rel(tzdb_dir))
        ok, problems = materialize(out_dir, tzdb_dir)
        if ok:
            print("fetch_tzdb --materialize: PASS（%s）" % rel(tzdb_dir))
            return EXIT_OK
        print("fetch_tzdb --materialize: FAIL（%d 处）" % len(problems))
        for item in problems:
            print("  FAIL  %s" % item)
        return EXIT_ENV

    if args.check:
        ok, problems, checked, found = check_all(out_dir)
        if ok:
            print("fetch_tzdb --check: PASS（%d 份下载件 sha256 与 provenance 一致；版本: %s）"
                  % (checked, ", ".join(found)))
            return EXIT_OK
        print("fetch_tzdb --check: FAIL（%d 处问题；已一致 %d 份）" % (len(problems), checked))
        for item in problems:
            print("  FAIL  %s" % item)
        return EXIT_ENV

    # 下载模式：任何一步失败都退 3，且**不跳过版本**。
    print("fetch_tzdb: 下载 %d 个版本到 %s" % (len(versions), rel(out_dir)))
    overrides = {}
    if args.pypi:
        pypi_list = [v.strip() for v in args.pypi.split(",") if v.strip()]
        if len(pypi_list) != len(versions):
            sys.stderr.write("fetch_tzdb: --pypi 数量（%d）必须与 --versions（%d）一致\n"
                             % (len(pypi_list), len(versions)))
            return EXIT_USAGE
        overrides = dict(zip(versions, pypi_list))

    failures = []
    for version in versions:
        print("== %s" % version)
        try:
            source = fetch_source(version, out_dir, args.timeout)
        except Exception as exc:
            failures.append("%s 源码包: %s" % (version, exc))
            print("  FAIL  %s" % exc)
            continue
        pypi_version = _pypi_for(version, overrides)
        if pypi_version is None:
            failures.append("%s: 推不出 PyPI 版本号" % version)
            continue
        try:
            slim = fetch_slim(pypi_version, out_dir, args.timeout,
                              source_sha256=source.get("sha256"),
                              source_url=source.get("source_url"))
        except Exception as exc:
            failures.append("%s slim: %s" % (version, exc))
            print("  FAIL  %s" % exc)
            continue
        if slim["version"] != version:
            failures.append("%s: wheel 的 IANA_VERSION 是 %s（不一致）"
                            % (version, slim["version"]))

    if failures:
        print("fetch_tzdb: FAIL（%d 处）—— 不跳过版本，整体退 3" % len(failures))
        for item in failures:
            print("  FAIL  %s" % item)
        return EXIT_ENV

    print("fetch_tzdb: 完成。离线复核请跑 --check")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())