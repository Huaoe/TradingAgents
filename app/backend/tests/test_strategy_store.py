"""Tests for the strategy store and LLM catalog validation."""

from __future__ import annotations

import pytest

from backend.models.strategy import StrategyCreate
from backend.services.strategy_store import (
    TEMPLATES,
    StrategyStore,
    _validate_llm_selection,
)


def test_validate_llm_selection_accepts_valid_combos():
    # GLM default.
    _validate_llm_selection("glm", "glm-5-turbo", "quick")
    # Anthropic quick.
    _validate_llm_selection("anthropic", "claude-sonnet-5", "quick")
    # OpenAI deep.
    _validate_llm_selection("openai", "gpt-5.5", "deep")


def test_validate_llm_selection_rejects_invalid_provider():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        _validate_llm_selection("unknown-provider", "glm-5-turbo", "quick")


def test_validate_llm_selection_rejects_invalid_mode():
    with pytest.raises(ValueError, match="Unknown LLM mode"):
        _validate_llm_selection("glm", "glm-5-turbo", "invalid-mode")


def test_validate_llm_selection_rejects_invalid_model():
    with pytest.raises(ValueError, match="Invalid model"):
        _validate_llm_selection("glm", "not-a-model", "quick")


def test_create_and_fetch_strategy():
    store = StrategyStore()
    before = len(store.list_strategies())

    payload = StrategyCreate(name="unit-test-strategy")
    strategy = store.create_strategy(payload)

    assert strategy.name == payload.name
    assert strategy.llmProvider == "glm"
    assert strategy.llmModel == "glm-5-turbo"
    assert strategy.llmMode == "quick"

    fetched = store.get_strategy(strategy.id)
    assert fetched is not None
    assert fetched.id == strategy.id

    assert len(store.list_strategies()) == before + 1


def test_create_strategy_rejects_invalid_llm_selection():
    store = StrategyStore()
    payload = StrategyCreate(name="bad-strategy", llmProvider="unknown")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        store.create_strategy(payload)


def test_strategy_store_seeds_templates():
    store = StrategyStore()
    strategies = store.list_strategies()
    template_ids = {s.id for s in strategies}
    for template in TEMPLATES:
        assert template["id"] in template_ids
