"""
DSE Chart Generator — produces visual analytical charts for DSE stocks.

Chart Types:
  1. Price-wise Chart: Price line + SMA 20/50/200 + Bollinger Bands + RSI subplot
  2. Volume-wise Chart: Volume bars with 30-day MA + volume divergence & spike highlights
  3. Market Cap-wise Chart: Sector-wise and top stocks market capitalization comparison

Outputs PNG charts to reports/charts/{category}/{filename}.png
"""

import os
import sqlite3
import datetime
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for headless agent execution
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

BASE_DIR   = Path(__file__).resolve().parent.parent
PROC_DIR   = BASE_DIR / "data" / "processed"
CHART_DIR  = BASE_DIR / "reports" / "charts"
DB_PATH    = PROC_DIR / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("chart_generator")

# Visual style setup
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["figure.autolayout"] = True


def get_db():
    return sqlite3.connect(DB_PATH)


# ── 1. Price-wise Chart ───────────────────────────────────────────────────────

def generate_price_chart(ticker: str, days: int = 180, save_dir: Path = None) -> Path:
    """
    Generates a dual-panel chart:
      Top panel: Close price, SMA20, SMA50, SMA200, Bollinger Bands
      Bottom panel: RSI (14) with 30 oversold / 70 overbought bands
    """
    conn = get_db()
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    query = """
        SELECT date, open, high, low, close, volume
        FROM prices
        WHERE ticker = ? AND date >= ?
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(ticker, since))
    conn.close()

    if df.empty or len(df) < 15:
        log.warning(f"Insufficient price data for {ticker} ({len(df)} rows)")
        return None

    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    # Compute Moving Averages
    df["SMA20"] = df["close"].rolling(window=20).mean()
    df["SMA50"] = df["close"].rolling(window=50).mean()
    df["SMA200"] = df["close"].rolling(window=200).mean()

    # Bollinger Bands (20, 2std)
    roll_std = df["close"].rolling(window=20).std()
    df["BB_Upper"] = df["SMA20"] + (roll_std * 2)
    df["BB_Lower"] = df["SMA20"] - (roll_std * 2)

    # RSI (14)
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # Figure Layout: 2 Subplots (Price 70%, RSI 30%)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

    # --- Top Panel: Price & MAs ---
    ax1.plot(df.index, df["close"], label="Close (BDT)", color="#1f77b4", linewidth=1.8)
    if not df["SMA20"].isna().all():
        ax1.plot(df.index, df["SMA20"], label="SMA 20", color="#ff7f0e", linestyle="--", alpha=0.85)
    if not df["SMA50"].isna().all():
        ax1.plot(df.index, df["SMA50"], label="SMA 50", color="#2ca02c", linestyle="--", alpha=0.85)
    if not df["SMA200"].isna().all():
        ax1.plot(df.index, df["SMA200"], label="SMA 200", color="#d62728", linestyle="-", linewidth=1.5, alpha=0.9)

    # Bollinger Bands Cloud
    if not df["BB_Upper"].isna().all():
        ax1.fill_between(df.index, df["BB_Upper"], df["BB_Lower"], color="#e0e0e0", alpha=0.35, label="Bollinger Bands (20,2)")

    last_close = df["close"].iloc[-1]
    ax1.set_title(f"DSE: {ticker} Price Trend & Technical Structure (Latest: BDT {last_close:.2f})", fontsize=14, weight="bold", pad=10)
    ax1.set_ylabel("Price (BDT)", fontsize=11)
    ax1.legend(loc="upper left", frameon=True, fontsize=9)
    ax1.grid(True, linestyle=":", alpha=0.6)

    # --- Bottom Panel: RSI ---
    ax2.plot(df.index, df["RSI"], label="RSI (14)", color="#9467bd", linewidth=1.4)
    ax2.axhline(70, color="#d62728", linestyle=":", alpha=0.7, label="Overbought (70)")
    ax2.axhline(30, color="#2ca02c", linestyle=":", alpha=0.7, label="Oversold (30)")
    ax2.fill_between(df.index, 30, 70, color="#9467bd", alpha=0.08)
    ax2.set_ylabel("RSI", fontsize=11)
    ax2.set_ylim(10, 90)
    ax2.legend(loc="upper right", frameon=True, fontsize=8)
    ax2.grid(True, linestyle=":", alpha=0.6)

    # Date formatting
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()

    out_dir = save_dir or (CHART_DIR / "price")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{ticker}_price.png"
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    log.info(f"Generated price chart: {out_path}")
    return out_path


# ── 2. Volume-wise Chart ──────────────────────────────────────────────────────

def generate_volume_chart(ticker: str, days: int = 180, save_dir: Path = None) -> Path:
    """
    Generates Volume profile chart:
      Daily trade volume bars (Green for Up day, Red for Down day)
      30-day Volume Moving Average
      Highlights abnormal volume spikes (>2.5x 30d MA)
    """
    conn = get_db()
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    query = """
        SELECT date, open, close, volume, value
        FROM prices
        WHERE ticker = ? AND date >= ?
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(ticker, since))
    conn.close()

    if df.empty or len(df) < 10:
        log.warning(f"Insufficient volume data for {ticker}")
        return None

    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df["Vol_MA30"] = df["volume"].rolling(window=30).mean()

    # Direction color: Close >= Open is Bullish (Green), else Bearish (Red)
    colors = np.where(df["close"] >= df["open"], "#2ca02c", "#d62728")

    # Volume spike flag (>2.5x 30-day average)
    spikes = df[df["volume"] > (df["Vol_MA30"] * 2.5)]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(df.index, df["volume"] / 1000, color=colors, alpha=0.75, width=0.8, label="Daily Volume (k shares)")
    ax.plot(df.index, df["Vol_MA30"] / 1000, color="#1f77b4", linewidth=1.6, label="30-Day Vol Average")

    # Annotate spikes
    if not spikes.empty:
        ax.scatter(spikes.index, spikes["volume"] / 1000, color="#ff7f0e", s=60, zorder=5, label="Vol Spike (>2.5x MA)")

    ax.set_title(f"DSE: {ticker} Trading Volume & Liquidity Profile", fontsize=14, weight="bold", pad=10)
    ax.set_ylabel("Volume (Thousands of Shares)", fontsize=11)
    ax.legend(loc="upper right", frameon=True)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()

    out_dir = save_dir or (CHART_DIR / "volume")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{ticker}_volume.png"
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    log.info(f"Generated volume chart: {out_path}")
    return out_path


