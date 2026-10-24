"""
HalalGuard — generic constraint-aware halal filter (view-only, S6 advisory).

Invariant: unified_score ranking is halal-blind (frozen acf502). This guard
is additive-only filtering *after* ranking, before top-N display / deployment.

Tiers: strict / flexible / off  (from config/halal_policy.json)
  L1 sector exclusion: universal_haram + halal_sensitive + sector_map (BATBC->Tobacco)
  L2 debt gates: strict 0.5 LT0.2, flexible 0.8, off 1.0
  L5 DSES membership: strict required, others advisory

BATBC is Tobacco via sector_map; blocked in strict+flexible (L1).
Custom exclusions merge additive-only on top of tier gates.

API:
  guard = HalalGuard(policy_path=...)
  is_eligible(ticker, asof, tier, pit_row, dses_row) -> {eligible, reasons, purification_rate, data_gaps}
  apply(universe, tier) -> filtered list (same order, subset)
  gates_for(tier) -> dict
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = BASE / "config" / "halal_policy.json"


def _load_policy(path: Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_POLICY
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _extract_debt(pit_row: Any) -> tuple[float | None, float | None]:
    """Return (de, lt_de) from pit_row supporting dict/Row/None with multiple key variants."""
    if pit_row is None:
        return None, None
    # dict-like
    def _get(keys: list[str]):
        for k in keys:
            try:
                v = pit_row[k] if isinstance(pit_row, dict) else pit_row[k]  # type: ignore
            except Exception:
                try:
                    v = getattr(pit_row, k)
                except Exception:
                    continue
            if v is not None:
                try:
                    return float(v)
                except Exception:
                    continue
        return None

    de = _get(["debt_equity", "debt_equity_val", "de", "debtEquity"])
    lt = _get(["long_term_debt_equity", "long_term_debt_equity_val", "lt_de", "ltDebtEquity"])
    return de, lt


def _resolve_sector(ticker: str, pit_row: Any, policy: dict) -> str:
    """Resolve effective sector: sector_map override > pit_row sector > Unknown."""
    t = (ticker or "").strip().upper()
    sector_map = (policy.get("L1", {}) or {}).get("sector_map", {}) or {}
    if t in sector_map:
        return str(sector_map[t])
    if pit_row is not None:
        for k in ("sector", "Sector", "SECTOR"):
            try:
                v = pit_row[k] if isinstance(pit_row, dict) else pit_row[k]  # type: ignore
            except Exception:
                continue
            if v:
                return str(v)
        try:
            v = getattr(pit_row, "sector", None)
            if v:
                return str(v)
        except Exception:
            pass
    return "Unknown"


def _is_in_haram_sectors(effective_sector: str, excluded: list[str]) -> bool:
    es = (effective_sector or "").strip().lower()
    for excl in excluded:
        if not excl:
            continue
        el = excl.strip().lower()
        if el == "tobacco" and es == "tobacco":
            return True
        if el.lower() == es:
            return True
        # Banking vs Banking variations, Insurance substrings
        if "bank" in el and "bank" in es:
            return True
        if "insurance" in el and "insurance" in es:
            return True
        if "financial institution" in el and ("financial" in es or "bank" in es):
            return True
        if el == es:
            return True
    return False


class HalalGuard:
    def __init__(self, policy_path: Path | str | None = None, profile: dict | None = None):
        self.policy = _load_policy(Path(policy_path) if policy_path else None)
        self.profile = profile  # optional injected profile; else load on apply
        # Normalize
        self._tiers = self.policy.get("tiers", {}) or {}
        self._l1 = self.policy.get("L1", {}) or {}
        self._l2 = self.policy.get("L2", {}) or {}
        self._l5 = self.policy.get("L5", {}) or {}

    def gates_for(self, tier: str) -> dict:
        t = (tier or "flexible").strip().lower()
        if t not in ("strict", "flexible", "off"):
            t = "flexible"
        tier_cfg = self._tiers.get(t, {}) if self._tiers else {}
        # Fallback defaults if policy missing keys
        defaults = {
            "strict": {"L2_debt_equity_max": 0.5, "L2_long_term_debt_equity_max": 0.2, "L1_sectors_excluded": ["Banking","Insurance","Financial Institutions","Tobacco"]},
            "flexible": {"L2_debt_equity_max": 0.8, "L2_long_term_debt_equity_max": 1.0, "L1_sectors_excluded": ["Banking","Insurance","Financial Institutions","Tobacco"]},
            "off": {"L2_debt_equity_max": 1.0, "L2_long_term_debt_equity_max": 1.0, "L1_sectors_excluded": []},
        }
        d = defaults[t]
        return {
            "tier": t,
            "L1_sectors_excluded": tier_cfg.get("L1_sectors_excluded", d["L1_sectors_excluded"]),
            "L2_debt_equity_max": tier_cfg.get("L2_debt_equity_max", d["L2_debt_equity_max"]),
            "L2_long_term_debt_equity_max": tier_cfg.get("L2_long_term_debt_equity_max", d["L2_long_term_debt_equity_max"]),
            "L5_dses_required": tier_cfg.get("L5_dses_required", False if t != "strict" else True),
        }

    def _load_custom_exclusions(self) -> dict:
        if self.profile is not None:
            ce = (self.profile.get("custom_exclusions") or {})
            return {"sectors": list(ce.get("sectors") or []), "tickers": list(ce.get("tickers") or [])}
        # lazy load from scripts.profile
        try:
            from profile import load_profile  # type: ignore
            prof = load_profile()
            ce = prof.get("custom_exclusions") or {}
            return {"sectors": list(ce.get("sectors") or []), "tickers": list(ce.get("tickers") or [])}
        except Exception:
            return {"sectors": [], "tickers": []}

    def is_eligible(
        self,
        ticker: str,
        asof: str | None = None,
        tier: str | None = None,
        pit_row: Any | None = None,
        dses_row: Any | None = None,
    ) -> dict:
        """
        Evaluate single ticker.

        Returns:
          { eligible: bool, reasons: str[], purification_rate: float, data_gaps: str[] }
        """
        t = (tier or "flexible").strip().lower()
        if t not in ("strict", "flexible", "off"):
            t = "flexible"
        if t == "off":
            return {"eligible": True, "reasons": [], "purification_rate": 0.0, "data_gaps": []}

        gates = self.gates_for(t)
        reasons: list[str] = []
        data_gaps: list[str] = []

        # Resolve tier for subsequent checks
        ticker_u = (ticker or "").strip().upper()

        # Custom exclusions (additive-only)
        ce = self._load_custom_exclusions()
        ce_tickers_u = {s.strip().upper() for s in ce.get("tickers", []) if isinstance(s, str)}
        ce_sectors_l = {s.strip().lower() for s in ce.get("sectors", []) if isinstance(s, str)}

        if ticker_u in ce_tickers_u:
            reasons.append(f"custom_ticker_exclusion:{ticker_u}")

        # L1 sector
        eff_sector = _resolve_sector(ticker_u, pit_row, self.policy)
        excluded = list(gates["L1_sectors_excluded"] or [])
        # tobacco tickers also block via explicit list even if sector_map missing
        tobacco_tickers = {s.upper() for s in (self._l1.get("tobacco_tickers") or [])}
        if ticker_u in tobacco_tickers:
            eff_sector = "Tobacco"
        if _is_in_haram_sectors(eff_sector, excluded):
            reasons.append(f"L1_sector:{eff_sector}")
        if eff_sector.lower() in ce_sectors_l:
            reasons.append(f"custom_sector:{eff_sector}")

        # L2 debt
        de, lt = _extract_debt(pit_row)
        max_de = float(gates["L2_debt_equity_max"])
        max_lt = float(gates["L2_long_term_debt_equity_max"])
        if de is None:
            data_gaps.append("debt_equity_missing")
        elif de > max_de:
            reasons.append(f"L2_debt:{de:.3f}>{max_de:.2f}")
        if t == "strict":
            if lt is None:
                data_gaps.append("lt_debt_missing")
            elif lt > max_lt:
                reasons.append(f"L2_lt_debt:{lt:.3f}>{max_lt:.2f}")

        # L5 DSES
        if gates["L5_dses_required"]:
            # dses_row: dict with dses membership or truthy; if None -> lookup gap
            has_dses = False
            if dses_row is not None:
                if isinstance(dses_row, dict):
                    has_dses = bool(dses_row.get("dses") or dses_row.get("is_dses") or dses_row.get("member"))
                else:
                    try:
                        has_dses = bool(dses_row["dses"])  # sqlite row
                    except Exception:
                        try:
                            has_dses = bool(getattr(dses_row, "dses"))
                        except Exception:
                            has_dses = False
            else:
                # No dses_row supplied -> treat as gap; strictly need membership but allow data_gaps signal
                # If asof provided, caller can supply dses_row; without it we flag gap not block silently
                data_gaps.append("dses_membership_missing")
            if not has_dses and "dses_membership_missing" not in data_gaps:
                # explicit non-member
                reasons.append("L5_dses_not_member")

        # Purification rate: proportional to debt pressure, capped 0.05
        purification_rate = 0.0
        if de is not None and max_de > 0:
            # scale debt ratio relative to gate; 0 if well under gate
            ratio = max(0.0, de / max_de)
            # tier-adjusted: strict more sensitive
            purification_rate = round(min(0.05, ratio * 0.05), 4)
            if reasons and any(r.startswith("L2") for r in reasons):
                purification_rate = 0.05
            elif de <= max_de * 0.4:
                purification_rate = 0.0

        eligible = len(reasons) == 0
        return {
            "eligible": eligible,
            "reasons": reasons,
            "purification_rate": purification_rate,
            "data_gaps": data_gaps,
        }

    def apply(self, universe: list[dict], tier: str | None = None) -> list[dict]:
        """
        Filter ranked universe (halal-blind order preserved). Each entry expected
        to have at least ticker and optionally pit_row/dses_row embedded; otherwise
        ticker-only filtering (L1 strictly via sector_map still applied).

        Returns filtered subset in same order.
        """
        t = (tier or "flexible").strip().lower()
        if t not in ("strict", "flexible", "off"):
            t = "flexible"
        if t == "off":
            return list(universe)
        out: list[dict] = []
        for row in universe:
            ticker = row.get("ticker") or row.get("symbol") or ""
            # Prefer embedded pit/dses if present else row itself as pit
            pit = row.get("pit_row", row)
            dses = row.get("dses_row", row.get("dses"))
            # also allow explicit debt keys on row
            res = self.is_eligible(ticker, asof=row.get("date") or row.get("asof"), tier=t, pit_row=pit, dses_row=dses)
            if res["eligible"]:
                # annotate for downstream columns
                nr = dict(row)
                nr["_halal"] = res
                out.append(nr)
        return out
