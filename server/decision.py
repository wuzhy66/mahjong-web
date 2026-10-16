"""截图识别后的公开局面 JSON → 合法动作 → 现有 RL 模型。"""
from collections import Counter
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .hangzhou import TILES, tile_name
from .policies import HINT_PRESETS
from hzmj import adapter
from mjenv.spaces import to_id

Tile = Literal[tuple(TILES)]
Seat = Annotated[int, Field(strict=True, ge=0, le=3)]
Count = Annotated[int, Field(strict=True, ge=0, le=136)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Meld(StrictModel):
    kind: Literal['chi', 'peng', 'gang_ming', 'gang_an', 'gang_bu']
    tiles: list[Tile] = Field(min_length=3, max_length=4)
    from_seat: Seat | None
    claimed_tile: Tile | None = Field(description='吃碰明杠所引用的弃牌；补杠填原碰牌，暗杠填 null')

    @model_validator(mode='after')
    def valid_group(self):
        ids = sorted(TILES.index(t) for t in self.tiles)
        if 33 in ids:
            raise ValueError('财神不能组成副露')
        if self.kind == 'chi':
            if len(ids) != 3 or ids[0] >= 27 or ids[-1] // 9 != ids[0] // 9 or ids != list(range(ids[0], ids[0]+3)):
                raise ValueError('吃必须是同花色连续三张')
        elif len(set(ids)) != 1 or len(ids) != (3 if self.kind == 'peng' else 4):
            raise ValueError('碰为三张同牌，杠为四张同牌')
        if self.kind == 'gang_an':
            if self.from_seat is not None or self.claimed_tile is not None:
                raise ValueError('暗杠没有来源弃牌')
        elif self.from_seat is None or self.claimed_tile not in self.tiles:
            raise ValueError('公开副露必须给出来源座位和被吃碰杠的牌')
        return self


class PublicPlayer(StrictModel):
    discards: list[Tile] = Field(max_length=136, description='从旧到新的全部弃牌记录，包含后来被吃碰杠的牌，不能直接用移除来源牌后的视觉牌河代替')
    melds: list[Meld] = Field(max_length=4)


class PublicEvent(StrictModel):
    kind: Literal['tile_discarded', 'chi', 'peng', 'gang']
    seat: Seat
    tile: Tile
    mode: Literal['an', 'ming', 'bu'] | None = None
    is_tedashi: StrictBool | None = Field(default=None, description='弃牌是否手切；摸切为 false，无法识别为 null')

    @model_validator(mode='after')
    def valid_mode(self):
        if (self.kind == 'gang') != (self.mode is not None):
            raise ValueError('只有杠事件需要 mode')
        if self.kind != 'tile_discarded' and self.is_tedashi is not None:
            raise ValueError('仅弃牌事件包含手切/摸切标记')
        return self


class LastDiscard(StrictModel):
    seat: Seat
    tile: Tile


class Observation(StrictModel):
    rule_id: Literal['hangzhou'] = 'hangzhou'
    seat: Seat
    dealer: Seat
    turn: Seat = Field(description='引擎当前回合座位；响应窗口通常仍是弃牌者')
    phase: Literal['draw', 'response_peng', 'response_chi']
    hand: list[Tile] = Field(min_length=1, max_length=14, description='仅本家暗手，包含刚摸牌，不含副露')
    drawn_tile: Tile | None
    last_discard: LastDiscard | None = Field(description='最近一次弃牌，已被吃碰后仍保留该记录；开局可为 null')
    drawable: Annotated[int, Field(strict=True, ge=0, le=63)]
    baotou: StrictBool
    chain_count: Count
    piao: Count
    catch_play: StrictBool = Field(description='抓打圈是否限制本家；发起者豁免时填 false')
    players: list[PublicPlayer] = Field(min_length=4, max_length=4, description='绝对座位 0、1、2、3 顺序；不能提供对手手牌')
    public_events: list[PublicEvent] | None = Field(default=None, max_length=512,
        description='当前整局从旧到新的全部弃牌/吃/碰/杠事件；未维护历史填 null，不能填空列表冒充无历史')

    @model_validator(mode='after')
    def consistent(self):
        hero = self.players[self.seat]
        own_turn = self.phase == 'draw'
        if own_turn and self.turn != self.seat:
            raise ValueError('只能请求本家当前决策')
        if len(self.hand) != (14 if own_turn else 13) - 3 * len(hero.melds):
            raise ValueError('本家手牌张数与阶段、副露数不一致')
        if self.drawn_tile is not None and (not own_turn or self.drawn_tile not in self.hand):
            raise ValueError('新摸牌必须属于当前出牌回合的本家手牌')
        if self.catch_play and own_turn and self.drawn_tile is None:
            raise ValueError('抓打圈出牌必须明确刚摸的牌')
        if self.piao > self.chain_count:
            raise ValueError('飘次数不能大于动作链次数')
        if not own_turn:
            if self.last_discard is None or self.last_discard.seat == self.seat or self.turn != self.last_discard.seat:
                raise ValueError('响应窗口必须给出他家的当前弃牌及回合')
            if self.phase == 'response_chi' and self.seat != (self.last_discard.seat + 1) % 4:
                raise ValueError('只能吃上家的牌')
        if self.last_discard and (not self.players[self.last_discard.seat].discards or
                self.players[self.last_discard.seat].discards[-1] != self.last_discard.tile):
            raise ValueError('最近弃牌与对应座位弃牌记录不一致')
        seen = Counter(self.hand)
        claims = Counter()
        for seat, player in enumerate(self.players):
            if sum(m.kind == 'chi' for m in player.melds) > 2:
                raise ValueError('每家最多两摊吃')
            seen.update(player.discards)
            for meld in player.melds:
                seen.update(meld.tiles)
                if meld.from_seat is not None:
                    if meld.from_seat == seat or (meld.kind == 'chi' and seat != (meld.from_seat + 1) % 4):
                        raise ValueError('副露来源座位不合法')
                    claims[(meld.from_seat, meld.claimed_tile)] += 1
                    seen[meld.claimed_tile] -= 1
        for (seat, tile), count in claims.items():
            if self.players[seat].discards.count(tile) < count:
                raise ValueError('弃牌记录缺少副露引用的来源牌；请维护完整弃牌历史')
        if any(count > 4 or count < 0 for count in seen.values()):
            raise ValueError('公开牌计数不合法，同种牌最多四张')
        if self.public_events is not None:
            rivers = [[] for _ in range(4)]
            expected = Counter((seat, m.kind if m.kind == 'chi' else 'peng' if m.kind in ('peng', 'gang_bu') else 'ming', m.claimed_tile, m.from_seat)
                               for seat, p in enumerate(self.players) for m in p.melds if m.kind != 'gang_an')
            actual = Counter()
            gangs = Counter()
            previous = None
            for e in self.public_events:
                if e.kind == 'gang':
                    gangs[(e.seat, e.mode, e.tile)] += 1
                if e.kind == 'tile_discarded':
                    rivers[e.seat].append(e.tile)
                    previous = (e.seat, e.tile)
                elif e.kind in ('chi', 'peng') or e.mode == 'ming':
                    if previous is None or previous[1] != e.tile or previous[0] == e.seat:
                        raise ValueError('公开吃碰杠事件没有匹配的来源弃牌')
                    actual[(e.seat, e.kind if e.kind != 'gang' else 'ming', e.tile, previous[0])] += 1
                    previous = None
            if rivers != [p.discards for p in self.players] or actual != expected:
                raise ValueError('公开事件必须覆盖整局，且与弃牌记录、副露一致')
            expected_gangs = Counter((seat, m.kind.removeprefix('gang_'), m.tiles[0])
                for seat, p in enumerate(self.players) for m in p.melds if m.kind.startswith('gang_'))
            if gangs != expected_gangs:
                raise ValueError('公开杠事件与当前杠副露不一致')
            if not own_turn and previous != (self.last_discard.seat, self.last_discard.tile):
                raise ValueError('响应窗口的弃牌已被认领或与公开历史不一致')
        return self


class DecisionRequest(StrictModel):
    schema_version: Literal[1] = 1
    strategy: Literal['easy', 'medium', 'hard', 'astra-0'] = 'astra-0'
    observation: Observation


def to_view(observation):
    view = adapter.GameView()
    view.seat, view.turn, view.dealer = observation.seat, observation.turn, observation.dealer
    view.phase, view.drawable, view.catch_play = observation.phase, observation.drawable, observation.catch_play
    view.drawn_tile = TILES.index(observation.drawn_tile) if observation.drawn_tile is not None else None
    if observation.last_discard:
        view.last_discard = TILES.index(observation.last_discard.tile)
        view.last_discarder = observation.last_discard.seat
    view.responding_seats = [observation.seat] if observation.phase != 'draw' else []
    for seat, (p, raw) in enumerate(zip(view.players, observation.players)):
        p.discards = [TILES.index(t) for t in raw.discards]
        p.melds = [adapter.MeldView(m.kind, min(TILES.index(t) for t in m.tiles),
                    [TILES.index(t) for t in m.tiles], m.from_seat if m.from_seat is not None else seat) for m in raw.melds]
        p.chi_count = sum(m.kind == 'chi' for m in raw.melds)
    hero = view.players[observation.seat]
    for tile in observation.hand: hero.counts[TILES.index(tile)] += 1
    hero.baotou, hero.chain_count, hero.piao = observation.baotou, observation.chain_count, observation.piao
    view.events = None if observation.public_events is None else [dict(kind=e.kind, data=dict(
        seat=e.seat, tile=TILES.index(e.tile), mode=e.mode, is_tedashi=e.is_tedashi)) for e in observation.public_events]
    return view


def describe_action(action, actions, view):
    kind = action[0]
    tile = action[1] if kind in ('discard', 'gang') else view.last_discard if kind in ('chi', 'peng') else None
    used = list(action[1:]) if kind == 'chi' else []
    label = {'discard': '打出', 'gang': '杠', 'peng': '碰', 'chi': '吃', 'hu': '自摸胡牌', 'pass': '过'}[kind]
    mode = action[2] if kind == 'gang' else None
    if mode: label = {'an': '暗杠', 'ming': '明杠', 'bu': '补杠'}[mode]
    if kind == 'chi': label += ' ' + ' '.join(tile_name(t) for t in sorted([tile, *used]))
    elif tile is not None: label += ' ' + tile_name(tile)
    return dict(id=to_id(action, actions), kind=kind, tile=TILES[tile] if tile is not None else None,
                tiles=[TILES[t] for t in used], mode=mode, label=label)


def decide(body, policies):
    view = to_view(body.observation)
    actions = adapter.legal_actions(view, body.observation.seat)
    if not actions:
        raise ValueError('当前局面没有本家可执行的合法动作')
    probabilities, decode = policies.distribution(body.strategy, view, body.observation.seat, actions)
    best = decode(int(probabilities.argmax()), actions)
    if best not in actions:
        raise RuntimeError('模型返回非法动作')
    values = dict.fromkeys(actions, 0.0)
    for index, probability in enumerate(probabilities):
        if probability > 0:
            action = decode(index, actions)
            if action not in values: raise RuntimeError('模型返回非法动作概率')
            values[action] += float(probability)
    result = [dict(**describe_action(a, actions, view), probability=values[a]) for a in actions]
    warnings = []
    if body.observation.public_events is None:
        warnings.append('未提供完整公开动作历史：近期动作、手切/摸切特征缺失；含吃副露时已见牌采用模型原有保守计数，结果可能与完整历史不同。')
    elif body.strategy == 'hard' and any(e.kind == 'tile_discarded' and e.is_tedashi is None for e in body.observation.public_events):
        warnings.append('部分弃牌的手切/摸切未知，historical297 使用未知标记。')
    return dict(schema_version=1, strategy=body.strategy, strategy_name=HINT_PRESETS[body.strategy]['strategy'],
                action=next(r for a, r in zip(actions, result) if a == best), actions=result,
                warnings=warnings, observation_dim=7113 if body.strategy == 'hard' else 6122,
                probability_meaning='合法动作的策略选择概率，不是胜率')
