"""建议流的信息边界、协议、鉴权与失败降级。"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from .advice import AdviceClient, AdviceError, advice_context, gateway_settings
from .app import create_app
from .hangzhou import HangzhouRound
from .rooms import Room


class Policy:
    def prepare(self, *_): pass
    def probabilities(self, difficulty, game, seat, actions, **kwargs):
        return {a: (i + 1) / (len(actions) * (len(actions) + 1) / 2) for i, a in enumerate(actions)}


def room_factory(rule_id, difficulties, policies):
    room = Room(rule_id, difficulties, policies, seed=1)
    room.core = HangzhouRound(seed=1, dealer=0)
    return room


class FakeAdvice:
    def __init__(self, fail=False): self.fail = fail
    async def stream(self, context):
        self.context = context
        if self.fail: raise AdviceError('建议暂不可用')
        yield '推荐理由：'
        yield '保留搭子。'


class AdviceTests(unittest.TestCase):
    def test_stream_guards_readonly_and_failure(self):
        for fail in (False, True):
            advisor = FakeAdvice(fail)
            app = create_app(Policy(), room_factory=room_factory, advisor=advisor)
            with TestClient(app) as client:
                created = client.post('/api/rooms', json={}).json()
                state = created['snapshot']
                path = '/api/rooms/' + state['id'] + '/hint-stream'
                headers = {'x-room-token': created['token']}
                payload = dict(revision=state['revision'], difficulty='astra-0')
                self.assertEqual(client.post(path, json=payload).status_code, 403)
                self.assertEqual(client.post(path, headers=headers, json={**payload, 'revision': 999}).status_code, 409)
                self.assertEqual(client.post(path, headers=headers, json={**payload, 'difficulty': 'bad'}).status_code, 422)
                response = client.post(path, headers=headers, json=payload)
                self.assertEqual(response.status_code, 200)
                events = response.text.split('\n\n')
                self.assertTrue(events[0].startswith('event: hint\n'))
                self.assertIn('event: error' if fail else 'event: done', response.text)
                room = app.state.rooms[state['id']]
                self.assertEqual(room.snapshot(), state)
                context = advisor.context
                self.assertEqual(context['recommended_action'], max(context['legal_actions'], key=lambda a: a['probability']))
                polluted = copy.deepcopy(state)
                polluted.update(wall=['secret-wall'], seed='secret-seed', events=['private-event'])
                for opponent in polluted['players'][1:]: opponent['hand'] = ['secret-hand']
                hint = room.hint(state['revision'], 'astra-0')
                self.assertEqual(advice_context(polluted, hint), context)
                self.assertNotIn('secret', json.dumps(context))


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_generic_gateway_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'llm-gateway.json'
            path.write_text(json.dumps({'base_url':'https://gateway.example/v1', 'api_key':'test-placeholder'}))
            with patch.dict(os.environ, {'LLM_GATEWAY_CONFIG_FILE':str(path)}, clear=True):
                self.assertEqual(gateway_settings(), ('https://gateway.example/v1','test-placeholder'))
                with patch.dict(os.environ, {'LLM_GATEWAY_BASE_URL':'https://override.example/v1/', 'LLM_GATEWAY_API_KEY':'override-placeholder'}):
                    self.assertEqual(gateway_settings(), ('https://override.example/v1','override-placeholder'))
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(AdviceError):
            gateway_settings()

    async def test_payload_and_content_only(self):
        def handle(request):
            body = json.loads(request.content)
            self.assertEqual(body['model'], 'deepseek-flash')
            self.assertEqual(body['reasoning_effort'], 'low')
            self.assertEqual(body['thinking'], {'type': 'enabled'})
            self.assertTrue(body['stream'])
            self.assertNotIn('temperature', body)
            parts = [{'reasoning_content': 'private-thought'}, {'content': '保留'}, {'content': '对子。'}]
            data = ''.join('data: ' + json.dumps({'choices': [{'delta': p}]}) + '\n\n' for p in parts)
            return httpx.Response(200, text=data + 'data: [DONE]\n\n')
        with patch('server.advice.gateway_settings', return_value=('https://gateway.example/v1', 'secret')):
            client = AdviceClient(transport=httpx.MockTransport(handle))
            self.assertEqual([text async for text in client.stream({'hand': []})], ['保留', '对子。'])

    async def test_failure_and_truncated_stream(self):
        for response in (httpx.Response(500, text='secret'),
                         httpx.Response(200, text='data: {"choices":[{"delta":{"content":"部分"}}]}\n\n'),
                         httpx.Response(200, text='data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n')):
            with patch('server.advice.gateway_settings', return_value=('https://gateway.example/v1', 'secret')):
                client = AdviceClient(transport=httpx.MockTransport(lambda _: response))
                with self.assertRaises(AdviceError) as error:
                    _ = [text async for text in client.stream({})]
                self.assertNotIn('secret', str(error.exception))
