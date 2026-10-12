"""持久化文档与可选稠密向量；轻量环境使用 BM25，多路召回用 RRF 融合。"""
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import httpx


STOP = {'什么', '怎么', '如何', '可以', '是否', '一下', '你好', '请问', '这个', '那个', '告诉', '我们', '我的', '是什', '么是', '的', '了'}


def tokens(text: str) -> list[str]:
    result = re.findall(r'[a-z0-9]+', text.lower())
    for sequence in re.findall(r'[\u4e00-\u9fff]+', text):
        result.extend(sequence[i:i + 2] for i in range(max(1, len(sequence) - 1)))
    return [t for t in result if t not in STOP]


def chunks(text: str, limit: int = 700) -> list[str]:
    """保留最近的标题路径，按段落切片，长段落退化为重叠窗口。"""
    result, headings, buffer = [], [], ''
    for paragraph in re.split(r'\n\s*\n', text.strip()):
        if paragraph.startswith('#'):
            if buffer:
                result.append(buffer)
                buffer = ''
            line = paragraph.splitlines()[0]
            depth = len(line) - len(line.lstrip('#'))
            headings = headings[:depth - 1] + [line.lstrip('# ').strip()]
        prefix = ' / '.join(headings)
        if len(buffer) + len(paragraph) > limit and buffer:
            result.append(buffer)
            buffer = ''
        if len(paragraph) > limit:
            for start in range(0, len(paragraph), limit - 80):
                result.append(f'{prefix}\n{paragraph[start:start + limit]}')
        else:
            buffer += ('\n\n' if buffer else f'{prefix}\n') + paragraph
    if buffer:
        result.append(buffer)
    return result


class KnowledgeStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,title TEXT NOT NULL,content TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,content TEXT NOT NULL,vector TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS seed_files(name TEXT PRIMARY KEY,checksum TEXT NOT NULL)')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        endpoint = os.getenv('EMBEDDING_BASE_URL', '').rstrip('/')
        if not endpoint:
            return None
        async with httpx.AsyncClient(timeout=40, trust_env=False) as client:
            response = await client.post(endpoint + '/embeddings', headers={'Authorization': 'Bearer ' + os.getenv('EMBEDDING_API_KEY', '')}, json={'model': os.getenv('EMBEDDING_MODEL', 'text-embedding-v4'), 'input': texts})
            response.raise_for_status()
            rows = sorted(response.json()['data'], key=lambda row: row['index'])
            return [row['embedding'] for row in rows]

    async def add(self, title: str, content: str) -> dict:
        doc_id = hashlib.sha256((title + '\n' + content).encode()).hexdigest()
        pieces = chunks(content)
        vectors = await self.embed([title + '\n' + part for part in pieces])
        with self.connection() as db:
            previous = list(db.execute('SELECT id FROM documents WHERE title=? AND id<>?', (title, doc_id)))
            for old in previous:
                db.execute('DELETE FROM chunks WHERE document_id=?', (old['id'],))
                db.execute('DELETE FROM documents WHERE id=?', (old['id'],))
            db.execute('INSERT OR IGNORE INTO documents VALUES(?,?,?)', (doc_id, title, content))
            for index, piece in enumerate(pieces):
                db.execute('INSERT OR REPLACE INTO chunks VALUES(?,?,?,?)', (f'{doc_id}:{index}', doc_id, piece, json.dumps(vectors[index]) if vectors else None))
        return {'id': doc_id, 'title': title, 'chunks': len(pieces)}

    async def seed(self, file: Path):
        content = file.read_text(encoding='utf-8')
        checksum = hashlib.sha256(content.encode()).hexdigest()
        with self.connection() as db:
            previous = db.execute('SELECT checksum FROM seed_files WHERE name=?', (file.name,)).fetchone()
        if previous and previous['checksum'] == checksum:
            return
        await self.add(file.stem, content)
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO seed_files VALUES(?,?)', (file.name, checksum))

    def documents(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT d.id,d.title,COUNT(c.id) AS chunks FROM documents d LEFT JOIN chunks c ON c.document_id=d.id GROUP BY d.id,d.title ORDER BY d.title')]

    def remove(self, doc_id: str):
        with self.connection() as db:
            db.execute('DELETE FROM chunks WHERE document_id=?', (doc_id,))
            db.execute('DELETE FROM documents WHERE id=?', (doc_id,))

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        with self.connection() as db:
            rows = [dict(row) for row in db.execute('SELECT c.*,d.title FROM chunks c JOIN documents d ON d.id=c.document_id')]
        if not rows:
            return []
        counts = [Counter(tokens(row['title'] + '\n' + row['content'])) for row in rows]
        lengths = [sum(c.values()) for c in counts]
        average = sum(lengths) / max(1, len(lengths))
        term_set = set(tokens(query))
        lexical = []
        for index, counter in enumerate(counts):
            score = 0.0
            for term in term_set:
                tf = counter[term]
                if not tf:
                    continue
                df = sum(term in c for c in counts)
                idf = math.log(1 + (len(rows) - df + .5) / (df + .5))
                score += idf * tf * 2.2 / (tf + 1.2 * (.25 + .75 * lengths[index] / max(1, average)))
            if score > 0:
                lexical.append((index, score))
        lexical.sort(key=lambda item: item[1], reverse=True)
        ranked = [lexical[:20]]
        vector = await self.embed([query])
        if vector:
            dense = []
            for index, row in enumerate(rows):
                if not row['vector']:
                    continue
                v = json.loads(row['vector'])
                if len(v) != len(vector[0]):
                    continue
                norm = math.sqrt(sum(x*x for x in v) * sum(x*x for x in vector[0]))
                similarity = sum(x*y for x, y in zip(v, vector[0])) / max(1e-9, norm)
                if similarity > .4:
                    dense.append((index, similarity))
            ranked.append(sorted(dense, key=lambda item: item[1], reverse=True)[:20])
        fused = Counter()
        for ranking in ranked:
            for rank, (index, _) in enumerate(ranking, 1):
                fused[index] += 1 / (60 + rank)
        return [{'id': rows[index]['id'], 'document_id': rows[index]['document_id'], 'title': rows[index]['title'], 'content': rows[index]['content'], 'score': round(score, 6)} for index, score in fused.most_common(limit)]
