"""finreport_metrics.py – Bước 1 (kiểm tra logic kế toán), Bước 2 (thư viện chỉ tiêu), Bước 3a (verify kép).

Một nguồn công thức duy nhất cho toàn hệ thống: NB2 (tín hiệu), NB3 (QA, file nộp) và dashboard
đều gọi lại module này, nên con số ở mọi nơi luôn nhất quán.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

KEY = ["company_id", "fiscal_year"]
TOL_ACCOUNTING = 0.5          # số liệu là số nguyên triệu VND -> lệch > 0.5 là sai thật

# ------------------------------------------------------------------ tên cột ngắn gọn
C = dict(
    rev="revenue_vnd_mn", cogs="cost_of_goods_sold_vnd_mn", gp="gross_profit_vnd_mn",
    sell="selling_expense_vnd_mn", admin="administrative_expense_vnd_mn", da="depreciation_amortization_vnd_mn",
    op="operating_profit_vnd_mn", fin_inc="finance_income_vnd_mn", int_exp="interest_expense_vnd_mn",
    oth_inc="other_income_vnd_mn", pbt="profit_before_tax_vnd_mn", tax="income_tax_expense_vnd_mn",
    ni="net_income_vnd_mn",
    cash="cash_and_cash_equivalents_vnd_mn", ar="accounts_receivable_vnd_mn", inv="inventory_vnd_mn",
    oca="other_current_assets_vnd_mn", tca="total_current_assets_vnd_mn", ppe="property_plant_equipment_net_vnd_mn",
    intang="intangible_assets_vnd_mn", lti="long_term_investments_vnd_mn", onca="other_noncurrent_assets_vnd_mn",
    ta="total_assets_vnd_mn", std="short_term_debt_vnd_mn", ap="accounts_payable_vnd_mn",
    ocl="other_current_liabilities_vnd_mn", tcl="total_current_liabilities_vnd_mn", ltd="long_term_debt_vnd_mn",
    oncl="other_noncurrent_liabilities_vnd_mn", tl="total_liabilities_vnd_mn", sc="share_capital_vnd_mn",
    re="retained_earnings_vnd_mn", oe="other_equity_vnd_mn", te="total_equity_vnd_mn",
    tle="total_liabilities_and_equity_vnd_mn",
    ce_ar="cash_effect_change_accounts_receivable_vnd_mn", ce_inv="cash_effect_change_inventory_vnd_mn",
    ce_oca="cash_effect_change_other_current_assets_vnd_mn", ce_ap="cash_effect_change_accounts_payable_vnd_mn",
    ce_ocl="cash_effect_change_other_current_liabilities_vnd_mn",
    ce_oncl="cash_effect_change_other_noncurrent_liabilities_vnd_mn",
    cfo="net_cash_from_operating_activities_vnd_mn", capex="capital_expenditure_vnd_mn",
    cf_intang="change_intangible_assets_vnd_mn", cf_lti="change_long_term_investments_vnd_mn",
    cf_onca="change_other_noncurrent_assets_vnd_mn", cfi="net_cash_from_investing_activities_vnd_mn",
    debt_iss="net_debt_issuance_repayment_vnd_mn", eq_iss="equity_issuance_vnd_mn", div="dividends_paid_vnd_mn",
    cff="net_cash_from_financing_activities_vnd_mn", chg="net_change_in_cash_vnd_mn",
    beg="beginning_cash_vnd_mn", end="ending_cash_vnd_mn",
)
# File nguồn của từng trường (dùng cho truy vết)
IS, BS, CF, NT = "income_statement.csv", "balance_sheet.csv", "cashflow.csv", "financial_notes.csv"
SRC = {}
for k in ["rev", "cogs", "gp", "sell", "admin", "da", "op", "fin_inc", "int_exp", "oth_inc", "pbt", "tax", "ni"]:
    SRC[k] = IS
for k in ["cash", "ar", "inv", "oca", "tca", "ppe", "intang", "lti", "onca", "ta", "std", "ap", "ocl", "tcl",
          "ltd", "oncl", "tl", "sc", "re", "oe", "te", "tle"]:
    SRC[k] = BS
for k in ["ce_ar", "ce_inv", "ce_oca", "ce_ap", "ce_ocl", "ce_oncl", "cfo", "capex", "cf_intang", "cf_lti",
          "cf_onca", "cfi", "debt_iss", "eq_iss", "div", "cff", "chg", "beg", "end"]:
    SRC[k] = CF


def prepare(master: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sắp xếp theo khóa và tạo khung 'năm trước' p (cùng DN, đúng năm t-1; nếu không có -> NaN)."""
    d = master.sort_values(KEY).reset_index(drop=True)
    p = d.groupby("company_id").shift(1)
    consecutive = (d["fiscal_year"] - p["fiscal_year"]) == 1
    p.loc[~consecutive, :] = np.nan          # không có năm liền trước (vd 2021) -> NaN, không tự sinh 2020
    return d, p


