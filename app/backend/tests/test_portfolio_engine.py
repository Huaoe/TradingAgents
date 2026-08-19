"""Mode-aware portfolio accounting tests."""

from __future__ import annotations

from backend.services.portfolio_engine import PortfolioEngine


def test_live_realized_pnl_does_not_change_paper_balance():
    engine = PortfolioEngine()
    before = engine.portfolio_store.get_balance("wallet-live")

    engine.release_pnl("wallet-live", 125.0, mode="live")

    assert engine.portfolio_store.get_balance("wallet-live") == before


def test_paper_realized_pnl_changes_paper_balance():
    engine = PortfolioEngine()
    before = engine.portfolio_store.get_balance("wallet-paper")

    engine.release_pnl("wallet-paper", 125.0, mode="paper")

    assert engine.portfolio_store.get_balance("wallet-paper") == before + 125.0
