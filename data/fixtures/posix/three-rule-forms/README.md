# fixture · posix/three-rule-forms

**注入了什么**：七条 POSIX TZ 尾串，逐条对应 `plan/03` §三 的测试点与 `data/README.md` §1.6 的技术坑。

| 用例 | 尾串 | 关键断言 |
|---|---|---|
| `west_positive` | `EST5EDT,M3.2.0/2,M11.1.0/2` | `EST5` → **-18000**（不是 +18000） |
| `wall_seconds` | 同上 | `/2` 是墙钟秒 → NY 展开得 **07:00Z**（不是 02:00Z） |
| `no_dst` | `MST7` | `dst is None`，零转换点 |
| `quarter_hour_chatham` | `<+1245>-12:45<+1345>,…` | `+45900`；`2:45` → 9900 秒 |
| `negative_dst_dublin` | `IST-1GMT0,M10.5.0,M3.5.0/1` | 负 DST：起跳走向**更小**偏移 |
| `negative_slash_time` | `<-03>3<-02>,M3.5.0/-2,M10.5.0/-1` | `time_sec` 为**负**，仍按墙钟解释 |
| `default_time` | `EST5EDT,M3.2.0,M11.1.0` | 缺省 `/time` = 7200 秒 |

**为什么需要它**：这三条坑"改对了也看不出"——对称时区（UTC+5 vs UTC-5）在多数断言下同形。
所以金标不只存结果，还存**中间量**：`std_offset_sec` / `dst_offset_sec` / `start_time_sec` /
`end_time_sec` / 展开出的 UTC 秒。只对最终输出断言会让"符号写反"漏过去。

**金标**：`expect.json` 的 `expected.cases` 由 `gen.py` 用手写规则表独立展开，不调产品的 parser。

重建：`py -3.12 data/fixtures/posix/three-rule-forms/gen.py --check`
