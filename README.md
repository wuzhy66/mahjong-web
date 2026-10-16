# Mahjong Web · 杭州麻将

基于 [莲花广麻](https://github.com/BestGuo2020/lianhuaguangdongmahjong) 的 Three.js 牌桌改造。一个真人与三位后台 AI 对局，各座位可独立选择难度。当前只启用杭州麻将，规则注册表保留扩展入口。

## 启动

需要 Git LFS、Node.js 22.12+、Python 3.11+。克隆后先下载模型，在 Linux / WSL 项目目录运行：

```bash
git lfs install
git lfs pull
npm ci
npm run build
python3 -m venv .venv
.venv/bin/pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r server/requirements.txt
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8866
```

访问 http://localhost:8866 。前端开发使用 `npm run dev`，`/api` 默认代理到 8866，可通过 `VITE_API_TARGET` 覆盖。

模型放在 `server/models/`，默认从仓库内加载，不依赖原训练仓库。导出时的调试路径已清理，模型权重与推理输出保持一致；加载前按 `server/models.json` 核对 SHA256，缺失或不匹配时明确报错。前两档使用 ONNX Runtime CPU，historical297 使用 PyTorch CPU 及其原始 7113 维观测 / 41 动作适配；均为合法动作 masked argmax，只在后台推理。可用 `MAHJONG_MODEL_DIR` 指向包含同名模型文件的替代目录。

本地测试扩展可通过 `MAHJONG_LOCAL_POLICY_PROVIDER` 指定 provider 文件，默认关闭。扩展源码和模型放在 Git 忽略的 `local-strategies/`，不进入公开仓库或部署包。

| 难度 | 策略 |
| --- | --- |
| 简单 | bc-mortal-v4-0-1 · argmax |
| 中等 | r1-4 · argmax |
| 困难 | historical297 · argmax |

难度是可修改的产品预设，尚未通过专门的人机体验测试标定；不保证三档强度严格排序。

## 操作与规则

选好三个 AI 后入座。点击手牌选中，再点「出牌」或再次点击同一张牌；吃、碰、杠、胡、过由后台合法动作驱动。牌桌支持滚轮缩放、按住鼠标左键上下左右拖动，以及重置视角。

轮到自己时，可选择简单 / 中等 / 困难 / Astra-0（默认）并点击「AI 提示」，显示合法动作概率，自动选中最高概率的可出手牌，操作仍需自己确认。Astra-0 是 r1-12、r1-14、r1-17 的等权概率集成。分数是合法动作 masked softmax 概率，不是胜率；同种牌共享分数，不可出牌显示「—」。困难模型的自杠与同牌弃牌共享输出槽，概率按模型实际解码计入杠。

概率显示后，`deepseek-flash`（`reasoning_effort=low`）根据推荐动作、本家手牌和公开牌局流式生成解释。解释不代表策略模型的内部推理；生成期间可以继续操作，切换策略或出牌会取消旧建议。网关不可用时仍可使用概率提示。

服务端通过 `LLM_GATEWAY_BASE_URL`（HTTPS）和 `LLM_GATEWAY_API_KEY` 配置兼容 OpenAI Chat Completions 的 LLM Gateway，也可设置 `LLM_GATEWAY_CONFIG_FILE` 指向仓库外的 JSON 文件，包含 `base_url`、`api_key` 两项。凭据文件仅服务用户可读（权限 `600`），不要提交到 Git 或放进前端构建。Supervisor 安装脚本支持 `--llm-gateway-config` 指定该文件。

结算后点击「明牌复盘本局」，可逐步前进 / 后退、拖动进度、自动播放并切换查看四家手牌；每步显示操作及随后自动摸牌。开始下一局后仍可「复盘上一局」，退出复盘会回到当前牌局。仅保留最近一局已完成的复盘，离开房间或服务重启后清除；未结束牌局不能获取明牌记录。刷新当前标签页可恢复牌桌。

136 张无花，白板财神，只能自摸，最多两摊吃，留 20 张；赢家接庄、流局连庄。有财必拷关闭，沿用现有比赛兼容引擎计分（庄家倍率 8）。积分仅作练习。具体规则由 vendored 引擎及 `engine_compat` 决定。

房间保存在单个 Python 进程内，空闲两小时过期；服务重启会丢失牌局。请保持 **单 worker**，当前未提供账号、多真人联网、数据库恢复或公网防滥用。浏览器逐步请求 AI 动作，关闭标签页后不继续自动对局。公开部署前另行配置 TLS 和访问控制。

## JSON 决策 API

`POST /api/decision` 接收本家手牌、公开牌局状态与动作历史，返回推荐动作和全部合法动作概率，默认使用 Astra-0。适用于多模态模型识别画面后的决策调用；不需要创建房间，也不执行出牌。字段约定、截图识别限制及调用示例见 [决策 API](docs/decision-api.md)，完整 JSON Schema 位于 `/api/decision/schema`。

不完整的识别 JSON 可用 `POST /api/decision/repair` 随机补全后决策，传入 `input` 和可选 `seed`。响应包含完整补全输入、修改记录及手牌变化标记；结果仅对应补全后的假设局面。

## 验证与扩展

```bash
.venv/bin/python -m unittest server.test_rooms server.test_policies server.test_replay server.test_hints -v
.venv/bin/python -m unittest server.test_decision server.test_decision_repair -v
.venv/bin/python -m server.smoke_models  # 使用仓库内三个真实模型
npm run typecheck
npm run build
```

浏览器测试运行方法见 [测试说明](tests/arena/README.md)。

房间层只处理访问凭证、版本、累计积分和生命周期。新增玩法实现 `RuleAdapter` / `RuleRound`，负责创建牌局、合法动作、AI 观测与公开视图，再加入 `server/rules.py`；前端共用牌桌协议。不向客户端发送对手暗手、牌墙内容和 seed。

保留上游 LICENSE、资源与历史。原 README 与开发约定位于 `docs/upstream/`，来源记录位于 `server/vendor/SOURCES.json`。本 fork 不沿用上游双分支同步和线上部署流程。
