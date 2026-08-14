"""Smoke-test that the backend package imports cleanly."""

from backend import main


def test_app_metadata():
    assert main.app.title == "Hyperliquid Trading Agent API"
    assert main.app.version == "0.1.0"


def test_import_models():
    from backend.models import alert, backtest, execution, portfolio, signal, strategy, wallet

    assert alert.AlertReadRequest is not None
    assert backtest.BacktestRequest is not None
    assert execution.ExecuteRequest is not None
    assert portfolio.PortfolioSummary is not None
    assert signal.SignalCreate is not None
    assert strategy.StrategyCreate is not None
    assert wallet.Wallet is not None


def test_import_services():
    from backend.services.alert_engine import AlertEngine
    from backend.services.hyperliquid_client import HyperliquidClient
    from backend.services.signal_engine import generate_signal

    assert AlertEngine is not None
    assert HyperliquidClient is not None
    assert callable(generate_signal)
