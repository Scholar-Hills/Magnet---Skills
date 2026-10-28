# 红笔改稿 · 独立网页应用

把一篇通知、邮件、推文或说明稿交进来，先确认「给谁看 / 要达到什么 / 最怕什么」，
再逐句拿到批注：哪一句有问题、为什么、往哪个方向改。改不改由你自己决定。

这个目录是 `red-pen` Skill 的网页外壳。**校验器没有被重写、没有被放宽**：
批注能不能上页面，由仓库里的 `red-pen/scripts/redpen.py review` 说了算。

## 跑起来

```bash
cd apps/red-pen
python3 scripts/sync_engine.py          # 把 red-pen 引擎同步进 engine/（首次必做）
PORT=8787 python3 server.py             # 打开 http://127.0.0.1:8787
```

只需要 Python 3.8+ 标准库，没有任何第三方依赖。

## 模型：三种状态，如实区分

模型调用在**服务端**完成，浏览器里没有任何密钥。按下面的顺序取配置：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | 环境变量 `REDPEN_LLM_BASE_URL` / `REDPEN_LLM_API_KEY` / `REDPEN_LLM_MODEL` | 任意 OpenAI 兼容的 `/chat/completions` 端点 |
| 2 | `apps/red-pen/config.local.json`（已在 `.gitignore`） | 字段同上：`base_url` / `api_key` / `model`，可加 `json_mode`、`allow_mock` |
| 3 | 都没有 | 页面显示「还没有配置模型」，点生成会 503 并说明缺哪一项 |

**模拟通道**：`REDPEN_ALLOW_MOCK=1` 时启用。批注由本地模板生成，每条批语带「【模拟】」前缀，
页面顶部有「模拟批注」标记，结果页有整幅说明。它只用来跑通「收稿 → 校验 → 定位 → 下载」，
**不是模型读稿子写出来的意见，不能当作验收结果**。

```bash
# 真实模型
REDPEN_LLM_BASE_URL=https://api.deepseek.com/v1 \
REDPEN_LLM_API_KEY=sk-... \
REDPEN_LLM_MODEL=deepseek-chat \
PORT=8787 python3 server.py
```

## 和引擎的关系

```
server.py         HTTP 路由、会话隔离、频率限制、任务调度
workspace.py      只通过 CLI 调引擎：init / brief set / context / review / stats / check
llm.py            模型通道 + 提示词 + 解析；返回的批注一律「未校验」
engine_bridge.py  只读：把引擎的定位结果换算成纯文本坐标，供页面渲染
engine/           red-pen 引擎的逐字节副本（scripts/sync_engine.py 同步，MANIFEST.json 记哈希）
static/           前端三件套 + 合成示例
tests/            e2e.py（接口层）、browser.mjs（1440 / 390 两档 + 键盘）
```

几条硬边界：

- **不复制闸门。** 锚定率、引文长度、改法预算、重复引文、形状校验全部由引擎判定。
  应用层只负责把 `[ERROR]` 原话交回页面。
- **不手改产物。** `marks.json` 与 `review.html` 是引擎写的。页面自己排版（用 `draft_text`
  与定位区间重新渲染），下载的文件仍是引擎原样渲染的那一份，可被 `redpen.py check` 复核。
- **不改稿子。** `draft.*` 从 `init` 落地就是只读。用户改稿走同一个 slug 再 `init`，
  引擎把上一版整个归档进 `history/v<N>/`；原样提交不会升版。
- **不替用户重写。** 提示词要求 `fix` 只针对被引那一句，引擎另有长度预算兜底。

## 数据与隐私

- 每个访客一个会话目录：`$REDPEN_DATA_DIR/sessions/<sid>/`，`sid` 是 32 位十六进制随机串，
  存在 HttpOnly Cookie 里。别人的稿件与下载件互相看不到（e2e 里有这条用例）。
- 稿件只用于当次批注。**提交前**在「确认目的」页写明：稿件正文与三条标准会发送给所配置的
  模型服务；校验与报告生成都在服务端本地完成，不上传。
- 服务端日志只记方法、路径、状态码，不记请求体。
- 输入上限 20000 字；交稿 30 次/小时、生成 10 次/小时（按会话），全局同时最多 4 个任务。
- 同一个 `request_id` 重复提交会复用同一个任务，不会重复建。

## 已实测（本轮真实跑过）

```bash
python3 tests/e2e.py        # 38 项：38 通过
node tests/browser.mjs      # 40 项：40 通过（需 playwright-core 与本机 Chromium）
```

覆盖：收稿 → 生成 → 过闸 → 定位 → 下载；改一句生成第 2 版且第 1 版仍可查看；原样提交不升版；
错引文被单列成「未能定位」；形状不合格被引擎拒收且应用如实转述；模型失败后输入保留、换正常
服务可重试成功；未配置模型时 503 并说清缺什么；会话隔离；超长稿件 413；同一 request_id 复用任务；
1440 / 390 两档主流程；键盘 Enter 定位批注；下载件可打开。

**没有测到的**：真实模型的批注质量（当前环境没有可用模型）；跨模型对比；真人试用；
上线后的未登录访问（部署后单独验证）。

## 部署

单端口 HTTP 服务，监听 `$PORT`、绑定 `0.0.0.0`，静态资源由同一个进程提供。

```bash
# 平台侧只需把 PORT 注入进来；模拟通道要开就在启动命令里带上环境变量
REDPEN_ALLOW_MOCK=1 python3 server.py
```

模型配置建议用环境变量注入（不要把密钥写进代码）。若用 `config.local.json`，它会随目录一起
上传到沙箱，但没有任何路由能读到它（静态目录只开放 `static/`）。

## 已知边界

- 只收粘贴文本与 TXT；`.md` / `.docx` / `.html` 引擎支持，但这一版界面没开。
- 一次只处理一篇稿子（一个会话一个 `draft-01` 工作区）。
- 会话数据落在本地磁盘，沙箱重启即失效；没有账号体系，也没有跨设备续看。
- 模拟通道的批语是模板，不针对内容；它只证明链路通，不证明模型好。
