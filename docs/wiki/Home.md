# 🏛️ Welcome to the `stock_market_expert_bd` Wiki

**The Institutional Knowledge Base for Autonomous Bangladesh Capital Markets Quantitative Research, Risk Screening, and Portfolio Decision-Support.**

---

## 🎯 Executive Mission
Emerging markets such as the **Dhaka Stock Exchange (DSE)** are characterized by extreme informational asymmetry, retail syndicate pump-and-dump operations, speculative rumors, and illiquid trading books. 

The `stock_market_expert_bd` platform was engineered from the ground up to enforce **institutional mathematical rigor, temporal Point-in-Time (PIT) isolation, and forensic risk filtering** on the Bangladesh capital markets.

---

## 📚 Knowledge Base Navigation

Explore the technical chapters and quantitative documentation:

* 🏗️ **[[System-Architecture]]**: The 6-layer pipeline, concurrency guards, and the 8 Non-Negotiable System Invariants.
* ⏱️ **[[Point-in-Time-Accounting]]**: Zero-lookahead temporal isolation across 1,707 company disclosure periods.
* 📐 **[[Quantitative-Formulas]]**: Benjamin Graham fair value, Central Bank sovereign hurdle rates, and Risk-Parity allocation.
* 📊 **[[Sector-Maturity-Matrix]]**: Empirical assessment across all 15 DSE sectors with zero guesswork.
* 🛡️ **[[Forensic-Surveillance]]**: Mathematical detection of volume anomalies ($\text{VAR} \ge 3\times$), negative cash-flow traps, and syndicate pumps.
* 💻 **[[CLI-Reference-&-Agent-Commands]]**: Complete reference for command-line tools, single-word AI agent triggers, and interactive usage.

---

## 🛡️ Core System Invariants

The entire platform is bounded by **8 mathematically non-negotiable invariants**:

1. **INV-1: Strict Point-in-Time Isolation**: No trading decision or backtest may use fundamental data prior to official disclosure (`tradable_date >= publication_date >= snapshot_date`).
2. **INV-2: Central Bank Macro Hurdle**: Every equity investment must yield an Equity Risk Premium $\ge +3.50\%$ above Bangladesh Bank 91-Day T-Bills (Hurdle = 15.10%).
3. **INV-3: 100% Shariah / Halal Shield**: Zero debt-trap or non-compliant balance sheets permitted under Halal profile.
4. **INV-4: Frontier Microstructure Realism**: Enforces statutory DSE transaction fees (0.415% buy / 0.465% sell including Section 53BBB AIT) and floor/circuit locks.
5. **INV-5: Frozen Champion Registry**: Eliminates p-hacking and multiple-testing bias via cryptographic model registration.
6. **INV-6: Cryptographic Forward Ledger V2**: Prospective out-of-sample portfolio decisions recorded in SHA-256 hash-chained blocks.
7. **INV-7: Universal SQLite WAL**: High-concurrency operations guarded by SQLite WAL mode and 30-second busy-timeout handlers.
8. **INV-8: Zero-Broken Portable Bootstrap**: Self-healing initialization from `dse.db.gz` with zero external dependencies.
