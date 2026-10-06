"""Sequential evaluation budget; unknown usage retains its full reservation.

Prices are for the original gpt-5.4-mini configuration, uncached input.
This wrapper is an evaluation facility, not a provider configuration change.
"""
import json
import math
from pathlib import Path


class EvaluationBudgetExceeded(RuntimeError):
    pass


class BudgetedEvaluationProvider:
    def __init__(self, provider, ledger: Path, *, limit_usd: float):
        if provider.settings.model != 'gpt-5.4-mini' or not 0 < limit_usd <= 2:
            raise ValueError('This evaluation supports gpt-5.4-mini and a maximum $2 budget')
        self.provider, self.ledger = provider, Path(ledger)
        self.limit = math.floor(limit_usd * 1_000_000)
        self.records = json.loads(self.ledger.read_text()) if self.ledger.exists() else []
        self.busy = False

    def save(self):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        temp = self.ledger.with_suffix('.tmp')
        temp.write_text(json.dumps(self.records, indent=2), encoding='utf-8')
        temp.replace(self.ledger)

    @property
    def charged_micro_usd(self):
        return sum(record['charged_micro_usd'] for record in self.records)

    async def stream(self, messages, tools):
        if self.busy:
            raise RuntimeError('Evaluation provider requires sequential requests')
        payload = json.dumps([messages, [tool.model_dump(mode='json') for tool in tools]], ensure_ascii=False)
        # UTF-8 bytes conservatively bound text tokens; reserve additional protocol overhead.
        input_bound = len(payload.encode('utf-8')) + 4096
        output_bound = self.provider.settings.max_output_tokens
        reserve = math.ceil(input_bound * .75 + output_bound * 4.5)
        if self.charged_micro_usd + reserve > self.limit:
            raise EvaluationBudgetExceeded('Evaluation budget would be exceeded before dispatch')
        record = {'request': len(self.records) + 1, 'charged_micro_usd': reserve,
                  'reserved_micro_usd': reserve, 'usage_known': False}
        self.records.append(record)
        self.save()  # Persist before dispatch: interruption must not refund an unknown request.
        self.busy = True
        usage = None
        completed = False
        try:
            async for event in self.provider.stream(messages, tools):
                if event.type == 'usage':
                    usage = event.usage
                if event.type == 'done':
                    completed = True
                yield event
        finally:
            if completed and usage is not None:
                values = [usage.get(key) for key in ('input_tokens', 'output_tokens')]
                if all(type(value) is int and value >= 0 for value in values):
                    actual = math.ceil(values[0] * .75 + values[1] * 4.5)
                    record.update(input_tokens=values[0], output_tokens=values[1], usage_known=True,
                                  charged_micro_usd=actual)
                    if actual > reserve:
                        # Fail closed on subsequent requests if a provider exceeds its reserved bound.
                        self.limit = 0
            self.save()
            self.busy = False
