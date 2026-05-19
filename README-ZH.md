# auto-search-hack

为 Claude Code 设计的**自主、授权范围内**的 API 发现与安全测试闭环框架。

> ⚠️ **仅限授权使用。** 适用场景：bug bounty 公开授权范围、有 SOW/Rules of Engagement 的客户渗透测试、CTF 比赛环境、你自己的系统或本地靶机（DVWA / Juice Shop / HackTheBox 本地实例等）。
>
> 没有有效的 `scope.yaml`，所有工具都会拒绝运行。

---

## 设计思路

一个由 Claude Code 驱动的"自主黑客"闭环：

- **`program.md`** —— agent 的"skill"（指令集），Claude 读完它就知道整个状态机怎么跑
- **少量固定工具**（`tools/`） —— 薄包装的 Python 脚本，每个工具入口都强制走授权门
- **一个自主循环** —— program.md 第 4 节定义的状态机，Claude 在一个 session 里反复 tick 直到停止条件命中
- **结构化产出**（`state/`） —— append-only JSONL 流，既是 agent 的记忆，也是最终报告

```
auto-search-hack/
├── program.md            # Claude 的"游戏规则"，读完即按状态机循环
├── README.md / README-ZH.md
├── scope.example.yaml    # 授权范围模板（用户拷贝为 scope.yaml）
├── .gitignore            # scope.yaml 与 state/ 中敏感产出默认不入库
├── tools/
│   ├── scope_check.py    # 授权门 + 预算检查（其他所有工具的前置闸）
│   ├── http.py           # 限速、全量记日志的 HTTP；destructive method 需显式确认
│   ├── docs.py           # 探测并解析 /openapi /swagger /robots /sitemap /.well-known
│   ├── discover.py       # 字典枚举（bug bounty / 客户渗透必须自带 wordlist）
│   ├── auth.py           # JWT / cookie / challenge 头的被动分析
│   └── creds.py          # 凭证测试，仅针对 scope 中指定的凭证文件
└── state/                # 全部 JSONL 流式产出
    ├── targets.jsonl     # 工作队列（agent 自维护）
    ├── findings.jsonl    # 结构化发现（最终产物）
    ├── http.log.jsonl    # 每次 HTTP 请求摘要（自动写入）
    ├── creds.log.jsonl   # 每次凭证尝试 + 结果（永不含明文密码）
    ├── run.log           # tick-by-tick 循环日志
    └── report.md         # 停止时自动生成的人类可读报告
```

---

## 准备工作

```bash
# 1. 拷贝并编辑授权范围
cp scope.example.yaml scope.yaml
$EDITOR scope.yaml          # 填入 authorization / targets.allow / targets.deny / budget

# 2. 安装唯一运行时依赖
pip install pyyaml

# 3. 如需做凭证测试：自备凭证清单（user:pass 一行一个）
echo "alice:hunter2" > state/creds.txt
echo "bob:correct horse" >> state/creds.txt
```

`scope.yaml` 的核心字段：

```yaml
authorization:
  type: own_system          # ctf | bug_bounty | client_pentest | own_system
  reference: "本地靶机: juice-shop docker"
  signed_by: "you@example.com"
  expires: 2026-12-31       # 过期后框架直接拒绝运行

targets:
  allow:
    - host: localhost
      ports: [3000]
      paths: ["/*"]
  deny:                     # 默认拦截高危后台路径
    - host: localhost
      paths: ["/admin/*", "/billing/*", "/internal/*"]

rate_limits:
  requests_per_second: 2
  max_concurrent: 1
  backoff_seconds: 30

credentials:
  source: state/creds.txt
  max_attempts_per_account: 5

budget:
  max_findings: 200
  max_runtime_minutes: 90
  max_requests: 5000
```

---

## 启动一次 autohack run

在仓库目录里，打开 Claude Code 然后说：

> Hi，看一下 program.md，启动一个 autohack run。

Claude 会自动按 `program.md` 执行：

