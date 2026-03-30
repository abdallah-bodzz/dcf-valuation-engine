"""
models.py — Pydantic request/response schemas
All financial inputs are validated here before touching any math.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class ValuationRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL")
    forecast_years: int = Field(5, ge=1, le=10, description="Number of years to forecast")

    # Growth assumptions
    revenue_growth_rate: float = Field(
        0.08, ge=-0.5, le=5.0,
        description="Annual revenue growth rate as decimal (e.g. 0.08 = 8%)"
    )

    # DCF parameters
    wacc: float = Field(
        0.10, ge=0.01, le=0.50,
        description="Weighted Average Cost of Capital as decimal (e.g. 0.10 = 10%)"
    )
    terminal_growth_rate: float = Field(
        0.025, ge=0.0, le=0.10,
        description="Perpetuity growth rate for terminal value (e.g. 0.025 = 2.5%)"
    )
    tax_rate: float = Field(
        0.21, ge=0.0, le=0.50,
        description="Effective corporate tax rate (e.g. 0.21 = 21%)"
    )

    # Sensitivity analysis bounds
    wacc_range: list[float] = Field(
        default=[0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13],
        description="WACC values for sensitivity table"
    )
    tgr_range: list[float] = Field(
        default=[0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04],
        description="Terminal growth rate values for sensitivity table"
    )

    @field_validator("terminal_growth_rate")
    @classmethod
    def tgr_less_than_wacc(cls, v, info):
        wacc = info.data.get("wacc", 0.10)
        if v >= wacc:
            raise ValueError(
                f"terminal_growth_rate ({v:.1%}) must be less than wacc ({wacc:.1%}) "
                "or the Gordon Growth Model denominator becomes zero/negative."
            )
        return v

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, v):
        return v.strip().upper()


class HistoricalDataPoint(BaseModel):
    year: str
    revenue: float          # in billions USD
    cogs: float
    gross_profit: float
    ebit: float
    da: float               # depreciation & amortization
    capex: float
    working_capital: float
    fcf: float


class ForecastDataPoint(BaseModel):
    year: str
    revenue: float
    cogs: float
    gross_profit: float
    opex: float             # operating expenses below gross profit
    ebit: float             # gross_profit - opex (always reconciles)
    nopat: float            # Net Operating Profit After Tax
    da: float
    capex: float
    delta_wc: float         # change in working capital
    fcf: float
    discounted_fcf: float
    pv_cumulative: float


class SensitivityMatrix(BaseModel):
    wacc_values: list[float]
    tgr_values: list[float]
    prices: list[list[float]]   # [wacc_idx][tgr_idx] → intrinsic price
    base_wacc: float
    base_tgr: float


class ValuationSummary(BaseModel):
    ticker: str
    company_name: str
    current_price: float
    intrinsic_price: float
    upside_downside_pct: float      # (intrinsic - current) / current
    enterprise_value_bn: float
    equity_value_bn: float
    net_debt_bn: float
    shares_outstanding_bn: float
    sum_pv_fcf_bn: float            # PV of forecast FCFs
    terminal_value_bn: float        # undiscounted
    pv_terminal_value_bn: float     # discounted terminal value
    terminal_value_pct_of_ev: float # how much of EV comes from TV (key insight)
    wacc: float
    terminal_growth_rate: float
    forecast_years: int


class ValuationResponse(BaseModel):
    summary: ValuationSummary
    historical: list[HistoricalDataPoint]
    forecast: list[ForecastDataPoint]
    sensitivity: SensitivityMatrix
    assumptions: dict               # echo back all inputs for transparency
    warnings: list[str]             # surface any data quality issues