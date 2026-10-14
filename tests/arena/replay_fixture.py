"""独立复盘测试服务：合法回放到可胡牌点，不在生产环境提供入口。"""
import json
from pathlib import Path
from server.app import create_app
from server.rooms import Room
from server.hangzhou import HangzhouRound

class ReplayPolicy:
    def __init__(self, core): self.core = core; self.aid = None
    def choose(self, difficulty, game, seat, actions): return self.core.decode(self.aid, actions)

def factory(rule_id, difficulties, policies):
    info = json.loads(Path(__file__).with_name('scenarios.json').read_text())['hu']
    room = Room(rule_id, difficulties, policies, seed=info['seed'])
    room.core = HangzhouRound(seed=info['seed'], dealer=info['dealer'])
    room.frames = []
    room.record_frame('开局发牌', [])
    replay = ReplayPolicy(room.core)
    room.policies = replay
    for aid in info['actions']:
        replay.aid = aid
        seat, actions = room.core.peek()
        room.step(aid if seat == 0 else None)
        assert room.core.tile_conservation()
    room.policies = policies
    return room

app = create_app(room_factory=factory)
