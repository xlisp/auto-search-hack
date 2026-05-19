# auto-search-hack

为 Claude Code 设计的**自主、授权范围内**的 **系统侦察 + 安全测试** 闭环框架。

> 这个工具最核心的定位是 **"API + 手脚收集器"**：丢给它一个新系统（新工作、新客户、
> 新 CTF box、新 bounty 目标），它在几分钟内给你一份结构化的图景 —— 这个系统暴露
> 了哪些 endpoint、认证模型长什么样、你手上的哪些账号能用、特权边界在哪里漏了。
> "渗透"是把侦察做扎实后的副产物。

> ⚠️ **仅限授权使用。** Bug bounty 公开授权范围、有 SOW 的客户渗透、CTF 比赛、
> 你自己的系统或本地靶机。没有有效的 `scope.yaml`，所有工具都会拒绝运行。

---

## 为什么需要这个

接手一个新项目、入职新公司、开一个 CTF 题、看一个新 bounty target —— 慢的部分
永远是"逆向理解这个系统"：有哪些 endpoint，认证怎么走，给我的测试账号到底能解锁
什么。这个仓库把这个循环自动化了：

- 一个常驻 **skill 规范**（`program.md`）告诉 Claude Code 怎么做事
- `tools/` 里一组**固定的薄工具**（每个都强制走授权门）做实际工作
- 一个 **JSONL 状态目录** 既是 agent 的记忆，也是审计追踪
- Claude 按 `program.md` 描述的状态机循环，直到收敛或预算耗尽

你只需要在仓库里说"看一下 program.md 启动一个 autohack run"，它自己跑下去。

---

## 架构

```
program.md                # Claude 的"游戏规则"，读完即按状态机循环
scope.yaml                # 必需。授权 + 目标 + 预算。.gitignore 中。
tools/
  scope_check.py          # 授权 + scope 校验。所有工具的前置闸。
  http.py                 # 限速 HTTP，全量记日志到 state/http.log.jsonl
  recon.py                # 静态源码分析（context_repos）——零网络流量！
  docs.py                 # 探测 /openapi /swagger /robots /sitemap /.well-known
  discover.py             # 字典枚举（默认用 tools/wordlists/api-paths.txt）
  spider.py               # HTML/JS endpoint 提取（a/form/fetch/axios）
  graphql.py              # GraphQL introspection
  auth.py                 # JWT / cookie / 401 challenge 被动分析
  creds.py                # 凭证测试，三种模式：pairs | combo | common-passwords
  replay.py               # 用捕获到的 JWT 在所有 endpoint 上回放（破坏认证检测）
  wordlists/
    api-paths.txt         # endpoint 默认字典
    common-usernames.txt  # 仅 own_system / ctf 可用（或 aggressive_credentials）
    common-passwords.txt  # 仅 own_system / ctf 可用（或 aggressive_credentials）
state/                    # 全部 JSONL 流式产出 + report.md
  targets.jsonl           # 工作队列
  findings.jsonl          # 结构化发现（最终产物）
  http.log.jsonl          # 每次 HTTP 请求摘要
  creds.log.jsonl         # 凭证尝试（只记 pw_len，永远不存明文密码）
  tokens/<user>.txt       # 捕获的 JWT（gitignored），供 replay.py 使用
  report.md               # 最终人类可读报告
examples/flask-api-project/
  app.py                  # 示例：JWT 认证的 Flask 靶机
  scope.yaml              # 该靶机对应的 scope 配置
  creds.txt               # 示例凭证列表
  sample-run/             # 一次成功运行的基线产物（用于回归对比）
```

---

## 准备工作

```bash
cp scope.example.yaml scope.yaml
$EDITOR scope.yaml          # 填 authorization / targets / budget / context_repos
pip install pyyaml          # 唯一运行时依赖（flask/pyjwt 只是 demo 需要）
# 如需凭证测试：
echo "alice:hunter2" > state/creds.txt
```

---

## 启动

在仓库目录里，打开 Claude Code 然后说：

> Hi，看一下 program.md，启动一个 autohack run。

Claude 会自动：

1. 校验 `scope.yaml`（任何不合法直接拒绝）
2. **Phase 0 静态侦察** —— 跑 `recon.py` 扫 `context_repos`：从源码里提路由、列出
   名字像 `*_TOKEN`/`*_SECRET` 的环境变量键（**只读 key 名，永不读 value**）、
   指向本地 API 文档。这步**零网络流量**，是白嫖的大头
3. 从 `scope.yaml#targets.allow` 播种网络目标
4. 进入循环：选目标 → 选 action → 跑 tool → 解析输出 → 入队子目标 → 写 findings
5. 一旦 `creds.py` 找到有效登录并捕获 JWT，**自动用 `replay.py`** 把这个 token
   在所有已知 endpoint 上回放，找特权边界漏洞
6. 在队列空 / 预算耗尽 / 429 / 用户中断时停
7. 自动写 `state/report.md`

---

## 侦察优先工作流（"手脚收集器"）

如果你有源码访问权（你自己的系统、公司的、有代码访问权的客户）：

```yaml
# scope.yaml
context_repos:
  - /Users/you/projects/target-service
  - /Users/you/projects/target-service-docs
```

`tools/recon.py` 会遍历这些路径并提取：

- **路由**：Flask `@app.route`、FastAPI `@app.get`、Express `app.get(...)`、Django
  `path(...)`、Rails `routes.rb`、Spring `@GetMapping`、`.proto` 里的 `rpc`
- **硬编码 URL**：源码/配置里任何 `https?://...`
- **疑似密钥环境变量名**：匹配 `*_TOKEN|*_SECRET|*_KEY|*_JWT|*_AUTH|*_PASS` 的
  键名 + `file:line`（**值从不读取或打印**）
