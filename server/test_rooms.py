"""协议边界与完整牌局回归：模型测试替身只用于测试。"""
import unittest
from fastapi.testclient import TestClient
from .app import create_app
from .rooms import Room
from .rules import get_rule, RULES
from mjenv.spaces import to_id

class LegalPolicy:
    def prepare(self, difficulties): pass
    def choose(self, difficulty, game, seat, actions):
        return next((a for a in actions if a[0] == 'hu'), next((a for a in actions if a[0] == 'discard'), actions[0]))

class RoomTests(unittest.TestCase):
    def test_full_round_and_private_view(self):
        for seed in range(6):
            room = Room('hangzhou', ['easy', 'medium', 'hard'], LegalPolicy(), seed=seed)
            for _ in range(1200):
                snap = room.snapshot()
                self.assertNotIn('seed', snap)
                self.assertNotIn('wall', snap)
                if snap['finished']: break
                for p in snap['players'][1:]: self.assertEqual(p['hand'], [])
                seat, acts = room.core.peek()
                if seat == 0:
                    a = room.policies.choose('easy', room.core.game, seat, acts)
                    room.step(to_id(a, acts))
                else: room.step()
            self.assertTrue(room.core.finished)
            self.assertEqual(sum(room.scores), 0)
            expected_dealer = room.core.result['next_dealer']
            old_scores = list(room.scores)
            room.next_round()
            self.assertEqual(room.core.game.dealer, expected_dealer)
            self.assertEqual(room.scores, old_scores)
            self.assertEqual(room.round, 2)

    def test_api_auth_revision_and_rules(self):
        app = create_app(LegalPolicy())
        with TestClient(app) as c:
            self.assertEqual(len(c.get('/api/catalog').json()['rules']), 1)
            self.assertEqual(c.post('/api/rooms', json={'rule_id':'unknown'}).status_code,400)
            self.assertEqual(c.post('/api/rooms', json={'difficulties':['hard']}).status_code,422)
            created = c.post('/api/rooms', json={}).json()
            path = '/api/rooms/' + created['snapshot']['id']
            h = {'x-room-token':created['token']}
            self.assertEqual(c.get(path).status_code,403)
            self.assertEqual(c.post(path+'/advance',headers=h,json={'revision':999}).status_code,409)
            room = app.state.rooms[created['snapshot']['id']]
            before = room.revision
            self.assertEqual(c.post(path+'/next',headers=h,json={'revision':before}).status_code,409)
            self.assertEqual(room.revision,before)
            if room.core.peek()[0] != 0:
                self.assertEqual(c.post(path+'/action',headers=h,json={'revision':before,'action_id':0}).status_code,409)
                self.assertEqual(c.post(path+'/advance',headers=h,json={'revision':before}).status_code,200)
            else:
                aid = created['snapshot']['legalActions'][0]['id']
                self.assertEqual(c.post(path+'/action',headers=h,json={'revision':before,'action_id':aid}).status_code,200)
            self.assertEqual(c.post(path+'/advance',headers=h,json={'revision':before}).status_code,409)
            self.assertEqual(c.delete(path,headers=h).status_code,200)
            self.assertEqual(c.get(path,headers=h).status_code,404)

    def test_rooms_are_isolated(self):
        a = Room('hangzhou',['easy']*3,LegalPolicy(),seed=10)
        b = Room('hangzhou',['hard']*3,LegalPolicy(),seed=11)
        old = b.snapshot()
        seat, acts = a.core.peek()
        a.step(to_id(acts[0],acts) if seat == 0 else None)
        self.assertEqual(b.snapshot(), old)

if __name__ == '__main__': unittest.main()