def evidence(*keys: str) -> str:
    """'balance_sheet.csv:accounts_receivable_vnd_mn;income_statement.csv:revenue_vnd_mn'"""
    return ";".join(f"{SRC[k]}:{C[k]}" for k in keys)


# ================================================================== BƯỚC 1 – LUẬT KẾ TOÁN
@dataclass
class Rule:
    rule_id: str
    group: str
    description: str
    formula: str
    lhs: Callable[[pd.DataFrame, pd.DataFrame], pd.Series]
    rhs: Callable[[pd.DataFrame, pd.DataFrame], pd.Series]
    fields: tuple[str, ...]
    needs_prev: bool = False
    kind: str = "equality"            # equality | nonnegative


def _s(d, *ks):
    return sum(d[C[k]] for k in ks)


RULES: list[Rule] = [
    # ---------- A. Báo cáo kết quả kinh doanh
    Rule("IS01", "A_income_statement", "Lợi nhuận gộp = Doanh thu − Giá vốn", "gp = rev − cogs",
         lambda d, p: d[C["gp"]], lambda d, p: d[C["rev"]] - d[C["cogs"]], ("gp", "rev", "cogs")),
    Rule("IS02", "A_income_statement", "LN hoạt động = LN gộp − CP bán hàng − CP quản lý − Khấu hao",
         "op = gp − sell − admin − da",
         lambda d, p: d[C["op"]], lambda d, p: d[C["gp"]] - _s(d, "sell", "admin", "da"), ("op", "gp", "sell", "admin", "da")),
    Rule("IS03", "A_income_statement", "LNTT = LN hoạt động + Thu nhập TC − Lãi vay + Thu nhập khác",
         "pbt = op + fin_inc − int_exp + oth_inc",
         lambda d, p: d[C["pbt"]], lambda d, p: d[C["op"]] + d[C["fin_inc"]] - d[C["int_exp"]] + d[C["oth_inc"]],
         ("pbt", "op", "fin_inc", "int_exp", "oth_inc")),
    Rule("IS04", "A_income_statement", "LNST = LNTT − Thuế TNDN", "ni = pbt − tax",
         lambda d, p: d[C["ni"]], lambda d, p: d[C["pbt"]] - d[C["tax"]], ("ni", "pbt", "tax")),
    Rule("IS05", "A_income_statement", "Chi phí thuế không âm", "tax ≥ 0",
         lambda d, p: d[C["tax"]], lambda d, p: d[C["tax"]] * 0, ("tax",), kind="nonnegative"),
    # ---------- B. Bảng cân đối kế toán
    Rule("BS01", "B_balance_sheet", "TS ngắn hạn = Tiền + Phải thu + Tồn kho + TSNH khác", "tca = cash + ar + inv + oca",
         lambda d, p: d[C["tca"]], lambda d, p: _s(d, "cash", "ar", "inv", "oca"), ("tca", "cash", "ar", "inv", "oca")),
    Rule("BS02", "B_balance_sheet", "Tổng TS = TSNH + TSCĐ + Vô hình + Đầu tư DH + TSDH khác",
         "ta = tca + ppe + intang + lti + onca",
         lambda d, p: d[C["ta"]], lambda d, p: _s(d, "tca", "ppe", "intang", "lti", "onca"),
         ("ta", "tca", "ppe", "intang", "lti", "onca")),
    Rule("BS03", "B_balance_sheet", "Nợ ngắn hạn = Vay NH + Phải trả + Nợ NH khác", "tcl = std + ap + ocl",
         lambda d, p: d[C["tcl"]], lambda d, p: _s(d, "std", "ap", "ocl"), ("tcl", "std", "ap", "ocl")),
    Rule("BS04", "B_balance_sheet", "Tổng nợ = Nợ NH + Vay DH + Nợ DH khác", "tl = tcl + ltd + oncl",
         lambda d, p: d[C["tl"]], lambda d, p: _s(d, "tcl", "ltd", "oncl"), ("tl", "tcl", "ltd", "oncl")),
    Rule("BS05", "B_balance_sheet", "Vốn chủ = Vốn góp + LN giữ lại + VCSH khác", "te = sc + re + oe",
         lambda d, p: d[C["te"]], lambda d, p: _s(d, "sc", "re", "oe"), ("te", "sc", "re", "oe")),
    Rule("BS06", "B_balance_sheet", "Tài sản = Nợ phải trả + Vốn chủ sở hữu", "ta = tl + te",
         lambda d, p: d[C["ta"]], lambda d, p: _s(d, "tl", "te"), ("ta", "tl", "te")),
    Rule("BS07", "B_balance_sheet", "Tổng nguồn vốn = Tổng tài sản", "tle = ta",
         lambda d, p: d[C["tle"]], lambda d, p: d[C["ta"]], ("tle", "ta")),
    # ---------- C. Dòng tiền trong năm
    Rule("CF01", "C_cashflow", "CFO = LNST + Khấu hao + các biến động vốn lưu động",
         "cfo = ni + da + Σ cash_effect_*",
         lambda d, p: d[C["cfo"]], lambda d, p: _s(d, "ni", "da", "ce_ar", "ce_inv", "ce_oca", "ce_ap", "ce_ocl", "ce_oncl"),
         ("cfo", "ni", "da", "ce_ar", "ce_inv", "ce_oca", "ce_ap", "ce_ocl", "ce_oncl")),
    Rule("CF02", "C_cashflow", "CFI = CAPEX + Δ vô hình + Δ đầu tư DH + Δ TSDH khác",
         "cfi = capex + cf_intang + cf_lti + cf_onca",
         lambda d, p: d[C["cfi"]], lambda d, p: _s(d, "capex", "cf_intang", "cf_lti", "cf_onca"),
         ("cfi", "capex", "cf_intang", "cf_lti", "cf_onca")),
    Rule("CF03", "C_cashflow", "CFF = Vay ròng + Phát hành vốn + Cổ tức", "cff = debt_iss + eq_iss + div",
         lambda d, p: d[C["cff"]], lambda d, p: _s(d, "debt_iss", "eq_iss", "div"), ("cff", "debt_iss", "eq_iss", "div")),
    Rule("CF04", "C_cashflow", "Biến động tiền = CFO + CFI + CFF", "chg = cfo + cfi + cff",
         lambda d, p: d[C["chg"]], lambda d, p: _s(d, "cfo", "cfi", "cff"), ("chg", "cfo", "cfi", "cff")),
    Rule("CF05", "C_cashflow", "Tiền đầu kỳ + Biến động = Tiền cuối kỳ", "end = beg + chg",
         lambda d, p: d[C["end"]], lambda d, p: d[C["beg"]] + d[C["chg"]], ("end", "beg", "chg")),
    Rule("CF06", "C_cashflow", "Tiền cuối kỳ (LCTT) = Tiền trên bảng cân đối", "end = cash",
         lambda d, p: d[C["end"]], lambda d, p: d[C["cash"]], ("end", "cash")),
    # ---------- D. Liên kết giữa hai năm (không áp dụng cho 2021)
    Rule("XP01", "D_cross_period", "Tiền đầu kỳ năm t = Tiền cuối kỳ năm t−1", "beg_t = end_(t−1)",
         lambda d, p: d[C["beg"]], lambda d, p: p[C["end"]], ("beg", "end"), needs_prev=True),
    Rule("XP02", "D_cross_period", "Ảnh hưởng tiền của phải thu = −(AR_t − AR_t−1)", "ce_ar = −ΔAR",
         lambda d, p: d[C["ce_ar"]], lambda d, p: -(d[C["ar"]] - p[C["ar"]]), ("ce_ar", "ar"), needs_prev=True),
    Rule("XP03", "D_cross_period", "Ảnh hưởng tiền của tồn kho = −ΔTồn kho", "ce_inv = −ΔInv",
         lambda d, p: d[C["ce_inv"]], lambda d, p: -(d[C["inv"]] - p[C["inv"]]), ("ce_inv", "inv"), needs_prev=True),
    Rule("XP04", "D_cross_period", "Ảnh hưởng tiền của TSNH khác = −ΔTSNH khác", "ce_oca = −ΔOCA",
         lambda d, p: d[C["ce_oca"]], lambda d, p: -(d[C["oca"]] - p[C["oca"]]), ("ce_oca", "oca"), needs_prev=True),
    Rule("XP05", "D_cross_period", "Ảnh hưởng tiền của phải trả = +ΔPhải trả", "ce_ap = +ΔAP",
         lambda d, p: d[C["ce_ap"]], lambda d, p: d[C["ap"]] - p[C["ap"]], ("ce_ap", "ap"), needs_prev=True),
    Rule("XP06", "D_cross_period", "Ảnh hưởng tiền của nợ NH khác = +ΔNợ NH khác", "ce_ocl = +ΔOCL",
         lambda d, p: d[C["ce_ocl"]], lambda d, p: d[C["ocl"]] - p[C["ocl"]], ("ce_ocl", "ocl"), needs_prev=True),
    Rule("XP07", "D_cross_period", "Ảnh hưởng tiền của nợ DH khác = +ΔNợ DH khác", "ce_oncl = +ΔONCL",
         lambda d, p: d[C["ce_oncl"]], lambda d, p: d[C["oncl"]] - p[C["oncl"]], ("ce_oncl", "oncl"), needs_prev=True),
    Rule("XP08", "D_cross_period", "Δ LN giữ lại = LNST + Cổ tức (cổ tức mang dấu âm)", "ΔRE = ni + div",
         lambda d, p: d[C["re"]] - p[C["re"]], lambda d, p: d[C["ni"]] + d[C["div"]], ("re", "ni", "div"), needs_prev=True),
    Rule("XP09", "D_cross_period", "Δ Nợ vay (NH + DH) = Vay/trả nợ ròng", "Δ(std + ltd) = debt_iss",
         lambda d, p: (d[C["std"]] + d[C["ltd"]]) - (p[C["std"]] + p[C["ltd"]]), lambda d, p: d[C["debt_iss"]],
         ("std", "ltd", "debt_iss"), needs_prev=True),
    Rule("XP10", "D_cross_period", "Δ Vốn góp = Phát hành vốn", "Δsc = eq_iss",
         lambda d, p: d[C["sc"]] - p[C["sc"]], lambda d, p: d[C["eq_iss"]], ("sc", "eq_iss"), needs_prev=True),
    Rule("XP11", "D_cross_period", "Δ TSCĐ = CAPEX − Khấu hao (CAPEX mang dấu âm)", "Δppe = −capex − da",
         lambda d, p: d[C["ppe"]] - p[C["ppe"]], lambda d, p: -d[C["capex"]] - d[C["da"]], ("ppe", "capex", "da"), needs_prev=True),
    Rule("XP12", "D_cross_period", "Δ TS vô hình = −Dòng tiền vô hình", "Δintang = −cf_intang",
         lambda d, p: d[C["intang"]] - p[C["intang"]], lambda d, p: -d[C["cf_intang"]], ("intang", "cf_intang"), needs_prev=True),
    Rule("XP13", "D_cross_period", "Δ Đầu tư DH = −Dòng tiền đầu tư DH", "Δlti = −cf_lti",
         lambda d, p: d[C["lti"]] - p[C["lti"]], lambda d, p: -d[C["cf_lti"]], ("lti", "cf_lti"), needs_prev=True),
    Rule("XP14", "D_cross_period", "Δ TSDH khác = −Dòng tiền TSDH khác", "Δonca = −cf_onca",
         lambda d, p: d[C["onca"]] - p[C["onca"]], lambda d, p: -d[C["cf_onca"]], ("onca", "cf_onca"), needs_prev=True),
]


