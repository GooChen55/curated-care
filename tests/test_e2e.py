"""真实 HTTP 联调。启动项目后设置 CURATED_CARE_E2E=1；测试仅使用演示账户和专用商品。"""
from concurrent.futures import ThreadPoolExecutor
import os
import uuid
import httpx
import pytest

pytestmark = pytest.mark.skipif(os.getenv('CURATED_CARE_E2E') != '1', reason='需要已启动的演示环境')
BASE = os.getenv('CURATED_CARE_TEST_URL', 'http://127.0.0.1:19081') + '/api'


def call(method, path, token=None, body=None, key=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    if key:
        headers['Idempotency-Key'] = key
    return httpx.request(method, BASE + path, headers=headers, json=body, timeout=75, trust_env=False)


def login(username):
    r = call('POST', '/auth/login', body={'username': username, 'password': 'Admin12345!' if username == 'admin' else 'Demo12345!'})
    assert r.status_code == 200, r.text
    return r.json()['data']['token']


@pytest.fixture
def environment():
    tokens = {name: login(name) for name in ['demo', 'other', 'admin']}
    products = []

    def create(stock=10):
        product = {'id': 900000 + int(uuid.uuid4().hex[:6], 16), 'title': '联调测试商品', 'category': '测试', 'description': '用于验证库存与订单事务的专用商品。', 'price': 12.34, 'stock': stock, 'active': True}
        r = call('PUT', f'/admin/products/{product["id"]}', tokens['admin'], product)
        assert r.status_code == 200, r.text
        products.append(product)
        return product

    yield tokens, create
    for user in ['demo', 'other']:
        for item in call('GET', '/cart', tokens[user]).json()['data']:
            if item['id'] in {p['id'] for p in products}:
                call('PUT', f'/cart/{item["id"]}', tokens[user], {'quantity': 0})
    for product in products:
        product['active'] = False
        call('PUT', f'/admin/products/{product["id"]}', tokens['admin'], product)


def make_order(token, product):
    r = call('PUT', '/cart/' + str(product['id']), token, {'quantity': 1})
    assert r.status_code == 200, r.text
    r = call('POST', '/orders', token, {'address': '上海市测试路100号'}, uuid.uuid4().hex)
    assert r.status_code == 200, r.text
    return r.json()['data']


def chat(token, text, order=None, request_id=None):
    return call('POST', '/assistant/chat', token, {'text': text, 'request_id': request_id or uuid.uuid4().hex, 'object': {'type': 'order', 'id': order} if order else None})


def test_purchase_chat_confirmation_review_and_permissions(environment):
    tokens, create = environment
    p = create()
    order = make_order(tokens['demo'], p)
    oid = order['id']
    assert order['amount'] == 12.34
    assert call('GET', '/orders/' + oid, tokens['other']).status_code == 404
    assert call('GET', '/admin/refunds', tokens['demo']).status_code == 403
    assert chat(tokens['other'], '查询订单', oid).status_code == 404
    assert call('POST', f'/orders/{oid}/demo-pay', tokens['demo'], {}).status_code == 200
    r = chat(tokens['demo'], '我要申请退款', oid)
    assert r.status_code == 200, r.text
    assert r.json()['data']['pending'] == 'refund_reason'
    r = chat(tokens['demo'], '不喜欢这件商品')
    assert r.status_code == 200, r.text
    assert r.json()['data']['pending'] == 'confirmation'
    assert call('GET', '/orders/' + oid, tokens['demo']).json()['data']['refunds'] == []
    # 查物流不会触发退款，状态可跨请求持久化并恢复。
    r = chat(tokens['demo'], '查询物流')
    assert r.status_code == 200, r.text
    assert '继续退款' in r.json()['data']['text']
    assert chat(tokens['demo'], '继续退款').status_code == 200
    req_id = uuid.uuid4().hex
    r = chat(tokens['demo'], '确认提交', request_id=req_id)
    assert r.status_code == 200, r.text
    repeated = chat(tokens['demo'], '确认提交', request_id=req_id)
    assert repeated.json() == r.json()
    assert chat(tokens['demo'], '不同消息', request_id=req_id).status_code == 409
    stored = call('GET', '/orders/' + oid, tokens['demo']).json()['data']
    assert len(stored['refunds']) == 1
    rid = stored['refunds'][0]['id']
    assert call('POST', f'/admin/refunds/{rid}/review', tokens['admin'], {'approve': True, 'note': '测试通过'}).status_code == 200
    assert call('GET', '/orders/' + oid, tokens['demo']).json()['data']['status'] == 'REFUNDED'
    assert call('GET', '/products/' + str(p['id'])).json()['data']['stock'] == 10
    knowledge = chat(tokens['demo'], '退款政策是什么？')
    assert knowledge.status_code == 200, knowledge.text
    assert knowledge.json()['data']['sources']
    assert chat(tokens['demo'], '南极企鹅的迁徙路线是什么？').json()['data']['sources'] == []
    assert call('GET', '/assistant/history', tokens['demo']).status_code == 200
    assert call('POST', '/assistant/chat', body={'text': '你好', 'request_id': uuid.uuid4().hex}).status_code == 401


def test_concurrent_checkout_never_oversells(environment):
    tokens, create = environment
    p = create(stock=1)
    for user in ['demo', 'other']:
        assert call('PUT', '/cart/' + str(p['id']), tokens[user], {'quantity': 1}).status_code == 200
    def checkout(user):
        return call('POST', '/orders', tokens[user], {'address': '北京市库存测试路100号'}, uuid.uuid4().hex)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(checkout, ['demo', 'other']))
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert call('GET', '/products/' + str(p['id'])).json()['data']['stock'] == 0
    success = next(r for r in results if r.status_code == 200).json()['data']
    owner = 'demo' if success['user_id'] == 2 else 'other'
    assert call('POST', '/orders/' + success['id'] + '/cancel', tokens[owner], {}).status_code == 200


def test_knowledge_admin_update_and_service_auth(environment):
    tokens, _ = environment
    title = '联调测试政策' + uuid.uuid4().hex[:8]
    doc = {'title': title, 'content': '# 联调专用政策\n\n专用保修流程需要提交商品序列号，审核后确认结果。'}
    assert call('POST', '/admin/knowledge', tokens['demo'], doc).status_code == 403
    r = call('POST', '/admin/knowledge', tokens['admin'], doc)
    assert r.status_code == 200, r.text
    doc_id = r.json()['data']['id']
    assert any(d['id'] == doc_id for d in call('GET', '/admin/knowledge', tokens['admin']).json()['data'])
    assert call('DELETE', '/admin/knowledge/' + doc_id, tokens['admin']).status_code == 200
    internal_url = os.getenv('CURATED_CARE_TEST_KNOWLEDGE_URL') or ('http://127.0.0.1:19083' if BASE == 'http://127.0.0.1:19081/api' else None)
    if internal_url:
        assert httpx.post(internal_url + '/search', json={'query': '退款'}, trust_env=False).status_code == 401
