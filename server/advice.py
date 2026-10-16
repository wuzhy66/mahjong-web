"""用显式可见信息解释策略结果；LLM Gateway 凭据与思考内容不下发客户端。"""
import asyncio
import json
import os
from pathlib import Path

import httpx

from .hangzhou import TILES, tile_name

MODEL = 'deepseek-flash'
SYSTEM_PROMPT = '''你是杭州麻将的牌局讲解助手。策略模型已经给出了合法动作概率和推荐动作，你负责由果推因，解释这个推荐。
这些概率是策略对动作的选择分布，不是胜率、胡牌率、收益率或确定性的置信度。
只使用当前输入中的本家手牌与公开信息；对手暗手和未摸牌墙未知，不推断它们的具体内容。
给出的推荐来自策略输出，并不包含模型内部的真实推理过程；你只能给出与可见牌形相符的合理解释，不要声称还原了模型思考。
保持推荐动作不变，不擅自提出另一张牌为首选。先核对手牌，再结合具体对子、搭子、孤张或副露解释取舍；每张实体牌只能使用一次。不必复述整副手牌。
信息不足时明确说明，禁止编造听口、向听数、剩余张数、胜率、对手听牌或确定的收益。接近的动作概率可以说明模型选择较接近。
本桌规则：白板是财神，不能吃碰杠，可以打出；红中和发财是普通字牌。只能自摸，不能点炮或抢杠胡；最多两摊吃，七对要求没有任何副露。
打白板会触发抓打圈；其他玩家只能打刚摸的牌，仍可自摸或暗杠。具体允许的操作以输入合法动作列表为准。
留20张，赢家接庄，流局连庄；底分1，庄家支付倍率8。1番庄家胡得24分，闲家胡得10分。有财必拷关闭。不套用日麻的役牌、自风、场风、立直或振听规则。
输出中文纯文本，2至4句，总计80至160字，直接解释牌形和取舍，不写标题、表格、动作编号、Markdown或内部思考。
优先解释推荐理由；必要时用一句比较一个主要备选。对于吃碰杠胡或过，解释对应操作，不强行讲成弃牌。'''


def _tile(code):
    return tile_name(TILES.index(code))


def advice_context(snapshot, hint):
    """只读白名单字段；即使视图意外带入暗牌，也不读取其他玩家的 hand。"""
    probabilities = {a['id']: a['probability'] for a in hint['actions']}
    actions = [dict(action=a['label'], kind=a['kind'], probability=probabilities[a['id']])
               for a in snapshot['legalActions']]
    if not actions:
        raise ValueError('没有可解释的合法动作')
    recommended = max(actions, key=lambda a: a['probability'])
    players = []
    for player in snapshot['players']:
        players.append(dict(seat=player['seat'], score=player['score'],
                            discards=[_tile(t) for t in player['discards']],
                            melds=[dict(kind=m['type'], tiles=[_tile(t) for t in m['tiles']],
                                        from_seat=m.get('from')) for m in player['melds']]))
    hero = snapshot['players'][0]
    drawn_index = hero.get('drawnTileIndex', -1)
    last = snapshot.get('lastDiscard')
    return dict(my_seat=0, dealer=snapshot['dealer'], round=snapshot['round'],
                hand=[_tile(t) for t in hero['hand']],
                drawn_tile=_tile(hero['hand'][drawn_index]) if 0 <= drawn_index < len(hero['hand']) else None,
                drawable=snapshot['drawable'], players=players,
                last_discard=dict(tile=_tile(last['tile']), from_seat=last['from']) if last else None,
                strategy=hint['difficulty'], legal_actions=actions,
                recommended_action=recommended,
                note='hand 已含新摸牌，不含副露；相同牌共享动作概率，勿按手牌张数重复相加。牌河已去掉被吃碰杠的来源牌。')


def event(kind, data):
    return 'event: ' + kind + '\ndata: ' + json.dumps(data, ensure_ascii=False) + '\n\n'


class AdviceError(Exception):
    pass


def gateway_settings():
    # 部署凭据放在仓库和 release 之外，仅由服务端读取。
    config = {}
    path = os.environ.get('LLM_GATEWAY_CONFIG_FILE')
    if path:
        try:
            config = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise AdviceError('AI 建议服务配置不可用，概率提示仍可使用。') from None
    base = os.environ.get('LLM_GATEWAY_BASE_URL') or config.get('base_url', '')
    key = os.environ.get('LLM_GATEWAY_API_KEY') or config.get('api_key', '')
    if not isinstance(base, str) or not base.startswith('https://') or not isinstance(key, str) or not key:
        raise AdviceError('AI 建议服务尚未配置，概率提示仍可使用。')
    return base.rstrip('/'), key


class AdviceClient:
    def __init__(self, *, transport=None):
        self.transport = transport
        self.slots = asyncio.Semaphore(4)

    async def stream(self, context):
        base, key = gateway_settings()
        payload = dict(model=MODEL, stream=True, thinking={'type': 'enabled'}, reasoning_effort='low',
                       max_tokens=4096, messages=[dict(role='system', content=SYSTEM_PROMPT),
                       dict(role='user', content=json.dumps(context, ensure_ascii=False))])
        try:
            async with asyncio.timeout(90), self.slots:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), transport=self.transport) as client:
                    async with client.stream('POST', base + '/chat/completions',
                                             headers={'Authorization': 'Bearer ' + key}, json=payload) as response:
                        if response.status_code != 200:
                            raise AdviceError('AI 建议暂时不可用，请稍后重试；概率提示仍可使用。')
                        has_text = False
                        finished = False
                        async for line in response.aiter_lines():
                            if not line.startswith('data:'):
                                continue
                            raw = line[5:].strip()
                            if raw == '[DONE]':
                                finished = True
                                break
                            data = json.loads(raw)
                            if data.get('error'):
                                raise AdviceError('AI 建议生成失败，请稍后重试。')
                            choices = data.get('choices') or []
                            if not choices:
                                continue
                            choice = choices[0]
                            text = (choice.get('delta') or {}).get('content')
                            # reasoning_content 只用于网关推理，不展示或记录。
                            if isinstance(text, str) and text:
                                has_text = True
                                yield text
                            reason = choice.get('finish_reason')
                            if reason is not None:
                                if reason != 'stop':
                                    raise AdviceError('AI 建议未生成完整，请重试；概率提示仍可使用。')
                                finished = True
                        if not has_text or not finished:
                            raise AdviceError('AI 建议未生成完整，请重试；概率提示仍可使用。')
        except (httpx.HTTPError, TimeoutError):
            raise AdviceError('AI 建议连接超时或中断，请重试；概率提示仍可使用。') from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AdviceError('AI 建议返回异常，请重试；概率提示仍可使用。') from None
