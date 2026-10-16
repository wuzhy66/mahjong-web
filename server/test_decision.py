"""公开 JSON 与实际环境的动作、观测张量和真实模型输出一致。"""
import copy
import unittest
import numpy as np
from fastapi.testclient import TestClient
from pydantic import ValidationError
from .app import create_app
from .decision import DecisionRequest, to_view, decide
from .hangzhou import HangzhouRound, TILES
from .policies import Policies, HINT_PRESETS
from .test_hints import SCENARIOS, scenario
from . import test_information_boundary as boundary
from hzmj import adapter


def public_request(game, seat, strategy='astra-0'):
    events = []
    claims = [[] for _ in range(4)]
    for raw in game.events:
        kind, d = raw['kind'], raw['data']
        if kind not in ('tile_discarded', 'chi', 'peng', 'gang'): continue
        e = dict(kind=kind, seat=d['seat'], tile=TILES[d['tile']])
        if kind == 'gang': e['mode'] = d['mode']
        if kind == 'tile_discarded': e['is_tedashi'] = d.get('is_tedashi')
        if kind in ('chi', 'peng') or e.get('mode') == 'ming': claims[d['seat']].append(e['tile'])
        events.append(e)
    players = []
    for s, p in enumerate(game.players):
        source = iter(claims[s])
        melds = [dict(kind=m.kind, tiles=[TILES[t] for t in m.tiles],
                      from_seat=None if m.kind == 'gang_an' else m.from_seat,
                      claimed_tile=None if m.kind == 'gang_an' else next(source)) for m in p.melds]
        players.append(dict(discards=[TILES[t] for t in p.discards], melds=melds))
    hero = game.players[seat]
    return dict(schema_version=1, strategy=strategy, observation=dict(
        seat=seat, dealer=game.dealer, turn=game.turn, phase=game.phase,
        hand=[TILES[t] for t in hero.tiles_in_hand()],
        drawn_tile=TILES[game.drawn_tile] if game.turn == seat and game.drawn_tile is not None else None,
        last_discard=dict(seat=game.last_discarder, tile=TILES[game.last_discard]) if game.last_discard is not None else None,
        drawable=game.drawable, baotou=hero.baotou, chain_count=hero.chain_count, piao=hero.piao,
        catch_play=game.catch_origin >= 0 and game.catch_origin != seat, players=players, public_events=events))


def cases():
    for seat in range(4): yield HangzhouRound(seed=297, dealer=seat)
    for name, info in SCENARIOS.items():
        yield scenario(name)
        after = scenario(name)
        _, actions = after.peek()
        after.step(after.decode(info['target'], actions))
        if not after.finished: yield after


class DecisionTests(unittest.TestCase):
    def test_observation_and_actions_match_engine(self):
        capture = boundary.InformationBoundaryTests().capture
        for core in cases():
            seat, actions = core.peek()
            body = DecisionRequest.model_validate(public_request(core.game, seat))
            view = to_view(body.observation)
            self.assertEqual(adapter.legal_actions(view, seat), actions)
            for strategy in HINT_PRESETS:
                with self.subTest(seat=seat, phase=core.game.phase, strategy=strategy):
                    original = capture(strategy, core.game, seat, actions)
                    restored = capture(strategy, view, seat, actions)
                    for a, b in zip(original, restored): np.testing.assert_array_equal(a, b)
            self.assertFalse(hasattr(view, 'wall'))
            self.assertTrue(all(not any(p.counts) for s, p in enumerate(view.players) if s != seat))

    def test_real_models_match(self):
        policies = Policies()
        for core in (HangzhouRound(seed=297, dealer=0), scenario('chi'), scenario('gang_an')):
            seat, actions = core.peek()
            for strategy in HINT_PRESETS:
                body = DecisionRequest.model_validate(public_request(core.game, seat, strategy))
                result = decide(body, policies)
                expected = policies.probabilities(strategy, core.game, seat, actions)
                np.testing.assert_allclose([r['probability'] for r in result['actions']], list(expected.values()), rtol=0, atol=1e-12)
                chosen = policies.choose(strategy, core.game, seat, actions)
                self.assertEqual(result['action'], result['actions'][actions.index(chosen)])
                self.assertAlmostEqual(sum(r['probability'] for r in result['actions']), 1)

    def test_reject_bad_visual_observations(self):
        raw = public_request(HangzhouRound(seed=297, dealer=0).game, 0)
        variants = []
        bad = copy.deepcopy(raw); bad['observation']['hand'] += ['m1']; variants.append(bad)
        bad = copy.deepcopy(raw); bad['observation']['hand'][:5] = ['m1']*5; variants.append(bad)
        bad = copy.deepcopy(raw); bad['observation']['players'][1]['hand'] = ['m1']; variants.append(bad)
        bad = copy.deepcopy(raw); bad['observation']['wall'] = []; variants.append(bad)
        bad = copy.deepcopy(raw); del bad['observation']['catch_play']; variants.append(bad)
        bad = copy.deepcopy(raw); bad['observation']['baotou'] = 'false'; variants.append(bad)
        core = scenario('chi'); seat, _ = core.peek()
        bad = public_request(core.game, seat); bad['observation']['public_events'] = []; variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValidationError): DecisionRequest.model_validate(bad)

    def test_http_schema_and_missing_history(self):
        policies = Policies()
        with TestClient(create_app(policies)) as client:
            schema = client.get('/api/decision/schema').json()
            self.assertEqual(schema['additionalProperties'], False)
            core = HangzhouRound(seed=297, dealer=0)
            raw = public_request(core.game, 0)
            raw['observation']['public_events'] = None
            response = client.post('/api/decision', json=raw)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()['warnings'])
            raw['observation']['hand'] = ['m1']
            self.assertEqual(client.post('/api/decision', json=raw).status_code, 422)
