"""仅供本地回归的独立服务；生产 app 不安装场景入口。"""
import json
from pathlib import Path
from server.app import create_app
from server.rooms import Room
from server.hangzhou import HangzhouRound

scenarios = json.loads(Path(__file__).with_name('scenarios.json').read_text())
queue = iter(['full','chi','peng','gang_an','gang_ming','gang_bu','hu'])
def factory(rule_id,difficulties,policies):
    kind = next(queue)
    info = scenarios.get(kind,dict(seed=297,dealer=0,actions=[]))
    room = Room(rule_id,difficulties,policies,seed=info['seed'])
    room.core = HangzhouRound(seed=info['seed'],dealer=info['dealer'])
    for aid in info['actions']:
        seat,actions = room.core.peek()
        action = room.core.decode(aid,actions)
        assert action is not None
        room.core.step(action)
        assert room.core.tile_conservation()
    room.revision = len(info['actions'])
    if kind != 'full':
        seat,actions = room.core.peek()
        assert seat==0 and room.core.decode(info['target'],actions) is not None
    return room
app = create_app(room_factory=factory)
