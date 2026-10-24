"""finreport_whatif.py – Mô phỏng kịch bản giả định (what-if / stress test) cho 1 company-year.

Nguyên tắc:
  * Chỉ sửa trên BẢN SAO master_panel; dữ liệu gốc không đổi.
  * Mỗi đòn bẩy điều chỉnh các khoản mục liên quan theo đúng quan hệ kế toán đơn giản
    (vd phải thu tăng -> CFO giảm đúng phần tăng và tiền giảm tương ứng, bảng cân đối vẫn cân).
  * Sau đó chạy lại NGUYÊN pipeline chỉ tiêu + tín hiệu + chấm điểm -> so sánh trước/sau.
  * Chỉ năm được chọn bị sửa; các năm sau giữ nguyên số liệu gốc (liên kết đầu kỳ năm sau không cập nhật).
  * Đây là mô phỏng hỗ trợ phân tích, không phải dự báo.
"""
from __future__ import annotations

import pandas as pd

import finreport_metrics as fm
import finreport_signals as fs

C = fm.C
LEVERS = {
    "revenue_change_pct": ("Doanh thu thay đổi (%)", -30.0, 20.0, 0.0,
                           "Doanh thu và giá vốn đổi cùng tỷ lệ; chi phí bán hàng, quản lý, khấu hao giữ nguyên → biên lợi nhuận co giãn"),
    "gross_margin_change_pp": ("Biên gộp thay đổi (điểm %)", -10.0, 5.0, 0.0,
                               "Giữ doanh thu, đổi giá vốn để biên gộp tăng/giảm"),
    "interest_rate_change_pp": ("Lãi suất vay thay đổi (điểm %)", -3.0, 6.0, 0.0,
                                "Chi phí lãi vay tăng theo tỷ lệ lãi suất mới / lãi suất bình quân hiện tại"),
    "debt_change_pct": ("Nợ vay thay đổi (%)", -50.0, 100.0, 0.0,
                        "Vay thêm/trả bớt nợ (NH & DH cùng tỷ lệ); tiền tăng/giảm tương ứng; lãi vay đổi theo"),
    "dso_target_days": ("DSO mục tiêu (ngày, 0 = giữ nguyên)", 0.0, 150.0, 0.0,
                        "Đặt phải thu cuối năm sao cho DSO bình quân = mục tiêu; chênh lệch phải thu đi vào CFO và tiền"),
    "inventory_days_target": ("Ngày tồn kho mục tiêu (0 = giữ nguyên)", 0.0, 200.0, 0.0,
                              "Đặt tồn kho cuối năm theo số ngày mục tiêu; chênh lệch đi vào CFO và tiền"),
}


