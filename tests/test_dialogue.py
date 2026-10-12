from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/assistant'))
from curated_assistant.domain.state import DialogueState, Session
from curated_assistant.domain.contexts import TaskContext
from curated_assistant.flows.conditions import evaluate
from curated_assistant.store import ChatStore


def test_state_round_trip_preserves_active_session_and_paused_task(tmp_path):
    state = DialogueState(sender_id='2', active_task=TaskContext('refund_request', 'confirmation', {'order_number': 'ZF123'}), interrupted_active_tasks=[TaskContext('refund_request', 'refund_reason', {})], sessions=[Session('session', 1, 2, None)])
    store = ChatStore(tmp_path / 'chat.db')
    store.save('2', 'request01', 'hash', '确认退款', {'text': '已提交'}, state)
    loaded = store.load('2')
    assert loaded.sessions[0].closed_at is None
    assert loaded.active_task.step_id == 'confirmation'
    assert loaded.interrupted_active_tasks[0].step_id == 'refund_reason'
    assert store.previous('2', 'request01')[1]['text'] == '已提交'
    assert store.history('3') == []


def test_flow_condition_supports_business_checks_but_rejects_code():
    assert evaluate("slots.get('order_number') and context.get('reason') != 'not_supported'", {'slots': {'order_number': 'ZF123'}, 'context': {}})
    assert not evaluate("context.get('reason') == 'not_supported'", {'context': {}})
    with pytest.raises(ValueError):
        evaluate("__import__('os').system('echo exploit')", {})
    with pytest.raises(ValueError):
        evaluate("slots.__class__.__mro__", {'slots': {}})
