"""
data.py — yfinance fetching & cleaning
-------------------------------------
All raw data comes through here. We normalize it so the rest of the
codebase never has to worry about yfinance quirks (missing rows,
sign conventions, scale, etc.)

Key yfinance conventions we fix here:
  - Values are in actual USD (not thousands). We convert to BILLIONS.
  - CapEx is negative in cashflow statement → we flip to positive.
  - Column order is newest-first → we reverse to chronological.
  - Some tickers have missing rows → we fill with NaN and warn.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional


class CompanyData:
    """Cleaned, normalized financial data for a single ticker."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self.warnings: list[str] = []

        t = yf.Ticker(self.ticker)

        # --- Fetch raw statements (annual, newest-first columns) ---
        self._income_raw   = t.financials          # income statement
        self._cashflow_raw = t.cashflow            # cash flow statement
        self._balance_raw  = t.balance_sheet       # balance sheet
        self._info         = t.info or {}

        # Validate we got something
        if self._income_raw is None or self._income_raw.empty:
            raise ValueError(f"No financial data found for ticker '{self.ticker}'. "
                             "Check the symbol or try again later.")

        # Reverse columns so index 0 = oldest year (chronological order)
        self.income   = self._income_raw.iloc[:, ::-1].copy()
        self.cashflow = self._cashflow_raw.iloc[:, ::-1].copy() if self._cashflow_raw is not None else pd.DataFrame()
        self.balance  = self._balance_raw.iloc[:, ::-1].copy()  if self._balance_raw  is not None else pd.DataFrame()

        # Year labels (strings like "2020", "2021", ...)
        self.years = [str(col.year) for col in self.income.columns]

    # ------------------------------------------------------------------
    # Safe row getter — returns a Series in billions, NaN if row missing
    # ------------------------------------------------------------------
    def _get_row(self, df: pd.DataFrame, *row_names: str,
                 scale: float = 1e9, negate: bool = False) -> pd.Series:
        """
        Try each row_name in order, return the first one found.
        Divides by `scale` (default 1e9 → billions).
        If `negate=True`, flips sign (for CapEx which is stored negative).
        """
        for name in row_names:
            if name in df.index:
                series = df.loc[name].astype(float) / scale
                if negate:
                    series = -series
                return series
        # Not found — return NaN series and warn
        self.warnings.append(
            f"Row '{row_names[0]}' not found in financial statements for {self.ticker}. "
            "Value will be treated as 0 in margin calculations — review this carefully."
        )
        return pd.Series(np.nan, index=df.columns)

    # ------------------------------------------------------------------
    # Public accessors — all in BILLIONS USD
    # ------------------------------------------------------------------

    @property
    def revenue(self) -> pd.Series:
        return self._get_row(self.income, "Total Revenue")

    @property
    def cogs(self) -> pd.Series:
        """Cost of Goods Sold. Some companies call it Cost of Revenue."""
        return self._get_row(self.income,
                             "Cost Of Revenue", "Cost of Revenue",
                             "Reconciled Cost Of Revenue")

    @property
    def gross_profit(self) -> pd.Series:
        return self._get_row(self.income, "Gross Profit")

    @property
    def ebit(self) -> pd.Series:
        """Operating income / EBIT."""
        return self._get_row(self.income,
                             "EBIT", "Operating Income",
                             "Ebit")

    @property
    def da(self) -> pd.Series:
        """Depreciation & Amortization — from cash flow statement (non-cash add-back)."""
        return self._get_row(self.cashflow,
                             "Depreciation And Amortization",
                             "Depreciation & Amortization",
                             "Depreciation",
                             "Reconciled Depreciation")

    @property
    def capex(self) -> pd.Series:
        """
        Capital Expenditures — conventionally stored as NEGATIVE in yfinance
        (it is a cash outflow). We return it as a POSITIVE number so the FCF
        formula reads: FCF = NOPAT + D&A - CapEx - DeltaWC (all positive = cleaner).

        Guard: some tickers already report CapEx as positive. We check the median
        sign of the raw series and only negate if it's negative, preventing
        double-negation errors.
        """
        raw = self._get_row(self.cashflow,
                            "Capital Expenditure",
                            "Capital Expenditures",
                            "Purchase Of PPE")
        # If median is negative (normal yfinance convention) -> negate to positive.
        # If already positive (some tickers) -> leave as-is.
        clean = raw.dropna()
        if not clean.empty and float(clean.median()) < 0:
            return -raw
        return raw

    @property
    def working_capital(self) -> pd.Series:
        """
        Working Capital = Current Assets - Current Liabilities
        Change in WC is a cash flow consideration:
          Increase in WC → cash outflow (company is tying up more cash)
          Decrease in WC → cash inflow
        """
        current_assets = self._get_row(self.balance,
                                       "Current Assets", "Total Current Assets")
        current_liab   = self._get_row(self.balance,
                                       "Current Liabilities", "Total Current Liabilities")
        return current_assets - current_liab

    @property
    def net_debt(self) -> float:
        """
        Net Debt = Total Debt - Cash & Equivalents (most recent year, in billions).
        Used to bridge Enterprise Value → Equity Value.
        """
        # Use most recent balance sheet column (last column after our reversal = newest)
        # Actually after reversal last = newest. Let's use iloc[:, -1]
        bal_latest = self.balance.iloc[:, -1] if not self.balance.empty else pd.Series(dtype=float)

        def _val(series_or_df, *names):
            for n in names:
                if n in (series_or_df.index if hasattr(series_or_df, 'index') else []):
                    v = series_or_df[n]
                    return float(v) / 1e9 if not np.isnan(v) else 0.0
            return 0.0

        total_debt = _val(bal_latest,
                          "Total Debt", "Long Term Debt And Capital Lease Obligation",
                          "Long Term Debt")
        cash       = _val(bal_latest,
                          "Cash And Cash Equivalents",
                          "Cash Cash Equivalents And Short Term Investments",
                          "Cash And Short Term Investments")

        if total_debt == 0.0:
            self.warnings.append(
                "Could not find Total Debt on balance sheet. Net Debt may be understated."
            )

        return total_debt - cash

    @property
    def shares_outstanding(self) -> float:
        """Diluted shares outstanding in billions."""
        # Try info dict first (most current)
        shares = self._info.get("sharesOutstanding") or self._info.get("impliedSharesOutstanding")
        if shares:
            return float(shares) / 1e9

        # Fallback: income statement diluted shares
        series = self._get_row(self.income,
                               "Diluted Average Shares", "Basic Average Shares",
                               scale=1e9)
        val = series.iloc[-1] if not series.isna().all() else np.nan
        if np.isnan(val):
            self.warnings.append("Could not determine shares outstanding. Equity value per share may be wrong.")
            return 1.0  # avoid division by zero
        return float(val)

    @property
    def current_price(self) -> float:
        price = self._info.get("currentPrice") or self._info.get("regularMarketPrice")
        if not price:
            self.warnings.append("Could not fetch current market price.")
            return 0.0
        return float(price)

    @property
    def company_name(self) -> str:
        return self._info.get("longName") or self._info.get("shortName") or self.ticker

    # ------------------------------------------------------------------
    # Margin helpers (used to project costs as % of revenue)
    # ------------------------------------------------------------------

    def avg_margin(self, numerator: pd.Series, denominator: pd.Series,
                   years: int = 3) -> float:
        """
        Average ratio of numerator/denominator over last `years` years.
        Standard analyst approach: use trailing average margins to project.
        """
        rev = denominator.iloc[-years:]
        num = numerator.iloc[-years:]
        ratios = num / rev
        ratios = ratios.replace([np.inf, -np.inf], np.nan).dropna()
        if ratios.empty:
            return 0.0
        return float(ratios.mean())

    def summary_dict(self) -> dict:
        """Return a clean dict of all key series for debugging."""
        return {
            "years":           self.years,
            "revenue_bn":      self.revenue.tolist(),
            "cogs_bn":         self.cogs.tolist(),
            "ebit_bn":         self.ebit.tolist(),
            "da_bn":           self.da.tolist(),
            "capex_bn":        self.capex.tolist(),
            "working_capital": self.working_capital.tolist(),
            "net_debt_bn":     self.net_debt,
            "shares_bn":       self.shares_outstanding,
            "current_price":   self.current_price,
        }