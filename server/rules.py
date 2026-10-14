"""规则注册表：协议固定，玩法通过 adapter 扩展。"""
from typing import Protocol
from .hangzhou import HangzhouRound

class RuleRound(Protocol):
    finished: bool
    result: dict
    event_count: int
    def peek(self): ...
    def decode(self, action_id, actions): ...
    def choose(self, policies, difficulty, seat, actions): ...
    def probabilities(self, policies, difficulty, seat, actions): ...
    def step(self, action): ...
    def view(self, scores, difficulties, *, reveal=False): ...
    def describe(self, seat, action, event_start): ...

class RuleAdapter(Protocol):
    id: str
    name: str
    description: str
    def create(self, *, seed: int, dealer: int) -> RuleRound: ...

class HangzhouRules:
    id = 'hangzhou'
    name = '杭州麻将'
    description = '136张无花，白板财神，只能自摸，最多两摊吃；留20张，赢家接庄、流局连庄。采用现有比赛引擎计分（庄家倍率8），有财必拷关闭。'
    def create(self, *, seed, dealer):
        return HangzhouRound(seed=seed, dealer=dealer, base=1, you_cai_bi_kao=False)

DEFAULT_RULE = 'hangzhou'
RULES: dict[str, RuleAdapter] = {'hangzhou': HangzhouRules()}
def get_rule(rule_id):
    if rule_id not in RULES:
        raise ValueError('未启用该麻将规则')
    return RULES[rule_id]
