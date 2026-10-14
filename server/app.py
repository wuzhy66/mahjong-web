"""本地网页 API；部署时由同源反向代理提供 TLS。"""
import secrets
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .rules import RULES, DEFAULT_RULE, get_rule
from .policies import Policies, PRESETS, HINT_PRESETS
from .rooms import Room

class CreateRoom(BaseModel):
    rule_id: str = DEFAULT_RULE
    difficulties: list[Literal['easy', 'medium', 'hard']] = Field(default_factory=lambda: ['easy', 'medium', 'hard'], min_length=3, max_length=3)

class Command(BaseModel):
    revision: int = Field(ge=0, strict=True)
    action_id: int | None = Field(default=None, ge=0, le=73, strict=True)

class HintRequest(BaseModel):
    revision: int = Field(ge=0, strict=True)
    difficulty: str = Field(min_length=1, max_length=64, pattern=r'^[a-z0-9-]+$')

def create_app(policies=None, *, room_factory=Room):
    app = FastAPI(title='麻将桌', docs_url=None, redoc_url=None)
    policies = policies or Policies()
    rooms = {}
    registry_lock = threading.RLock()
    app.state.rooms = rooms

    @app.get('/api/catalog')
    def catalog():
        return {'defaultRule': DEFAULT_RULE, 'rules': [dict(id=r.id, name=r.name, description=r.description) for r in RULES.values()],
                'difficulties': [dict(id=k, **v) for k, v in PRESETS.items()],
                'hintStrategies': [dict(id=k, **v) for k, v in getattr(policies, 'hint_presets', HINT_PRESETS).items()]}

    def find(room_id, token):
        with registry_lock:
            room = rooms.get(room_id)
        if room is None or time.monotonic() - room.touched > 7200:
            raise HTTPException(404, '房间不存在或已过期')
        if not token or not secrets.compare_digest(room.token, token):
            raise HTTPException(403, '房间访问凭证无效')
        return room

    @app.post('/api/rooms')
    def create(body: CreateRoom):
        try:
            get_rule(body.rule_id)
            policies.prepare(body.difficulties)
            with registry_lock:
                for key in list(rooms):
                    if time.monotonic() - rooms[key].touched > 7200:
                        del rooms[key]
                if len(rooms) >= 64:
                    raise HTTPException(503, '牌桌已满，请稍后再试')
                room = room_factory(body.rule_id, body.difficulties, policies)
                rooms[room.id] = room
            return dict(token=room.token, snapshot=room.snapshot())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get('/api/rooms/{room_id}')
    def snapshot(room_id: str, x_room_token: str = Header(default='')):
        room = find(room_id, x_room_token)
        with room.lock:
            return room.snapshot()

    @app.get('/api/rooms/{room_id}/replay')
    def replay(room_id: str, x_room_token: str = Header(default='')):
        room = find(room_id, x_room_token)
        with room.lock:
            try:
                return room.replay()
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post('/api/rooms/{room_id}/hint')
    def hint(room_id: str, body: HintRequest, x_room_token: str = Header(default='')):
        room = find(room_id, x_room_token)
        if body.difficulty not in getattr(policies, 'hint_presets', HINT_PRESETS):
            raise HTTPException(422, '未知提示策略')
        with room.lock:
            try:
                return room.hint(body.revision, body.difficulty)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(503, 'AI 提示推理失败，请稍后重试') from exc

    @app.post('/api/rooms/{room_id}/{operation}')
    def command(room_id: str, operation: Literal['action', 'advance', 'next'], body: Command, x_room_token: str = Header(default='')):
        room = find(room_id, x_room_token)
        with room.lock:
            try:
                room.check_revision(body.revision)
                if operation == 'next':
                    room.next_round()
                elif operation == 'action':
                    if body.action_id is None:
                        raise ValueError('请选择动作')
                    room.step(body.action_id)
                else:
                    room.step()
                return room.snapshot()
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(503, 'AI 推理失败，请稍后重试') from exc

    @app.delete('/api/rooms/{room_id}')
    def leave(room_id: str, x_room_token: str = Header(default='')):
        room = find(room_id, x_room_token)
        with registry_lock:
            rooms.pop(room.id, None)
        return {'ok': True}

    dist = Path(__file__).resolve().parents[1] / 'dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='web')
    return app

app = create_app()
