"""独立提示测试服务，每次建桌依次进入合法决策点。"""
from server.app import create_app
from server.rooms import Room
from server.hangzhou import HangzhouRound
from server.test_hints import scenario

names = iter(['discard', 'chi', 'peng', 'gang_an', 'gang_ming', 'gang_bu', 'hu'])
def factory(rule_id, difficulties, policies):
    name = next(names)
    room = Room(rule_id, difficulties, policies, seed=1)
    room.core = HangzhouRound(seed=1, dealer=0) if name == 'discard' else scenario(name)
    room.frames = []
    room.record_frame('提示测试决策点', [])
    return room

app = create_app(room_factory=factory)
