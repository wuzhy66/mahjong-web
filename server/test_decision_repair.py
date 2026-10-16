"""修复必须保留有效输入、受牌数约束、可复现且真实模型可决策。"""
import unittest

from fastapi.testclient import TestClient

from .app import create_app
from .decision import DecisionRequest, to_view
from .decision_repair import RepairRequest, repair
from . import test_decision as fixtures
from .policies import HINT_PRESETS
from hzmj import adapter


class RepairTests(unittest.TestCase):
    def test_valid_engine_states_unchanged(self):
        for core in fixtures.cases():
            seat, _ = core.peek()
            raw = fixtures.public_request(core.game, seat)
            ready, report = repair(RepairRequest(input=raw, seed=7))
            self.assertEqual(ready, DecisionRequest.model_validate(raw))
            self.assertFalse(report['repaired'])

    def test_null_hand_reproducible(self):
        hand = [None]*6 + ['p1','p2','p4','p6','p6','p9','p8']
        raw = {'hand':hand, 'uncertain_indices':list(range(1,7))}
        first = repair(RepairRequest(input=raw, seed=29))
        self.assertEqual(first, repair(RepairRequest(input=raw, seed=29)))
        ready, report = first
        self.assertEqual(ready.observation.hand[6:13], hand[6:13])
        self.assertEqual(len(ready.observation.hand), 14)
        self.assertTrue(report['hand_changed'])
        self.assertNotEqual(ready.observation.hand, repair(RepairRequest(input=raw, seed=30))[0].observation.hand)

    def test_malformed_and_conflicting_states(self):
        broken = [None, {}, [], 7, True, 'unknown']
        cases = list(fixtures.cases())
        for seed in range(60):
            core = cases[seed % len(cases)]
            seat, _ = core.peek()
            raw = fixtures.public_request(core.game, seat)
            keys = list(raw['observation'])
            raw['observation'][keys[seed % len(keys)]] = broken[seed % len(broken)]
            if seed % 3 == 0:
                raw['observation']['hand'] = ['m1']*30 + [None]
            if seed % 4 == 0:
                raw['observation']['players'] = [{'melds':[], 'discards':['m1']*136} for _ in range(4)]
            ready, report = repair(RepairRequest(input=raw, seed=seed))
            DecisionRequest.model_validate(ready.model_dump())
            self.assertTrue(adapter.legal_actions(to_view(ready.observation), ready.observation.seat))
        ready, report = repair(RepairRequest(input={'hand':['中']*14, 'wall':['m1'], 'players':[{'hand':['s1']}]},seed=1))
        self.assertNotIn('wall', ready.observation.model_dump())
        self.assertNotIn('hand', ready.observation.players[0].model_dump())
        self.assertTrue(all('value' not in c for c in report['changes'] if c['operation']=='remove'))

    def test_real_http_decision_for_all_strategies(self):
        with TestClient(create_app()) as client:
            for strategy in HINT_PRESETS:
                raw = {'strategy':strategy, 'observation':{'hand':[None]*6+['p1','p2','p4','p6','p6','p9','p8']}}
                response = client.post('/api/decision/repair', json={'input':raw,'seed':29})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertTrue(result['repair']['hand_changed'])
                strict = client.post('/api/decision',json=result['normalized_request'])
                self.assertEqual(strict.status_code,200,strict.text)
                self.assertEqual(strict.json()['action'],result['action'])
                self.assertEqual(strict.json()['actions'],result['actions'])
                self.assertAlmostEqual(sum(a['probability'] for a in result['actions']),1)
            self.assertEqual(client.post('/api/decision',json=raw).status_code,422)
            self.assertEqual(client.post('/api/decision/repair',json={'input':{},'seed':'29'}).status_code,422)