# ── 3. Market Cap-wise Comparison Chart ───────────────────────────────────────

def generate_market_cap_chart(save_dir: Path = None) -> Path:
    """
    Generates horizontal bar chart comparing Top 15 DSE Listed Companies by Market Capitalization (Crore BDT).
    """
    conn = get_db()
    query = """
        SELECT ticker, sector, market_cap_cr, category
        FROM companies
        WHERE market_cap_cr IS NOT NULL AND market_cap_cr > 0
        ORDER BY market_cap_cr DESC
        LIMIT 15
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        log.warning("No market cap data in DB")
        return None

    # Sort ascending for clean horizontal bar chart
    df = df.sort_values(by="market_cap_cr", ascending=True)

    fig, ax = plt.subplots(figsize=(11, 7))
    bars = ax.barh(df["ticker"], df["market_cap_cr"] / 100, color="#1f77b4", edgecolor="#0e4368", alpha=0.85)

    # Value labels on bars
    for bar in bars:
        width = bar.get_width()
        ax.text(width + (width * 0.01), bar.get_y() + bar.get_height() / 2,
                f" BDT {width:.1f}k Cr", va="center", ha="left", fontsize=9, weight="bold", color="#333333")

    ax.set_title("Top 15 Listed Companies by Market Capitalization (DSE)", fontsize=14, weight="bold", pad=12)
    ax.set_xlabel("Market Cap (Thousand Crore BDT)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6, axis="x")

    out_dir = save_dir or (CHART_DIR / "market_cap")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "top_15_market_cap.png"
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    log.info(f"Generated market cap chart: {out_path}")
    return out_path


# ── 4. Generate All Charts for Top Tracked Tickers ────────────────────────────

def generate_all_stock_charts(tickers: list[str] = None):
    """
    Runs price, volume, and market cap generation for given tickers (or top tracked).
    """
    if tickers is None:
        conn = get_db()
        rows = conn.execute("SELECT ticker FROM companies ORDER BY market_cap_cr DESC LIMIT 10").fetchall()
        conn.close()
        tickers = [r[0] for r in rows] if rows else ["SQURPHARMA", "GP", "BATBC", "PUBALIBANK", "BRACBANK"]

    generated = {}
    for t in tickers:
        p_path = generate_price_chart(t)
        v_path = generate_volume_chart(t)
        generated[t] = {"price": str(p_path) if p_path else None, "volume": str(v_path) if v_path else None}

    m_path = generate_market_cap_chart()
    generated["_market_cap_overview"] = str(m_path) if m_path else None
    return generated


if __name__ == "__main__":
    import sys
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if ticker_arg and ticker_arg != "all":
        p = generate_price_chart(ticker_arg)
        v = generate_volume_chart(ticker_arg)
        print(f"Price chart: {p}\nVolume chart: {v}")
    else:
        results = generate_all_stock_charts()
        print("Generated charts for all tracked leaders.")
