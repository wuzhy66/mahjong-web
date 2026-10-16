"""将不完整视觉 JSON 补成可校验的假设局面，保留修复记录。"""
from collections import Counter
import json
import random
import secrets

from pydantic import Field, ValidationError

from .decision import DecisionRequest, Meld, StrictModel
from .hangzhou import TILES


class RepairRequest(StrictModel):
    input: dict
    seed: int | None = Field(default=None, strict=True, ge=0, le=2**53-1)


ALIASES = dict(zip(['东', '南', '西', '北', '中', '发', '白'], TILES[27:]))
ALIASES.update(dict(zip(['东风', '南风', '西风', '北风', '红中', '发财', '白板'], TILES[27:])))
for suit, code in [('万', 'm'), ('筒', 'p'), ('条', 's')]:
    for i, numeral in enumerate('一二三四五六七八九', 1):
        ALIASES[numeral + suit] = code + str(i)
        ALIASES[str(i) + suit] = code + str(i)


def tile(value):
    if not isinstance(value, str):
        return None
    value = ALIASES.get(value.strip(), value.strip().lower())
    return value if value in TILES else None


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def changes(before, after, path=''):
    """只回传允许字段的新值；删除字段不回显内容，避免记录暗牌。"""
    if type(before) == type(after) and before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() - after.keys()):
            result.append(dict(path=path + '/' + str(key), operation='remove'))
        for key, value in after.items():
            if key not in before:
                result.append(dict(path=path + '/' + str(key), operation='add', value=value))
            else:
                result.extend(changes(before[key], value, path + '/' + str(key)))
        return result
    if isinstance(before, list) and isinstance(after, list):
        result = []
        for i in range(max(len(before), len(after))):
            if i >= len(after):
                result.append(dict(path=f'{path}/{i}', operation='remove'))
            else:
                result.extend(changes(before[i] if i < len(before) else None, after[i], f'{path}/{i}'))
        return result
    return [dict(path=path, operation='replace', value=after)]


