from types import SimpleNamespace

import pytest

from muse.commerce.evaluation_budget import (
    BudgetedEvaluationProvider,
    EvaluationBudgetExceeded,
)
from muse.contracts import ModelEvent


class Provider:
    settings = SimpleNamespace(model='gpt-5.4-mini', max_output_tokens=2048)
    dispatched = 0

    def __init__(self, fail=False):
        self.fail = fail

    async def stream(self, messages, tools):
        self.dispatched += 1
        if self.fail:
            raise RuntimeError('Interrupted request')
        yield ModelEvent(type='usage', usage={'input_tokens': 100, 'output_tokens': 20})
        yield ModelEvent(type='done')


async def test_known_usage_and_restart(tmp_path):
    ledger = tmp_path / 'cost.json'
    budget = BudgetedEvaluationProvider(Provider(), ledger, limit_usd=2)
    _ = [event async for event in budget.stream([], [])]
    assert budget.charged_micro_usd == 165
    restored = BudgetedEvaluationProvider(Provider(), ledger, limit_usd=2)
    assert restored.charged_micro_usd == 165


async def test_interruption_keeps_reservation_and_blocks_before_dispatch(tmp_path):
    provider = Provider(fail=True)
    ledger = tmp_path / 'cost.json'
    budget = BudgetedEvaluationProvider(provider, ledger, limit_usd=.02)
    with pytest.raises(RuntimeError, match='Interrupted'):
        _ = [event async for event in budget.stream([], [])]
    charged = budget.charged_micro_usd
    assert charged > 12000 and not budget.records[0]['usage_known']
    restored = BudgetedEvaluationProvider(provider, ledger, limit_usd=.02)
    with pytest.raises(EvaluationBudgetExceeded):
        _ = [event async for event in restored.stream([], [])]
    assert provider.dispatched == 1 and restored.charged_micro_usd == charged
