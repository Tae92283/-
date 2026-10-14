"""FastAPI application: market-data + indicators + backtest API, and it also
serves the static frontend so the whole app runs from one server.

Run:
    uvicorn backend.main:app --reload --port 8000
Then open http://localhost:8000
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import backtest, data_sources, indicators

app = FastAPI(title="Chart Studio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


# ---------------------------------------------------------------------------
# request models
# ---------------------------------------------------------------------------
class IndicatorSpec(BaseModel):
    id: str
    params: Dict[str, Any] = {}


class ComputeRequest(BaseModel):
    ohlcv: List[Dict[str, Any]]
    indicators: List[IndicatorSpec]


class BacktestRequest(BaseModel):
    source: str
    symbol: str
    interval: str
    strategy: str
    params: Dict[str, Any] = {}
    limit: int = 1000
    initial_cash: float = 10_000.0
    commission: float = 0.001


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/sources")
def get_sources():
    return {"sources": [{"id": k, **v} for k, v in data_sources.SOURCES.items()],
            "intervals": data_sources.INTERVALS}


@app.get("/api/ohlcv")
def get_ohlcv(
    source: str = Query(...),
    symbol: str = Query(...),
    interval: str = Query("1h"),
    limit: int = Query(500, ge=10, le=2000),
):
    try:
        candles = data_sources.fetch_ohlcv(source, symbol, interval, limit)
    except data_sources.DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"ดึงข้อมูลไม่สำเร็จ: {exc}")
    return {"source": source, "symbol": symbol, "interval": interval, "candles": candles}


@app.get("/api/indicators")
def get_indicators():
    return {"indicators": indicators.catalog_meta()}


@app.post("/api/indicators/compute")
def compute_indicators(req: ComputeRequest):
    df = data_sources.to_dataframe(req.ohlcv)
    if df.empty:
        raise HTTPException(status_code=400, detail="ไม่มีข้อมูล OHLCV")
    specs = [spec.model_dump() for spec in req.indicators]
    return {"results": indicators.compute(df, specs)}


@app.get("/api/strategies")
def get_strategies():
    return {"strategies": backtest.strategies_meta()}


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    try:
        candles = data_sources.fetch_ohlcv(req.source, req.symbol, req.interval, req.limit)
    except data_sources.DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    df = data_sources.to_dataframe(candles)
    try:
        result = backtest.run_backtest(df, req.strategy, req.params,
                                       req.initial_cash, req.commission)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result["symbol"] = req.symbol
    result["interval"] = req.interval
    return result


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# static frontend (mounted last so /api/* wins)
# ---------------------------------------------------------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/", include_in_schema=False)
def index():  # pragma: no cover - fallback when static mount is unavailable
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"message": "Chart Studio API. ดู /docs สำหรับ API"}
