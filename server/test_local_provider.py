"""本地扩展必须显式启用，公开策略与模型清单保持独立。"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from .policies import Policies, HINT_PRESETS
from .hangzhou import HangzhouRound

class LocalProviderTests(unittest.TestCase):
    def test_default_public_catalog(self):
        with patch.dict(os.environ, {}, clear=True):
            policies=Policies()
        self.assertIsNone(policies.local_provider)
        self.assertEqual(policies.hint_presets,HINT_PRESETS)
        self.assertEqual(set(policies.manifest),{'bc-mortal-v4-0-1','r1-4','historical297','r1-12','r1-14','r1-17'})

    def test_explicit_local_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'provider.py'
            path.write_text('''import numpy as np
from mjenv.spaces import action_mask, from_id
class Provider:
    presets={'local-test':{'name':'本地测试','strategy':'本地测试','models':[]}}
    def prepare(self,difficulty): self.ready=True
    def distribution(self,difficulty,game,seat,actions,softmax,context):
        self.prepare(difficulty)
        return softmax(np.zeros(74),np.array(action_mask(actions),dtype=bool)),from_id
def create_provider(): return Provider()
''',encoding='utf-8')
            with patch.dict(os.environ,{'MAHJONG_LOCAL_POLICY_PROVIDER':str(path)}):
                policies=Policies()
            self.assertIn('local-test',policies.hint_presets)
            self.assertNotIn('local-test',policies.manifest)
            core=HangzhouRound(seed=297,dealer=0)
            seat,actions=core.peek()
            probabilities=policies.probabilities('local-test',core.game,seat,actions)
            self.assertAlmostEqual(sum(probabilities.values()),1)
            self.assertEqual(set(probabilities),set(actions))
            self.assertTrue(policies.local_provider.ready)

if __name__=='__main__': unittest.main()
