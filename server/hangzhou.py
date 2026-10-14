"""杭州规则适配：动作、AI 观测与公开牌桌视图封装在同一边界内。"""
from . import bootstrap
from .policies import PRESETS
from mjenv.core import MahjongCore
from mjenv.spaces import from_id, to_id

TILES = [f'{s}{n}' for s in 'mps' for n in range(1, 10)] + ['east', 'south', 'west', 'north', 'red', 'green', 'white']
MELDS = {'peng': 'peng', 'chi': 'chi', 'gang_ming': 'gang', 'gang_bu': 'gang', 'gang_an': 'angang'}

def tile_name(tile):
    return ('一二三四五六七八九'[tile % 9] + ('万', '筒', '条')[tile // 9]
            if tile < 27 else ('东风', '南风', '西风', '北风', '红中', '发财', '白板')[tile - 27])

class HangzhouRound(MahjongCore):
    def decode(self, action_id, actions):
        return from_id(action_id, actions)

    def choose(self, policies, difficulty, seat, actions):
        return policies.choose(difficulty, self.game, seat, actions)

    def probabilities(self, policies, difficulty, seat, actions, context=None):
        values = policies.probabilities(difficulty, self.game, seat, actions, context=context)
        return [dict(id=to_id(action, actions), probability=values[action]) for action in actions]

    @property
    def event_count(self):
        return len(self.game.events)

    def describe(self, seat, action, event_start):
        names = ['本家', '下家', '对家', '上家']
        def tile(t):
            return f'{t % 9 + 1}{["万", "筒", "条"][t // 9]}' if t < 27 else ['东', '南', '西', '北', '中', '发', '白'][t - 27]
        kind = action[0]
        text = {'discard': '打出', 'peng': '碰', 'chi': '吃', 'gang': '杠', 'hu': '自摸胡牌', 'pass': '过'}[kind]
        if kind in ('discard', 'gang'):
            text = ({'an': '暗杠', 'ming': '明杠', 'bu': '补杠'}[action[2]] if kind == 'gang' else text) + ' ' + tile(action[1])
        events = []
        for event in self.game.events[event_start:]:
            data = event['data']
            if event['kind'] in ('peng', 'chi'):
                text += ' ' + ' '.join(tile(t) for t in sorted([data['tile'], *data.get('used', [])]))
            if event['kind'] == 'tile_drawn':
                events.append(f'{names[data["seat"]]}摸入 {tile(data["tile"])}')
            elif event['kind'] == 'round_ended':
                events.append('流局' if data.get('draw') else '本局结算')
        return names[seat] + text, events

    def view(self, scores, difficulties, *, reveal=False):
        g = self.game
        decision_seat, actions = self.peek()
        players = []
        # 引擎牌河保留被吃碰杠的来源牌，展示层移除这些牌，避免重复出现。
        rivers = [list(p.discards) for p in g.players]
        last_discard = None
        last_discard_id = 0
        for event_id, event in enumerate(g.events):
            kind, data = event['kind'], event['data']
            if kind == 'tile_discarded':
                last_discard = (data['seat'], data['tile'])
                last_discard_id = event_id
            if kind in ('peng', 'chi') or (kind == 'gang' and data.get('mode') == 'ming'):
                if last_discard:
                    source, tile = last_discard
                    rivers[source].remove(tile)
                    last_discard = None
        for seat, player in enumerate(g.players):
            visible = reveal or seat == 0 or g.finished
            hand = [TILES[t] for t in player.tiles_in_hand()] if visible else []
            drawn = -1
            if visible and g.turn == seat and g.drawn_tile is not None and TILES[g.drawn_tile] in hand:
                hand.remove(TILES[g.drawn_tile])
                hand.append(TILES[g.drawn_tile])
                drawn = len(hand) - 1
            melds = [dict(type=MELDS[m.kind], tile=TILES[m.tile], tiles=[TILES[t] for t in m.tiles],
                          **{'from': m.from_seat}, added=m.kind == 'gang_bu') for m in player.melds]
            preset = PRESETS[difficulties[seat - 1]] if seat else None
            players.append(dict(name='你' if seat == 0 else f'{preset["name"]} AI', avatar='', seat=seat,
                                score=scores[seat], hand=hand, concealedTileCount=sum(player.counts),
                                discards=[TILES[t] for t in rivers[seat]], melds=melds, redCount=0,
                                drawnTileIndex=drawn, strategy=preset['strategy'] if preset else '玩家'))
        legal = []
        if decision_seat == 0:
            for a in actions:
                label = {'hu': '胡牌', 'pass': '过', 'peng': '碰', 'chi': '吃', 'gang': '杠', 'discard': '打'}[a[0]]
                if a[0] in ('discard', 'gang'):
                    if a[0] == 'gang':
                        label = {'an': '暗杠', 'ming': '明杠', 'bu': '补杠'}[a[2]]
                    label += ' ' + tile_name(a[1])
                if a[0] == 'peng':
                    label += ' ' + tile_name(g.last_discard)
                if a[0] == 'chi':
                    label += ' ' + ' '.join(tile_name(t) for t in sorted([g.last_discard, *a[1:]]))
                legal.append(dict(id=to_id(a, actions), kind=a[0], label=label,
                                  tile=TILES[a[1]] if a[0] in ('discard', 'gang') else None))
        return dict(dealer=g.dealer, currentPlayer=decision_seat if decision_seat is not None else -1,
                    players=players, legalActions=legal, finished=g.finished, result=g.result,
                    wallCount=g.tail-g.head, drawable=g.drawable, wallHeadDrawn=g.head,
                    lastDiscard=dict(id=last_discard_id, tile=TILES[last_discard[1]], **{'from': last_discard[0]}) if last_discard else None)
