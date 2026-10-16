# 公开观测 JSON 决策 API

多模态模型识别画面并维护公开历史 → JSON → 服务端校验、编码和合法动作计算 → RL 模型给出动作。接口无状态，不需要创建房间，不会替用户执行动作，也不调用 LLM。支持当前客户端的杭州麻将规则：白板财神、只能自摸、最多两摊吃、留 20 张、抓打圈及财飘/杠动作链，有财必拷关闭。

## 调用

启动方式见根目录 README。`POST /api/decision` 接收 JSON；`GET /api/decision/schema` 返回完整输入 JSON Schema，服务的 OpenAPI 描述位于 `/openapi.json`。

```bash
curl http://localhost:8866/api/decision \
  -H 'Content-Type: application/json' \
  --data-binary @examples/decision-request.json
```

[完整请求示例](../examples/decision-request.json) 可直接调用。Python 调用示例：

```python
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

base = os.environ.get('MAHJONG_API_URL', 'http://localhost:8866').rstrip('/')
body = json.loads(Path('examples/decision-request.json').read_text(encoding='utf-8'))
# 用视觉识别及历史跟踪结果替换 body['observation']。
request = Request(base + '/api/decision', data=json.dumps(body).encode(),
                  headers={'Content-Type': 'application/json'}, method='POST')
with urlopen(request, timeout=60) as response:
    result = json.load(response)
print(result['action'])
print(result['warnings'])
```

`strategy` 可选：

| 值 | 实际策略 |
| --- | --- |
| `easy` | bc-mortal-v4-0-1 · argmax |
| `medium` | r1-4 · argmax |
| `hard` | historical297 · argmax |
| `astra-0`（默认） | r1-12 + r1-14 + r1-17 · 等权 prob-sum |

## 随机补全后决策

对缺失字段、`null` 手牌或其他不符合输入约束的数据，可调用 `POST /api/decision/repair`。它先修复输入，再通过与严格接口相同的校验，最后调用真实 RL 模型。请求格式：

```json
{
  "seed": 29,
  "input": {
    "hand": [null, null, null, null, null, null, "p1", "p2", "p4", "p6", "p6", "p9", "p8"],
    "uncertain_indices": [1, 2, 3, 4, 5, 6]
  }
}
```

`input` 支持完整决策请求、直接的观测对象、仅含 `hand` 的识别结果，以及带 `decision_request` 对象的视觉模型输出。`seed` 可省略；响应会返回实际使用的 seed。同一版本、同一输入和 seed 得到相同补全结果。

- 尽量保留合法字段和已识别手牌，支持“中”“四万”等中文牌名转换。`null`、未知牌码、超过四张的同种牌，以及缺少的手牌，从剩余合法牌中随机补齐；超出当前阶段所需的手牌会截短。
- 合法的完整请求直接推理。缺少阶段时，只有手牌张数符合响应阶段且提供了弃牌对象，才推断为碰杠响应；其他情况按本家出牌补齐。因此只有 13 张手牌的识别结果也可能随机增加一张，此变化会记录。
- 缺失/非法的座位、剩余张数、布尔状态及动作链使用受约束的随机值；回合、新摸牌、最近弃牌等按相互关系修复。动作链缺失时从 0–6 取值，财飘次数不超过链次数。未支持的策略改用 Astra-0，规则固定杭州麻将。
- 无法使用的副露移除；来源、弃牌记录和牌数冲突按一致性约束修复。无法验证的公开事件历史置为 `null`，不编造整局事件。额外字段移除，他家手牌和牌墙不参与补全。
- **合法牌码但识别错误的牌不会自动纠正**；`uncertain_indices` 仅作为额外字段移除，需要随机替换的位置应在 `hand` 中填 `null`。

响应保留原来的 `action/actions/warnings`，并增加：

