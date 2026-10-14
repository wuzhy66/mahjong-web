"""真实模型提示：只读、鉴权、概率归一及自杠共享动作槽。"""
import copy
import pickle
import json
from pathlib import Path
import unittest
import numpy as np
from fastapi.testclient import TestClient
from .app import create_app
from .hangzhou import HangzhouRound
from .policies import Policies, HINT_PRESETS
from .rooms import Room
from mjenv.spaces import to_id

SCENARIOS = json.loads((Path(__file__).resolve().parents[1] / 'tests/arena/scenarios.json').read_text())

def scenario(name):
    info = SCENARIOS[name]
    core = HangzhouRound(seed=info['seed'], dealer=info['dealer'])
    for aid in info['actions']:
        _, actions = core.peek()
        core.step(core.decode(aid, actions))
    return core

class HintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policies = Policies()
        cls.policies.prepare(HINT_PRESETS)

    def test_real_distributions_and_read_only(self):
        cores = [HangzhouRound(seed=1, dealer=0), *(scenario(name) for name in SCENARIOS)]
        for core in cores:
            seat, actions = core.peek()
            before = pickle.dumps(core.game)
            for difficulty in HINT_PRESETS:
                with self.subTest(difficulty=difficulty, actions=actions):
                    result = self.policies.probabilities(difficulty, core.game, seat, actions)
                    self.assertEqual(set(result), set(actions))
                    self.assertAlmostEqual(sum(result.values()), 1, places=12)
                    self.assertTrue(all(np.isfinite(p) and 0 <= p <= 1 for p in result.values()))
                    choice = self.policies.choose(difficulty, core.game, seat, actions)
                    self.assertEqual(result[choice], max(result.values()))
                    self.assertEqual(pickle.dumps(core.game), before)
                    if difficulty == 'hard':
                        for action in actions:
                            if action[0] == 'gang' and action[2] in ('an', 'bu'):
                                discard = next((a for a in actions if a[0] == 'discard' and a[1] == action[1]), None)
                                if discard: self.assertEqual(result[discard], 0)

    def test_astra_is_equal_weight_probability_sum(self):
        # 同时覆盖弃牌和吃碰杠胡：先对每个成员做合法动作 softmax，再等权归一。
        for name in SCENARIOS:
            core = scenario(name)
            seat, actions = core.peek()
            members = [self.policies.probabilities(key, core.game, seat, actions)
                       for key in ('r1-12', 'r1-14', 'r1-17')]
            ensemble = self.policies.probabilities('astra-0', core.game, seat, actions)
            for action in actions:
                self.assertAlmostEqual(ensemble[action], sum(p[action] for p in members)/3, places=12)

    def test_api_guard_and_state_unchanged(self):
        def factory(rule_id, difficulties, policies):
            room = Room(rule_id, difficulties, policies, seed=1)
            room.core = HangzhouRound(seed=1, dealer=0)
            return room
        app = create_app(self.policies, room_factory=factory)
        with TestClient(app) as client:
            catalog = client.get('/api/catalog').json()
            self.assertEqual([d['id'] for d in catalog['difficulties']], ['easy', 'medium', 'hard'])
            self.assertEqual({d['id'] for d in catalog['hintStrategies']}, set(HINT_PRESETS))
            self.assertEqual(client.post('/api/rooms', json={'difficulties':['astra-0']*3}).status_code, 422)
            created = client.post('/api/rooms', json={}).json()
            room = app.state.rooms[created['snapshot']['id']]
            path = '/api/rooms/' + room.id
            headers = {'x-room-token': created['token']}
            payload = dict(revision=room.revision, difficulty='hard')
            before = room.snapshot()
            frames = copy.deepcopy(room.frames)
            self.assertEqual(client.post(path+'/hint', json=payload).status_code, 403)
            self.assertEqual(client.post(path+'/hint', headers=headers, json={**payload, 'revision':999}).status_code, 409)
            self.assertEqual(client.post(path+'/hint', headers=headers, json={**payload, 'difficulty':'bad'}).status_code, 422)
            for difficulty in HINT_PRESETS:
                response = client.post(path+'/hint', headers=headers, json={**payload, 'difficulty':difficulty})
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertEqual(set(data), {'revision', 'difficulty', 'actions'})
                self.assertEqual({a['id'] for a in data['actions']}, {a['id'] for a in before['legalActions']})
                self.assertAlmostEqual(sum(a['probability'] for a in data['actions']), 1)
                self.assertEqual(room.snapshot(), before)
                self.assertEqual(room.frames, frames)
            room.core = HangzhouRound(seed=1, dealer=1)
            self.assertEqual(client.post(path+'/hint', headers=headers, json=payload).status_code, 409)
            room.core = scenario('hu')
            _, actions = room.core.peek()
            room.step(to_id(next(a for a in actions if a[0] == 'hu'), actions))
            self.assertEqual(client.post(path+'/hint', headers=headers, json={**payload, 'revision':room.revision}).status_code, 409)

if __name__ == '__main__': unittest.main()
