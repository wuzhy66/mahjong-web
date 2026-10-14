"""AEC 序列化状态机：把 hzmj.engine.Game 包成「一次只问一个座位」的模型。

杭麻的响应阶段（碰/吃窗口）在平台上是**同时**决策，AEC 要求严格序列。
好在 hzmj.engine 内部已经把响应窗口拆成了有序的 `responding_seats`
（碰窗口按 (s - 打牌者) % 4 排序，吃窗口只有下家），
并用 `responded` 集合累积，全员 pass 才推进 —— 本模块只需复刻
`engine.play_round` 的座位选择逻辑，并把「无人可决策」的中间状态自动跳过。

对外只暴露三件事：
    peek()   -> (seat, actions)  当前该谁决策、可选动作有哪些
    step(a)  执行动作并推进到下一个决策点
    result   局末结算（与 engine.Game.result 同一对象）
"""

from hzmj.engine import (PHASE_CHI, PHASE_DRAW, PHASE_PENG, PHASE_SETTLED,
                         RESERVED_TILES, Game)
from hzmj.tiles import TILE_KINDS, TILES_PER_KIND

MAX_SKIP = 256


class MahjongCore:
    """一局杭州麻将的 AEC 视角封装。"""

    def __init__(self, dealer=0, base=1, you_cai_bi_kao=False, seed=None,
                 wall=None, n_players=4):
        self.n = n_players
        self.you_cai_bi_kao = you_cai_bi_kao
        self.game = Game(dealer=dealer, base=base,
                         you_cai_bi_kao=you_cai_bi_kao, seed=seed, wall=wall,
                         n_players=n_players)
        self._seat = None
        self._acts = []
        self._advance()

    # ---------------- 状态推进 ----------------

    def _advance(self):
        """跳过所有「无需决策」的中间状态，停在下一个决策点或局末。"""
        g = self.game
        for _ in range(MAX_SKIP):
            if g.finished:
                break
            if g.phase == PHASE_DRAW:
                acts = g.legal_actions(g.turn)
                if not acts:
                    g._exhaust()
                    break
                self._seat, self._acts = g.turn, acts
                return
            if g.phase in (PHASE_PENG, PHASE_CHI):
                if not g.responding_seats:
                    g._advance_turn()
                    continue
                pending = [s for s in g.responding_seats
                           if s not in g.responded]
                if not pending:
                    g._do_pass(g.responding_seats[0])
                    continue
                seat = pending[0]
                acts = g.legal_actions(seat)
                if not acts:
                    g.responded.add(seat)
                    continue
                self._seat, self._acts = seat, acts
                return
            break
        if not g.finished:
            g._exhaust()
        self._seat, self._acts = None, []

    def peek(self):
        """(座位, 合法动作列表)；对局结束时返回 (None, [])。"""
        return self._seat, list(self._acts)

    def step(self, action):
        if self._seat is None:
            raise RuntimeError("对局已结束，无可执行动作")
        seat = self._seat
        self.game.step(seat, action)
        self._advance()
        return seat

    # ---------------- 观察 ----------------

    @property
    def finished(self):
        return self.game.finished

    @property
    def result(self):
        return self.game.result

    @property
    def phase(self):
        return self.game.phase

    @property
    def drawable(self):
        return self.game.drawable

    @property
    def wall_remaining(self):
        return self.game.drawable + RESERVED_TILES

    def player(self, seat):
        return self.game.players[seat]

    def seen_by(self, seat):
        """本家视角已见牌：自己手牌 + 全场副露 + 全场弃牌。"""
        seen = [0] * TILE_KINDS
        for i, c in enumerate(self.game.players[seat].counts):
            seen[i] += c
        for p in self.game.players:
            for m in p.melds:
                for t in m.tiles:
                    seen[t] += 1
            for t in p.discards:
                seen[t] += 1
        return seen

    def scores(self):
        r = self.game.result
        return list(r["scores"]) if r else [0] * self.n

    # ---------------- 完整性校验 ----------------

    def tile_conservation(self):
        """全场牌张守恒：手牌 + 副露 + 弃牌 + 未摸牌墙 == 136。

        注意副露里来自他家的那张牌仍留在打出者的弃牌堆里（engine 不做移除），
        因此每个「吃/碰/明杠/补杠」要扣掉 1 张避免重复计数。
        """
        g = self.game
        total = 0
        for p in g.players:
            total += sum(p.counts)
            total += len(p.discards)
            for m in p.melds:
                total += len(m.tiles)
                if m.kind != "gang_an":
                    total -= 1      # 来源牌已计在打出者的弃牌堆中
        wall_left = max(0, g.tail - g.head)
        return total + wall_left == TILE_KINDS * TILES_PER_KIND


def run_core(bots, dealer=0, base=1, you_cai_bi_kao=False, wall=None,
             seed=None, max_steps=4000):
    """用 4 个 hzmj 风格 bot 通过 core 跑完一局（用于与 play_round 对拍）。"""
    core = MahjongCore(dealer=dealer, base=base, you_cai_bi_kao=you_cai_bi_kao,
                       seed=seed, wall=wall)
    steps = 0
    while steps < max_steps:
        seat, acts = core.peek()
        if seat is None:
            break
        steps += 1
        core.step(bots[seat](core.game, seat, acts))
    return core.result


PHASES = (PHASE_DRAW, PHASE_PENG, PHASE_CHI, PHASE_SETTLED)
