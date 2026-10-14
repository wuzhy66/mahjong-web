"""复盘完整性、只读边界与结束前暗手隔离。"""
import unittest
from fastapi.testclient import TestClient
from .app import create_app
from .rooms import Room
from .test_rooms import LegalPolicy
from mjenv.spaces import to_id

class ReplayTests(unittest.TestCase):
    def test_finished_only_authenticated_and_preserved_across_rounds(self):
        app = create_app(LegalPolicy())
        with TestClient(app) as c:
            data = c.post('/api/rooms', json={}).json()
            room = app.state.rooms[data['snapshot']['id']]
            path = '/api/rooms/' + room.id
            headers = {'x-room-token': data['token']}
            self.assertEqual(c.get(path + '/replay').status_code, 403)
            self.assertEqual(c.get(path + '/replay', headers=headers).status_code, 409)
            steps = 0
            while not room.core.finished:
                snap = c.get(path, headers=headers).json()
                self.assertNotIn('frames', snap)
                self.assertNotIn('seed', snap)
                self.assertTrue(all(not p['hand'] for p in snap['players'][1:]))
                seat, actions = room.core.peek()
                action = room.policies.choose('easy', room.core.game, seat, actions)
                room.step(to_id(action, actions) if seat == 0 else None)
                steps += 1
                self.assertLess(steps, 1500)
            replay = c.get(path + '/replay', headers=headers).json()
            self.assertEqual(len(replay['frames']), steps + 1)
            self.assertEqual(replay['frames'][0]['label'], '开局发牌')
            self.assertTrue(replay['frames'][-1]['snapshot']['finished'])
            self.assertEqual(replay['frames'][-1]['snapshot']['result'], room.core.result)
            for index, frame in enumerate(replay['frames']):
                self.assertEqual(frame['index'], index)
                self.assertEqual(frame['snapshot']['legalActions'], [])
                self.assertNotIn('seed', frame['snapshot'])
                self.assertNotIn('wall', frame['snapshot'])
                self.assertTrue(all(p['hand'] for p in frame['snapshot']['players']))
            # 调用者改写返回对象不能污染房间留存数据。
            returned = room.replay()
            returned['frames'][0]['snapshot']['players'][0]['hand'].clear()
            self.assertTrue(room.replay()['frames'][0]['snapshot']['players'][0]['hand'])
            original = room.replay()
            self.assertEqual(c.post(path + '/next', headers=headers, json={'revision': room.revision}).status_code, 200)
            self.assertEqual(c.get(path + '/replay', headers=headers).json(), original)
            snap = c.get(path, headers=headers).json()
            self.assertEqual(snap['round'], 2)
            self.assertEqual(snap['replayRound'], 1)
            self.assertTrue(all(not p['hand'] for p in snap['players'][1:]))
            self.assertEqual(len(room.frames), 1)

if __name__ == '__main__': unittest.main()