def apply_scenario(master: pd.DataFrame, company_id: str, year: int, levers: dict) -> pd.DataFrame:
    m = master.copy()
    for c in m.columns:
        if c.endswith("_vnd_mn"):
            m[c] = m[c].astype(float)
    i = m.index[(m["company_id"] == company_id) & (m["fiscal_year"].astype(int) == int(year))]
    if len(i) != 1:
        raise ValueError("Không tìm thấy company-year")
    i = i[0]
    prev = m[(m["company_id"] == company_id) & (m["fiscal_year"].astype(int) == int(year) - 1)]
    r = m.loc[i].copy()
    tax_rate = (r[C["tax"]] / r[C["pbt"]]) if r[C["pbt"]] > 0 else 0.0
    ni_before = r[C["ni"]]

    # --- biên & doanh thu
    k = 1 + levers.get("revenue_change_pct", 0.0) / 100
    r[C["rev"]] *= k
    r[C["cogs"]] *= k
    dgm = levers.get("gross_margin_change_pp", 0.0) / 100
    r[C["cogs"]] = r[C["cogs"]] - dgm * r[C["rev"]]
    r[C["gp"]] = r[C["rev"]] - r[C["cogs"]]
    # --- nợ vay & lãi suất
    dk = levers.get("debt_change_pct", 0.0) / 100
    d_debt = (r[C["std"]] + r[C["ltd"]]) * dk
    r[C["std"]] *= 1 + dk; r[C["ltd"]] *= 1 + dk
    rate = float(r.get("average_borrowing_rate_pct", 0) or 0)
    drate = levers.get("interest_rate_change_pp", 0.0)
    rate_factor = (rate + drate) / rate if rate > 0 else 1.0
    r[C["int_exp"]] *= (1 + dk) * rate_factor
    if rate > 0:
        r["average_borrowing_rate_pct"] = rate + drate
    # --- lợi nhuận
    r[C["op"]] = r[C["gp"]] - r[C["sell"]] - r[C["admin"]] - r[C["da"]]
    r[C["pbt"]] = r[C["op"]] + r[C["fin_inc"]] - r[C["int_exp"]] + r[C["oth_inc"]]
    r[C["tax"]] = max(r[C["pbt"]], 0) * tax_rate
    r[C["ni"]] = r[C["pbt"]] - r[C["tax"]]
    # --- vốn lưu động
    def wc_target(col, days, base_col):
        if days and days > 0 and len(prev):
            p = float(prev.iloc[0][col])
            new = max(2 * days * r[base_col] / 365 - p, 0.0)
            return new - r[col]
        return 0.0
    d_ar = wc_target(C["ar"], levers.get("dso_target_days", 0), C["rev"])
    d_inv = wc_target(C["inv"], levers.get("inventory_days_target", 0), C["cogs"])
    r[C["ar"]] += d_ar; r[C["inv"]] += d_inv
    # --- báo cáo lưu chuyển tiền tệ (giữ đúng các đẳng thức CF01–CF06)
    r[C["ce_ar"]] -= d_ar
    r[C["ce_inv"]] -= d_inv
    r[C["cfo"]] = (r[C["ni"]] + r[C["da"]] + r[C["ce_ar"]] + r[C["ce_inv"]] + r[C["ce_oca"]]
                   + r[C["ce_ap"]] + r[C["ce_ocl"]] + r[C["ce_oncl"]])
    r[C["debt_iss"]] += d_debt
    r[C["cff"]] = r[C["debt_iss"]] + r[C["eq_iss"]] + r[C["div"]]
    r[C["chg"]] = r[C["cfo"]] + r[C["cfi"]] + r[C["cff"]]
    r[C["end"]] = r[C["beg"]] + r[C["chg"]]
    # --- bảng cân đối (tiền khớp LCTT; LN giữ lại theo LNST mới -> vẫn cân)
    r[C["cash"]] = r[C["end"]]
    r[C["tca"]] = r[C["cash"]] + r[C["ar"]] + r[C["inv"]] + r[C["oca"]]
    r[C["ta"]] = r[C["tca"]] + r[C["ppe"]] + r[C["intang"]] + r[C["lti"]] + r[C["onca"]]
    r[C["tcl"]] = r[C["std"]] + r[C["ap"]] + r[C["ocl"]]
    r[C["tl"]] = r[C["tcl"]] + r[C["ltd"]] + r[C["oncl"]]
    r[C["re"]] += r[C["ni"]] - ni_before
    r[C["te"]] = r[C["sc"]] + r[C["re"]] + r[C["oe"]]
    r[C["tle"]] = r[C["tl"]] + r[C["te"]]
    m.loc[i] = r
    return m


def check_identities(master_scn, company_id, year):
    """Chạy lại 32 luật kế toán cho company-year đã mô phỏng -> bằng chứng kịch bản vẫn nhất quán."""
    d, p = fm.prepare(master_scn)
    ch = fm.run_accounting_checks(d, p)
    return ch[(ch["company_id"] == company_id) & (ch["fiscal_year"] == int(year))]


def simulate(master: pd.DataFrame, company_id: str, year: int, levers: dict) -> dict:
    """Chạy pipeline trước & sau, trả về bảng so sánh chỉ tiêu và kết quả cảnh báo."""
    def pipe(mm):
        w, _ = fm.compute_metrics(mm)
        s = fm.compute_supplementary(mm)
        f, sig, pred = fs.run(mm, w, s)
        return w, pred

    w0, p0 = pipe(master)
    m1 = apply_scenario(master, company_id, year, levers)
    w1, p1 = pipe(m1)
    sel = lambda d: d[(d["company_id"] == company_id) & (d["fiscal_year"].astype(int) == int(year))].iloc[0]
    a, b = sel(w0), sel(w1)
    metrics = pd.DataFrame({"chỉ tiêu": [fm.METRIC_BY_ID[k].name_vi for k in fm.METRIC_IDS],
                            "metric_id": fm.METRIC_IDS,
                            "trước": [a[k] for k in fm.METRIC_IDS], "sau": [b[k] for k in fm.METRIC_IDS]})
    metrics["thay đổi"] = metrics["sau"] - metrics["trước"]
    pa, pb = sel(p0), sel(p1)
    keys = ["risk_score", "predicted_primary_scenario", "predicted_severity", "predicted_overall_health", "alert_tags", "priority_rank"]
    outcome = pd.DataFrame({"trước": [pa[k] for k in keys], "sau": [pb[k] for k in keys]}, index=keys)
    comps = pd.DataFrame({"thành phần": list(fs.RISK_WEIGHTS),
                          "trước": [pa[f"rc_{k}"] for k in fs.RISK_WEIGHTS], "sau": [pb[f"rc_{k}"] for k in fs.RISK_WEIGHTS]})
    ident = check_identities(m1, company_id, year)
    return {"identity_fail": int((ident["status"] == "FAIL").sum()), "identity_pass": int((ident["status"] == "PASS").sum()),
            "metrics": metrics, "outcome": outcome, "components": comps, "reason_after": pb["alert_reason"],
            "reason_before": pa["alert_reason"]}
