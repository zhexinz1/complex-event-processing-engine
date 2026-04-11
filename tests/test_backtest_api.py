from adapters.flask_app import create_app


def test_backtest_api_runs_pbx_ma_preset() -> None:
    app = create_app()
    client = app.test_client()

    presets_response = client.get("/api/backtests/presets")
    assert presets_response.status_code == 200
    presets_payload = presets_response.get_json()
    assert presets_payload["success"] is True
    assert presets_payload["data"][0]["id"] == "pbx_ma"

    run_response = client.post("/api/backtests/run", json={"strategy_id": "pbx_ma"})
    assert run_response.status_code == 200
    run_payload = run_response.get_json()
    assert run_payload["success"] is True

    data = run_payload["data"]
    assert data["market_events_processed"] == 38
    assert data["final_equity"] == 1_000_694.21
    assert data["realized_pnl"] == 700.0
    assert len(data["signals"]) == 2
    assert len(data["trades"]) == 2
    assert data["signals"][0]["payload"]["side"] == "BUY"
    assert data["signals"][1]["payload"]["side"] == "SELL"