| 字段 | 含义 |
| --- | --- |
| `normalized_request` | 已通过严格校验、实际送入 RL 的完整请求，可直接再次提交 `/api/decision` |
| `repair.seed` | 本次补全使用的随机种子，不是牌局发牌 seed |
| `repair.repaired` | 是否执行了修复 |
| `repair.hand_changed` | 本家手牌是否变化，包含中文编码规范化、补牌、替换、截短 |
| `repair.changes` | 按字段路径列出增加、替换及删除操作；删除字段不回显原内容 |

**补全后的决策针对假设局面，不能当作原图真实局面的正确决策。** 随机补牌不提升视觉识别准确率。该模式不会自动执行动作。JSON 语法本身必须可解析、`input` 必须是对象，最大 64000 字符；无效 envelope、超限或非法 seed 仍返回 `422`。原 `POST /api/decision` 保持严格校验。

## 输入约定

最外层为 `schema_version: 1`、`strategy`、`observation`。牌用 `m1`–`m9`（万）、`p1`–`p9`（筒）、`s1`–`s9`（条）、`east/south/west/north/red/green/white`（东南西北中发白）。`white` 为财神。座位按行牌顺序编号 0–3，下家为 `(seat + 1) % 4`；无需把本家旋转为 0，但整局必须一致。

`observation` 字段如下，除 `rule_id`、`public_events` 外均必填，布尔值必须为 JSON `true/false`：

| 字段 | 含义 |
| --- | --- |
| `rule_id` | `hangzhou`，默认值 |
| `seat` / `dealer` | 当前请求决策的本家 / 庄家座位 |
| `turn` | 引擎回合座位；响应他家弃牌时仍填弃牌者 |
| `phase` | `draw`：本家摸牌或吃碰后出牌；`response_peng`：碰/明杠响应；`response_chi`：吃牌响应。由当前合法操作窗口判定，不能把两个响应阶段合并 |
| `hand` | 本家暗手，包含刚摸牌，不含副露；同种牌重复列出。出牌阶段应为 `14 - 3 × 副露数` 张，响应阶段为 `13 - 3 × 副露数` 张 |
| `drawn_tile` | 刚摸的牌，须已包含在 `hand`；吃碰后未摸牌或响应他家时为 `null` |
| `last_discard` | 最近弃牌 `{ "seat": 3, "tile": "p3" }`；即使已被吃碰，也保留该记录；开局没有弃牌时为 `null` |
| `drawable` | 扣除保留牌后还能摸的张数，0–63；不是整个牌墙张数 |
| `baotou` | 原引擎的本家爆头状态，通常在摸牌前更新；不能把摸牌后任意 14 张的胡牌判断当成该状态 |
| `chain_count` | 本家当前连续财飘与杠动作链次数；断链后清零，不是整局累计次数 |
| `piao` | 当前链内财飘次数，不能大于 `chain_count` |
| `catch_play` | 抓打圈是否限制本家；发起者豁免时填 `false` |
| `players` | 按绝对座位 0–3 排列，四个对象，每个只有 `discards` 和 `melds` |
| `public_events` | 当前整局按时间顺序的公开弃牌/吃/碰/杠事件。未维护时填 `null` 或省略；只有确实没有这些动作时才填 `[]` |

`players[].discards` 是**从旧到新的完整弃牌记录，包括后来被吃碰杠走的牌**。画面牌河移除了来源牌时，需要通过历史跟踪补回。各家 `melds` 按形成顺序排列，补杠保留原碰的位置。副露示例：

```json
{
  "kind": "chi",
  "tiles": ["p2", "p3", "p4"],
  "from_seat": 3,
  "claimed_tile": "p3"
}
```

`kind` 支持 `chi/peng/gang_ming/gang_an/gang_bu`，杠列出四张牌。补杠的 `from_seat/claimed_tile` 填原碰的来源；暗杠两者为 `null`，牌面按原环境可见语义提供。不能提供他家暗手或牌墙内容；这些额外字段会被拒绝。

`public_events` 使用以下格式，按真实时间顺序混合排列，不包含摸牌事件：