def run_accounting_checks(d: pd.DataFrame, p: pd.DataFrame, rules: list[Rule] = RULES,
                          tol: float = TOL_ACCOUNTING) -> pd.DataFrame:
    """Trả về bảng dài: 1 dòng = 1 luật × 1 company-year."""
    out = []
    for r in rules:
        lhs, rhs = r.lhs(d, p), r.rhs(d, p)
        if r.kind == "nonnegative":
            res = lhs.where(lhs < 0, 0.0)
        else:
            res = lhs - rhs
        for i in d.index:
            cid, fy = d.at[i, "company_id"], int(d.at[i, "fiscal_year"])
            if pd.isna(res.at[i]):
                status, detail = "N/A", "INSUFFICIENT_HISTORY – không có năm trước (không tự sinh 2020)"
            else:
                ok = abs(res.at[i]) <= tol
                status = "PASS" if ok else "FAIL"
                if r.kind == "nonnegative":
                    detail = f"{C[r.fields[0]]} = {lhs.at[i]:,.0f}"
                else:
                    detail = f"vế trái {lhs.at[i]:,.0f} | vế phải {rhs.at[i]:,.0f} | lệch {res.at[i]:,.0f}"
            out.append({"rule_id": r.rule_id, "group": r.group, "company_id": cid, "fiscal_year": fy,
                        "status": status, "lhs": lhs.at[i], "rhs": rhs.at[i] if r.kind == "equality" else 0,
                        "residual": res.at[i], "detail": detail, "description": r.description,
                        "evidence": evidence(*r.fields)})
    return pd.DataFrame(out)