def repair(body):
    if len(json.dumps(body.input, ensure_ascii=False)) > 64000:
        raise ValueError('修复输入不能超过 64000 字符')
    seed = body.seed if body.seed is not None else secrets.randbits(53)
    rng = random.Random(seed)
    raw = body.input
    if isinstance(raw.get('decision_request'), dict):
        raw = raw['decision_request']
    if 'observation' not in raw:
        raw = dict(observation=raw)
    try:
        ready = DecisionRequest.model_validate(raw)
        return ready, dict(seed=seed, repaired=False, hand_changed=False, changes=[])
    except ValidationError:
        pass
    obs = raw.get('observation')
    obs = obs if isinstance(obs, dict) else {}
    strategy = raw.get('strategy')
    if strategy not in ('easy', 'medium', 'hard', 'astra-0'):
        strategy = 'astra-0'
    seat = obs.get('seat')
    seat = seat if integer(seat, 0, 3) else rng.randrange(4)
    players = []
    source_players = obs.get('players')
    source_players = source_players if isinstance(source_players, list) else []
    for s in range(4):
        source = source_players[s] if s < len(source_players) and isinstance(source_players[s], dict) else {}
        melds = []
        for item in (source.get('melds') if isinstance(source.get('melds'), list) else [])[:4]:
            if not isinstance(item, dict):
                continue
            item = {k: v for k, v in item.items() if k in Meld.model_fields}
            item['tiles'] = [tile(t) for t in item.get('tiles', [])] if isinstance(item.get('tiles'), list) else []
            item['claimed_tile'] = tile(item.get('claimed_tile'))
            item.setdefault('from_seat', None)
            try:
                meld = Meld.model_validate(item)
            except ValidationError:
                continue
            if meld.kind == 'chi':
                if sum(m['kind'] == 'chi' for m in melds) >= 2:
                    continue
                meld.from_seat = (s - 1) % 4
            elif meld.from_seat == s:
                meld.from_seat = rng.choice([x for x in range(4) if x != s])
            melds.append(meld.model_dump())
        players.append(dict(discards=[], melds=melds))
    original_hand = obs.get('hand') if isinstance(obs.get('hand'), list) else []
    phase = obs.get('phase')
    if phase not in ('draw', 'response_peng', 'response_chi'):
        phase = 'response_peng' if len(original_hand) == 13 - 3 * len(players[seat]['melds']) and isinstance(obs.get('last_discard'), dict) else 'draw'
    def hand_size():
        return (14 if phase == 'draw' else 13) - 3 * len(players[seat]['melds'])
    hand = []
    used = Counter()
    for t in original_hand[:hand_size()]:
        t = tile(t)
        if t is not None and used[t] < 4:
            hand.append(t); used[t] += 1
        else:
            hand.append(None)
    credits = Counter()
    for s, player in enumerate(players):
        accepted = []
        for meld in player['melds']:
            counts = Counter(meld['tiles'])
            if any(used[t] + n > 4 for t, n in counts.items()):
                continue
            accepted.append(meld)
            used.update(counts)
            if meld['from_seat'] is not None:
                credits[(meld['from_seat'], meld['claimed_tile'])] += 1
        player['melds'] = accepted
    hand += [None] * (hand_size() - len(hand))
    # 为未知手牌和可能需要补入的最近弃牌预留容量。
    missing = hand.count(None)
    budget = 135 - missing
    def available():
        return [t for t in TILES for _ in range(4 - used[t])]
    for s, player in enumerate(players):
        source = source_players[s] if s < len(source_players) and isinstance(source_players[s], dict) else {}
        river = source.get('discards') if isinstance(source.get('discards'), list) else []
        for value in river[:136]:
            t = tile(value)
            if t and credits[(s, t)]:
                credits[(s, t)] -= 1
            elif sum(used.values()) < budget:
                if t is None or used[t] >= 4:
                    t = rng.choice(available())
                used[t] += 1
            else:
                continue
            player['discards'].append(t)
    for (s, t), n in credits.items():
        players[s]['discards'].extend([t] * n)
    for i, t in enumerate(hand):
        if t is None:
            hand[i] = rng.choice(available()); used[hand[i]] += 1
    last = obs.get('last_discard')
    last = last if isinstance(last, dict) else None
    if phase != 'draw' or last is not None:
        source = last.get('seat') if last else None
        if not integer(source, 0, 3) or (phase != 'draw' and source == seat):
            source = rng.choice([s for s in range(4) if phase == 'draw' or s != seat])
        if phase == 'response_chi':
            source = (seat - 1) % 4
        river = players[source]['discards']
        t = tile(last.get('tile')) if last else None
        if river and (t is None or t == river[-1] or used[t] >= 4):
            t = river[-1]
        else:
            if t is None or used[t] >= 4:
                t = rng.choice(available())
            river.append(t); used[t] += 1
        last = dict(seat=source, tile=t)
    def number(name, low, high):
        value = obs.get(name)
        return value if integer(value, low, high) else rng.randint(low, high)
    def boolean(name):
        value = obs.get(name)
        return value if type(value) is bool else bool(rng.getrandbits(1))
    chain = number('chain_count', 0, 136) if integer(obs.get('chain_count'), 0, 136) else rng.randint(0, 6)
    piao = number('piao', 0, chain)
    catch = boolean('catch_play')
    drawn = tile(obs.get('drawn_tile'))
    if phase != 'draw':
        drawn = None
    elif drawn not in hand:
        drawn = None if obs.get('drawn_tile', 'missing') is None and not catch else rng.choice(hand)
    repaired = dict(schema_version=1, strategy=strategy, observation=dict(
        rule_id='hangzhou', seat=seat, dealer=number('dealer', 0, 3),
        turn=seat if phase == 'draw' else last['seat'], phase=phase, hand=hand,
        drawn_tile=drawn, last_discard=last, drawable=number('drawable', 0, 63),
        baotou=boolean('baotou'), chain_count=chain, piao=piao, catch_play=catch,
        players=players, public_events=None))
    # 已有完整历史只有通过同一严格校验才保留，不随机编造事件序列。
    if obs.get('public_events') is not None:
        repaired['observation']['public_events'] = obs['public_events']
        try:
            DecisionRequest.model_validate(repaired)
        except ValidationError:
            repaired['observation']['public_events'] = None
    ready = DecisionRequest.model_validate(repaired)
    return ready, dict(seed=seed, repaired=True, hand_changed=original_hand != hand,
                      changes=changes(raw, ready.model_dump()))
