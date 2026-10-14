"""真实模型协议、资源完整性与公开观测隔离回归。"""
import copy
import json
import unittest
from pathlib import Path
import numpy as np
from .policies import Policies, PRESETS
from .hangzhou import HangzhouRound
from mahjong.observation import encode_observation
from mjenv.spaces import action_mask
from historical297_source.observation import encode_observation as encode297
from historical297_source.action_scheme import action_mask as mask297

class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policies = Policies()
        cls.policies.prepare(['easy', 'medium', 'hard'])

    def test_presets_and_real_decisions(self):
        self.assertEqual([p['models'] for p in PRESETS.values()],
                         [['bc-mortal-v4-0-1'], ['r1-4'], ['historical297']])
        core = HangzhouRound(seed=297, dealer=0)
        seat, actions = core.peek()
        self.assertGreater(len(actions), 1)
        for difficulty in PRESETS:
            with self.subTest(difficulty=difficulty):
                self.assertIn(self.policies.choose(difficulty, core.game, seat, actions), actions)

    def test_hidden_information_does_not_change_observation(self):
        core = HangzhouRound(seed=297, dealer=0)
        seat, actions = core.peek()
        original = core.game
        changed = copy.deepcopy(original)
        # 保持公开事件、本家手牌不变，只互换两家暗手并重排未摸牌墙。
        changed.players[1].counts, changed.players[2].counts = changed.players[2].counts, changed.players[1].counts
        changed.wall[changed.head:changed.tail] = list(reversed(changed.wall[changed.head:changed.tail]))
        mask = np.asarray(action_mask(actions), dtype=np.float32)
        np.testing.assert_array_equal(encode_observation(original, seat, mask), encode_observation(changed, seat, mask))
        mask = np.asarray(mask297(actions), dtype=np.float32)
        a = encode297(original, seat, mask, legal_actions=actions, you_cai_bi_kao=False)
        b = encode297(changed, seat, mask, legal_actions=actions, you_cai_bi_kao=False)
        self.assertEqual(a.shape, (7113,))
        np.testing.assert_array_equal(a, b)

    def test_key_actions_replay_legally(self):
        cases = json.loads((Path(__file__).parents[1] / 'tests/arena/scenarios.json').read_text())
        for kind, case in cases.items():
            with self.subTest(kind=kind):
                core = HangzhouRound(seed=case['seed'], dealer=case['dealer'])
                for aid in [*case['actions'], case['target']]:
                    seat, actions = core.peek()
                    action = core.decode(aid, actions)
                    self.assertIn(action, actions)
                    core.step(action)
                    self.assertTrue(core.tile_conservation())
                if kind == 'hu':
                    self.assertTrue(core.finished)
                    self.assertEqual(core.result['winner'], 0)
                    self.assertEqual(sum(core.result['scores']), 0)

if __name__ == '__main__':
    unittest.main()
