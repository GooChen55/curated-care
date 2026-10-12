import importlib.util
from pathlib import Path
import asyncio

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('knowledge_store', ROOT / 'services/knowledge/curated_knowledge/store.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_retrieval_has_sources_and_does_not_invent_evidence(tmp_path):
    async def run():
        store = module.KnowledgeStore(tmp_path / 'knowledge.db')
        await store.add('耳机使用手册', '# 耳机使用手册\n\n## 蓝牙配对\n请开启配对模式，再在手机蓝牙列表连接耳机。')
        result = await store.search('耳机蓝牙配对怎么操作')
        assert result and '配对模式' in result[0]['content']
        assert result[0]['document_id'] and result[0]['title'] == '耳机使用手册'
        assert await store.search('南极企鹅的迁徙路线') == []
    asyncio.run(run())


def test_document_update_delete_and_seed_tombstone(tmp_path):
    async def run():
        store = module.KnowledgeStore(tmp_path / 'knowledge.db')
        old = await store.add('政策', '退款政策：已付款订单可以提交退款申请。')
        new = await store.add('政策', '退款政策：未发货已付款订单才能申请退款。')
        assert old['id'] != new['id']
        assert len(store.documents()) == 1
        seed = tmp_path / '商品.md'
        seed.write_text('耳机支持主动降噪，一年质保。', encoding='utf-8')
        await store.seed(seed)
        for d in store.documents():
            if d['title'] == '商品':
                store.remove(d['id'])
        await store.seed(seed)
        assert all(d['title'] != '商品' for d in store.documents())
        store.remove(new['id'])
        assert await store.search('退款政策') == []
    asyncio.run(run())