1. **授权门**（§0）——校验 `scope.yaml` 存在、type 合法、reference 非空、未过期。任一不满足就直接拒绝。
2. **种子目标**（§7）——从 `targets.allow` 播种到 `state/targets.jsonl`。
3. **进入循环**（§4）——每个 tick：
   - 选最高优先级的 `pending` 目标
   - 按目标当前状态决定 action（`docs` / `discover` / `auth` / `creds` / 分类）
   - 跑对应的 tool，解析输出
   - 新发现的 endpoint 自动入队，深度衰减优先级
   - 结果写入 `findings.jsonl`，目标标记为 `done`
4. **停止条件**（§4a/§6）——队列空 / 预算耗尽 / 429 / 连续 5xx / 用户中断。
5. **写报告** —— `state/report.md`（包含发现汇总、认证模型、凭证矩阵、OOS 旁见、待人工复核项）。

---

## 安全栏（不可绕过）

| 规则 | 实现位置 |
|------|----------|
| 所有 HTTP 请求前强制走 `scope_check.py` | `tools/http.py` 启动时 subprocess 调用 |
| OOS host / deny path 立即 exit 1 | `tools/scope_check.py` |
| 授权过期立即 exit 3 | `tools/scope_check.py` |
| 预算（请求数 / 发现数）耗尽 exit 4 | `tools/scope_check.py` 每次调用都检查 |
| `DELETE/PUT/PATCH/POST` 需 `--confirm-destructive` + 用户 chat 确认 | `tools/http.py` + `program.md §6` |
| 429 → 整轮停止，不重试放大 | `tools/http.py` 返回 exit 7 |
| `bug_bounty` / `client_pentest` 拒绝内置 wordlist | `tools/discover.py` |
| 凭证仅来源 `scope.yaml#credentials.source` | `tools/creds.py` |
| findings / 日志中永不存明文密码 | `creds.py` 只记 `pw_len` + `cred_id` |
| 重定向到 OOS host → 记录但绝不跟进 | `program.md §6` + agent 状态机 |

---

## 工具速查

| 工具 | 作用 | 典型调用 |
|------|------|---------|
| `tools/scope_check.py URL` | 授权 + scope + 预算校验 | 由其他工具自动调用 |
| `tools/http.py URL [--method M] [--header H] [--data D]` | 限速 HTTP，日志入 `http.log.jsonl` | `python3 tools/http.py https://api.x/v1/me` |
| `tools/docs.py BASE` | 探测 openapi/swagger/robots/.well-known，解析 endpoint | `python3 tools/docs.py https://api.x` |
| `tools/discover.py BASE [--wordlist F] [--depth N]` | 字典 endpoint 枚举 | `python3 tools/discover.py https://api.x --wordlist words.txt` |
| `tools/auth.py {jwt\|cookie\|challenge} ARG` | 被动认证分析 | `python3 tools/auth.py jwt eyJhbGc...` |
| `tools/creds.py URL --user-field u --pass-field p` | 凭证测试 | `python3 tools/creds.py https://api.x/login --user-field email --pass-field pwd` |

---

## 中断与恢复

`state/` 是 append-only 的——所有 JSONL 文件只追加不重写。

- 跑到一半中断（Ctrl+C / 网络断 / 时间不够），直接重新发"启动一个 autohack run"指令即可。
- Claude 会检测 `state/targets.jsonl` 里的 `pending` 项，询问你要**恢复**还是**归档重来**。
- 归档时旧 state 会被移到 `state/archive-<时间戳>/`。

---

## 把你已有的项目代码作为线索

如果你正在对一个有源码访问权的目标做评估（自己的系统 / 授权客户的代码），在 `scope.yaml` 中加：

```yaml
context_repos:
  - /Users/you/projects/target-service
  - /Users/you/projects/target-service-docs
```

Claude 在种子和分析阶段会读这些路径下的 swagger 文件、路由定义、文档，把发现的 endpoint 候选 enqueue 进 `targets.jsonl`（仍然受 scope 校验）。这一步比纯黑盒扫快得多，也是把"递归 hack 所有 API"做扎实的关键。

---

## 一句话总结

**Claude Code + `program.md` + 固定工具 + JSONL 状态 = 一个授权范围内可自主循环、可中断恢复、可审计、可生成结构化报告的渗透测试 agent。**

授权范围之外的事，框架拒绝做；授权范围之内的事，agent 自己跑到收敛。
