"""每个房间独立状态、锁和版本；浏览器只拿本家公开视图。"""
import copy
import secrets
import threading
import time

from .rules import get_rule

class Room:
    def __init__(self, rule_id, difficulties, policies, *, seed=None):
        self.id = secrets.token_urlsafe(16)
        self.token = secrets.token_urlsafe(32)
        self.rule = get_rule(rule_id)
        self.difficulties = list(difficulties)
        self.policies = policies
        self.lock = threading.RLock()
        self.revision = 0
        self.round = 1
        self.scores = [0, 0, 0, 0]
        self.touched = time.monotonic()
        self.seed = seed if seed is not None else secrets.randbits(63)
        self.core = self.rule.create(seed=self.seed, dealer=secrets.randbelow(4))
        self.applied_result = False
        self.completed_replay = None
        self.frames = []
        self.record_frame('开局发牌', [])

    def record_frame(self, label, events):
        # 私有明牌状态仅在内存保留，不能通过普通 snapshot 返回。
        state = self.core.view(self.scores, self.difficulties, reveal=True)
        state['legalActions'] = []
        self.frames.append(copy.deepcopy(dict(index=len(self.frames), label=label, events=events,
                                             snapshot=dict(id=self.id, ruleId=self.rule.id, round=self.round,
                                                           revision=self.revision, **state))))

    def replay(self):
        if self.completed_replay is None:
            raise ValueError('本局尚未结束，不能明牌复盘')
        return copy.deepcopy(self.completed_replay)

    def check_revision(self, revision):
        if revision != self.revision:
            raise ValueError('牌局已更新，请刷新状态后重试')

    def hint(self, revision, difficulty):
        self.check_revision(revision)
        seat, actions = self.core.peek()
        if seat != 0:
            raise ValueError('仅在轮到你操作时可以请求 AI 提示')
        values = self.core.probabilities(self.policies, difficulty, seat, actions,
                                         context={'round_no': self.round, 'scores': tuple(self.scores)})
        self.touched = time.monotonic()
        return dict(revision=self.revision, difficulty=difficulty, actions=values)

    def step(self, action_id=None):
        seat, actions = self.core.peek()
        if seat is None:
            raise ValueError('本局已经结束')
        if action_id is not None:
            if seat != 0:
                raise ValueError('尚未轮到你操作')
            action = self.core.decode(action_id, actions)
            if action is None:
                raise ValueError('该动作当前不合法')
        else:
            if seat == 0:
                raise ValueError('请由玩家选择动作')
            action = self.core.choose(self.policies, self.difficulties[seat - 1], seat, actions)
        event_start = self.core.event_count
        self.core.step(action)
        self.revision += 1
        if self.core.finished and not self.applied_result:
            self.scores = [a + b for a, b in zip(self.scores, self.core.result['scores'])]
            self.applied_result = True
        label, events = self.core.describe(seat, action, event_start)
        self.record_frame(label, events)
        if self.core.finished:
            self.completed_replay = dict(round=self.round, frames=self.frames)

    def next_round(self):
        if not self.core.finished:
            raise ValueError('当前对局尚未结束')
        dealer = self.core.result['next_dealer']
        self.seed = secrets.randbits(63)
        self.core = self.rule.create(seed=self.seed, dealer=dealer)
        self.applied_result = False
        self.round += 1
        self.revision += 1
        self.frames = []
        self.record_frame('开局发牌', [])

    def snapshot(self):
        self.touched = time.monotonic()
        return dict(id=self.id, ruleId=self.rule.id, revision=self.revision, round=self.round,
                    replayRound=self.completed_replay["round"] if self.completed_replay else None,
                    **self.core.view(self.scores, self.difficulties))
