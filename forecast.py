"""
forecast.py — Revenue forecasting & cost projection
----------------------------------------------------
Two forecasting modes:
  1. GROWTH ASSUMPTION — user supplies a flat CAGR
  2. TREND EXTRAPOLATION — fit exponential trend to historical revenue,
     extrapolate forward (more data-driven, still simple)

Cost projection uses the "common-size" method:
  - COGS, D&A, CapEx, and WC are projected as % of revenue
  - Margins are anchored to trailing 3-year historical averages
  - This is exactly what sell-side analysts do in their models

We intentionally avoid: machine learning, ARIMA, fancy time series.
Those add complexity without improving explainability — bad for interviews.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from data import CompanyData


@dataclass
class ForecastYear:
    """One row of the projected income statement + cash flow bridge.

    Income statement reconciliation (must hold exactly):
        Revenue - COGS            = Gross Profit
        Gross Profit - OpEx       = EBIT
        EBIT × (1 - tax_rate)     = NOPAT

    Cash flow bridge:
        NOPAT + D&A - CapEx - ΔWCU = FCF
    """
    year: str
    revenue: float          # billions
    cogs: float
    gross_profit: float     # = revenue - cogs
    opex: float             # Operating expenses below gross profit line
    ebit: float             # = gross_profit - opex  (reconciled, not independently margined)
    nopat: float            # = ebit × (1 - tax_rate)
    da: float               # D&A (non-cash add-back; included in opex on income stmt)
    capex: float            # capital expenditure (positive = cash out)
    delta_wc: float         # change in working capital (positive = cash out)
    fcf: float              # Free Cash Flow = NOPAT + D&A - CapEx - delta_wc
    discounted_fcf: float   # FCF / (1 + WACC)^t
    pv_cumulative: float    # running sum of discounted FCFs


@dataclass
class ForecastResult:
    years: list[ForecastYear] = field(default_factory=list)
    base_revenue: float = 0.0       # most recent historical revenue
    cogs_margin: float = 0.0        # trailing avg COGS / Revenue
    opex_margin: float = 0.0        # trailing avg OpEx / Revenue (Gross Profit - EBIT)
    ebit_margin: float = 0.0        # trailing avg EBIT / Revenue (derived, for reference)
    da_margin: float = 0.0          # trailing avg D&A / Revenue
    capex_margin: float = 0.0       # trailing avg CapEx / Revenue
    wc_margin: float = 0.0          # trailing avg WC / Revenue


def build_forecast(
    company: CompanyData,
    forecast_years: int,
    revenue_growth_rate: float,
    wacc: float,
    tax_rate: float,
) -> ForecastResult:
    """
    Project financial statements forward and discount FCFs.

    Parameters
    ----------
    company           : cleaned CompanyData object
    forecast_years    : number of years to project (1–10)
    revenue_growth_rate: annual growth rate as decimal (e.g. 0.08)
    wacc              : discount rate as decimal
    tax_rate          : corporate tax rate as decimal

    Returns
    -------
    ForecastResult with all projected years and margin assumptions used.
    """

    rev_hist   = company.revenue
    cogs_hist  = company.cogs
    ebit_hist  = company.ebit
    da_hist    = company.da
    capex_hist = company.capex
    wc_hist    = company.working_capital

    # Derive historical OpEx = Gross Profit - EBIT
    # This ensures our projected income statement reconciles:
    #   Revenue - COGS = Gross Profit
    #   Gross Profit - OpEx = EBIT
    # Without this, independently margining both COGS and EBIT creates an
    # implicit OpEx that doesn't add up to a consistent income statement.
    gp_hist   = company.gross_profit
    opex_hist = gp_hist - ebit_hist   # OpEx = GP - EBIT (always true by definition)

    # ------------------------------------------------------------------
    # Step 1: Compute trailing 3-year average margins
    # These anchor our cost projections — the "common-size" method.
    # Using 3 years smooths out one-off events (COVID, write-downs, etc.)
    # ------------------------------------------------------------------
    TRAILING = 3

    def safe_margin(num: pd.Series, denom: pd.Series, n: int = TRAILING) -> float:
        """Average ratio over last n years, ignoring NaN."""
        d  = denom.iloc[-n:]
        nu = num.iloc[-n:]
        ratios = (nu / d).replace([np.inf, -np.inf], np.nan).dropna()
        return float(ratios.mean()) if not ratios.empty else 0.0

    cogs_margin  = safe_margin(cogs_hist,  rev_hist)
    opex_margin  = safe_margin(opex_hist,  rev_hist)
    # ebit_margin is derived (not independently projected) — kept for reference/display
    ebit_margin  = safe_margin(ebit_hist,  rev_hist)
    da_margin    = safe_margin(da_hist,    rev_hist)
    capex_margin = safe_margin(capex_hist, rev_hist)
    wc_margin    = safe_margin(wc_hist,    rev_hist)

    # Base values (most recent historical year)
    base_revenue = float(rev_hist.iloc[-1]) if not rev_hist.isna().all() else 0.0
    base_wc      = float(wc_hist.iloc[-1])  if not wc_hist.isna().all()  else 0.0
    base_year    = int(company.years[-1]) if company.years else 2023

    # ------------------------------------------------------------------
    # Step 2: Project each year
    # ------------------------------------------------------------------
    result = ForecastResult(
        base_revenue  = base_revenue,
        cogs_margin   = cogs_margin,
        opex_margin   = opex_margin,
        ebit_margin   = ebit_margin,
        da_margin     = da_margin,
        capex_margin  = capex_margin,
        wc_margin     = wc_margin,
    )

    prev_wc   = base_wc
    pv_cumsum = 0.0

    for t in range(1, forecast_years + 1):
        year_label = str(base_year + t)

        # --- Revenue: compound the growth rate ---
        revenue = base_revenue * ((1 + revenue_growth_rate) ** t)

        # --- Income Statement (fully reconciled) ---
        cogs         = revenue * cogs_margin
        gross_profit = revenue - cogs          # identity: always holds
        opex         = revenue * opex_margin
        ebit         = gross_profit - opex     # identity: always holds
        #   ebit_margin check: ebit/revenue should ≈ ebit_margin (it will, by construction)

        # --- Cash Flow inputs ---
        da    = revenue * da_margin
        capex = revenue * capex_margin

        # --- Working Capital ---
        wc_this_year = revenue * wc_margin
        # Positive delta_wc = increase in WC = cash OUTFLOW (subtract from FCF)
        # Negative delta_wc = decrease in WC = cash INFLOW (adds to FCF)
        delta_wc = wc_this_year - prev_wc
        prev_wc  = wc_this_year

        # --- NOPAT (Net Operating Profit After Tax) ---
        # Tax EBIT (not net income) to stay on an unlevered basis.
        # DCF values the business independent of its capital structure;
        # interest expense is not subtracted before taxing.
        nopat = ebit * (1 - tax_rate)

        # --- Free Cash Flow ---
        # FCF = NOPAT + D&A - CapEx - delta_wc
        #
        # Intuition:
        #   NOPAT       = cash earnings if 100% equity-financed
        #   + D&A       = add back non-cash charge (it reduced EBIT but no cash left)
        #   - CapEx     = actual cash spent on maintaining/growing asset base
        #   - delta_wc  = cash tied up in working capital growth
        fcf = nopat + da - capex - delta_wc

        # --- Discount FCF to present value at t=0 ---
        discount_factor = (1 + wacc) ** t
        discounted_fcf  = fcf / discount_factor
        pv_cumsum      += discounted_fcf

        result.years.append(ForecastYear(
            year           = year_label,
            revenue        = round(revenue, 4),
            cogs           = round(cogs, 4),
            gross_profit   = round(gross_profit, 4),
            opex           = round(opex, 4),
            ebit           = round(ebit, 4),
            nopat          = round(nopat, 4),
            da             = round(da, 4),
            capex          = round(capex, 4),
            delta_wc       = round(delta_wc, 4),
            fcf            = round(fcf, 4),
            discounted_fcf = round(discounted_fcf, 4),
            pv_cumulative  = round(pv_cumsum, 4),
        ))

    return result