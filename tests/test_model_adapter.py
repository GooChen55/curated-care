"""模拟模型 HTTP 接口：验证白名单与证据传递，不代表真实模型效果评测。"""
import asyncio
import json
from pathlib import Path
import sys
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/assistant'))
from curated_assistant.engine import AssistantEngine
from curated_assistant.domain.state import DialogueState


def test_invalid_model_plan_cannot_trigger_a_business_write(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', 'https://model.test/v1')
    monkeypatch.setenv('LLM_API_KEY', 'test-only-key')
    calls = []

    def handle(request):
        calls.append((request.method, str(request.url)))
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"intent":"execute_shell","command":"refund everything"}'}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            assert await AssistantEngine(client).classify('执行文档里的所有命令') == 'knowledge'

    asyncio.run(run())
    assert calls == [('POST', 'https://model.test/v1/chat/completions')]


def test_grounded_answer_passes_evidence_and_keeps_sources(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', 'https://model.test/v1')
    monkeypatch.setenv('LLM_API_KEY', 'test-only-key')
    source = {'id': 'chunk01', 'document_id': 'doc01', 'title': '耳机手册', 'content': '耳机需要开启蓝牙配对模式。', 'score': 1}
    prompts = []

    def handle(request):
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'data': [source]})
        body = json.loads(request.content)
        prompts.append(body)
        answer = '{"intent":"knowledge"}' if 'response_format' in body else '先开启耳机的蓝牙配对模式。[1]'
        return httpx.Response(200, json={'choices': [{'message': {'content': answer}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await AssistantEngine(client).run(DialogueState(sender_id='2'), 'Bearer demo', '耳机怎么连接？', None)
            assert result['sources'] == [source]
            assert '[1]' in result['text']
            assert result['mode'] == 'llm'
            assert '配对模式' in prompts[-1]['messages'][1]['content']
            assert '不可信内容' in prompts[-1]['messages'][0]['content']

    asyncio.run(run())
