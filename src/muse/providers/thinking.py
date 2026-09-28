"""Explicit capability configuration, never a heuristic based on model names."""


def thinking_parameters(settings):
    from muse.providers.compatible import ProviderError
    if not settings.thinking:
        return {}
    capability, protocol = settings.thinking_capability, settings.protocol
    if capability == 'openai-reasoning' and protocol == 'openai-responses':
        reasoning = {'effort': settings.reasoning_effort}
        if settings.thinking_summary:
            reasoning['summary'] = 'auto'
        return {'reasoning': reasoning, 'include': ['reasoning.encrypted_content']}
    if capability == 'openai-reasoning' and protocol == 'openai-compat':
        return {'reasoning_effort': settings.reasoning_effort}
    if protocol == 'anthropic' and capability == 'anthropic-manual':
        if settings.thinking_budget_tokens >= settings.max_output_tokens:
            raise ProviderError('THINKING_BUDGET: manual thinking must leave room for final output')
        return {'thinking': {'type': 'enabled', 'budget_tokens': settings.thinking_budget_tokens}}
    if protocol == 'anthropic' and capability == 'anthropic-adaptive':
        return {'thinking': {'type': 'adaptive'}, 'output_config': {'effort': settings.reasoning_effort}}
    raise ProviderError('UNSUPPORTED_THINKING: declare a tested capability for the selected protocol/model')
