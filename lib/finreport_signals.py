"""finreport_signals.py – Bước 4 (xu hướng & đồng ngành), Bước 5 (phát hiện tín hiệu), Bước 6 (chấm điểm & xếp hạng).

Thiết kế:
  * Mọi ngưỡng nằm trong THRESHOLDS (một chỗ) -> minh bạch, kiểm tra độ nhạy được.
  * Một tín hiệu chỉ bật khi kết hợp: MỨC + XU HƯỚNG (so với năm gốc / 2 năm gần nhất) + ĐỒNG NGÀNH (median/P25/P75 theo năm).
  * Không có nhánh nào theo company_id. Chỉ dùng dữ liệu đến năm t (không nhìn tương lai).
  * Kịch bản chính được chọn theo thứ tự ưu tiên "nguyên nhân gốc"; tên tag phụ thuộc kịch bản (đúng từ vựng BTC).
  * Cảnh báo là tín hiệu hỗ trợ phân tích – không phải kết luận gian lận/kiểm toán/khuyến nghị đầu tư.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import finreport_metrics as fm

KEY = fm.KEY
C = fm.C
MODEL_NAME = "FinReport-RuleSignals v1.0 (trend + peer + multi-signal rules)"

# ================================================================== NGƯỠNG (một chỗ duy nhất)
THRESHOLDS = {
    "margin_drop_pp": 3.0,          # biên gộp giảm ≥ 3 điểm % so với năm gốc
    "op_margin_drop_pp": 3.0,       # biên hoạt động giảm ≥ 3 điểm %
    "ar_gap_pp": 15.0,              # tăng trưởng phải thu − tăng trưởng doanh thu, TB 2 năm gần nhất
    "inv_gap_pp": 10.0,             # tăng trưởng tồn kho − tăng trưởng giá vốn, TB 2 năm
    "days_rel": 1.25,               # DSO / Inventory days so với năm gốc
    "days_rel_strong": 1.50,        # mức nghiêm trọng (kèm so ngành)
    "peer_days_rel_ar": 1.50,       # DSO ≥ 1,5 × median ngành
    "peer_days_rel_inv": 1.30,      # Inventory days ≥ 1,3 × median ngành
    "debt_growth_pct": 20.0,        # nợ vay tăng ≥ 20%/năm, 2 năm liên tiếp
    "de_increase": 0.10,            # D/E tăng ≥ 0,10 so với năm gốc
    "icr_drop": 0.40,               # Interest coverage giảm ≥ 40% so với năm gốc
    "cfo_ni_weak": 0.80,            # CFO/LNST < 0,8 (khi LNST > 0)
    "cfo_ni_liquidity": 0.30,       # CFO/LNST ≤ 0,3 -> gần như không tạo tiền
    "maturity_12m_pct": 45.0,       # ≥ 45% nợ vay đáo hạn trong 12 tháng
    "distress_op_margin": 2.0,      # biên hoạt động < 2%
    "recovery_margin_pp": 3.0,      # biên gộp hồi ≥ 3 điểm % từ đáy
    "improve_margin_pp": 2.0,       # biên gộp cải thiện ≥ 2 điểm %
    "deleverage": 0.05,             # D/E giảm ≥ 0,05
    "growth_high_pct": 10.0,        # tăng trưởng doanh thu ≥ 10% và ≥ P75 ngành
    "strong_icr": 20.0,             # ICR ≥ 20 lần
    "critical_icr": 3.0,            # ICR < 3 -> CRITICAL
    "liquidity_cfo_margin": 2.0,    # CFO/Doanh thu < 2% -> áp lực thanh khoản (HIGH_RISK)
    "recovery_low_nm": 2.0,         # đang phục hồi nhưng biên ròng < 2% -> MEDIUM
}

RISK_SCENARIOS = ["MULTI_FACTOR_STRESS", "LIQUIDITY_STRESS", "PROFIT_CASH_DIVERGENCE", "REVENUE_GROWTH_WEAK_CASH",
                  "RECEIVABLES_RISK", "INVENTORY_BUILDUP", "DEBT_EXPANSION", "MARGIN_DETERIORATION", "DISTRESS_BASELINE"]
POSITIVE_SCENARIOS = ["NORMAL_STABLE", "STRONG_PERFORMANCE", "OPERATIONAL_IMPROVEMENT"]
POSITIVE_TAGS = {"STRONG_GROWTH", "STRONG_LIQUIDITY", "LOW_LEVERAGE", "MARGIN_IMPROVEMENT", "MARGIN_RECOVERY",
                 "WORKING_CAPITAL_IMPROVEMENT", "DELEVERAGING"}
SEV_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# Trường nguồn của từng tag (truy vết)
TAG_FIELDS = {
    "CFO_WEAKNESS": ["cfo", "ni"], "CFO_PRESSURE": ["cfo", "ni"], "PROFIT_CASH_DIVERGENCE": ["ni", "cfo", "ar", "inv"],
    "RECEIVABLES_RISK": ["ar", "rev"], "INVENTORY_RISK": ["inv", "cogs"], "WORKING_CAPITAL_PRESSURE": ["ar", "inv", "rev", "cogs"],
    "LEVERAGE_RISK": ["std", "ltd", "te"], "INTEREST_BURDEN": ["op", "int_exp"],
    "GROSS_MARGIN_DECLINE": ["gp", "rev"], "MARGIN_DETERIORATION": ["gp", "rev"], "PROFITABILITY_PRESSURE": ["op", "rev"],
    "LIQUIDITY_STRESS": ["cfo", "ni", "std"], "LOW_MARGIN": ["op", "rev"], "HIGH_LEVERAGE": ["std", "ltd", "ta"],
    "LIQUIDITY_PRESSURE": ["tca", "tcl", "cfo"], "MARGIN_RECOVERY": ["gp", "rev"], "MARGIN_IMPROVEMENT": ["gp", "rev"],
    "DELEVERAGING": ["std", "ltd", "te"], "WORKING_CAPITAL_IMPROVEMENT": ["ar", "inv", "rev", "cogs"],
    "STRONG_GROWTH": ["rev"], "STRONG_LIQUIDITY": ["tca", "tcl"], "LOW_LEVERAGE": ["std", "ltd", "te"],
}
NOTE_FIELDS = {"LIQUIDITY_STRESS": ["debt_maturing_within_12m_pct"]}


# ================================================================== BƯỚC 4 – ĐẶC TRƯNG XU HƯỚNG & ĐỒNG NGÀNH
def build_features(master: pd.DataFrame, metrics_wide: pd.DataFrame, supplementary: pd.DataFrame) -> pd.DataFrame:
    d, p = fm.prepare(master)
    f = d[KEY].copy()
    w = metrics_wide.set_index(KEY).loc[list(zip(d.company_id, d.fiscal_year))].reset_index(drop=True)
    s = supplementary.set_index(KEY).loc[list(zip(d.company_id, d.fiscal_year))].reset_index(drop=True)
    for col in w.columns:
        f[col] = w[col].values
    for col in ["accounts_receivable_growth_pct", "inventory_growth_pct", "total_debt_growth_pct"]:
        f[col] = s[col].values
    f["cogs_growth_pct"] = ((d[C["cogs"]] - p[C["cogs"]]) / p[C["cogs"]] * 100).values
    f["ni"], f["cfo"] = d[C["ni"]].values, d[C["cfo"]].values
    f["mat12"] = d["debt_maturing_within_12m_pct"].values
    f["credit_terms"] = d["average_customer_credit_terms_days"].values
    f["inv_policy"] = d["inventory_policy_days_target"].values
    f["cfo_ni_valid"] = np.where(f["ni"] > 0, f["cfo_to_net_income_x"], np.nan)    # tôn trọng cờ NON_POSITIVE_NET_INCOME
    f["ar_gap"] = f["accounts_receivable_growth_pct"] - f["revenue_growth_pct"]
    f["inv_gap"] = f["inventory_growth_pct"] - f["cogs_growth_pct"]

    g = f.groupby("company_id")
    first = lambda col: g[col].transform(lambda x: x.dropna().iloc[0] if x.notna().any() else np.nan)
    # ---- so với năm gốc (năm đầu có dữ liệu của chính DN)
    for col, base in [("gross_margin_pct", "gm"), ("operating_margin_pct", "om"), ("debt_to_equity_x", "de"),
                      ("interest_coverage_x", "icr"), ("dso_days", "dso"), ("inventory_days", "invd"), ("ni", "ni")]:
        f[f"{base}_base"] = first(col)
    f["d_gm"] = f["gross_margin_pct"] - f["gm_base"]
    f["d_om"] = f["operating_margin_pct"] - f["om_base"]
    f["d_de"] = f["debt_to_equity_x"] - f["de_base"]
    f["icr_drop"] = 1 - f["interest_coverage_x"] / f["icr_base"]
    f["dso_rel"] = f["dso_days"] / f["dso_base"]
    f["invd_rel"] = f["inventory_days"] / f["invd_base"]
    f["ni_growth_cum"] = np.where(f["ni_base"] > 0, (f["ni"] / f["ni_base"] - 1) * 100, np.nan)
    # ---- 2 năm gần nhất
    f["ar_gap2"] = g["ar_gap"].transform(lambda x: x.rolling(2, min_periods=1).mean())
    f["inv_gap2"] = g["inv_gap"].transform(lambda x: x.rolling(2, min_periods=1).mean())
    f["debt_g_min2"] = g["total_debt_growth_pct"].transform(lambda x: x.rolling(2, min_periods=2).min())
    f["dso_prev"] = g["dso_days"].shift(1)
    f["invd_prev"] = g["inventory_days"].shift(1)
    # ---- lịch sử trước năm t (không nhìn tương lai)
    f["distress_before"] = g["operating_margin_pct"].transform(
        lambda x: (x < THRESHOLDS["distress_op_margin"]).astype(float).shift(1).cummax().fillna(0)).astype(bool)
    f["gm_trough_prior"] = g["gross_margin_pct"].transform(lambda x: x.shift(1).cummin())
    f["de_peak_prior"] = g["debt_to_equity_x"].transform(lambda x: x.shift(1).cummax())
    # ---- đồng ngành theo từng năm (benchmark động)
    yr = f.groupby("fiscal_year")
    for col, name in [("revenue_growth_pct", "rev_g"), ("gross_margin_pct", "gm"), ("operating_margin_pct", "om"),
                      ("current_ratio_x", "cr"), ("debt_to_equity_x", "de"), ("dso_days", "dso"),
                      ("inventory_days", "invd"), ("interest_coverage_x", "icr")]:
        f[f"peer_{name}_p25"] = yr[col].transform(lambda x: x.quantile(0.25))
        f[f"peer_{name}_med"] = yr[col].transform("median")
        f[f"peer_{name}_p75"] = yr[col].transform(lambda x: x.quantile(0.75))
    f["dso_vs_peer"] = f["dso_days"] / f["peer_dso_med"]
    f["invd_vs_peer"] = f["inventory_days"] / f["peer_invd_med"]
    f["gm_vs_peer_pp"] = f["gross_margin_pct"] - f["peer_gm_med"]
    f["history_years"] = g.cumcount()           # số năm trước đó có trong dữ liệu
    return f


# ================================================================== BƯỚC 5 – TÍN HIỆU
def detect_signals(f: pd.DataFrame, T: dict | None = None) -> pd.DataFrame:
    T = {**THRESHOLDS, **(T or {})}
    s = f[KEY].copy()
    ge = lambda a, b: (a >= b).fillna(False)
    le = lambda a, b: (a <= b).fillna(False)
    s["S_MARGIN"] = le(f["d_gm"], -T["margin_drop_pp"])
    s["S_PROFIT_PRESS"] = le(f["d_om"], -T["op_margin_drop_pp"])
    s["S_REC_P"] = ge(f["ar_gap2"], T["ar_gap_pp"])
    s["S_REC"] = s["S_REC_P"] & ge(f["dso_rel"], T["days_rel"])
    s["S_REC_STRONG"] = ge(f["dso_rel"], T["days_rel_strong"]) & ge(f["dso_vs_peer"], T["peer_days_rel_ar"])
    s["S_INV_P"] = ge(f["inv_gap2"], T["inv_gap_pp"])
    s["S_INV"] = s["S_INV_P"] & ge(f["invd_rel"], T["days_rel"])
    s["S_INV_STRONG"] = ge(f["invd_rel"], T["days_rel_strong"]) & ge(f["invd_vs_peer"], T["peer_days_rel_inv"])
    s["S_LEV"] = ge(f["debt_g_min2"], T["debt_growth_pct"]) & ge(f["d_de"], T["de_increase"])
    s["S_INT"] = ge(f["icr_drop"], T["icr_drop"])
    s["S_CASH"] = (f["cfo"] < 0) | ((f["ni"] > 0) & (f["cfo_ni_valid"] < T["cfo_ni_weak"]))
    s["S_LIQ"] = ((f["cfo"] < 0) | ((f["ni"] > 0) & (f["cfo_ni_valid"] <= T["cfo_ni_liquidity"]))) & ge(f["mat12"], T["maturity_12m_pct"])
    s["S_DISTRESS"] = f["operating_margin_pct"] < T["distress_op_margin"]
    s["S_RECOV"] = (f["distress_before"] & ~s["S_DISTRESS"] & (f["ni"] > 0)
                    & ge(f["gross_margin_pct"] - f["gm_trough_prior"], T["recovery_margin_pp"]))
    s["S_IMPROVE"] = (ge(f["d_gm"], T["improve_margin_pp"]) & le(f["d_de"], -T["deleverage"])
                      & ((f["dso_rel"] < 1) | (f["invd_rel"] < 1)).fillna(False))
    s["S_STRONG"] = (ge(f["gross_margin_pct"], f["peer_gm_p75"]) & ge(f["operating_margin_pct"], f["peer_om_p75"])
                     & ge(f["interest_coverage_x"], T["strong_icr"]) & le(f["debt_to_equity_x"], f["peer_de_p25"])
                     & ge(f["current_ratio_x"], f["peer_cr_p75"]))
    s["S_GROWTH_HI"] = ge(f["revenue_growth_pct"], T["growth_high_pct"]) & ge(f["revenue_growth_pct"], f["peer_rev_g_p75"])
    s["S_PCD"] = s["S_CASH"] & s["S_REC_P"] & s["S_INV_P"] & (f["d_gm"] >= 0).fillna(False)
    s["S_CRIT"] = (f["interest_coverage_x"] < T["critical_icr"]) | (f["ni"] <= 0)
    return s


def _scenario(r) -> str:
    if r.S_DISTRESS:
        return "DISTRESS_BASELINE"
    if r.S_RECOV:
        return "FINANCIAL_RECOVERY"
    if r.S_STRONG:
        return "STRONG_PERFORMANCE"
    if r.S_MARGIN and (int(r.S_REC_P) + int(r.S_INV_P) + int(r.S_LEV)) >= 2:
        return "MULTI_FACTOR_STRESS"
    if r.S_LIQ:
        return "LIQUIDITY_STRESS"
    if r.S_PCD:
        return "PROFIT_CASH_DIVERGENCE"
    if r.S_CASH and r.S_GROWTH_HI:
        return "REVENUE_GROWTH_WEAK_CASH"
    if r.S_REC:
        return "RECEIVABLES_RISK"
    if r.S_INV:
        return "INVENTORY_BUILDUP"
    if r.S_LEV:
        return "DEBT_EXPANSION"
    if r.S_MARGIN:
        return "MARGIN_DETERIORATION"
    if r.S_IMPROVE:
        return "OPERATIONAL_IMPROVEMENT"
    return "NORMAL_STABLE"


def _tags(sc: str, r, x) -> list[str]:
    """Tag theo kịch bản – mỗi tag chỉ được gắn khi tín hiệu tương ứng thật sự bật."""
    t = []
    add = lambda tag, cond: t.append(tag) if cond else None
    if sc == "DISTRESS_BASELINE":
        add("LOW_MARGIN", True)
        add("HIGH_LEVERAGE", x.debt_to_equity_x >= x.peer_de_p75)
        add("LIQUIDITY_PRESSURE", (x.current_ratio_x <= x.peer_cr_p25) or x.cfo < 0)
    elif sc == "FINANCIAL_RECOVERY":
        add("MARGIN_RECOVERY", True)
        add("DELEVERAGING", x.debt_to_equity_x <= x.de_peak_prior - THRESHOLDS["deleverage"])
        add("WORKING_CAPITAL_IMPROVEMENT", (x.dso_days < x.dso_prev) and (x.inventory_days < x.invd_prev))
    elif sc == "STRONG_PERFORMANCE":
        add("STRONG_GROWTH", x.revenue_growth_pct >= x.peer_rev_g_med)
        add("STRONG_LIQUIDITY", True)
        add("LOW_LEVERAGE", True)
    elif sc == "OPERATIONAL_IMPROVEMENT":
        add("MARGIN_IMPROVEMENT", True)
        add("WORKING_CAPITAL_IMPROVEMENT", True)
        add("DELEVERAGING", True)
    elif sc == "MULTI_FACTOR_STRESS":
        add("MARGIN_DETERIORATION", r.S_MARGIN)
        add("RECEIVABLES_RISK", r.S_REC_P)
        add("INVENTORY_RISK", r.S_INV_P)
        add("LEVERAGE_RISK", r.S_LEV)
    elif sc == "LIQUIDITY_STRESS":
        add("LIQUIDITY_STRESS", True)
        add("WORKING_CAPITAL_PRESSURE", r.S_REC_P or r.S_INV_P)
        add("RECEIVABLES_RISK", r.S_REC_STRONG)
        add("INVENTORY_RISK", r.S_INV_STRONG)
    elif sc == "PROFIT_CASH_DIVERGENCE":
        add("PROFIT_CASH_DIVERGENCE", True)
        add("WORKING_CAPITAL_PRESSURE", True)
    elif sc == "REVENUE_GROWTH_WEAK_CASH":
        add("CFO_WEAKNESS", True)
        add("RECEIVABLES_RISK", r.S_REC)
    elif sc == "RECEIVABLES_RISK":
        add("RECEIVABLES_RISK", True)
        add("CFO_PRESSURE", r.S_CASH)
    elif sc == "INVENTORY_BUILDUP":
        add("INVENTORY_RISK", True)
        add("CFO_PRESSURE", r.S_CASH)
    elif sc == "DEBT_EXPANSION":
        add("LEVERAGE_RISK", True)
        add("INTEREST_BURDEN", r.S_INT)
    elif sc == "MARGIN_DETERIORATION":
        add("GROSS_MARGIN_DECLINE", True)
        add("PROFITABILITY_PRESSURE", r.S_PROFIT_PRESS)
    return t


# ================================================================== BƯỚC 6 – ĐIỂM RỦI RO, MỨC ĐỘ, SỨC KHỎE, XẾP HẠNG
RISK_WEIGHTS = {"cash": 0.20, "coverage": 0.20, "leverage": 0.15, "margin": 0.15, "working_capital": 0.15, "loss": 0.15}


def risk_components(f: pd.DataFrame) -> pd.DataFrame:
    clip = lambda x: np.clip(x, 0, 1)
    c = pd.DataFrame(index=f.index)
    cash = np.where(f["cfo"] < 0, 1.0, np.where(f["ni"] > 0, clip(1 - f["cfo_ni_valid"].fillna(1)), 0.5))
    c["cash"] = cash
    c["coverage"] = clip((8 - f["interest_coverage_x"]) / 8)
    c["leverage"] = 0.5 * clip(f["debt_to_equity_x"] / 1.0) + 0.5 * clip(f["d_de"].fillna(0) / 0.4)
    c["margin"] = 0.5 * clip(-f["d_gm"].fillna(0) / 10) + 0.5 * clip(-f["d_om"].fillna(0) / 10)
    c["working_capital"] = np.maximum(clip(f["dso_rel"].fillna(1) - 1), clip(f["invd_rel"].fillna(1) - 1))
    c["loss"] = (f["ni"] <= 0).astype(float)
    return c


def score(f: pd.DataFrame, sig: pd.DataFrame, T: dict | None = None) -> pd.DataFrame:
    T = {**THRESHOLDS, **(T or {})}
    comp = risk_components(f)
    out = f[KEY].copy()
    out["risk_score"] = sum(comp[k] * w for k, w in RISK_WEIGHTS.items()).round(4)
    for k in RISK_WEIGHTS:
        out[f"rc_{k}"] = comp[k].round(4)
    scen, tags, sev, health = [], [], [], []
    for i in f.index:
        r, x = sig.loc[i], f.loc[i]
        sc = _scenario(r)
        tg = _tags(sc, r, x)
        n_risk = len([t for t in tg if t not in POSITIVE_TAGS])
        if sc in POSITIVE_SCENARIOS:
            sv = "LOW"
        elif sc == "FINANCIAL_RECOVERY":
            sv = "MEDIUM" if x.net_margin_pct < T["recovery_low_nm"] else "LOW"
        elif sc == "DISTRESS_BASELINE" or r.S_CRIT:
            sv = "CRITICAL"
        else:
            sv = "HIGH" if n_risk >= 2 else ("MEDIUM" if n_risk == 1 else "LOW")
        if sc in POSITIVE_SCENARIOS:
            hl = "HEALTHY"
        elif sc == "FINANCIAL_RECOVERY":
            hl = "RECOVERING"
        elif (sv == "CRITICAL" or bool(r.S_PROFIT_PRESS) or sc == "MULTI_FACTOR_STRESS"
              or (x.cfo_margin_pct < T["liquidity_cfo_margin"])):
            hl = "HIGH_RISK"
        else:
            hl = "WATCH"
        scen.append(sc); tags.append(";".join(tg)); sev.append(sv); health.append(hl)
    out["predicted_primary_scenario"], out["alert_tags"] = scen, tags
    out["predicted_severity"], out["predicted_overall_health"] = sev, health
    # Xếp hạng ưu tiên toàn danh mục (60 company-year): mức độ trước, rồi risk_score
    key = out["predicted_severity"].map(SEV_ORDER) * 10 + out["risk_score"]
    out["priority_rank"] = key.rank(ascending=False, method="first").astype(int)
    out["priority_rank_in_year"] = out.assign(k=key).groupby("fiscal_year")["k"].rank(ascending=False, method="first").astype(int)
    return out


# ------------------------------------------------------------------ độ tin cậy
def confidence(f: pd.DataFrame, T: dict | None = None) -> pd.Series:
    """Độ đủ lịch sử × độ xa ngưỡng: năm 2021 thiếu xu hướng; tín hiệu sát ngưỡng (±10%) bị trừ."""
    T = {**THRESHOLDS, **(T or {})}
    hist = f["history_years"].map({0: 0.60, 1: 0.80}).fillna(0.95)
    checks = [(f["d_gm"], -T["margin_drop_pp"]), (f["ar_gap2"], T["ar_gap_pp"]), (f["inv_gap2"], T["inv_gap_pp"]),
              (f["dso_rel"], T["days_rel"]), (f["invd_rel"], T["days_rel"]), (f["cfo_ni_valid"], T["cfo_ni_weak"]),
              (f["interest_coverage_x"], T["critical_icr"]), (f["d_de"], T["de_increase"]),
              (f["debt_g_min2"], T["debt_growth_pct"])]
    near = np.zeros(len(f), dtype=int)
    for v, thr in checks:
        near += ((v - thr).abs() / abs(thr) < 0.10).fillna(False).astype(int).values
    return (hist * (1 - 0.08 * np.minimum(near, 3))).round(3)


# ------------------------------------------------------------------ giải thích & truy vết
def explain(f: pd.DataFrame, pred: pd.DataFrame, T: dict | None = None) -> tuple[pd.Series, pd.Series]:
    T = {**THRESHOLDS, **(T or {})}
    reasons, evid = [], []
    for i in pred.index:
        x, p_ = f.loc[i], pred.loc[i]
        y, cid = int(x.fiscal_year), x.company_id
        base_y = y - int(x.history_years)
        R = []
        for t in [t for t in str(p_.alert_tags).split(";") if t]:
            if t in ("CFO_WEAKNESS", "CFO_PRESSURE"):
                R.append(f"CFO/LNST {x.cfo_ni_valid:.2f}x < {T['cfo_ni_weak']}" if pd.notna(x.cfo_ni_valid) else f"CFO {x.cfo:,.0f} âm")
            elif t == "PROFIT_CASH_DIVERGENCE":
                R.append(f"LNST +{x.ni_growth_cum:.0f}% so với {base_y} nhưng CFO/LNST chỉ {x.cfo_ni_valid:.2f}x")
            elif t == "RECEIVABLES_RISK":
                R.append(f"DSO {x.dso_days:.0f} ngày (×{x.dso_rel:.2f} so với gốc, ×{x.dso_vs_peer:.2f} median ngành); "
                         f"phải thu tăng nhanh hơn doanh thu {x.ar_gap2:.1f}đ%/năm")
            elif t == "INVENTORY_RISK":
                R.append(f"Ngày tồn kho {x.inventory_days:.0f} (×{x.invd_rel:.2f} so với gốc, ×{x.invd_vs_peer:.2f} median ngành)")
            elif t == "WORKING_CAPITAL_PRESSURE":
                R.append(f"Vốn bị giữ trong phải thu/tồn kho: chênh tăng trưởng AR {x.ar_gap2:.1f}đ%, tồn kho {x.inv_gap2:.1f}đ%")
            elif t == "LEVERAGE_RISK":
                R.append(f"Nợ vay tăng ≥{T['debt_growth_pct']:.0f}%/năm 2 năm liền; D/E {x.de_base:.2f}→{x.debt_to_equity_x:.2f}")
            elif t == "INTEREST_BURDEN":
                R.append(f"ICR {x.icr_base:.1f}x→{x.interest_coverage_x:.1f}x (giảm {x.icr_drop:.0%})")
            elif t in ("GROSS_MARGIN_DECLINE", "MARGIN_DETERIORATION"):
                R.append(f"Biên gộp {x.gm_base:.1f}%→{x.gross_margin_pct:.1f}% ({x.d_gm:+.1f}đ%)")
            elif t == "PROFITABILITY_PRESSURE":
                R.append(f"Biên hoạt động {x.om_base:.1f}%→{x.operating_margin_pct:.1f}% ({x.d_om:+.1f}đ%)")
            elif t == "LIQUIDITY_STRESS":
                R.append(f"CFO/doanh thu {x.cfo_margin_pct:.1f}%, {x.mat12:.0f}% nợ vay đáo hạn ≤12 tháng")
            elif t == "LOW_MARGIN":
                R.append(f"Biên hoạt động {x.operating_margin_pct:.1f}% (< {T['distress_op_margin']}%)")
            elif t == "HIGH_LEVERAGE":
                R.append(f"D/E {x.debt_to_equity_x:.2f} ≥ P75 ngành {x.peer_de_p75:.2f}")
            elif t == "LIQUIDITY_PRESSURE":
                R.append(f"Current ratio {x.current_ratio_x:.2f} ≤ P25 ngành {x.peer_cr_p25:.2f} hoặc CFO âm")
            elif t in ("MARGIN_RECOVERY", "MARGIN_IMPROVEMENT"):
                R.append(f"Biên gộp {x.gross_margin_pct:.1f}% (+{x.gross_margin_pct - (x.gm_trough_prior if t == 'MARGIN_RECOVERY' else x.gm_base):.1f}đ%)")
            elif t == "DELEVERAGING":
                R.append(f"D/E giảm còn {x.debt_to_equity_x:.2f}")
            elif t == "WORKING_CAPITAL_IMPROVEMENT":
                R.append(f"DSO {x.dso_days:.0f} ngày, tồn kho {x.inventory_days:.0f} ngày (giảm)")
            elif t == "STRONG_GROWTH":
                R.append(f"Doanh thu +{x.revenue_growth_pct:.1f}% ≥ median ngành")
            elif t == "STRONG_LIQUIDITY":
                R.append(f"Current ratio {x.current_ratio_x:.2f} ≥ P75 ngành")
            elif t == "LOW_LEVERAGE":
                R.append(f"D/E {x.debt_to_equity_x:.2f} ≤ P25 ngành")
        if p_.predicted_severity == "CRITICAL" and p_.predicted_primary_scenario not in ("DISTRESS_BASELINE",):
            R.append(f"CRITICAL do ICR {x.interest_coverage_x:.2f}x < {T['critical_icr']}" if x.ni > 0 else "CRITICAL do lỗ ròng")
        reasons.append(f"[{p_.predicted_primary_scenario}] " + ("; ".join(R) if R else "Các chỉ tiêu trong vùng ổn định so với lịch sử và đồng ngành"))
        tags = [t for t in str(p_.alert_tags).split(";") if t]
        fields = sorted({k for t in tags for k in TAG_FIELDS.get(t, [])}) or ["rev", "gp", "cfo", "ni"]
        yrs = f"{base_y}-{y}" if y > base_y else str(y)
        ev = [f"{fm.SRC[k]}:{cid}:{yrs}:{C[k]}" for k in fields]
        ev += [f"financial_notes.csv:{cid}:{y}:{n}" for t in tags for n in NOTE_FIELDS.get(t, [])]
        evid.append("|".join(ev))
    return pd.Series(reasons, index=pred.index), pd.Series(evid, index=pred.index)


def run(master, metrics_wide, supplementary, T: dict | None = None):
    f = build_features(master, metrics_wide, supplementary)
    sig = detect_signals(f, T)
    pred = score(f, sig, T)
    pred["confidence"] = confidence(f, T)
    pred["alert_reason"], pred["evidence_fields"] = explain(f, pred, T)
    return f, sig, pred


# ================================================================== BASELINE (để so sánh – mức Silver)
def baseline(f: pd.DataFrame) -> pd.DataFrame:
    """Luật 1 năm, 1 chỉ tiêu, ngưỡng cố định, không xu hướng, không ngữ cảnh."""
    out = f[KEY].copy()
    tags, scen, sev, hl = [], [], [], []
    for _, x in f.iterrows():
        t = []
        if x.ni > 0 and x.cfo_to_net_income_x < 0.8 or x.cfo < 0: t.append("CFO_WEAKNESS")
        if pd.notna(x.dso_days) and x.dso_days > 1.3 * x.peer_dso_med: t.append("RECEIVABLES_RISK")
        if pd.notna(x.inventory_days) and x.inventory_days > 1.3 * x.peer_invd_med: t.append("INVENTORY_RISK")
        if x.debt_to_equity_x > x.peer_de_p75: t.append("LEVERAGE_RISK")
        if x.interest_coverage_x < 5: t.append("INTEREST_BURDEN")
        if x.gross_margin_pct < x.peer_gm_med - 3: t.append("GROSS_MARGIN_DECLINE")
        if x.current_ratio_x < x.peer_cr_p25: t.append("LIQUIDITY_STRESS")
        tags.append(";".join(t))
        scen.append({"CFO_WEAKNESS": "REVENUE_GROWTH_WEAK_CASH", "RECEIVABLES_RISK": "RECEIVABLES_RISK",
                     "INVENTORY_RISK": "INVENTORY_BUILDUP", "LEVERAGE_RISK": "DEBT_EXPANSION",
                     "INTEREST_BURDEN": "DEBT_EXPANSION", "GROSS_MARGIN_DECLINE": "MARGIN_DETERIORATION",
                     "LIQUIDITY_STRESS": "LIQUIDITY_STRESS"}.get(t[0], "NORMAL_STABLE") if t else "NORMAL_STABLE")
        n = len(t)
        sev.append(["LOW", "MEDIUM", "HIGH", "CRITICAL"][min(n, 3)])
        hl.append("HEALTHY" if n == 0 else ("WATCH" if n <= 2 else "HIGH_RISK"))
    out["alert_tags"], out["predicted_primary_scenario"] = tags, scen
    out["predicted_severity"], out["predicted_overall_health"] = sev, hl
    return out


# ================================================================== ĐÁNH GIÁ
def _set(s):
    return {t for t in str(s).split(";") if t and t != "nan"}


def evaluate(pred: pd.DataFrame, labels: pd.DataFrame) -> dict:
    m = labels.merge(pred, on=KEY, how="left", suffixes=("_true", ""))
    tp = fp = fn = 0
    per_tag = {}
    for _, r in m.iterrows():
        yt, yp = _set(r["alert_tags_true"]), _set(r["alert_tags"])
        tp += len(yt & yp); fp += len(yp - yt); fn += len(yt - yp)
        for t in yt | yp:
            d = per_tag.setdefault(t, [0, 0, 0])
            d[0] += t in yt and t in yp; d[1] += t in yp and t not in yt; d[2] += t in yt and t not in yp
    P = tp / (tp + fp) if tp + fp else 0
    R = tp / (tp + fn) if tp + fn else 0
    F1 = 2 * P * R / (P + R) if P + R else 0
    f1s = []
    for t, (a, b, c) in per_tag.items():
        p_, r_ = (a / (a + b) if a + b else 0), (a / (a + c) if a + c else 0)
        f1s.append(2 * p_ * r_ / (p_ + r_) if p_ + r_ else 0)
    sc_ok = m["primary_scenario"] == m["predicted_primary_scenario"]
    macro_rec = m.assign(ok=sc_ok).groupby("primary_scenario")["ok"].mean().mean()
    sev_ok = m["severity"] == m["predicted_severity"]
    sev_1 = (m["severity"].map(SEV_ORDER) - m["predicted_severity"].map(SEV_ORDER)).abs() <= 1
    hi = m["severity"].isin(["HIGH", "CRITICAL"])
    hi_rec = (m.loc[hi, "predicted_severity"].isin(["HIGH", "CRITICAL"])).mean()
    neg = m["severity"] == "LOW"
    false_alarm = (m.loc[neg, "predicted_severity"].isin(["HIGH", "CRITICAL"])).mean()
    out = {"n_labels": len(m), "tag_precision": P, "tag_recall": R, "tag_f1_micro": F1, "tag_f1_macro": float(np.mean(f1s)),
           "scenario_accuracy": sc_ok.mean(), "scenario_macro_recall": macro_rec,
           "severity_accuracy": sev_ok.mean(), "severity_within_1": sev_1.mean(),
           "health_accuracy": (m["overall_health"] == m["predicted_overall_health"]).mean(),
           "high_critical_recall": hi_rec, "false_alarm_rate_on_low": false_alarm}
    if "risk_score" in m:
        out["spearman_risk_vs_severity"] = m["risk_score"].rank().corr(m["severity"].map(SEV_ORDER).rank())
    return out


def compare_rows(pred: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    m = labels.merge(pred, on=KEY, how="left", suffixes=("_true", "_pred"))
    m["scenario_ok"] = m["primary_scenario"] == m["predicted_primary_scenario"]
    m["severity_ok"] = m["severity"] == m["predicted_severity"]
    m["health_ok"] = m["overall_health"] == m["predicted_overall_health"]
    m["tags_missing"] = [";".join(sorted(_set(a) - _set(b))) for a, b in zip(m["alert_tags_true"], m["alert_tags_pred"])]
    m["tags_extra"] = [";".join(sorted(_set(b) - _set(a))) for a, b in zip(m["alert_tags_true"], m["alert_tags_pred"])]
    return m


def sensitivity(master, metrics_wide, supplementary, labels, factors=(0.8, 0.9, 1.0, 1.1, 1.2)) -> pd.DataFrame:
    """Nhân TẤT CẢ ngưỡng (trừ ngưỡng tỷ lệ quanh 1) với cùng hệ số -> kết quả có ổn định không?"""
    rows = []
    for k in factors:
        T = {}
        for name, v in THRESHOLDS.items():
            T[name] = 1 + (v - 1) * k if name in ("days_rel", "days_rel_strong", "peer_days_rel_ar", "peer_days_rel_inv") else v * k
        _, _, pr = run(master, metrics_wide, supplementary, T)
        e = evaluate(pr, labels)
        rows.append({"threshold_factor": k, **{kk: round(vv, 3) for kk, vv in e.items() if kk != "n_labels"}})
    return pd.DataFrame(rows)


def one_at_a_time(master, metrics_wide, supplementary, labels, delta=0.2) -> pd.DataFrame:
    """Đổi từng ngưỡng ±20% (các ngưỡng khác giữ nguyên) -> ngưỡng nào nhạy nhất."""
    base = evaluate(run(master, metrics_wide, supplementary)[2], labels)
    rows = []
    for name, v in THRESHOLDS.items():
        for sgn in (-1, 1):
            nv = 1 + (v - 1) * (1 + sgn * delta) if name.startswith(("days_rel", "peer_days")) else v * (1 + sgn * delta)
            e = evaluate(run(master, metrics_wide, supplementary, {name: nv})[2], labels)
            rows.append({"threshold": name, "change": f"{'+' if sgn > 0 else '−'}{int(delta*100)}%", "value": round(nv, 3),
                         "tag_f1_micro": round(e["tag_f1_micro"], 3), "scenario_acc": round(e["scenario_accuracy"], 3),
                         "severity_acc": round(e["severity_accuracy"], 3),
                         "Δf1": round(e["tag_f1_micro"] - base["tag_f1_micro"], 3)})
    return pd.DataFrame(rows)
