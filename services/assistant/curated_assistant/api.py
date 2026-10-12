import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from curated_assistant.engine import AssistantEngine
from curated_assistant.store import ChatStore

ROOT = Path(__file__).resolve().parents[3]
store = ChatStore(Path(os.getenv('ASSISTANT_DB', str(ROOT / 'data/assistant.sqlite3'))))
locks: dict[str, asyncio.Lock] = {}


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        app.state.engine = AssistantEngine(client)
        yield


app = FastAPI(title='Curated Care · 售后助手', lifespan=lifespan)


class Object(BaseModel):
    type: Literal['order', 'product']
    id: str = Field(pattern=r'^(?:ZF[A-F0-9]{20}|[0-9]{1,18})$')


class Chat(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    object: Object | None = None


@app.get('/health')
def health():
    return {'data': {'service': 'assistant', 'mode': 'llm' if os.getenv('LLM_API_KEY') and os.getenv('LLM_BASE_URL') else 'local'}}


@app.post('/chat')
async def chat(request: Chat, authorization: str = Header(default='')):
    if not request.text.strip():
        raise HTTPException(400, '消息不能为空')
    engine = app.state.engine
    try:
        user = await engine.commerce_call(authorization, '/me')
        user_id = str(user['id'])
        fingerprint = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        async with locks.setdefault(user_id, asyncio.Lock()):
            previous = store.previous(user_id, request.request_id)
            if previous:
                if previous[0] != fingerprint:
                    raise HTTPException(409, '同一消息标识不能用于不同内容')
                return {'data': previous[1]}
            state = store.load(user_id)
            result = await engine.run(state, authorization, request.text, request.object.model_dump() if request.object else None)
            store.save(user_id, request.request_id, fingerprint, request.text, result, state)
            return {'data': result}
    except httpx.HTTPError:
        raise HTTPException(502, '依赖服务暂时不可用，未确认的操作不会显示为成功')


@app.get('/history')
async def history(authorization: str = Header(default='')):
    try:
        user = await app.state.engine.commerce_call(authorization, '/me')
    except httpx.HTTPError:
        raise HTTPException(502, '业务服务暂时不可用')
    return {'data': store.history(str(user['id']))}
