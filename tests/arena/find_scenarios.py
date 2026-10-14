"""从合法完整牌局搜索可复现的吃碰杠胡场景，不手改牌墙或暗手。"""
import json
from pathlib import Path
from server.hangzhou import HangzhouRound
from hzmj.bots import GreedyBot
from mjenv.spaces import to_id

found = {}
required = {'chi','peng','gang_an','gang_ming','gang_bu','hu'}
bot = GreedyBot()
for seed in range(2000):
    core = HangzhouRound(seed=seed,dealer=0)
    prefix = []
    for step in range(1500):
        seat, actions = core.peek()
        if seat is None: break
        assert core.tile_conservation()
        if seat == 0:
            for a in actions:
                key = 'gang_'+a[2] if a[0]=='gang' else a[0]
                if key in required-found.keys():
                    found[key] = dict(seed=seed,dealer=0,actions=list(prefix),target=to_id(a,actions),kind=key)
                    print('found',key,'seed',seed,'step',step,flush=True)
        action = next((a for k in ['hu','gang','peng','chi'] for a in actions if a[0]==k),None)
        if action is None: action=bot(core.game,seat,actions)
        prefix.append(to_id(action,actions));core.step(action)
    if required <= found.keys(): break
assert required <= found.keys(),found.keys()
Path(__file__).with_name('scenarios.json').write_text(json.dumps(found,indent=2)+'\n',encoding='utf-8')