```json
[
  {"kind": "tile_discarded", "seat": 3, "tile": "p3", "is_tedashi": true},
  {"kind": "chi", "seat": 0, "tile": "p3"},
  {"kind": "tile_discarded", "seat": 0, "tile": "red", "is_tedashi": true},
  {"kind": "gang", "seat": 1, "tile": "s7", "mode": "an"}
]
```

吃/碰/明杠事件的 `tile` 为来源弃牌，杠的 `mode` 为 `an/ming/bu`。弃牌 `is_tedashi=true` 表示手切，`false` 表示摸切，无法判断为 `null`。提供的历史必须覆盖整局，并与当前弃牌记录、副露匹配。

**单张截图不一定足够。** 刚摸牌、被认领的弃牌、动作顺序、爆头/财飘链和抓打圈状态可能需要连续画面或比赛事件流。必需状态无法确认时，识别端应先补充信息，不能编造 `0/false`。允许省略公开事件，但接口会返回 `warnings`；近期动作特征缺失，困难模型的手切/摸切使用未知标记，含吃副露时已见牌沿用原编码器的保守计数，结果可能与完整历史不同。当前接口不会仅凭图片自动恢复这些状态。

## 输出

示例请求实测返回的 `action` 如下（仅摘录推荐动作，概率可能随推理运行库有微小浮点差异）：

```json
{
  "id": 16,
  "kind": "discard",
  "tile": "p8",
  "tiles": [],
  "mode": null,
  "label": "打出 八筒",
  "probability": 0.3830261591155757
}
```

| 字段 | 含义 |
| --- | --- |
| `action` | 真实模型 argmax 解码后的推荐动作，结构与 `actions` 内元素相同 |
| `actions` | 全部合法动作及其 `probability`，概率合计约 1；不包含非法动作 |
| `strategy` / `strategy_name` | 请求策略及实际模型名称 |
| `warnings` | 缺失公开历史等提示；完整观测时通常为空 |
| `observation_dim` | 服务端编码维数：困难为 7113，其余为 6122；调用者无需构造数值向量 |
| `schema_version` / `probability_meaning` | 协议版本与概率含义 |

每个动作包含 `id`、`kind`、`tile`、`tiles`、`mode`、`label`、`probability`：

- `kind`：`discard/chi/peng/gang/hu/pass`。
- `tile`：打出的牌、被吃碰的牌或杠牌；胡/过为 `null`。
- `tiles`：吃牌时从自己暗手拿出的两张牌，其余动作是 `[]`。
- `mode`：杠为 `an/ming/bu`，其余为 `null`。
- `label`：中文动作说明。
- `id`：统一的 74 动作编码，包含当前局面下的吃牌选项；外部执行建议以结构化字段为准。
- `probability`：合法动作选择概率，**不是胜率**。同种牌共享弃牌动作；困难模型的自杠与同牌弃牌共享原始输出槽，解码后概率计入杠。

非法牌数、错误座位、矛盾历史、未支持策略或额外字段返回 HTTP `422`；推理运行异常返回 `503`。接口只校验所提供局面的结构及一致性，不能证明视觉识别结果与真实画面一致。

## 视觉模型提示词模板

配合 `/api/decision/schema` 和跨帧状态使用：

```text
你负责识别杭州麻将画面，输出符合所附 JSON Schema 的决策请求，不负责选择动作。
只使用本家手牌及公开信息；不能猜他家暗手或牌墙。
牌用 m/p/s 数字及 east/south/west/north/red/green/white 编码。
结合此前已确认的公开历史，维护固定座位、完整弃牌记录和副露；被吃碰杠走的弃牌仍保留在记录中。
区分刚摸牌、手切/摸切、出牌与吃碰杠响应阶段，并保留财飘/杠动作链、爆头和抓打圈状态。
已确认的历史不可因当前截图没有显示而丢弃。
无法确认必需字段时先报告缺失信息，不要生成伪造的决策请求。
只有公开事件历史可以缺失，缺失填 null，不要用 [] 冒充无历史。
信息齐全时仅输出 JSON，由服务端计算合法动作和 RL 决策。
```
