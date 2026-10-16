"""服务器 ONNX / PyTorch 推理；难度映射固定且可审计，失败绝不替换策略。"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from threading import RLock

import numpy as np
import onnxruntime as ort
from . import bootstrap
from mahjong.observation import encode_observation
from mjenv.spaces import action_mask, from_id

PRESETS = {
    'easy': {'name': '简单', 'strategy': 'bc-mortal-v4-0-1 · argmax', 'models': ['bc-mortal-v4-0-1']},
    'medium': {'name': '中等', 'strategy': 'r1-4 · argmax', 'models': ['r1-4']},
    'hard': {'name': '困难', 'strategy': 'historical297 · argmax', 'models': ['historical297']},
}

# 提示策略独立于对手难度，Astra-0 固定采用三个成员的等权 prob-sum。
HINT_PRESETS = {
    **PRESETS,
    'astra-0': {'name': 'Astra-0', 'strategy': 'r1-12 + r1-14 + r1-17 · prob-sum',
                'models': ['r1-12', 'r1-14', 'r1-17']},
}

class Policies:
    def __init__(self):
        self.directory = Path(os.environ.get('MAHJONG_MODEL_DIR', str(Path(__file__).with_name('models'))))
        self.manifest = json.loads(Path(__file__).with_name('models.json').read_text())
        self.sessions = {}
        self.lock = RLock()
        self.local_provider = None
        self.hint_presets = dict(HINT_PRESETS)
        # 本地测试扩展须由环境变量显式开启，源码与权重不随公开仓库提交。
        provider_file = os.environ.get('MAHJONG_LOCAL_POLICY_PROVIDER')
        if provider_file:
            spec = importlib.util.spec_from_file_location('server.local_policy_provider', Path(provider_file).resolve())
            if spec is None or spec.loader is None:
                raise ValueError('本地策略扩展不可用')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.local_provider = module.create_provider()
            if self.hint_presets.keys() & self.local_provider.presets.keys():
                raise ValueError('本地策略 ID 与公开策略重复')
            self.hint_presets.update(self.local_provider.presets)

    def load(self, model_id):
        with self.lock:
            if model_id not in self.sessions:
                entry = self.manifest[model_id]
                path = self.directory / entry['file']
                if not path.is_file():
                    raise ValueError(f'模型 {model_id} 不可用，请配置 MAHJONG_MODEL_DIR')
                with path.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
                        raise ValueError(f'模型 {model_id} SHA256 不匹配')
                if entry['format'] == 'torch':
                    import torch
                    from historical297_source.public_student import load_public_bundle
                    torch.set_num_threads(2)
                    bundle = torch.load(path, map_location='cpu', weights_only=True)
                    self.sessions[model_id] = load_public_bundle(bundle).eval().requires_grad_(False)
                    return self.sessions[model_id]
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                options.inter_op_num_threads = 1
                session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
                inputs = session.get_inputs()
                if len(inputs) != 1 or inputs[0].name != 'obs' or inputs[0].shape[1] != 6122:
                    raise ValueError('模型观测协议不是 6122 维公开观测')
                self.sessions[model_id] = session
            return self.sessions[model_id]

    def prepare(self, difficulties):
        for difficulty in difficulties:
            if difficulty not in self.hint_presets:
                raise ValueError('未知难度')
            if self.local_provider and difficulty in self.local_provider.presets:
                with self.lock: self.local_provider.prepare(difficulty)
                continue
            for model_id in HINT_PRESETS[difficulty]['models']:
                self.load(model_id)

    @staticmethod
    def softmax(logits, mask):
        values = np.where(mask, logits.astype(np.float64), -np.inf)
        weights = np.exp(values - values[mask].max())
        return weights / weights.sum()

    def distribution(self, difficulty, game, seat, actions, context=None):
        if difficulty not in self.hint_presets or not actions:
            raise ValueError('提示难度或合法动作无效')
        if self.local_provider and difficulty in self.local_provider.presets:
            with self.lock:
                return self.local_provider.distribution(difficulty, game, seat, actions, self.softmax, context)
        if difficulty == 'hard':
            import torch
            from historical297_source.observation import encode_observation as encode_public
            from historical297_source.action_scheme import action_mask as mask41, from_id as decode41
            mask = np.asarray(mask41(actions), dtype=bool)
            obs = encode_public(game, seat, mask.astype(np.float32), legal_actions=actions,
                                you_cai_bi_kao=False)[None, :]
            model = self.load('historical297')
            with self.lock, torch.inference_mode():
                logits = model(torch.from_numpy(obs))['policy_logits'][0].numpy()
            if logits.shape != (41,) or not np.isfinite(logits[mask]).all():
                raise RuntimeError('historical297 输出无效')
            return self.softmax(logits, mask), decode41
        mask = np.asarray(action_mask(actions), dtype=bool)
        obs = encode_observation(game, seat, mask.astype(np.float32))[None, :]
        total = np.zeros(74, dtype=np.float64)
        for model_id in HINT_PRESETS[difficulty]['models']:
            logits = self.load(model_id).run(['logits'], {'obs': obs})[0][0].astype(np.float64)
            if logits.shape != (74,) or not np.isfinite(logits[mask]).all():
                raise RuntimeError('模型输出无效')
            total += self.softmax(logits, mask)
        return total / len(HINT_PRESETS[difficulty]['models']), from_id

    def probabilities(self, difficulty, game, seat, actions, context=None):
        probabilities, decode = self.distribution(difficulty, game, seat, actions, context)
        result = {action: 0.0 for action in actions}
        # 41 动作协议的自杠与弃牌共享槽，严格按模型解码归属，不能重复计分。
        for action_id, probability in enumerate(probabilities):
            if probability > 0:
                action = decode(action_id, actions)
                if action is None:
                    raise RuntimeError('模型返回非法动作概率')
                result[action] += float(probability)
        return result

    def choose(self, difficulty, game, seat, actions):
        if len(actions) == 1:
            return actions[0]
        probabilities, decode = self.distribution(difficulty, game, seat, actions)
        action = decode(int(probabilities.argmax()), actions)
        if action is None:
            raise RuntimeError('模型返回非法动作')
        return action
