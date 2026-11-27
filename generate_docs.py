"""Regenerate docs/QUESTION_SCORING.md and docs/FUND_MAPPING.md directly from the code (so they never drift).

Run from the project root:  python scripts/generate_docs.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smart_investor import risk_engine as re_  # noqa: E402
from smart_investor.allocation import EQUITY_BANDS, MIN_CASH  # noqa: E402
from smart_investor.funds_catalog import CATEGORIES, HYBRID_ALTERNATIVES, PROFILE_MIX, VERIFY_NOTE  # noqa: E402
from smart_investor.questionnaire import ALL_QUESTIONS, SECTIONS  # noqa: E402


def scoring_doc() -> str:
    L = ["# Question scoring reference", "", "_Generated from the code by `scripts/generate_docs.py`. Scores are 0-100; higher = more "
         "tolerance / capacity for risk. 'Context' questions are never scored (age, occupation and spending style are not used "
         "to infer risk preference). Weights are relative within the dimension._", ""]
    for sec, (title, _) in SECTIONS.items():
        L += [f"## Section {sec} - {title}", ""]
        for q in [x for x in ALL_QUESTIONS if x.section == sec]:
            role = {"capacity": "Capacity", "tolerance": "Tolerance", "goal": "Goal model", "context": "Context only",
                    "review": "Review"}[q.dimension]
            w = f", weight {q.weight:g}" if q.scored else ""
            L.append(f"**Q{q.num}. {q.label}** - {role}{w}" + (f" (scorer: {q.scorer})" if q.scorer else ""))
            if q.kind in ("single", "multi") and q.options:
                items = []
                for label, s in q.options.items():
                    items.append(f"{label} = {s:g}" if (s is not None and q.dimension in ('capacity', 'tolerance') and q.scorer != 'pressure')
                                 else (f"{label} = {s:g} pts" if s is not None and q.scorer == 'pressure' else label))
                L.append("- " + "; ".join(items))
            elif q.kind == "number":
                L.append("- Amount in rupees")
            else:
                L.append("- Free text")
            L.append("")
    L += ["## Caps and thresholds", "", "| Rule | Value |", "|---|---|"]
    for (k, a), cap in re_.CAPACITY_CAPS.items():
        L.append(f"| Capacity cap: {k} = '{a}' | {cap} |")
    for b, cap in re_.HORIZON_CAPS:
        L.append(f"| Capacity cap: effective horizon < {b:g} years | {cap} |")
    L += [f"| Profile cut-offs on overall score | {re_.PROFILE_THRESHOLDS} |", f"| Low / Moderate / High cut-offs | {re_.LEVEL_THRESHOLDS} |",
          f"| Capacity vs tolerance gap warning | {re_.DIMENSION_GAP_WARNING} points |",
          f"| Required vs overall gap warning | {re_.REQUIRED_GAP_WARNING} points |",
          f"| Required return mapped to 0 / 100 | {re_.REQ_RETURN_LOW:.0%} / {re_.REQ_RETURN_HIGH:.0%} |",
          f"| Unrealistic required return | above {re_.MAX_PLAUSIBLE_RETURN:.0%} a year |", ""]
    return "\n".join(L)


def mapping_doc() -> str:
    L = ["# Which fund categories fit which risk profile", "", f"> {VERIFY_NOTE}", "",
         "The app first sets an illustrative equity / debt / cash split from the profile (and caps equity for short horizons), "
         "then spreads each sleeve across the categories below. 'Share' is the share within the sleeve.", ""]
    for p, sleeves in PROFILE_MIX.items():
        lo, hi = EQUITY_BANDS[p]
        L += [f"## {p}", "", f"Equity {lo:.0%}-{hi:.0%}; minimum cash {MIN_CASH[p]:.0%}; the rest in debt.", "",
              "| Sleeve | Category | Share in sleeve | Typical risk (indicative) | Example schemes to research |", "|---|---|---|---|---|"]
        for sleeve in ("equity", "debt", "cash"):
            for key, share in sleeves[sleeve]:
                c = CATEGORIES[key]
                L.append(f"| {sleeve.title()} | {c.name} | {share:.0%} | {c.risk_note} | {'; '.join(c.examples)} |")
        alts = [CATEGORIES[k] for k in HYBRID_ALTERNATIVES[p]]
        L += ["", "One-fund alternatives: " + "; ".join(f"{c.name} (e.g. {c.examples[0]})" for c in alts), ""]
    L += ["## How to shortlist within a category", "",
          "1. Compare only funds of the same SEBI category and the same plan type (Direct-Growth with Direct-Growth).",
          "2. Look at 3- and 5-year rolling returns, maximum drawdown and volatility, not just the latest return.",
          "3. Check expense ratio, AUM, fund-manager tenure and portfolio concentration on the AMC factsheet.",
          "4. Use the app's Fund comparison tab (live mfapi.in NAVs) with the 'Live search term' for each category.",
          "5. Fix the emergency fund, high-cost debt and near-term obligations before adding equity funds.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "QUESTION_SCORING.md").write_text(scoring_doc(), encoding="utf-8")
    (ROOT / "docs" / "FUND_MAPPING.md").write_text(mapping_doc(), encoding="utf-8")
    print("docs regenerated")
