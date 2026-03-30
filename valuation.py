"""
valuation.py — DCF engine & sensitivity analysis
-------------------------------------------------
Core valuation math lives here. Three responsibilities:

1. Terminal Value calculation (Gordon Growth Model)
2. Enterprise Value → Equity Value bridge
3. Sensitivity matrix (WACC × Terminal Growth Rate)

Gordon Growth Model for Terminal Value:
    TV = FCF_final × (1 + g) / (WACC - g)

This is the standard perpetuity formula. It assumes the business grows
at rate `g` forever after the explicit forecast period. This is why:
  - g must be < WACC (otherwise PV = infinity — nonsensical)
  - g is typically set close to long-run GDP growth (~2–3%)
  - Terminal Value often represents 60–80% of Enterprise Value
    → We surface this prominently as a key risk disclosure

Enterprise Value → Equity Value bridge:
    Equity Value = Enterprise Value - Net Debt
    Intrinsic Price = Equity Value / Diluted Shares Outstanding
"""

import numpy as np
from dataclasses import dataclass

from data import CompanyData
from forecast import ForecastResult


@dataclass
class DCFResult:
    sum_pv_fcf: float           # PV of all forecast FCFs (billions)
    terminal_value: float       # Undiscounted terminal value (billions)
    pv_terminal_value: float    # Discounted terminal value (billions)
    enterprise_value: float     # EV = sum_pv_fcf + pv_terminal_value (billions)
    equity_value: float         # EV - Net Debt (billions)
    intrinsic_price: float      # Equity Value / Shares Outstanding
    terminal_value_pct: float   # TV / EV — key transparency metric


def calculate_dcf(
    forecast: ForecastResult,
    company: CompanyData,
    wacc: float,
    terminal_growth_rate: float,
) -> DCFResult:
    """
    Run a full DCF on a completed forecast.

    Parameters
    ----------
    forecast            : output of forecast.build_forecast()
    company             : CompanyData (for net_debt and shares)
    wacc                : discount rate
    terminal_growth_rate: perpetuity growth rate (must be < wacc)
    """

    n = len(forecast.years)
    if n == 0:
        raise ValueError("Forecast has no years — run build_forecast() first.")

    # --- Sum of discounted FCFs over forecast period ---
    sum_pv_fcf = forecast.years[-1].pv_cumulative   # already computed incrementally

    # --- Terminal Value (Gordon Growth Model) ---
    # Using the LAST forecast year's FCF as the base
    fcf_final = forecast.years[-1].fcf

    # Safety check (should be validated in models.py already)
    denominator = wacc - terminal_growth_rate
    if denominator <= 0:
        raise ValueError(
            f"WACC ({wacc:.2%}) must be greater than terminal growth rate "
            f"({terminal_growth_rate:.2%}). Gordon Growth Model requires WACC > g."
        )

    terminal_value    = fcf_final * (1 + terminal_growth_rate) / denominator
    pv_terminal_value = terminal_value / ((1 + wacc) ** n)

    # --- Enterprise Value ---
    enterprise_value = sum_pv_fcf + pv_terminal_value

    # --- Bridge to Equity Value ---
    # Net Debt = Total Financial Debt - Cash
    # Positive net debt → subtract from EV (debt holders claim this portion)
    # Negative net debt (net cash) → add to EV (cash accrues to equity holders)
    net_debt     = company.net_debt             # in billions
    equity_value = enterprise_value - net_debt  # in billions

    # --- Intrinsic Share Price ---
    shares   = company.shares_outstanding       # in billions
    price    = equity_value / shares if shares > 0 else 0.0

    # --- Terminal Value as % of EV (transparency metric) ---
    tv_pct = pv_terminal_value / enterprise_value if enterprise_value != 0 else 0.0

    return DCFResult(
        sum_pv_fcf        = round(sum_pv_fcf, 4),
        terminal_value    = round(terminal_value, 4),
        pv_terminal_value = round(pv_terminal_value, 4),
        enterprise_value  = round(enterprise_value, 4),
        equity_value      = round(equity_value, 4),
        intrinsic_price   = round(price, 2),
        terminal_value_pct = round(tv_pct, 4),
    )


def build_sensitivity_matrix(
    forecast: ForecastResult,
    company: CompanyData,
    wacc_values: list[float],
    tgr_values: list[float],
) -> list[list[float]]:
    """
    Build a 2D sensitivity table of intrinsic prices.

    Rows    = WACC values
    Columns = Terminal Growth Rate values

    For each (WACC, TGR) pair:
      1. Re-discount the FCFs (different WACC changes discounting)
      2. Recalculate terminal value
      3. Derive intrinsic price

    Returns
    -------
    prices[wacc_idx][tgr_idx] = intrinsic price (float)
    """

    prices = []

    for wacc in wacc_values:
        row = []
        for tgr in tgr_values:
            # Skip invalid combinations
            if wacc <= tgr:
                row.append(float("nan"))
                continue

            # Re-discount FCFs with this WACC
            pv_fcfs = sum(
                yr.fcf / ((1 + wacc) ** (i + 1))
                for i, yr in enumerate(forecast.years)
            )

            # Terminal value with this WACC and TGR
            fcf_final = forecast.years[-1].fcf
            n         = len(forecast.years)
            tv        = fcf_final * (1 + tgr) / (wacc - tgr)
            pv_tv     = tv / ((1 + wacc) ** n)

            ev           = pv_fcfs + pv_tv
            equity_value = ev - company.net_debt
            price        = equity_value / company.shares_outstanding if company.shares_outstanding > 0 else 0.0

            row.append(round(price, 2))

        prices.append(row)

    return prices