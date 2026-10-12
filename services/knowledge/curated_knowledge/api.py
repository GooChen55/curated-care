import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from curated_knowledge.store import KnowledgeStore

ROOT = Path(__file__).resolve().parents[3]
store = KnowledgeStore(Path(os.getenv('KNOWLEDGE_DB', str(ROOT / 'data/knowledge.sqlite3'))))


@asynccontextmanager
async def lifespan(app):
    for document in (ROOT / 'data/knowledge').glob('*.md'):
        await store.seed(document)
    yield


def service_auth(x_service_token: str = Header(default='')):
    expected = os.getenv('SERVICE_TOKEN', 'local-development-only')
    if not secrets.compare_digest(x_service_token, expected):
        raise HTTPException(401, '服务身份验证失败')


app = FastAPI(title='Curated Care · 知识服务', lifespan=lifespan)


class Document(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=10, max_length=100000)


class Search(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


@app.get('/health')
def health():
    return {'data': {'service': 'knowledge', 'retrieval': 'hybrid' if os.getenv('EMBEDDING_BASE_URL') else 'bm25', 'documents': len(store.documents())}}


@app.get('/documents', dependencies=[Depends(service_auth)])
def documents():
    return {'data': store.documents()}


@app.post('/documents', dependencies=[Depends(service_auth)])
async def add(document: Document):
    if not document.title.strip() or len(document.content.strip()) < 10:
        raise HTTPException(400, '文档标题或正文为空')
    return {'data': await store.add(document.title.strip(), document.content.strip())}


@app.delete('/documents/{doc_id}', dependencies=[Depends(service_auth)])
def delete(doc_id: str):
    store.remove(doc_id)
    return {'data': True}


@app.post('/search', dependencies=[Depends(service_auth)])
async def search(request: Search):
    if os.getenv('ADVANCED_KNOWLEDGE_URL'):
        import httpx
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            try:
                response = await client.post(os.environ['ADVANCED_KNOWLEDGE_URL'].rstrip('/') + '/search', headers={'X-Service-Token': os.getenv('SERVICE_TOKEN', 'local-development-only')}, json=request.model_dump())
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                raise HTTPException(502, '高级检索服务不可用，请检查配置')
    return {'data': await store.search(request.query, request.limit)}
