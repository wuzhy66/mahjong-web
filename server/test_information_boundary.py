"""改变不可见信息时，所有上线策略送入网络的张量必须逐元素不变。"""
import copy
import unittest
import numpy as np
import torch
from .hangzhou import HangzhouRound
from .policies import Policies, HINT_PRESETS
from .test_hints import SCENARIOS, scenario


class InformationBoundaryTests(unittest.TestCase):
    def capture(self, strategy, game, seat, actions):
        captured = []
        class Network:
            def run(self, outputs, inputs):
                captured.append(inputs['obs'].copy())
                return [np.zeros((1, 74), dtype=np.float32)]
            def __call__(self, *inputs):
                captured.extend(x.numpy().copy() for x in inputs)
                return ({'policy_logits': torch.zeros((1, 41))} if strategy == 'hard'
                        else torch.zeros((1, 231)))
        policies = Policies()
        policies.load = lambda _: Network()
        policies.probabilities(strategy, game, seat, actions)
        return captured

    def test_all_strategies_ignore_hidden_information(self):
        cores = [HangzhouRound(seed=297, dealer=seat) for seat in range(4)]
        for name, info in SCENARIOS.items():
            cores.append(scenario(name))
            after = scenario(name)
            _, actions = after.peek()
            after.step(after.decode(info['target'], actions))
            if not after.finished: cores.append(after)
        for core in cores:
            seat, actions = core.peek()
            original = core.game
            # 暗杠沿用原环境可见性；只扰动他家暗手、牌墙及私有发摸牌记录。
            variants = {}
            changed = copy.deepcopy(original)
            for i, p in enumerate(changed.players):
                if i != seat: p.counts[:] = p.counts[1:] + p.counts[:1]
            variants['暗手'] = changed
            changed = copy.deepcopy(original)
            changed.wall[:] = reversed(changed.wall)
            variants['牌墙'] = changed
            changed = copy.deepcopy(original)
            for event in changed.events:
                if event['kind'] in ('tile_drawn', 'tile_dealt') and event['data'].get('seat') != seat:
                    event['data']['tile'] = 0
            variants['私有摸牌事件'] = changed
            for strategy in HINT_PRESETS:
                expected = self.capture(strategy, original, seat, actions)
                for kind, changed in variants.items():
                    with self.subTest(seat=seat, strategy=strategy, hidden=kind):
                        actual = self.capture(strategy, changed, seat, actions)
                        self.assertEqual(len(expected), len(actual))
                        for a,b in zip(expected,actual): np.testing.assert_array_equal(a,b)

    def test_real_model_probabilities_ignore_hand_and_wall(self):
        core = HangzhouRound(seed=297, dealer=0)
        seat, actions = core.peek()
        changed = copy.deepcopy(core.game)
        for player in changed.players[1:]:
            player.counts[:] = player.counts[1:] + player.counts[:1]
        changed.wall[:] = reversed(changed.wall)
        for event in changed.events:
            if event['kind'] in ('tile_drawn', 'tile_dealt') and event['data'].get('seat') != seat:
                event['data']['tile'] = 0
        policies = Policies()
        for strategy in HINT_PRESETS:
            with self.subTest(strategy=strategy):
                before = policies.probabilities(strategy, core.game, seat, actions)
                after = policies.probabilities(strategy, changed, seat, actions)
                self.assertEqual(before, after)

if __name__ == '__main__': unittest.main()
