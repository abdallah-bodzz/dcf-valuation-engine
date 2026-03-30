"""
main.py — FastAPI application
-----------------------------
Three endpoints:
  GET  /                         → serve the frontend HTML
  POST /api/valuation            → full DCF analysis
  GET  /api/health               → sanity check

Run with:
  uvicorn main:app --reload --port 8000

Then open: http://localhost:8000
"""

import os
import numpy as np
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from models import (
    ValuationRequest, ValuationResponse, ValuationSummary,
    HistoricalDataPoint, ForecastDataPoint, SensitivityMatrix,
)
from data import CompanyData
from forecast import build_forecast
from valuation import calculate_dcf, build_sensitivity_matrix

app = FastAPI(
    title="Company Valuation & Forecast Engine",
    description="DCF-based equity valuation using real financial data via yfinance",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = Path(__file__).parent / "frontend" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Frontend not found. Place index.html in /frontend/</h1>")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Valuation engine is running."}


# ---------------------------------------------------------------------------
# Main valuation endpoint
# ---------------------------------------------------------------------------

@app.post("/api/valuation", response_model=ValuationResponse)
async def run_valuation(req: ValuationRequest):
    """
    Full DCF valuation pipeline:
      1. Fetch & clean financial data via yfinance
      2. Project revenue & costs forward
      3. Calculate FCF for each forecast year
      4. Discount FCFs + compute terminal value
      5. Bridge EV → Equity Value → Price per share
      6. Build sensitivity matrix (WACC × TGR)
    """

    # --- Step 1: Fetch data ---
    try:
        company = CompanyData(req.ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {str(e)}")

    # --- Step 2: Build historical rows for the frontend table ---
    historical_rows = []
    years      = company.years
    rev_hist   = company.revenue
    cogs_hist  = company.cogs
    gp_hist    = company.gross_profit
    ebit_hist  = company.ebit
    da_hist    = company.da
    capex_hist = company.capex
    wc_hist    = company.working_capital

    # Define safe() OUTSIDE the loop to avoid Python closure capture bug
    # (inner functions in loops capture the loop variable by reference, not value)
    def safe(series, idx):
        try:
            v = series.iloc[idx]
            return round(float(v), 4) if not (v != v) else 0.0  # NaN check via identity
        except Exception:
            return 0.0

    for i, yr in enumerate(years):
        # Historical FCF reconstruction from actual statements
        # Year 0: no prior period WC available, so delta_wc = 0
        # (We only know WC changed; we don't know from what prior level)
        nopat_hist = safe(ebit_hist, i) * (1 - req.tax_rate)
        if i == 0:
            delta_wc = 0.0   # no prior period data; can't compute first difference
        else:
            delta_wc = safe(wc_hist, i) - safe(wc_hist, i - 1)
        fcf_hist = nopat_hist + safe(da_hist, i) - safe(capex_hist, i) - delta_wc

        historical_rows.append(HistoricalDataPoint(
            year           = yr,
            revenue        = safe(rev_hist, i),
            cogs           = safe(cogs_hist, i),
            gross_profit   = safe(gp_hist, i),
            ebit           = safe(ebit_hist, i),
            da             = safe(da_hist, i),
            capex          = safe(capex_hist, i),
            working_capital= safe(wc_hist, i),
            fcf            = round(fcf_hist, 4),
        ))

    # --- Step 3: Forecast ---
    try:
        forecast = build_forecast(
            company             = company,
            forecast_years      = req.forecast_years,
            revenue_growth_rate = req.revenue_growth_rate,
            wacc                = req.wacc,
            tax_rate            = req.tax_rate,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Forecast error: {str(e)}")

    # --- Step 4: DCF ---
    try:
        dcf = calculate_dcf(
            forecast             = forecast,
            company              = company,
            wacc                 = req.wacc,
            terminal_growth_rate = req.terminal_growth_rate,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # --- Step 5: Sensitivity matrix ---
    sensitivity_prices = build_sensitivity_matrix(
        forecast    = forecast,
        company     = company,
        wacc_values = req.wacc_range,
        tgr_values  = req.tgr_range,
    )

    # --- Step 6: Assemble response ---
    current_price   = company.current_price
    intrinsic_price = dcf.intrinsic_price
    upside          = ((intrinsic_price - current_price) / current_price
                       if current_price > 0 else 0.0)

    summary = ValuationSummary(
        ticker                 = req.ticker,
        company_name           = company.company_name,
        current_price          = round(current_price, 2),
        intrinsic_price        = intrinsic_price,
        upside_downside_pct    = round(upside, 4),
        enterprise_value_bn    = dcf.enterprise_value,
        equity_value_bn        = dcf.equity_value,
        net_debt_bn            = round(company.net_debt, 4),
        shares_outstanding_bn  = round(company.shares_outstanding, 4),
        sum_pv_fcf_bn          = dcf.sum_pv_fcf,
        terminal_value_bn      = dcf.terminal_value,
        pv_terminal_value_bn   = dcf.pv_terminal_value,
        terminal_value_pct_of_ev = dcf.terminal_value_pct,
        wacc                   = req.wacc,
        terminal_growth_rate   = req.terminal_growth_rate,
        forecast_years         = req.forecast_years,
    )

    forecast_rows = [
        ForecastDataPoint(
            year           = yr.year,
            revenue        = yr.revenue,
            cogs           = yr.cogs,
            gross_profit   = yr.gross_profit,
            opex           = yr.opex,
            ebit           = yr.ebit,
            nopat          = yr.nopat,
            da             = yr.da,
            capex          = yr.capex,
            delta_wc       = yr.delta_wc,
            fcf            = yr.fcf,
            discounted_fcf = yr.discounted_fcf,
            pv_cumulative  = yr.pv_cumulative,
        )
        for yr in forecast.years
    ]

    sensitivity = SensitivityMatrix(
        wacc_values = req.wacc_range,
        tgr_values  = req.tgr_range,
        prices      = sensitivity_prices,
        base_wacc   = req.wacc,
        base_tgr    = req.terminal_growth_rate,
    )

    assumptions = {
        "ticker":               req.ticker,
        "forecast_years":       req.forecast_years,
        "revenue_growth_rate":  req.revenue_growth_rate,
        "wacc":                 req.wacc,
        "terminal_growth_rate": req.terminal_growth_rate,
        "tax_rate":             req.tax_rate,
        "cogs_margin_used":     round(forecast.cogs_margin, 4),
        "opex_margin_used":     round(forecast.opex_margin, 4),
        "ebit_margin_used":     round(forecast.ebit_margin, 4),
        "da_margin_used":       round(forecast.da_margin, 4),
        "capex_margin_used":    round(forecast.capex_margin, 4),
        "wc_margin_used":       round(forecast.wc_margin, 4),
        "base_revenue_bn":      round(forecast.base_revenue, 4),
    }

    return ValuationResponse(
        summary     = summary,
        historical  = historical_rows,
        forecast    = forecast_rows,
        sensitivity = sensitivity,
        assumptions = assumptions,
        warnings    = company.warnings,
    )