- **本地文档文件**：`openapi.yaml`、`swagger.json`、`*.postman_collection.json`、
  `API.md`、`README.md` —— 任何描述 API 表面的东西

效果：网络阶段开始前，agent 已经知道这个系统的形状了。生产实战中代码访问权 + recon.py
通常在 10 秒内能挖出比 10 分钟网络扫描更多的 API 表面。

---

## 凭证测试三种模式

| 模式      | 触发参数                                   | 授权门                                                       |
|-----------|--------------------------------------------|--------------------------------------------------------------|
| `pairs`   | 默认 —— 读 `credentials.source`            | 总是允许（你自己给定的 `user:pass` 对）                       |
| `combo`   | `--user-list F --pass-list F`              | 仅 `own_system` / `ctf` —— 或 `aggressive_credentials: true`  |
| `common`  | `--common-passwords --users a,b`           | 仅 `own_system` / `ctf` —— 或 `aggressive_credentials: true`  |

捕获 token 用 `--capture-token-path token` 或 `--capture-token-path data.access_token`，
会自动写到 `state/tokens/<user>.txt`，下一步 `replay.py` 直接 `--token-file` 引用。

内置 wordlist 故意做得很小（冒烟测试级）。真实业务请用 `--wordlist`/`--user-list`/
`--pass-list` 自带的引擎级字典。

---

## JWT 回放检测破坏的授权（broken auth）

一旦拿到任意有效 JWT（哪怕是低权限用户），`replay.py` 会：

1. 读取 `state/tokens/<user>.txt`
2. 把这个 token 用 `Authorization: Bearer ...` 拍到 `state/targets.jsonl` 里所有
   GET endpoint 上
3. 任何 200 即记录为 `auth_replay` finding；命中 `/admin/*` / `/internal/*` /
   `/billing/*` → **high 严重度**（垂直越权候选）

这是发现"前端鉴权后端不校验"类问题最快的方法之一。

---

## 不可绕过的安全栏

| 规则 | 实现位置 |
|------|----------|
| 所有 HTTP 请求前强制走 `scope_check.py` | `tools/http.py` |
| OOS host / deny path 立即 exit 1 | `tools/scope_check.py` |
| 授权过期立即 exit 3 | `tools/scope_check.py` |
| 预算（请求数 / 发现数）耗尽 exit 4 | `tools/scope_check.py` |
| `DELETE/PUT/PATCH/POST` 需 `--confirm-destructive` + chat 二次确认 | `tools/http.py` + `program.md §6` |
| 429 → 整轮停止，不重试放大 | `tools/http.py` 返回 exit 7 |
| `bug_bounty` / `client_pentest` 默认拒绝 combo / common-passwords | `tools/creds.py` |
| 凭证默认仅来源 `scope.yaml#credentials.source` | `tools/creds.py` |
| findings / 日志中**永不**存明文密码（只记 `pw_len`） | `creds.py` |
| 重定向 / spider 到 OOS host → 记录为 `oos_sighting`，绝不跟进 | `spider.py` + agent 状态机 |
| `recon.py` **只读 env key 名**，永不读 value | `tools/recon.py` |
| 捕获 token 存 `state/tokens/`，已 gitignore | `creds.py` + `.gitignore` |

---

## 工具速查

| 工具 | 作用 | 典型调用 |
|------|------|---------|
| `tools/recon.py [PATH...]` | 静态分析本地仓库（路由 / URL / 密钥名 / 文档） | `python3 tools/recon.py` |
| `tools/scope_check.py URL` | 授权 + scope + 预算校验 | 由其他工具自动调用 |
| `tools/http.py URL [opts]` | 限速 HTTP，日志入 `http.log.jsonl` | `python3 tools/http.py https://api.x/v1/me` |
| `tools/docs.py BASE` | 探测 openapi/swagger/robots/.well-known | `python3 tools/docs.py https://api.x` |
| `tools/discover.py BASE [--wordlist F]` | 字典 endpoint 枚举 | `python3 tools/discover.py https://api.x` |
| `tools/spider.py URL` | HTML/JS endpoint 提取 | `python3 tools/spider.py https://app.x/` |
| `tools/graphql.py BASE` | GraphQL introspection | `python3 tools/graphql.py https://api.x` |
| `tools/auth.py {jwt\|cookie\|challenge} ARG` | 被动认证分析 | `python3 tools/auth.py jwt eyJhbGc...` |
| `tools/creds.py URL --user-field u --pass-field p [模式]` | 凭证测试 | `python3 tools/creds.py https://api.x/login --user-field email --pass-field pwd` |
| `tools/replay.py --token-file TOK --targets T --label L` | JWT 回放找破坏的授权 | `python3 tools/replay.py --token-file state/tokens/alice.txt --targets state/targets.jsonl --label alice_user` |

---

## 中断与恢复

`state/` 是 append-only —— 所有 JSONL 文件只追加不重写。

- 跑到一半中断，直接重新发"启动一个 autohack run"。
- Claude 会检测 `state/targets.jsonl` 里的 `pending` 项，询问你要**恢复**还是**归档重来**。
- 归档时旧 state 会被移到 `state/archive-<时间戳>/`。

---

## 一句话总结

**Claude Code + `program.md` + 10 个固定工具 + JSONL 状态 = 一个授权范围内可自主循环、
可中断恢复、可审计、可生成结构化报告的 API 侦察 + 渗透 agent。**

授权范围之外的事，框架拒绝做；授权范围之内的事，agent 自己跑到收敛。
