# 杭州浏览器回归

安装 Python Playwright 与 Chromium，先构建前端。测试服务只绑定 loopback；生产服务没有场景 API。

```bash
npm run build
PYTHONPATH=.:tests/arena .venv/bin/python -m uvicorn fixture_server:app --host 127.0.0.1 --port 8867
# 另一个终端（Python 环境需安装 playwright）
python tests/arena/browser_check.py
```

每次运行浏览器脚本前重新启动 fixture_server，以重置场景顺序。脚本使用真实三档模型、HTTP API 和 production UI，通过按钮完成整局、刷新恢复、结算查看、下一局及吃碰明杠暗杠补杠胡。输出位于 `artifacts/browser-regression/`，失败保留截图。

`scenarios.json` 由 `find_scenarios.py` 从合法对局搜索产生，只记录 seed 和合法动作序列。测试服务从开局逐步回放，不直接修改牌墙、暗手或结算。可通过 `PYTHONPATH=. .venv/bin/python tests/arena/find_scenarios.py` 重新生成。

## 缩放、拖动与明牌复盘

```bash
PYTHONPATH=.:tests/arena .venv/bin/python -m uvicorn replay_fixture:app --host 127.0.0.1 --port 8867
# 另一个终端
python tests/arena/replay_browser.py
```

使用原合法动作序列推进到可胡牌点，再由浏览器胡牌并逐步核对整局历史。检查镜头截图变化、缩放边界和重置、四家手牌、播放 / 暂停、上一局复盘及返回当前局。结果保留在 `artifacts/replay-browser/`。

## AI 提示

```bash
PYTHONPATH=.:tests/arena .venv/bin/python -m uvicorn hint_fixture:app --host 127.0.0.1 --port 8867
# 另一个终端；每次运行前重启测试服务，重置场景顺序
python tests/arena/hint_browser.py
```

覆盖出牌、吃、碰、暗杠、明杠、补杠、胡牌七个决策点，每个分别验证三档真实模型。检查概率显示、推荐选牌、提示不执行动作、切换难度和操作后清除、推理失败重试及窄屏布局；结果在 `artifacts/ai-hint/`。
