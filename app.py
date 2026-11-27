"""Smart Investor Risk Profile - Streamlit dashboard (53-question questionnaire).

Run:  streamlit run app.py
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from smart_investor import allocation as alloc_mod
from smart_investor import crash as crash_mod
from smart_investor import dry_periods as dp
from smart_investor import data_loader as dl
from smart_investor import fund_analytics as fa
from smart_investor import persistence
from smart_investor import scorecard as sc
from smart_investor import sector_analysis as sa
from smart_investor import technicals as tech
from smart_investor.export import build_bundle
from smart_investor.funds_catalog import VERIFY_NOTE, hybrid_alternatives, profile_matrix, shortlist
from smart_investor.goal import assess_goal
from smart_investor.questionnaire import (ALL_QUESTIONS, PREFERRED_EQUITY, SECTIONS, TOLERABLE_DECLINE, InvestorInputs,
                                          ValidationError, missing_questions)
from smart_investor.report import DISCLAIMER, build_report, scorecard_section, sector_section
from smart_investor.risk_engine import PROFILES, assess
from smart_investor.samples import PERSONAS_FULL

st.set_page_config(page_title="Smart Investor Risk Profile", page_icon="📊", layout="wide")
st.title("📊 Smart Investor Risk Profile")
st.caption("Risk tolerance · Risk capacity · Risk required · Lifestyle & financial context")
st.info(DISCLAIMER)

(tab_q, tab_p, tab_g, tab_c, tab_fc, tab_f, tab_s, tab_sc, tab_r, tab_h) = st.tabs(
    ["1 Questionnaire", "2 Assessment", "3 Goal & allocation", "4 Crash scenarios", "5 Fund categories",
     "6 Fund comparison", "7 Sectors & dry periods", "8 Fund scorecard", "9 Report & export", "10 History"])
if "session_id" not in st.session_state:
    st.session_state["session_id"] = persistence.new_session_id()

QKEY = "q_{}".format


# ------------------------------------------------------------------ reusable data-source picker
def pick_data(prefix: str, kind: str):
    """Data-source UI shared by the fund and sector tabs. kind = 'fund' or 'sector'. Returns navs, bench, meta, note."""
    label = "sector proxies (sector index funds / ETFs)" if kind == "sector" else "funds"
    source = st.radio("Data source", ["Sample data (synthetic, offline)", "Live from mfapi.in", "Upload CSVs (date, nav)"],
                      horizontal=True, key=f"{prefix}_src")
    navs, bench, meta, note = {}, None, {}, ""
    if source.startswith("Sample"):
        navs, bench, meta = dl.sample_sectors() if kind == "sector" else dl.sample_universe()
        note = "SYNTHETIC demo data - not real performance."
        st.warning(note)
    elif source.startswith("Live"):
        hint = ("Search a sector proxy, e.g. 'nifty bank index direct growth'. Search terms for common sectors are listed under the chart."
                if kind == "sector" else "Search scheme name (e.g. 'nifty 50 index direct growth')")
        q = st.text_input(hint, key=f"{prefix}_q")
        store = st.session_state.setdefault(f"{prefix}_store", {})   # label -> scheme code, kept across searches
        if q or store:
            try:
                opts = {}
                if q:
                    found = dl.search_schemes(q)[:25]
                    opts = {f"{f['schemeName']} ({f['schemeCode']})": f["schemeCode"] for f in found}
                all_opts = {**opts, **store}          # earlier picks stay selectable while you search for more
                chosen = st.multiselect(f"Pick {label} (search again to add more; picks are kept)", list(all_opts),
                                        key=f"{prefix}_pick")
                st.session_state[f"{prefix}_store"] = {lab: all_opts[lab] for lab in chosen}
                bq = st.text_input("Benchmark scheme (optional, e.g. a Nifty 50 index fund)", key=f"{prefix}_bq")
                for lab in chosen:
                    s, m = dl.fetch_nav(all_opts[lab])
                    navs[m["name"]] = s
                    meta[m["name"]] = {"category": m.get("category", "")}
                if bq:
                    bf = dl.search_schemes(bq)[:10]
                    if bf:
                        bl = st.selectbox("Benchmark match", [f"{f['schemeName']} ({f['schemeCode']})" for f in bf], key=f"{prefix}_bm")
                        bench, _ = dl.fetch_nav(bl.rsplit("(", 1)[1].rstrip(")"))
                if navs:
                    note = "mfapi.in (AMFI NAVs); last NAV dates shown in table."
                if kind == "fund":
                    st.caption("Expense ratio and holdings concentration are not in NAV data; enter them below.")
                    for n in navs:
                        c1, c2 = st.columns(2)
                        meta[n]["expense_ratio"] = c1.number_input(f"{n[:40]} expense ratio %", 0.0, 5.0, 0.0, 0.05, key=f"{prefix}_er_{n}") / 100 or float("nan")
                        meta[n]["top10_concentration"] = c2.number_input(f"{n[:40]} top-10 holdings %", 0.0, 100.0, 0.0, 1.0, key=f"{prefix}_tc_{n}") / 100 or float("nan")
            except Exception as e:  # network / API errors
                st.error(f"Could not reach mfapi.in ({e}). Use sample data or upload CSVs.")
    else:
        files = st.file_uploader("NAV / price CSVs, one per series (columns: date, nav)", type="csv", accept_multiple_files=True, key=f"{prefix}_up")
        for f in files or []:
            try:
                nm = f.name.rsplit(".", 1)[0]
                navs[nm] = dl.load_csv_nav(f)
                meta[nm] = {}
            except ValueError as e:
                st.error(f"{f.name}: {e}")
        bf = st.file_uploader("Benchmark CSV (optional)", type="csv", key=f"{prefix}_ubf")
        if bf:
            bench = dl.load_csv_nav(bf)
        if navs:
            note = "User-uploaded NAV files."
    return navs, bench, meta, note


# ------------------------------------------------------------------ questionnaire widgets
def load_persona():
    name = st.session_state.get("persona_choice")
    if name in PERSONAS_FULL:
        for k, v in PERSONAS_FULL[name].items():
            st.session_state[QKEY(k)] = v


def clear_answers():
    for q in ALL_QUESTIONS:
        st.session_state.pop(QKEY(q.key), None)


def render_question(q):
    label = f"{q.num}. {q.text}" + (" *" if q.required else "")
    key = QKEY(q.key)
    if q.kind == "single":
        opts = list(q.options)
        st.radio(label, opts, index=None, key=key, horizontal=sum(len(o) for o in opts) < 85, help=q.help or None)
    elif q.kind == "multi":
        st.multiselect(label, list(q.options), key=key, placeholder="Select all that apply")
    elif q.kind == "number":
        st.number_input(label, min_value=0.0, value=None, step=1000.0, format="%.0f", key=key, placeholder="₹ amount")
    else:
        st.text_area(label, key=key, height=70)


def collect_inputs() -> InvestorInputs:
    ans = {}
    for q in ALL_QUESTIONS:
        v = st.session_state.get(QKEY(q.key))
        ans[q.key] = list(v or []) if q.kind == "multi" else (v if v is not None or q.kind != "text" else "")
    infl = (st.session_state.get("q_inflation_pct") or 6.0) / 100
    override = st.session_state.get("q_horizon_override") or None
    return InvestorInputs(ans, infl, override)


with tab_q:
    st.subheader("Complete investor questionnaire")
    c1, c2, c3 = st.columns([3, 1, 1])
    c1.selectbox("Try an example investor (fictional)", ["—"] + list(PERSONAS_FULL), key="persona_choice")
    c2.button("Load example", on_click=load_persona, width="stretch")
    c3.button("Clear answers", on_click=clear_answers, width="stretch")
    st.caption("Select one answer unless a question says 'select all that apply'. Amounts are approximate, in ₹. "
               "Nothing is stored unless you press 'Save this run' on the Report tab (scores only, no personal details). "
               "Questions marked * are required.")
    st.text_input("Investor reference (optional; appears on the report, never stored)", key="investor_ref")
    with st.form("questionnaire"):
        for sec, (title, intro) in SECTIONS.items():
            st.markdown(f"### Section {sec} — {title}")
            st.caption(intro)
            for q in [x for x in ALL_QUESTIONS if x.section == sec]:
                render_question(q)
                if q.key == "goal_inflation":
                    i1, i2 = st.columns(2)
                    i1.number_input("Assumed inflation (% a year)", 0.0, 15.0, 6.0, 0.5, key="q_inflation_pct",
                                    help="Used only if the goal rises with inflation.")
                    i2.number_input("Exact goal horizon in years (optional; 0 = use the range chosen above)", 0.0, 50.0, 0.0, 0.5,
                                    key="q_horizon_override")
        st.form_submit_button("Calculate my profile", type="primary")

inputs = collect_inputs()
missing = missing_questions(inputs)
with tab_q:
    total_required = len([q for q in ALL_QUESTIONS if q.required])
    st.progress((total_required - len(missing)) / total_required, text=f"{total_required - len(missing)} of {total_required} required questions answered")
    if missing:
        st.warning("Still to answer: " + ", ".join(f"Q{q.num}" for q in missing) + ". Then press 'Calculate my profile'.")

risk, input_error = None, None
if not missing:
    try:
        risk = assess(inputs)
    except ValidationError as e:
        input_error = str(e)
if input_error:
    with tab_q:
        st.error(input_error)

if risk is None:
    for t in (tab_p, tab_g, tab_c, tab_fc, tab_r):
        with t:
            st.info("Answer all required questions on the Questionnaire tab and press 'Calculate my profile' (or load an example investor).")
else:
    a = inputs.answers
    goal = risk.goal

    # ------------------------------------------------------------------ 2. Assessment (Section 8)
    with tab_p:
        st.subheader(f"Overall risk profile: {risk.profile}" + ("  (provisional)" if risk.provisional else ""))
        m1, m2, m3, m4 = st.columns(4)
        for col, label, score, lvl, tip in (
                (m1, "Risk tolerance", risk.tolerance, risk.tolerance_level, "Emotional willingness to accept volatility"),
                (m2, "Risk capacity", risk.capacity, risk.capacity_level, "Financial ability to absorb losses"),
                (m3, "Risk required", risk.required, risk.required_level, "Risk implied by your goal"),
                (m4, "Overall", risk.overall, risk.profile, "Lower of capacity and tolerance")):
            col.metric(label, f"{score:.0f}", help=tip)
            col.caption(f"**{lvl}**")
        fig = go.Figure(go.Bar(x=["Tolerance", "Capacity", "Required by goal", "Overall (drives profile)"],
                               y=[risk.tolerance, risk.capacity, risk.required, risk.overall],
                               marker_color=["#61a5c2", "#2a6f97", "#e09f3e", "#1b4332"]))
        fig.update_layout(yaxis=dict(range=[0, 100], title="Score (0-100)"), height=300, margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")
        st.markdown("**Scale:** " + " → ".join(f"**{p}**" if p == risk.profile else p for p in PROFILES))
        st.success("**Rule used when the dimensions conflict:** " + risk.rule)

        st.markdown("#### Assessment summary")
        feas_preview = assess_goal(risk, alloc_mod.allocation_for(risk.profile, risk.liquidity_horizon))
        summary = pd.DataFrame([
            ["Risk Tolerance", f"{risk.tolerance_level} ({risk.tolerance:.0f})", " ".join(risk.explanations["tolerance"][1:]) or "-"],
            ["Risk Capacity", f"{risk.capacity_level} ({risk.capacity:.0f})", " ".join(risk.explanations["capacity"][1:]) or "-"],
            ["Risk Required", f"{risk.required_level} ({risk.required:.0f})", " ".join(risk.explanations["required"])],
            ["Overall Risk Profile", risk.profile, f"Capacity-based: {risk.capacity_profile}; tolerance-based: {risk.tolerance_profile}"],
            ["Goal Feasibility", feas_preview.label, f"Base case {feas_preview.base_value:,.0f} vs target {feas_preview.target:,.0f} (default allocation)"],
            ["Risk Mismatch", "Potential mismatch" if risk.mismatch else "None", f"{len(risk.warnings)} warning(s) below"],
        ], columns=["Assessment", "Result", "Explanation / notes"])
        st.table(summary.set_index("Assessment"))

        for code, w in zip(risk.codes, risk.warnings):
            (st.error if code in ("LOW_EMERGENCY_RESERVE", "HIGH_DEBT", "GOAL_UNREALISTIC") else st.warning)(w)
        if not risk.warnings:
            st.success("No warnings raised.")
        with st.expander("Score breakdown by question"):
            labels = {q.key: q.label for q in ALL_QUESTIONS}
            labels["horizon"] = "Time horizon (effective)"
            st.dataframe(pd.Series({labels[k]: v for k, v in risk.breakdown.items()}, name="score (0-100)").to_frame(), width="stretch")
        st.caption("Labels are educational, not regulatory categories. Weights and thresholds need validation before any live use.")

    # ------------------------------------------------------------------ 3. Goal & allocation
    with tab_g:
        lo, hi = alloc_mod.EQUITY_BANDS[risk.profile]
        st.subheader("Illustrative allocation")
        st.caption(f"Equity band for {risk.profile}: {lo:.0%}-{hi:.0%}. The shorter of your time-to-withdrawal and goal horizon "
                   f"({risk.liquidity_horizon:g} years) may cap equity further. Educational, not personalised instructions.")
        tilt = st.slider("Position within the profile's equity band", 0.0, 1.0, 0.5, 0.05, help="0 = lowest equity, 1 = highest in band")
        with st.expander("Return and volatility assumptions (illustrative, editable)"):
            assumptions = {}
            cols = st.columns(3)
            for col, k in zip(cols, ("equity", "debt", "cash")):
                d = alloc_mod.DEFAULT_ASSUMPTIONS[k]
                assumptions[k] = {
                    "return": col.number_input(f"{k.title()} return %", value=d["return"] * 100, step=0.5, key=f"r_{k}") / 100,
                    "vol": col.number_input(f"{k.title()} volatility %", value=d["vol"] * 100, step=0.5, key=f"v_{k}") / 100}
        alloc = alloc_mod.allocation_for(risk.profile, risk.liquidity_horizon, tilt)
        ret, vol = alloc_mod.portfolio_stats(alloc, assumptions)
        feas = assess_goal(risk, alloc, assumptions, a["shortfall_preference"])

        g1, g2 = st.columns(2)
        with g1:
            pie = px.pie(names=["Equity", "Debt", "Cash"], values=[alloc.equity, alloc.debt, alloc.cash], hole=0.5,
                         color_discrete_sequence=["#2a6f97", "#61a5c2", "#bfd7ea"])
            pie.update_layout(height=300, margin=dict(t=10, b=10))
            st.plotly_chart(pie, width="stretch")
            st.metric("Assumed portfolio return (annual)", f"{ret:.1%}")
            st.metric("Assumed portfolio volatility", f"{vol:.1%}")
        with g2:
            st.markdown("#### Goal feasibility")
            st.metric("Goal feasibility", feas.label, delta="base case reaches target" if feas.feasible else f"shortfall ₹{feas.shortfall:,.0f}",
                      delta_color="normal" if feas.feasible else "inverse")
            st.write(f"Target ₹{goal.goal_amount:,.0f} today" + (f" → **₹{feas.target:,.0f}** in {goal.horizon_years:g} years at "
                     f"{goal.inflation_rate:.1%} inflation" if goal.inflation_linked else " (fixed)"))
            bar = go.Figure(go.Bar(x=["Pessimistic", "Base", "Optimistic"], y=[feas.pessimistic_value, feas.base_value, feas.optimistic_value],
                                   marker_color=["#bfd7ea", "#2a6f97", "#61a5c2"]))
            bar.add_hline(y=feas.target, line_dash="dash", annotation_text="Target")
            bar.update_layout(height=280, yaxis_title="Value at goal date (₹)", margin=dict(t=20))
            st.plotly_chart(bar, width="stretch")
            st.caption("Scenarios shift the assumed return by one portfolio volatility. They are not forecasts.")
        if risk.required_return is not None:
            st.write(f"Return needed to reach the goal: **{risk.required_return:.1%} a year** vs {ret:.1%} assumed for this portfolio.")
        else:
            st.error("The goal needs more than 20% a year, which is not a realistic planning assumption.")
        if feas.levers:
            st.markdown("**Alternatives if the plan falls short (your preferred option first; none is guaranteed):**")
            for l in feas.levers:
                st.write("• " + l)
        lo_m, hi_m = PREFERRED_EQUITY[a["preferred_mix"]]
        if not (lo_m - 1e-9 <= alloc.equity <= hi_m + 1e-9):
            st.info(f"Comfort check: you said '{a['preferred_mix']}' (about {lo_m:.0%}-{hi_m:.0%} equity), while this illustrative "
                    f"allocation has {alloc.equity:.0%} equity. Neither is 'right'; the allocation follows your profile.")

    # ------------------------------------------------------------------ 4. Crash scenarios
    with tab_c:
        st.subheader("Hypothetical downside scenarios")
        st.caption("A scenario, not a forecast or a maximum-loss estimate. Debt and cash can also lose value in stress.")
        s1, s2, s3 = st.columns(3)
        pf_value = s1.number_input("Portfolio value today (₹)", min_value=1_000, value=max(int(goal.current_investments), 100_000), step=10_000)
        eq_shock = s2.slider("Equity fall %", 5, 60, 20) / 100
        debt_shock = s3.slider("Debt fall %", 0, 10, 0) / 100
        res = crash_mod.simulate_crash(pf_value, alloc, eq_shock, debt_shock)
        x1, x2, x3 = st.columns(3)
        x1.metric("Value after fall", f"₹{res.end_value:,.0f}", f"-{res.loss_pct:.1%}", delta_color="inverse")
        x2.metric("Loss", f"₹{res.loss_amount:,.0f}")
        x3.metric("Approx. recovery", f"{res.recovery_years:.1f} yrs" if res.recovery_years is not None else "n/a",
                  help="At the assumed return, with no new money")
        tol_dec = TOLERABLE_DECLINE[a["tolerable_decline"]]
        warn = crash_mod.comfort_warning(res.loss_pct, tol_dec)
        if warn:
            st.warning(warn)
        crashes = crash_mod.crash_table(pf_value, alloc, debt_shock=debt_shock)
        cb = go.Figure(go.Bar(x=[f"-{c.equity_shock:.0%} equity" for c in crashes], y=[c.end_value for c in crashes], marker_color="#2a6f97"))
        cb.add_hline(y=pf_value, line_dash="dash", annotation_text="Starting value")
        cb.update_layout(height=280, yaxis_title="Portfolio value (₹)", margin=dict(t=20))
        st.plotly_chart(cb, width="stretch")

        st.markdown("#### Estimated impact on your goal")
        timing = {"Right now": 0.0, "Half-way to the goal": goal.horizon_years / 2, "One year before the goal date": max(goal.horizon_years - 1, 0.0)}
        impacts = [crash_mod.goal_impact(goal.current_investments, goal.monthly_contribution, goal.horizon_years, alloc, eq_shock,
                                         t, feas.target, assumptions, debt_shock) for t in timing.values()]
        gi = pd.DataFrame([{"Shock timing": k, "Value at goal date (no shock)": f"₹{i.value_no_shock:,.0f}",
                            "Value at goal date (with shock)": f"₹{i.value_with_shock:,.0f}", "Value lost": f"₹{i.value_lost:,.0f}",
                            "Goal still met?": "Yes" if i.met_with_shock else f"No (short by ₹{i.shortfall_with_shock:,.0f})"}
                           for k, i in zip(timing, impacts)])
        st.dataframe(gi, width="stretch", hide_index=True)
        st.caption("A late shock leaves little time to recover, which is why near-term goals suit lower equity exposure.")

    # ------------------------------------------------------------------ 5. Fund categories
    with tab_fc:
        sl = shortlist(risk.profile, alloc)
        st.subheader(f"Fund categories to research for the {risk.profile} profile")
        st.warning(VERIFY_NOTE)
        show = sl.copy()
        show["Portfolio weight"] = show["Portfolio weight"].map(lambda x: f"{x:.1%}")
        st.dataframe(show.drop(columns=["Live search term"]), width="stretch", hide_index=True)
        st.caption(f"Weights follow the illustrative allocation (equity {alloc.equity:.0%} / debt {alloc.debt:.0%} / cash {alloc.cash:.0%}). "
                   "Use the 'Live search term' on the Fund comparison tab to pull real NAV data and compare funds in the same category.")
        st.markdown("**One-fund alternatives** (for investors who prefer a single scheme):")
        st.dataframe(hybrid_alternatives(risk.profile), width="stretch", hide_index=True)
        notes = ["Prefer Direct plans for lower cost, and compare funds only within the same category.",
                 "A short horizon or an emergency fund below 3 months should be fixed before adding equity funds."]
        if a["objectives"] and "Regular income generation" in a["objectives"]:
            notes.append("You selected regular income: debt and hybrid categories fit income needs better than growth-oriented equity; "
                         "note that mutual-fund returns are not guaranteed and income is taxable.")
        for n in notes:
            st.write("• " + n)
        with st.expander("All five profiles at a glance"):
            st.dataframe(profile_matrix(), width="stretch", hide_index=True)
        shortlist_df = sl

    # ------------------------------------------------------------------ 6. Fund comparison
with tab_f:
    st.subheader("Mutual-fund comparison")
    navs, bench, meta, data_note = pick_data("fund", "fund")

    if len(navs) >= 1:
        # Default to funds in the same category as the first fund, so the first view is like-for-like.
        first_cat = meta.get(next(iter(navs)), {}).get("category", "")
        same_cat = [n for n in navs if first_cat and meta.get(n, {}).get("category") == first_cat]
        default_funds = same_cat if len(same_cat) >= 2 else list(navs)[:4]
        names = st.multiselect("Funds to compare", list(navs), default=default_funds)
        c1, c2, c3 = st.columns(3)
        years = c1.selectbox("Evaluation window (years)", [1, 3, 5], index=1)
        rf = c2.number_input("Risk-free rate %", 0.0, 15.0, fa.DEFAULT_RF * 100, 0.25) / 100
        roll_w = c3.selectbox("Rolling-return window (years)", [1, 3, 5], index=1)
        if names:
            cw = fa.category_warning(meta, names)
            if cw:
                st.warning(cw)
            table = fa.compare_funds({n: navs[n] for n in names}, bench, years, rf, meta)
            if not table["Full window?"].all():
                st.warning("Some funds do not have a full history for this window; their metrics are not like-for-like.")
            fmt = {"CAGR": "{:.1%}", "Volatility": "{:.1%}", "Sharpe": "{:.2f}", "Max drawdown": "{:.1%}",
                   "Beta": "{:.2f}", "Expense ratio": "{:.2%}", "Top-10 holdings %": "{:.0%}"}
            st.dataframe(table.style.format(fmt, na_rep="n/a"), width="stretch")
            st.caption("Beta needs a benchmark; expense ratio and concentration come from factsheets. "
                       "No single metric (Sharpe or recent return) is a complete fund assessment.")
            wins = {n: fa.slice_period(navs[n], years) for n in names}
            growth = go.Figure()
            for n, s in wins.items():
                growth.add_scatter(x=s.index, y=s / s.iloc[0] * 100, name=n)
            growth.update_layout(title="Growth of 100", height=340, margin=dict(t=40))
            st.plotly_chart(growth, width="stretch")
            r1, r2 = st.columns(2)
            with r1:
                dd = go.Figure()
                for n, s in wins.items():
                    d = fa.drawdown_series(s)
                    dd.add_scatter(x=d.index, y=d, name=n)
                dd.update_layout(title="Drawdown", yaxis_tickformat=".0%", height=320, margin=dict(t=40))
                st.plotly_chart(dd, width="stretch")
            with r2:
                rr = go.Figure()
                for n in names:
                    s = fa.rolling_returns(navs[n], roll_w)
                    if len(s):
                        rr.add_scatter(x=s.index, y=s, name=n)
                rr.update_layout(title=f"{roll_w}Y rolling returns (annualised)", yaxis_tickformat=".0%", height=320, margin=dict(t=40))
                st.plotly_chart(rr, width="stretch")
            st.session_state["fund_table"] = table
            st.session_state["data_note"] = data_note
            st.session_state["export_navs"] = {n: navs[n] for n in names}
            st.session_state["export_years"] = years
            st.session_state["export_roll"] = roll_w


# ------------------------------------------------------------------ 7. Sectors & dry periods
with tab_s:
    st.subheader("Sectors & dry periods")
    st.caption("A 'dry period' is a stretch with no progress: the wait to regain a previous high, a run of negative or below-inflation "
               "returns, or lagging the broad market. Sectors are measured through proxies (sector index funds or ETFs). "
               "History describes the past; it does not forecast the future.")
    s_navs, s_bench, s_meta, s_note = pick_data("sec", "sector")
    if len(s_navs) >= 1:
        infl = st.number_input("Inflation for 'below inflation' test %", 0.0, 15.0, 6.0, 0.5, key="sec_infl") / 100
        if risk is not None:
            horizon = float(risk.liquidity_horizon)
            tol_dd = TOLERABLE_DECLINE[inputs.answers["tolerable_decline"]]
            st.caption(f"Using your questionnaire: horizon {horizon:g} years, tolerable decline about {tol_dd:.0%}.")
        else:
            c1, c2 = st.columns(2)
            horizon = float(c1.number_input("Your investment horizon (years)", 1, 40, 5, key="sec_h"))
            tol_dd = c2.slider("Temporary fall you could tolerate %", 5, 60, 20, key="sec_t") / 100
        summ = sa.sector_summary(s_navs, s_bench, infl)
        pct = ["CAGR", "Volatility", "Max drawdown", "% time >10% below peak", "Current drawdown", "% 1Y windows negative",
               "% 3Y windows below inflation", "Worst year", "Best year", "% 1Y windows lagging benchmark"]
        fmt = {c: "{:.1%}" for c in pct}
        fmt.update({"History (yrs)": "{:.1f}", "Longest underwater (yrs)": "{:.1f}", "Years since high": "{:.1f}",
                    "Longest negative-1Y spell (yrs)": "{:.1f}", "Longest lag vs benchmark (yrs)": "{:.1f}"})
        st.markdown("**Dry-period scorecard**")
        st.dataframe(summ.style.format(fmt, na_rep="n/a"), width="stretch")
        st.caption("Dry-period risk: High if the longest wait for a new high exceeded 5 years or the series spent over 50% of days more than 10% "
                   "below a prior peak; Moderate at 3 years / 30%. Trend is context only.")
        warns = sa.horizon_warnings(summ, horizon, tol_dd)
        if warns:
            with st.expander(f"Compared with your horizon and tolerance ({len(warns)} notes)", expanded=True):
                for w in warns:
                    st.write("• " + w)

        st.markdown("**Underwater episodes (falls of 10% or more)**")
        rows = []
        for n, s in s_navs.items():
            ep = dp.drawdown_episodes(s, 0.10)
            for _, r in ep.iterrows():
                rows.append({"Sector": n, "Start": r["peak_date"], "Finish": r["recovery_date"] if pd.notna(r["recovery_date"]) else s.index[-1],
                             "Depth": f"{r['depth']:.0%}", "Status": "Still below peak" if r["ongoing"] else "Recovered"})
        if rows:
            tl = px.timeline(pd.DataFrame(rows), x_start="Start", x_end="Finish", y="Sector", color="Status", hover_data=["Depth"],
                             color_discrete_map={"Recovered": "#8ab6d6", "Still below peak": "#c0392b"})
            tl.update_layout(height=120 + 40 * len(s_navs), margin=dict(t=20))
            st.plotly_chart(tl, width="stretch")
        else:
            st.info("No falls of 10% or more in this history.")

        cal = dp.calendar_returns(s_navs)
        if not cal.empty:
            h1, h2 = st.columns(2)
            with h1:
                hm = px.imshow(cal.T, text_auto=".0%", color_continuous_scale="RdYlGn", color_continuous_midpoint=0, aspect="auto",
                               title="Calendar-year returns (latest year is year-to-date)")
                hm.update_layout(height=120 + 45 * len(cal.columns), margin=dict(t=40), coloraxis_showscale=False)
                st.plotly_chart(hm, width="stretch")
            with h2:
                rk = sa.rotation_ranks(s_navs).astype(float)
                rm = px.imshow(rk.T, text_auto=".0f", color_continuous_scale="RdYlGn_r", aspect="auto",
                               title="Rotation: rank each year (1 = best)")
                rm.update_layout(height=120 + 45 * len(cal.columns), margin=dict(t=40), coloraxis_showscale=False)
                st.plotly_chart(rm, width="stretch")
            st.dataframe(sa.rotation_summary(s_navs), width="stretch")
        cm = sa.correlation_matrix(s_navs)
        if not cm.empty:
            with st.expander("Diversification: correlation of daily returns"):
                st.plotly_chart(px.imshow(cm, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r"), width="stretch")
                st.caption("High correlation means sectors tend to be dry at the same time, so holding both diversifies less.")

        st.markdown("**Single-sector detail**")
        pick = st.selectbox("Sector", list(s_navs), key="sec_detail_pick")
        sel = s_navs[pick]
        win = st.selectbox("Rolling window (years)", [1, 3, 5], index=1, key="sec_win")
        sp = dp.dry_spells(sel, win, infl)
        rr = fa.rolling_returns(sel, win)
        fig = go.Figure()
        if len(rr):
            fig.add_scatter(x=rr.index, y=rr, name=f"{win}Y rolling return")
            fig.add_hline(y=0, line_dash="dash")
            fig.add_hline(y=infl, line_dash="dot", annotation_text="inflation")
            for _, r in sp.iterrows():
                fig.add_vrect(x0=r["start"], x1=r["end"], fillcolor="red", opacity=0.12, line_width=0)
        fig.update_layout(title=f"{pick}: {win}Y rolling return; shaded = below inflation", yaxis_tickformat=".0%", height=320, margin=dict(t=40))
        st.plotly_chart(fig, width="stretch")
        dd = fa.drawdown_series(sel)
        dfig = go.Figure(go.Scatter(x=dd.index, y=dd, fill="tozeroy", line_color="#c0392b"))
        dfig.update_layout(title="Drawdown from previous high", yaxis_tickformat=".0%", height=260, margin=dict(t=40))
        st.plotly_chart(dfig, width="stretch")
        with st.expander("Technical trend (context only, not scored)"):
            st.dataframe(tech.trend_table(s_navs).style.format(
                {"RSI(14)": "{:.0f}", "3M": "{:.1%}", "6M": "{:.1%}", "12M": "{:.1%}", "12-1M momentum": "{:.1%}", "vs 52w high": "{:.1%}"}, na_rep="n/a"),
                width="stretch")
            st.caption("Moving averages and RSI describe the current trend only; they do not predict returns and are weak tools for choosing long-term funds.")
        with st.expander("Search terms for sector proxies (live mode)"):
            st.dataframe(pd.DataFrame({"Sector": list(sa.SECTOR_PROXY_SEARCH), "Search term": list(sa.SECTOR_PROXY_SEARCH.values())}),
                         width="stretch", hide_index=True)
            st.caption("Availability varies; verify each result is the intended index and plan type.")
        st.session_state["extra_sections"] = [sector_section(summ, warns, s_note)]
        st.session_state["extra_files"] = {"sector_summary.csv": summ.reset_index(), "sector_calendar_returns.csv": cal.reset_index(names="year")}
    else:
        st.info("Choose sample data or load sector proxies to see dry periods.")

# ------------------------------------------------------------------ 8. Fund scorecard
with tab_sc:
    st.subheader("Fund scorecard (compare within one category)")
    st.caption("Market metrics come from NAV history; fundamentals (expense, P/E, ROE, tenure...) come from factsheets you enter, because NAV data "
               "does not contain them. Scores are percentile ranks among the funds you compare: a research aid, not a recommendation.")
    f_navs, f_bench, f_meta, f_note = pick_data("sc", "fund")
    if len(f_navs) >= 2:
        cats = sorted({f_meta.get(n, {}).get("category", "") for n in f_navs} - {""})
        first = next(iter(f_navs))
        same = [n for n in f_navs if f_meta.get(n, {}).get("category") == f_meta.get(first, {}).get("category")] if cats else list(f_navs)
        chosen = st.multiselect("Funds to score (same category and plan type)", list(f_navs), default=same if len(same) >= 2 else list(f_navs)[:3], key="sc_funds")
        cw = fa.category_warning(f_meta, chosen) if chosen else None
        if cw:
            st.warning(cw)
        if len(chosen) >= 2:
            if f_note.startswith("SYNTHETIC"):
                fs = dl.sample_factsheet(chosen)
            else:
                fs = pd.DataFrame({"fund": chosen})
                for c in sc.FACTSHEET_COLUMNS[2:]:
                    fs[c] = float("nan")
                for n in chosen:
                    m = f_meta.get(n, {})
                    fs.loc[fs["fund"] == n, "expense_ratio"] = m.get("expense_ratio", float("nan"))
                    fs.loc[fs["fund"] == n, "top10_concentration"] = m.get("top10_concentration", float("nan"))
            st.markdown("**Factsheet inputs** (edit cells, or upload a CSV). Fractions: 0.0070 = 0.70%.")
            st.download_button("Download factsheet CSV template", sc.FACTSHEET_TEMPLATE, file_name="factsheet_template.csv", mime="text/csv")
            up = st.file_uploader("Upload factsheet CSV (optional)", type="csv", key="sc_fs_up")
            if up is not None:
                try:
                    fs = sc.parse_factsheet_csv(up)
                except Exception as e:
                    st.error(f"Could not read factsheet: {e}")
            show_cols = [c for c in sc.FACTSHEET_COLUMNS if c != "category"]
            for c in show_cols:
                if c not in fs.columns:
                    fs[c] = float("nan")
            fs = fs[show_cols]
            fs = st.data_editor(fs, width="stretch", hide_index=True, key=f"sc_edit_{len(chosen)}_{'|'.join(chosen)[:60]}")
            c1, c2 = st.columns(2)
            infl2 = c1.number_input("Inflation %", 0.0, 15.0, 6.0, 0.5, key="sc_infl") / 100
            rf2 = c2.number_input("Risk-free rate %", 0.0, 15.0, fa.DEFAULT_RF * 100, 0.25, key="sc_rf") / 100
            st.markdown("**Theme weights**")
            w1, w2, w3, w4 = st.columns(4)
            wts = {"returns": w1.slider("Return consistency", 0, 100, 30, 5, key="w_r"), "risk": w2.slider("Risk & dry periods", 0, 100, 30, 5, key="w_k"),
                   "cost": w3.slider("Cost & structure", 0, 100, 20, 5, key="w_c"), "quality": w4.slider("Portfolio quality", 0, 100, 20, 5, key="w_q")}
            if sum(wts.values()) == 0:
                st.error("At least one theme weight must be above zero.")
            else:
                sub = {n: f_navs[n] for n in chosen}
                table = sc.build_table(sub, fs, f_bench, infl2, rf2)
                scores = sc.score_funds(table, {k: v / 100 for k, v in wts.items()})
                st.dataframe(scores.style.format({c: "{:.0f}" for c in scores.columns if c not in ("Data coverage", "Rank")}
                                                 | {"Data coverage": "{:.0%}", "Rank": "{:.0f}"}, na_rep="n/a"), width="stretch")
                st.caption("Themes missing data are left out and the remaining weights are rescaled; check 'Data coverage'. With few funds, ranks swing widely.")
                fl = sc.flags(table)
                if fl:
                    with st.expander("Caveats per fund", expanded=True):
                        for k, v in fl.items():
                            st.write(f"• **{k}**: " + "; ".join(v))
                st.dataframe(sc.trend_context(sub).to_frame(), width="stretch")
                with st.expander("Raw metrics behind the scores"):
                    labels = {k: v[2] for k, v in sc.METRICS.items()}
                    st.dataframe(table[list(sc.METRICS)].rename(columns=labels), width="stretch")
                st.session_state["extra_sections_sc"] = [scorecard_section(scores, fl, f_note)]
                st.session_state["extra_files_sc"] = {"fund_scorecard.csv": scores.reset_index(), "fund_scorecard_raw.csv": table.reset_index()}
    else:
        st.info("Load at least two funds (sample data works) to score them.")

# ------------------------------------------------------------------ 9. Report & export
if risk is not None:
    with tab_r:
        st.subheader("Assessment report")
        note = (f"equity {assumptions['equity']['return']:.1%} / debt {assumptions['debt']['return']:.1%} / "
                f"cash {assumptions['cash']['return']:.1%} assumed annual returns; volatilities "
                f"{assumptions['equity']['vol']:.1%} / {assumptions['debt']['vol']:.1%} / {assumptions['cash']['vol']:.1%}; "
                f"inflation {goal.inflation_rate:.1%} (applied only if the goal rises with inflation).")
        md = build_report(risk, alloc, feas, crashes, impacts, note, shortlist_df, st.session_state.get("fund_table"),
                          st.session_state.get("data_note", ""), st.session_state.get("investor_ref", ""),
                          st.session_state.get("extra_sections", []) + st.session_state.get("extra_sections_sc", []))
        st.markdown(md)
        d1, d2, d3 = st.columns(3)
        d1.download_button("Download report (Markdown)", md, file_name="risk_profile_report.md", mime="text/markdown")
        bundle = build_bundle(risk, alloc, crashes, st.session_state.get("fund_table"), st.session_state.get("export_navs"),
                              st.session_state.get("export_years"), st.session_state.get("export_roll", 3),
                              st.session_state.get("data_note", ""), feas, impacts, shortlist_df,
                              {**st.session_state.get("extra_files", {}), **st.session_state.get("extra_files_sc", {})})
        d2.download_button("Download Power BI data (zip of CSVs)", bundle, file_name="powerbi_data.zip", mime="application/zip",
                           help="Tidy CSVs plus an import guide for Power BI Desktop")
        if d3.button("Save this run (scores only)"):
            conn = persistence.connect()
            persistence.save_run(conn, st.session_state["session_id"], risk, alloc.equity)
            conn.close()
            st.success("Saved. See the History tab.")

# ------------------------------------------------------------------ 10. History
with tab_h:
    st.subheader("Saved runs")
    st.caption("Stored locally in data/runs.db. Only scores, profile and equity weight are kept.")
    conn = persistence.connect()
    import os
    # On a shared public deployment, never show other visitors' runs. Set SHOW_ALL_RUNS=1 only for local/private use.
    shared_ok = os.environ.get("SHOW_ALL_RUNS") == "1"
    scope = st.radio("Show", ["This session", "All saved runs"], horizontal=True) if shared_ok else "This session"
    runs = persistence.load_runs(conn, st.session_state["session_id"] if scope == "This session" else None)
    if runs.empty:
        st.info("No saved runs yet.")
    else:
        st.dataframe(runs, width="stretch", hide_index=True)
        trend = px.line(runs.sort_values("id"), x="created_at", y=["capacity", "tolerance", "required", "bearable"],
                        markers=True, title="Scores across saved runs")
        trend.update_layout(height=320, margin=dict(t=40), yaxis_range=[0, 100])
        st.plotly_chart(trend, width="stretch")
    if shared_ok and st.button("Delete ALL saved runs"):
        persistence.delete_all(conn)
        st.rerun()
    conn.close()
