import yfinance as yf
import pandas as pd
import numpy as np

# Italian banks (Milan tickers need .MI suffix) + high-dividend ETFs
tickers = {
    "BPER Banca":    "BPE.MI",
    "UniCredit":     "UCG.MI",
    "Intesa Sanpaolo": "ISP.MI",
    "Banca Monte dei Paschi": "BMPS.MI",
    "Azimut":        "AZM.MI",
    "VHYL All-World High Div (EUR)": "VHYL.AS",
    "iShares EuroStoxx Select Div 30": "IDVY.L",
}

data = yf.download(list(tickers.values()), period="5y", interval="1mo", auto_adjust=True)["Close"]
data = data.rename(columns={v: k for k, v in tickers.items()}).dropna(how="all")

rets = data.pct_change().dropna()

# cache last prices from the monthly series
last_px = data.iloc[-1]

print("=== Total return (price only, 5y) ===")
print((data.iloc[-1] / data.dropna().iloc[0] - 1).round(3).sort_values(ascending=False))

print("\n=== CAGR, 5y total-return (adjusted, dividends reinvested) ===")
y05 = len(rets.dropna()) / 12
cagr = ((data.dropna().iloc[-1] / data.dropna().iloc[0]) ** (1 / y05) - 1)
print((cagr * 100).round(1).to_string())

print("\n=== Correlation matrix (monthly returns) ===")
print(rets.corr().round(2).to_string())

print("\n=== Volatility (annualized) ===")
print((rets.std() * np.sqrt(12)).round(3))

print("\n=== Dividend yield (TTM cash dividends / last close) ===")
def ttm_yield(t):
    tk = yf.Ticker(t)
    d = tk.dividends
    if d.empty:
        return 0.0, 0.0
    ttm = d[d.index >= d.index.max() - pd.Timedelta(days=365)].sum()
    try:
        px = tk.history(period="10d")["Close"].dropna().iloc[-1]
    except Exception:
        px = np.nan
    if np.isnan(px):
        px = last_px[tickers_inv[t]]
    return (ttm / px), ttm

tickers_inv = {v: k for k, v in tickers.items()}
for name, t in tickers.items():
    y, ttm = ttm_yield(t)
    print(f"{name:34s} {y*100:5.2f}%  (TTM div {ttm:.2f} EUR)")

# === The actual question: 5k split 1.25k x 2 banks + 1.25k x 2 ETFs ===
print("\n=== 5k portfolio: 1.25k x (2 picked banks) + 1.25k x (2 ETFs) ===")
sel = ["UniCredit", "BPER Banca", "VHYL All-World High Div (EUR)", "iShares EuroStoxx Select Div 30"]
w = pd.Series(1250, index=sel)
pr = rets[sel]
port = (pr * (w / w.sum())).sum(axis=1)
print(f"Total-return volatility: {port.std()*np.sqrt(12)*100:.1f}%   CAGR 5y: {((1+port).prod()**(12/len(port))-1)*100:.1f}%")

income_port = 0
for n in sel:
    y, ttm = ttm_yield(tickers[n])
    inc = 1250 * y
    income_port += inc
    print(f"  {n:34s} 1250 EUR -> ~{inc:6.2f} EUR/yr cash ({y*100:.2f}%)")
print(f"  {'TOTAL':34s}          -> ~{income_port:6.2f} EUR/yr  ({income_port/5000*100:.2f}% blended)")

print("\n=== 5k fully in one instrument (income reference) ===")
for n in list(tickers.keys()):
    y, ttm = ttm_yield(tickers[n])
    print(f"  {n:34s} 5000 EUR -> ~{5000*y:6.2f} EUR/yr ({y*100:.2f}%)")