def rule_catalog(rules: list[Rule] = RULES) -> pd.DataFrame:
    return pd.DataFrame([{"rule_id": r.rule_id, "group": r.group, "description": r.description,
                          "formula": r.formula, "needs_prev_year": r.needs_prev, "evidence": evidence(*r.fields)}
                         for r in rules])


def summarize_checks(checks: pd.DataFrame) -> pd.DataFrame:
    s = (checks.groupby(["rule_id", "group", "description", "status"]).size().unstack(fill_value=0)
         .reindex(columns=["PASS", "FAIL", "N/A"], fill_value=0).reset_index())
    s["max_abs_residual"] = checks.groupby("rule_id")["residual"].apply(lambda x: x.abs().max()).values
    return s


def row_flags(d: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Cờ cho các dòng mà một số tỷ số cần diễn giải thận trọng."""
    f = d[KEY].copy()
    flags = []
    for i in d.index:
        fl = []
        if pd.isna(p.at[i, C["rev"]]):
            fl.append("FIRST_YEAR_NO_PREV")
        if d.at[i, C["ni"]] <= 0:
            fl.append("NET_LOSS")
        if d.at[i, C["cfo"]] < 0:
            fl.append("NEGATIVE_CFO")
        if d.at[i, C["op"]] <= 0:
            fl.append("OPERATING_LOSS")
        if d.at[i, C["te"]] <= 0:
            fl.append("NEGATIVE_EQUITY")
        if d.at[i, C["int_exp"]] == 0:
            fl.append("NO_INTEREST_EXPENSE")
        if d.at[i, C["op"]] < d.at[i, C["int_exp"]]:
            fl.append("OP_BELOW_INTEREST")
        flags.append(";".join(fl))
    f["row_flags"] = flags
    return f


# ================================================================== BƯỚC 2 – THƯ VIỆN CHỈ TIÊU
@dataclass
class Metric:
    metric_id: str            # trùng tên cột trong submission_output_template
    name_vi: str
    pillar: str               # nhóm: Tăng trưởng, Sinh lời, Thanh khoản, Đòn bẩy, Dòng tiền, Vốn lưu động
    unit: str                 # pct | x | days | vnd_mn
    formula: str
    fields: tuple[str, ...]
    func: Callable[[pd.DataFrame, pd.DataFrame], pd.Series]
    needs_prev: bool = False
    guard: Callable[[pd.DataFrame, pd.DataFrame], pd.Series] | None = None   # True -> gắn cờ diễn giải
    guard_flag: str = ""


def _div(a, b):
    a, b = a.astype(float), b.astype(float)
    return a / b.where(b != 0)          # mẫu số 0 -> NaN, không chia lỗi


def _avg(d, p, k):
    return (d[C[k]] + p[C[k]]) / 2       # NaN nếu không có năm trước


METRICS: list[Metric] = [
    Metric("revenue_growth_pct", "Tăng trưởng doanh thu", "Tăng trưởng", "pct",
           "(Revenue_t − Revenue_t−1) / Revenue_t−1 × 100", ("rev",),
           lambda d, p: _div(d[C["rev"]] - p[C["rev"]], p[C["rev"]]) * 100, needs_prev=True),
    Metric("gross_margin_pct", "Biên lợi nhuận gộp", "Sinh lời", "pct", "Gross Profit / Revenue × 100", ("gp", "rev"),
           lambda d, p: _div(d[C["gp"]], d[C["rev"]]) * 100),
    Metric("operating_margin_pct", "Biên lợi nhuận hoạt động", "Sinh lời", "pct", "Operating Profit / Revenue × 100",
           ("op", "rev"), lambda d, p: _div(d[C["op"]], d[C["rev"]]) * 100),
    Metric("net_margin_pct", "Biên lợi nhuận ròng", "Sinh lời", "pct", "Net Income / Revenue × 100", ("ni", "rev"),
           lambda d, p: _div(d[C["ni"]], d[C["rev"]]) * 100),
    Metric("current_ratio_x", "Hệ số thanh toán hiện hành", "Thanh khoản", "x",
           "Total Current Assets / Total Current Liabilities", ("tca", "tcl"),
           lambda d, p: _div(d[C["tca"]], d[C["tcl"]])),
    Metric("quick_ratio_x", "Hệ số thanh toán nhanh", "Thanh khoản", "x",
           "(Cash + Accounts Receivable) / Total Current Liabilities", ("cash", "ar", "tcl"),
           lambda d, p: _div(d[C["cash"]] + d[C["ar"]], d[C["tcl"]])),
    Metric("debt_to_assets_pct", "Nợ vay / Tổng tài sản", "Đòn bẩy", "pct",
           "(Short-term Debt + Long-term Debt) / Total Assets × 100", ("std", "ltd", "ta"),
           lambda d, p: _div(d[C["std"]] + d[C["ltd"]], d[C["ta"]]) * 100),
    Metric("debt_to_equity_x", "Nợ vay / Vốn chủ sở hữu", "Đòn bẩy", "x",
           "(Short-term Debt + Long-term Debt) / Total Equity", ("std", "ltd", "te"),
           lambda d, p: _div(d[C["std"]] + d[C["ltd"]], d[C["te"]]),
           guard=lambda d, p: d[C["te"]] <= 0, guard_flag="NEGATIVE_EQUITY_DENOMINATOR"),
    Metric("roa_pct", "ROA (tài sản bình quân)", "Sinh lời", "pct", "Net Income / Average Total Assets × 100",
           ("ni", "ta"), lambda d, p: _div(d[C["ni"]], _avg(d, p, "ta")) * 100, needs_prev=True),
    Metric("roe_pct", "ROE (vốn chủ bình quân)", "Sinh lời", "pct", "Net Income / Average Total Equity × 100",
           ("ni", "te"), lambda d, p: _div(d[C["ni"]], _avg(d, p, "te")) * 100, needs_prev=True,
           guard=lambda d, p: _avg(d, p, "te") <= 0, guard_flag="NEGATIVE_EQUITY_DENOMINATOR"),
    Metric("cfo_margin_pct", "CFO / Doanh thu", "Dòng tiền", "pct", "CFO / Revenue × 100", ("cfo", "rev"),
           lambda d, p: _div(d[C["cfo"]], d[C["rev"]]) * 100),
    Metric("cfo_to_net_income_x", "CFO / LNST (chất lượng lợi nhuận)", "Dòng tiền", "x",
           "Net Cash from Operating Activities / Net Income", ("cfo", "ni"),
           lambda d, p: _div(d[C["cfo"]], d[C["ni"]]),
           guard=lambda d, p: d[C["ni"]] <= 0, guard_flag="NON_POSITIVE_NET_INCOME"),
    Metric("free_cash_flow_vnd_mn", "Dòng tiền tự do", "Dòng tiền", "vnd_mn",
           "CFO + Capital Expenditure (CAPEX mang dấu âm)", ("cfo", "capex"),
           lambda d, p: (d[C["cfo"]] + d[C["capex"]]).astype(float)),
    Metric("dso_days", "Số ngày thu tiền (DSO)", "Vốn lưu động", "days",
           "Average Accounts Receivable / Revenue × 365", ("ar", "rev"),
           lambda d, p: _div(_avg(d, p, "ar"), d[C["rev"]]) * 365, needs_prev=True),
    Metric("inventory_days", "Số ngày tồn kho", "Vốn lưu động", "days", "Average Inventory / COGS × 365",
           ("inv", "cogs"), lambda d, p: _div(_avg(d, p, "inv"), d[C["cogs"]]) * 365, needs_prev=True),
    Metric("dpo_days", "Số ngày trả tiền (DPO)", "Vốn lưu động", "days", "Average Accounts Payable / COGS × 365",
           ("ap", "cogs"), lambda d, p: _div(_avg(d, p, "ap"), d[C["cogs"]]) * 365, needs_prev=True),
    Metric("interest_coverage_x", "Khả năng trả lãi", "Đòn bẩy", "x", "Operating Profit / Interest Expense",
           ("op", "int_exp"), lambda d, p: _div(d[C["op"]], d[C["int_exp"]]),
           guard=lambda d, p: d[C["op"]] <= 0, guard_flag="NON_POSITIVE_OPERATING_PROFIT"),
    Metric("working_capital_vnd_mn", "Vốn lưu động ròng", "Thanh khoản", "vnd_mn",
           "Total Current Assets − Total Current Liabilities", ("tca", "tcl"),
           lambda d, p: (d[C["tca"]] - d[C["tcl"]]).astype(float)),
]
METRIC_BY_ID = {m.metric_id: m for m in METRICS}
METRIC_IDS = [m.metric_id for m in METRICS]


def metric_catalog() -> pd.DataFrame:
    return pd.DataFrame([{"metric_id": m.metric_id, "name_vi": m.name_vi, "pillar": m.pillar, "unit": m.unit,
                          "formula": m.formula, "needs_prev_year": m.needs_prev,
                          "interpretation_guard": m.guard_flag, "evidence": evidence(*m.fields)} for m in METRICS])


def compute_metrics(master: pd.DataFrame, metrics: list[Metric] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trả về (wide, long).
    wide : 60 dòng × (khóa + 18 chỉ tiêu) – đúng thứ tự cột của template nộp.
    long : 1 dòng = 1 chỉ tiêu × 1 company-year, kèm công thức, nguồn, cờ.
    Quy tắc: giá trị luôn là kết quả toán học đúng công thức BTC; cờ diễn giải đi kèm ở cột riêng
    (vd CFO/NI khi LNST ≤ 0 vẫn tính, nhưng gắn NON_POSITIVE_NET_INCOME để bước cảnh báo không hiểu sai).
    """
    d, p = prepare(master)
    wide = d[KEY].copy()
    long_rows = []
    for m in (metrics or METRICS):
        v = m.func(d, p)
        wide[m.metric_id] = v
        g = m.guard(d, p) if m.guard else pd.Series(False, index=d.index)
        for i in d.index:
            flag = ""
            if pd.isna(v.at[i]):
                flag = "INSUFFICIENT_HISTORY" if m.needs_prev and pd.isna(p.at[i, C["rev"]]) else "UNDEFINED_ZERO_DENOMINATOR"
            elif bool(g.at[i]):
                flag = m.guard_flag
            long_rows.append({"company_id": d.at[i, "company_id"], "fiscal_year": int(d.at[i, "fiscal_year"]),
                              "metric_id": m.metric_id, "value": v.at[i], "unit": m.unit, "flag": flag,
                              "formula": m.formula,
                              "years_used": f"{int(d.at[i, 'fiscal_year']) - 1}-{int(d.at[i, 'fiscal_year'])}" if m.needs_prev
                              else str(int(d.at[i, "fiscal_year"])),
                              "evidence": evidence(*m.fields)})
    return wide, pd.DataFrame(long_rows)


# ================================================================== BƯỚC 3a – VERIFY KÉP (cách tính độc lập)
def compute_metrics_independent(data_dir: str | Path) -> pd.DataFrame:
    """Tính lại 18 chỉ tiêu theo một đường hoàn toàn khác:
    đọc thẳng 3 file BCTC gốc bằng module csv (không dùng master_panel, không dùng pandas merge/shift),
    tra năm trước bằng dict (company_id, year-1). Nếu kết quả trùng với compute_metrics -> phép tính được xác nhận.
    """
    data_dir = Path(data_dir)

    def load(rel):
        path = data_dir / rel
        if not path.exists():                      # layout khác README: tìm theo tên file
            hits = sorted(data_dir.rglob(Path(rel).name))
            path = hits[0] if hits else path
        with open(path, encoding="utf-8-sig", newline="") as f:
            return {(r["company_id"], int(r["fiscal_year"])): {k: float(v) for k, v in r.items()
                                                                if k not in ("company_id", "fiscal_year")}
                    for r in csv.DictReader(f)}

    is_, bs, cf = load("01_data/income_statement.csv"), load("01_data/balance_sheet.csv"), load("01_data/cashflow.csv")

    def div(a, b):
        return a / b if b not in (0, None) and a is not None else math.nan

    rows = []
    for (cid, y) in sorted(is_):
        i, b, c = is_[(cid, y)], bs[(cid, y)], cf[(cid, y)]
        ip, bp = is_.get((cid, y - 1)), bs.get((cid, y - 1))
        avg = (lambda k: (b[k] + bp[k]) / 2) if bp else (lambda k: None)
        debt = b["short_term_debt_vnd_mn"] + b["long_term_debt_vnd_mn"]
        rows.append({
            "company_id": cid, "fiscal_year": y,
            "revenue_growth_pct": div(i["revenue_vnd_mn"] - ip["revenue_vnd_mn"], ip["revenue_vnd_mn"]) * 100 if ip else math.nan,
            "gross_margin_pct": div(i["gross_profit_vnd_mn"], i["revenue_vnd_mn"]) * 100,
            "operating_margin_pct": div(i["operating_profit_vnd_mn"], i["revenue_vnd_mn"]) * 100,
            "net_margin_pct": div(i["net_income_vnd_mn"], i["revenue_vnd_mn"]) * 100,
            "current_ratio_x": div(b["total_current_assets_vnd_mn"], b["total_current_liabilities_vnd_mn"]),
            "quick_ratio_x": div(b["cash_and_cash_equivalents_vnd_mn"] + b["accounts_receivable_vnd_mn"],
                                 b["total_current_liabilities_vnd_mn"]),
            "debt_to_assets_pct": div(debt, b["total_assets_vnd_mn"]) * 100,
            "debt_to_equity_x": div(debt, b["total_equity_vnd_mn"]),
            "roa_pct": div(i["net_income_vnd_mn"], avg("total_assets_vnd_mn")) * 100 if bp else math.nan,
            "roe_pct": div(i["net_income_vnd_mn"], avg("total_equity_vnd_mn")) * 100 if bp else math.nan,
            "cfo_margin_pct": div(c["net_cash_from_operating_activities_vnd_mn"], i["revenue_vnd_mn"]) * 100,
            "cfo_to_net_income_x": div(c["net_cash_from_operating_activities_vnd_mn"], i["net_income_vnd_mn"]),
            "free_cash_flow_vnd_mn": c["net_cash_from_operating_activities_vnd_mn"] + c["capital_expenditure_vnd_mn"],
            "dso_days": div(avg("accounts_receivable_vnd_mn"), i["revenue_vnd_mn"]) * 365 if bp else math.nan,
            "inventory_days": div(avg("inventory_vnd_mn"), i["cost_of_goods_sold_vnd_mn"]) * 365 if bp else math.nan,
            "dpo_days": div(avg("accounts_payable_vnd_mn"), i["cost_of_goods_sold_vnd_mn"]) * 365 if bp else math.nan,
            "interest_coverage_x": div(i["operating_profit_vnd_mn"], i["interest_expense_vnd_mn"]),
            "working_capital_vnd_mn": b["total_current_assets_vnd_mn"] - b["total_current_liabilities_vnd_mn"],
        })
    return pd.DataFrame(rows)


def dual_verify(wide: pd.DataFrame, indep: pd.DataFrame, rel_tol: float = 1e-9) -> pd.DataFrame:
    """So sánh từng ô giữa 2 cách tính. Trả về 1 dòng / chỉ tiêu."""
    a = wide.set_index(KEY).sort_index()
    b = indep.set_index(KEY).sort_index()
    out = []
    for mid in METRIC_IDS:
        x, y = a[mid].astype(float), b[mid].astype(float)
        both_nan = x.isna() & y.isna()
        close = np.isclose(x, y, rtol=rel_tol, atol=1e-9) | both_nan
        diff = (x - y).abs()
        out.append({"metric_id": mid, "cells": len(x), "agree": int(close.sum()), "disagree": int((~close).sum()),
                    "na_cells (2021/không xác định)": int(both_nan.sum()),
                    "max_abs_diff": float(diff.max()) if diff.notna().any() else 0.0,
                    "status": "PASS" if close.all() else "FAIL"})
    return pd.DataFrame(out)


# ================================================================== CHỈ TIÊU BỔ SUNG (có trong financial_metrics_sample)
SUPPLEMENTARY = {
    "total_debt_vnd_mn": ("Tổng nợ vay", "vnd_mn", "Short-term Debt + Long-term Debt", ("std", "ltd"), False,
                          lambda d, p: (d[C["std"]] + d[C["ltd"]]).astype(float)),
    "cfo_vnd_mn": ("CFO", "vnd_mn", "Net Cash from Operating Activities", ("cfo",), False,
                   lambda d, p: d[C["cfo"]].astype(float)),
    "accounts_receivable_growth_pct": ("Tăng trưởng phải thu", "pct", "(AR_t − AR_t−1) / AR_t−1 × 100", ("ar",), True,
                                       lambda d, p: _div(d[C["ar"]] - p[C["ar"]], p[C["ar"]]) * 100),
    "inventory_growth_pct": ("Tăng trưởng tồn kho", "pct", "(Inv_t − Inv_t−1) / Inv_t−1 × 100", ("inv",), True,
                             lambda d, p: _div(d[C["inv"]] - p[C["inv"]], p[C["inv"]]) * 100),
    "total_debt_growth_pct": ("Tăng trưởng nợ vay", "pct", "(Debt_t − Debt_t−1) / Debt_t−1 × 100", ("std", "ltd"), True,
                              lambda d, p: _div((d[C["std"]] + d[C["ltd"]]) - (p[C["std"]] + p[C["ltd"]]),
                                                p[C["std"]] + p[C["ltd"]]) * 100),
}


def compute_supplementary(master: pd.DataFrame) -> pd.DataFrame:
    """5 chỉ tiêu bổ sung (không thuộc template nộp, dùng cho cảnh báo ở NB2)."""
    d, p = prepare(master)
    out = d[KEY].copy()
    for mid, (_, _, _, _, _, f) in SUPPLEMENTARY.items():
        out[mid] = f(d, p)
    return out


BTC_TOL = {"pct": 0.05, "x": 0.01, "days": 0.2, "vnd_mn": 0.0}     # dung sai BTC dùng trong answer_key


def compare_with_metrics_sample(wide: pd.DataFrame, supp: pd.DataFrame, sample_path) -> pd.DataFrame:
    """Đối chiếu từng ô với financial_metrics_sample.csv.
    Hai thước đo: (1) khớp tuyệt đối ở đúng số chữ số thập phân BTC ghi; (2) trong dung sai BTC theo đơn vị."""
    raw = pd.read_csv(sample_path, encoding="utf-8-sig", dtype=str)
    ours = wide.merge(supp, on=KEY).set_index(KEY)
    units = {m.metric_id: m.unit for m in METRICS} | {k: v[1] for k, v in SUPPLEMENTARY.items()}
    rows = []
    for _, r in raw.iterrows():
        key = (r["company_id"], int(r["fiscal_year"]))
        for col in raw.columns:
            if col in KEY:
                continue
            txt = str(r[col]).strip()
            ref = float(txt) if txt not in ("", "nan") else np.nan
            dec = len(txt.split(".")[1]) if "." in txt else 0
            val = float(ours.at[key, col]) if col in ours.columns else np.nan
            diff = abs(val - ref) if not (np.isnan(val) or np.isnan(ref)) else np.nan
            exact = bool(diff <= 0.5 * 10 ** (-dec) + 1e-9) if not np.isnan(diff) else (np.isnan(val) and np.isnan(ref))
            unit = units.get(col, "")
            tol = max(BTC_TOL.get(unit, 0.0), 0.5 * 10 ** (-dec))
            within = bool(diff <= tol + 1e-9) if not np.isnan(diff) else exact
            rows.append({"company_id": key[0], "fiscal_year": key[1], "metric_id": col,
                         "in_template": col in METRIC_IDS, "unit": unit, "ours": val, "btc": ref, "btc_decimals": dec,
                         "abs_diff": diff, "exact_at_btc_precision": exact, "within_btc_tolerance": within})
    return pd.DataFrame(rows)
