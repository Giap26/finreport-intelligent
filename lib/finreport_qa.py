"""finreport_qa.py – Numerical QA engine + chấm điểm với answer key.

Nguyên tắc chống hard-code:
  * Engine CHỈ đọc questions (question_type, target_company_id, target_fiscal_year, source_fields, text).
    Không đọc answer_key khi trả lời; không có nhánh nào theo question_id.
  * Mọi con số lấy từ finreport_metrics (cùng công thức với bảng chỉ tiêu và file nộp).
  * Câu không nhận dạng được -> trả lời rỗng, confidence 0, cờ UNSUPPORTED (không đoán bừa).
"""
from __future__ import annotations

import re
import time

import numpy as np
import pandas as pd

import finreport_metrics as fm

C = fm.C
_F = {v: k for k, v in C.items()}            # tên cột đầy đủ -> tên ngắn

# Tập trường nguồn -> chỉ tiêu (tra theo frozenset tên ngắn)
FIELDSET_TO_METRIC = {
    frozenset({"gp", "rev"}): "gross_margin_pct",
    frozenset({"op", "rev"}): "operating_margin_pct",
    frozenset({"ni", "rev"}): "net_margin_pct",
    frozenset({"cash", "ar", "tcl"}): "quick_ratio_x",
    frozenset({"std", "ltd", "ta"}): "debt_to_assets_pct",
    frozenset({"std", "ltd", "te"}): "debt_to_equity_x",
    frozenset({"ni", "ta"}): "roa_pct",
    frozenset({"ni", "te"}): "roe_pct",
    frozenset({"cfo", "rev"}): "cfo_margin_pct",
    frozenset({"cfo", "ni"}): "cfo_to_net_income_x",
    frozenset({"cfo", "capex"}): "free_cash_flow_vnd_mn",
    frozenset({"ar", "rev"}): "dso_days",
    frozenset({"inv", "cogs"}): "inventory_days",
    frozenset({"ap", "cogs"}): "dpo_days",
    frozenset({"op", "int_exp"}): "interest_coverage_x",
    frozenset({"rev"}): "revenue_growth_pct",
}
NUMERIC_TYPES = {"numeric_vnd_mn", "numeric_percentage", "numeric_ratio", "numeric_days", "numeric_percentage_point"}


def _split(s) -> list[str]:
    return [x.strip() for x in str(s).split(";") if x.strip() and str(s) != "nan"]


def _years(s) -> list[int]:
    """'2025' -> [2025] · '2021;2025' -> [2021, 2025] · '2023-2025' -> [2023, 2025]"""
    return [int(x) for x in re.findall(r"\d{4}", str(s))]


class QAEngine:
    MODEL_NAME = "FinReport-RuleQA v1.0 (deterministic, no LLM)"

    def __init__(self, master: pd.DataFrame, wide: pd.DataFrame, metrics_long: pd.DataFrame | None = None):
        self.d, _ = fm.prepare(master)
        self.m = self.d.set_index(fm.KEY)
        self.w = wide.set_index(fm.KEY).sort_index()
        self.names = dict(zip(master["company_id"], master["company_name"]))
        self.flags = ({} if metrics_long is None else
                      {(r.company_id, r.fiscal_year, r.metric_id): r.flag for r in metrics_long.itertuples() if r.flag})
        self.companies = sorted(master["company_id"].unique())

    # ------------------------------------------------------------------ tiện ích
    def _label(self, cid):
        return f"{cid} - {self.names.get(cid, '')}".strip(" -")

    def _resolve_metric(self, short_fields: list[str], exp_type: str):
        fs = frozenset(short_fields)
        if fs == frozenset({"tca", "tcl"}):
            return "working_capital_vnd_mn" if exp_type == "numeric_vnd_mn" else "current_ratio_x"
        return FIELDSET_TO_METRIC.get(fs)

    def _val(self, cid, y, col):
        return float(self.m.at[(cid, y), col])

    def _metric(self, cid, y, mid):
        return float(self.w.at[(cid, y), mid])

    def _sum_fields(self, cid, y, fields):
        return sum(self._val(cid, y, f) for f in fields)

    # ------------------------------------------------------------------ trả lời 1 câu
    def answer(self, q: dict) -> dict:
        t0 = time.perf_counter()
        qtype = q["question_type"]
        exp = q.get("expected_answer_type", "")
        text = str(q.get("question_text_vi", "")).lower()
        cid = q.get("target_company_id") if isinstance(q.get("target_company_id"), str) and q.get("target_company_id") else None
        years = _years(q.get("target_fiscal_year", ""))
        files, fields = _split(q.get("source_files")), _split(q.get("source_fields"))
        short = [_F.get(f, f) for f in fields]
        res = {"question_id": q["question_id"], "answer": "", "normalized": "", "evidence_source_files": ";".join(files),
               "evidence_source_fields": ";".join(fields), "explanation": "", "confidence": 0.0,
               "handler": qtype, "answer_flags": ""}
        try:
            handler = getattr(self, f"_h_{qtype.lower()}", None)
            if handler is None:
                raise NotImplementedError(f"Chưa hỗ trợ loại câu hỏi {qtype}")
            handler(res, cid, years, fields, short, exp, text)
        except Exception as e:                                  # không đoán bừa
            res.update(answer="", normalized="", confidence=0.0, answer_flags="UNSUPPORTED", explanation=f"Không trả lời được: {e}")
        res["processing_time_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        res["model_name"] = self.MODEL_NAME
        return res

    def answer_all(self, questions: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([self.answer(r) for r in questions.to_dict("records")])

    # ------------------------------------------------------------------ các handler theo question_type
    def _h_direct_value(self, res, cid, years, fields, short, exp, text):
        y, col = years[0], fields[0]
        v = self._val(cid, y, col)
        res.update(answer=self._fmt(v, exp), normalized=v, confidence=0.99,
                   explanation=f"Lấy trực tiếp {col} của {cid} năm {y} = {self._fmt(v, exp)}.")

    def _metric_answer(self, res, cid, y, mid, exp):
        v = self._metric(cid, y, mid)
        if np.isnan(v):
            raise ValueError(f"{mid} không xác định cho {cid}/{y}")
        meta = fm.METRIC_BY_ID[mid]
        flag = self.flags.get((cid, y, mid), "")
        conf = 0.97 if not flag else 0.75
        note = f" Lưu ý: {flag} – cần diễn giải thận trọng." if flag else ""
        res.update(answer=self._fmt(v, exp), normalized=v, confidence=conf, answer_flags=flag,
                   explanation=f"{meta.name_vi} = {meta.formula} = {v:.6f} ({cid}, {meta.unit}, năm {y}"
                               f"{', số dư bình quân ' + str(y - 1) + '–' + str(y) if meta.needs_prev else ''}).{note}")

    def _h_ratio_calculation(self, res, cid, years, fields, short, exp, text):
        mid = self._resolve_metric(short, exp)
        if mid is None:
            raise ValueError(f"Không nhận dạng được chỉ tiêu từ {fields}")
        self._metric_answer(res, cid, years[0], mid, exp)

    _h_working_capital_metric = _h_ratio_calculation
    _h_cashflow_calculation = _h_ratio_calculation
    _h_liquidity_calculation = _h_ratio_calculation

    def _h_growth_calculation(self, res, cid, years, fields, short, exp, text):
        y = years[-1]
        now, prev = self._sum_fields(cid, y, fields), self._sum_fields(cid, y - 1, fields)
        g = (now - prev) / prev * 100
        lbl = " + ".join(fields)
        res.update(answer=self._fmt(g, exp), normalized=g, confidence=0.97,
                   explanation=f"Tăng trưởng ({lbl}) {y} so với {y-1} = ({now:,.0f} − {prev:,.0f}) / {prev:,.0f} × 100 = {g:.6f}%.")

    def _h_change_calculation(self, res, cid, years, fields, short, exp, text):
        mid = self._resolve_metric(short, exp)
        y1, y2 = years[0], years[-1]
        v1, v2 = self._metric(cid, y1, mid), self._metric(cid, y2, mid)
        decline = "giảm" in text
        ch = (v1 - v2) if decline else (v2 - v1)
        name = fm.METRIC_BY_ID[mid].name_vi
        res.update(answer=self._fmt(ch, exp), normalized=ch, confidence=0.97,
                   explanation=f"{name} {y1} = {v1:.4f}%, {y2} = {v2:.4f}% → {'giảm' if decline else 'thay đổi'} "
                               f"{ch:.6f} điểm phần trăm.")

    def _rank(self, mid, y, desc=True):
        s = self.w.xs(y, level="fiscal_year")[mid].dropna().sort_values(ascending=not desc)
        return s

    def _h_ranking(self, res, cid, years, fields, short, exp, text):
        mid = self._resolve_metric(short, "numeric_ratio")
        y = years[-1]
        desc = "thấp nhất" not in text
        s = self._rank(mid, y, desc)
        n = int(m.group(1)) if (m := re.search(r"(\d+)\s*doanh nghiệp", text)) else 1
        top = list(s.index[:n])
        name, unit = fm.METRIC_BY_ID[mid].name_vi, fm.METRIC_BY_ID[mid].unit
        res.update(answer=";".join(self._label(c) for c in top), normalized=";".join(top), confidence=0.97,
                   explanation=f"Xếp hạng {name} năm {y} ({'giảm' if desc else 'tăng'} dần, {len(s)} DN): "
                               + "; ".join(f"{c}={s[c]:.3f}{'%' if unit == 'pct' else ''}" for c in s.index[:max(n, 3)]) + ".")

    def _h_boolean_analysis(self, res, cid, years, fields, short, exp, text):
        y1, y2 = (years[0], years[-1]) if len(years) > 1 else (years[0] - 1, years[0])
        f_a, f_b = fields[0], fields[1]
        a1, a2, b1, b2 = (self._val(cid, y1, f_a), self._val(cid, y2, f_a), self._val(cid, y1, f_b), self._val(cid, y2, f_b))
        ga, gb = (a2 - a1) / a1 * 100, (b2 - b1) / b1 * 100
        yes = ga > gb
        res.update(answer="Có" if yes else "Không", normalized=yes, confidence=0.95,
                   explanation=f"{f_a}: {a1:,.0f} → {a2:,.0f} ({ga:+.2f}%); {f_b}: {b1:,.0f} → {b2:,.0f} ({gb:+.2f}%) "
                               f"giai đoạn {y1}→{y2}. {'Có' if yes else 'Không'}: tốc độ tăng {f_a} "
                               f"{'cao hơn' if yes else 'không cao hơn'} {f_b}.")

    def _h_trend_analysis(self, res, cid, years, fields, short, exp, text):
        if exp == "company_id":                      # DN thay đổi mạnh nhất giữa 2 năm
            mid = self._resolve_metric(short, "numeric_ratio")
            y1, y2 = years[0], years[-1]
            ch = (self.w.xs(y2, level="fiscal_year")[mid] - self.w.xs(y1, level="fiscal_year")[mid]).dropna()
            ch = ch.sort_values(ascending=("giảm" in text))
            top = ch.index[0]
            res.update(answer=self._label(top), normalized=top, confidence=0.95,
                       explanation=f"Thay đổi {fm.METRIC_BY_ID[mid].name_vi} {y1}→{y2} (điểm %): "
                                   + "; ".join(f"{c}={ch[c]:+.2f}" for c in ch.index[:3]) + ".")
            return
        self._narrative(res, cid, years[0], years[-1])

    def _narrative(self, res, cid, y1, y2):
        """Mô tả xu hướng ngắn + bộ tag chuẩn hóa (dùng để chấm và để tái sử dụng cho cảnh báo)."""
        ys = list(range(y1, y2 + 1))
        g = lambda col: [self._val(cid, y, C[col]) for y in ys]
        rev, cfo, ni, ar, inv = g("rev"), g("cfo"), g("ni"), g("ar"), g("inv")
        growth = lambda s: (s[-1] - s[0]) / abs(s[0]) * 100 if s[0] else np.nan
        conv = [c / n if n > 0 else np.nan for c, n in zip(cfo, ni)]
        tags, parts = [], []
        if rev[-1] > rev[0]:
            tags.append("REVENUE_UP")
            parts.append(f"Doanh thu tăng {'liên tục' if all(b > a for a, b in zip(rev, rev[1:])) else ''} "
                         f"{growth(rev):+.1f}% ({rev[0]:,.0f} → {rev[-1]:,.0f})")
        else:
            tags.append("REVENUE_DOWN"); parts.append(f"Doanh thu giảm {growth(rev):+.1f}%")
        if cfo[-1] < cfo[0]:
            tags.append("CFO_DOWN")
        parts.append(f"CFO {cfo[0]:,.0f} → {cfo[-1]:,.0f}")
        if not np.isnan(conv[-1]) and (np.isnan(conv[0]) or conv[-1] < conv[0]) and conv[-1] < 0.8:
            tags.append("CFO_CONVERSION_WEAKENING")
            parts.append(f"CFO/LNST giảm còn {conv[-1]:.3f}x (từ {conv[0]:.3f}x) – khả năng chuyển lợi nhuận thành tiền suy yếu")
        if growth(ar) > growth(rev):
            tags.append("RECEIVABLES_UP"); parts.append(f"phải thu tăng {growth(ar):+.1f}%, nhanh hơn doanh thu")
        if growth(inv) > growth(rev):
            tags.append("INVENTORY_UP"); parts.append(f"tồn kho tăng {growth(inv):+.1f}%, nhanh hơn doanh thu")
        if ({"RECEIVABLES_UP", "INVENTORY_UP"} & set(tags)) and ({"CFO_CONVERSION_WEAKENING", "CFO_DOWN"} & set(tags)):
            tags.append("WORKING_CAPITAL_PRESSURE")
            parts.append("gợi ý chất lượng dòng tiền giảm và áp lực vốn lưu động (tiền bị giữ trong phải thu/tồn kho)")
        text = f"{cid} {y1}–{y2}: " + "; ".join(parts) + "."
        res.update(answer=text, normalized=";".join(tags), confidence=0.85,
                   evidence_source_fields=res["evidence_source_fields"] + ";" + C["ni"] + ";" + C["inv"],
                   explanation=f"Tag: {';'.join(tags)}. Chuỗi: revenue={rev}; CFO={cfo}; NI={ni}; AR={ar}; INV={inv}.")

    def _h_list_filter(self, res, cid, years, fields, short, exp, text):
        y, col = years[-1], fields[0]
        s = self.m.xs(y, level="fiscal_year")[col]
        if "âm" in text:
            sel, cond = s[s < 0], "< 0"
        elif "dương" in text:
            sel, cond = s[s > 0], "> 0"
        else:
            raise ValueError("Không nhận dạng được điều kiện lọc")
        ids = sorted(sel.index)
        res.update(answer=";".join(self._label(c) for c in ids), normalized=";".join(ids), confidence=0.97,
                   explanation=f"Lọc {col} {cond} năm {y} trên {len(s)} DN: " +
                               ("; ".join(f"{c}={sel[c]:,.0f}" for c in ids) if ids else "không có DN nào") + ".")

    def _h_reconciliation(self, res, cid, years, fields, short, exp, text):
        y = years[-1]
        a, b = self._val(cid, y, fields[0]), self._val(cid, y, fields[1])
        ok = abs(a - b) < 0.5
        res.update(answer="Có" if ok else "Không", normalized=ok, confidence=0.99,
                   explanation=f"{fields[0]} = {a:,.0f}; {fields[1]} = {b:,.0f} → {'khớp' if ok else f'lệch {a-b:,.0f}'}.")

    # ------------------------------------------------------------------ định dạng
    @staticmethod
    def _fmt(v, exp):
        if exp == "numeric_vnd_mn":
            return f"{v:.0f}" if float(v).is_integer() else f"{v:.6f}"
        return f"{v:.6f}"


# ================================================================== CHẤM ĐIỂM
def grade(answers: pd.DataFrame, key: pd.DataFrame) -> pd.DataFrame:
    """So từng câu với answer_key_sample theo answer_unit_or_type và numeric_tolerance của BTC."""
    k = key.set_index("question_id")
    rows = []
    for a in answers.itertuples():
        r = k.loc[a.question_id]
        typ, ref = str(r["answer_unit_or_type"]), r["normalized_answer"]
        tol = 0.0 if pd.isna(r["numeric_tolerance"]) else float(r["numeric_tolerance"])
        mine, ok, note = a.normalized, False, ""
        try:
            if typ in ("VND_million", "percent", "x", "percentage_point", "days"):
                diff = abs(float(mine) - float(ref))
                ok = diff <= tol + 1e-9
                note = f"|lệch| = {diff:.6g} (dung sai {tol})"
            elif typ == "company_id":
                ok = str(mine).strip() == str(ref).strip()
            elif typ == "ordered_company_id_list":
                ok = _split(mine) == _split(ref); note = "so khớp cả thứ tự"
            elif typ == "company_id_list":
                ok = set(_split(mine)) == set(_split(ref)); note = "so khớp tập hợp"
            elif typ == "boolean":
                ok = bool(mine) == (str(ref).upper() == "TRUE")
            elif typ == "short_text":
                need, got = set(_split(ref)), set(_split(mine))
                ok = need <= got
                note = f"tag bắt buộc {len(need & got)}/{len(need)}" + (f"; tag thêm: {sorted(got - need)}" if got - need else "")
            else:
                note = f"loại đáp án chưa hỗ trợ: {typ}"
        except (TypeError, ValueError) as e:
            note = f"không so được: {e}"
        rows.append({"question_id": a.question_id, "question_type": r["question_type"], "difficulty": r["difficulty"],
                     "answer_type": typ, "our_answer": a.answer, "our_normalized": mine,
                     "reference_answer": r["reference_answer"], "reference_normalized": ref,
                     "tolerance": tol, "correct": bool(ok), "note": note, "confidence": a.confidence})
    return pd.DataFrame(rows)


def to_submission(answers: pd.DataFrame, template: pd.DataFrame) -> pd.DataFrame:
    """Điền kết quả vào đúng schema qa_submission_template (giữ nguyên thứ tự question_id và cột)."""
    a = answers.set_index("question_id")
    out = template[["question_id"]].copy()
    for col in ["answer", "evidence_source_files", "evidence_source_fields", "explanation", "confidence",
                "model_name", "processing_time_ms"]:
        out[col] = out["question_id"].map(a[col])
    return out[template.columns.tolist()]


# ================================================================== KIỂM THỬ TỔNG QUÁT HÓA (mô phỏng câu hỏi ẩn)
_UNIT = {"pct": ("numeric_percentage", "percent", 0.05), "x": ("numeric_ratio", "x", 0.01),
         "days": ("numeric_days", "days", 0.2), "vnd_mn": ("numeric_vnd_mn", "VND_million", 0.0)}
_QTYPE = {"dso_days": "WORKING_CAPITAL_METRIC", "inventory_days": "WORKING_CAPITAL_METRIC",
          "dpo_days": "WORKING_CAPITAL_METRIC", "free_cash_flow_vnd_mn": "CASHFLOW_CALCULATION",
          "working_capital_vnd_mn": "LIQUIDITY_CALCULATION", "revenue_growth_pct": "GROWTH_CALCULATION"}


def make_variant_suite(indep: pd.DataFrame, master: pd.DataFrame, n: int = 300, seed: int = 2026):
    """Sinh bộ câu hỏi MỚI cùng schema questions_sample/answer_key_sample.
    Đáp án lấy từ compute_metrics_independent (đường tính thứ hai) -> không vòng lặp tự chấm mình.
    Gồm: tỷ số theo DN-năm, chỉ tiêu cần năm trước, xếp hạng cao/thấp nhất, top-3, lọc CFO âm, tra cứu trực tiếp.
    """
    rng = np.random.default_rng(seed)
    iw = indep.set_index(fm.KEY)
    mi = master.set_index(fm.KEY)
    comps, years = sorted(master["company_id"].unique()), sorted(master["fiscal_year"].unique())
    Q, K = [], []

    def add(qtype, text, cid, yr, mid_or_fields, exp, unit, tol, ans, diff="GEN"):
        fields = list(mid_or_fields)
        qid = f"G{len(Q)+1:04d}"
        Q.append({"question_id": qid, "question_type": qtype, "difficulty": diff, "question_text_vi": text,
                  "expected_answer_type": exp, "target_company_id": cid or "", "target_fiscal_year": yr,
                  "source_files": ";".join(sorted({fm.SRC[_F[f]] for f in fields if _F.get(f) in fm.SRC})),
                  "source_fields": ";".join(fields), "numeric_tolerance": tol})
        K.append({"question_id": qid, "question_type": qtype, "difficulty": diff, "reference_answer": ans,
                  "normalized_answer": ans, "answer_unit_or_type": unit, "numeric_tolerance": tol})

    metrics = [m for m in fm.METRICS]
    for _ in range(n):
        kind = rng.choice(["metric", "metric", "metric", "rank", "top3", "filter", "direct"])
        if kind == "metric":
            m = metrics[rng.integers(len(metrics))]
            yrs = years[1:] if m.needs_prev else years
            cid, y = comps[rng.integers(len(comps))], int(yrs[rng.integers(len(yrs))])
            exp, unit, tol = _UNIT[m.unit]
            v = float(iw.at[(cid, y), m.metric_id])
            if np.isnan(v):
                continue
            add(_QTYPE.get(m.metric_id, "RATIO_CALCULATION"), f"{m.name_vi} của {cid} năm {y} là bao nhiêu?",
                cid, y, [C[f] for f in m.fields], exp, unit, tol, v)
        elif kind in ("rank", "top3"):
            rankable = [x for x in metrics if x.unit != "vnd_mn" and x.metric_id != "revenue_growth_pct"]
            m = rankable[rng.integers(len(rankable))]
            yrs = years[1:] if m.needs_prev else years
            y = int(yrs[rng.integers(len(yrs))])
            hi = bool(rng.integers(2)) if kind == "rank" else True
            s = iw.xs(y, level="fiscal_year")[m.metric_id].dropna().sort_values(ascending=not hi)
            if kind == "rank":
                add("RANKING", f"Doanh nghiệp nào có {m.name_vi} {'cao nhất' if hi else 'thấp nhất'} trong năm {y}?",
                    None, y, [C[f] for f in m.fields], "company_id", "company_id", np.nan, s.index[0])
            else:
                add("RANKING", f"Liệt kê 3 doanh nghiệp có {m.name_vi} cao nhất năm {y} theo thứ tự giảm dần.",
                    None, y, [C[f] for f in m.fields], "ordered_company_id_list", "ordered_company_id_list", np.nan,
                    ";".join(s.index[:3]))
        elif kind == "filter":
            y = int(years[rng.integers(len(years))])
            col = str(rng.choice([C["cfo"], C["ni"], C["op"]]))
            s = mi.xs(y, level="fiscal_year")[col]
            add("LIST_FILTER", f"Những doanh nghiệp nào có {col} âm trong năm {y}?", None, y, [col],
                "company_id_list", "company_id_list", np.nan, ";".join(sorted(s[s < 0].index)))
        else:
            col = list(C.values())[rng.integers(len(C))]
            if col not in mi.columns:
                continue
            cid, y = comps[rng.integers(len(comps))], int(years[rng.integers(len(years))])
            add("DIRECT_VALUE", f"Giá trị {col} của {cid} năm {y} là bao nhiêu?", cid, y, [col],
                "numeric_vnd_mn", "VND_million", 0.0, float(mi.at[(cid, y), col]))
    return pd.DataFrame(Q), pd.DataFrame(K)


# ================================================================== TRỢ LÝ HỎI ĐÁP: CÂU CHỮ TỰ DO -> CÂU HỎI CÓ CẤU TRÚC
import unicodedata as _ud

_NOTES = {"capex_intensity_pct": "capex intensity|cuong do capex|cuong do dau tu",
          "debt_maturing_within_12m_pct": "no dao han trong vong 12 thang|no dao han trong 12 thang|dao han trong 12 thang|debt maturing",
          "average_borrowing_rate_pct": "lai suat vay binh quan|lai suat vay|borrowing rate",
          "average_customer_credit_terms_days": "thoi han tin dung|credit terms|tin dung khach hang",
          "inventory_policy_days_target": "muc tieu so ngay ton kho|chinh sach ton kho",
          "major_customer_concentration_pct": "tap trung khach hang|customer concentration",
          "export_revenue_pct": "doanh thu xuat khau|xuat khau|export"}
_METRIC_SYN = {
    "gross_margin_pct": "bien loi nhuan gop|gross margin|bien gop",
    "operating_margin_pct": "bien loi nhuan hoat dong|operating margin|bien hoat dong",
    "net_margin_pct": "bien loi nhuan rong|net margin|bien rong|ty suat loi nhuan rong",
    "current_ratio_x": "current ratio|thanh toan hien hanh",
    "quick_ratio_x": "quick ratio|thanh toan nhanh",
    "debt_to_assets_pct": "debt/assets|debt to assets|no vay/tong tai san|no vay / tong tai san|no tren tong tai san",
    "debt_to_equity_x": "debt/equity|debt to equity|d/e|no vay/von chu|no vay / von chu|no tren von chu",
    "roa_pct": "roa", "roe_pct": "roe",
    "cfo_to_net_income_x": "cfo/net income|cfo / net income|cfo/lnst|cfo / lnst|chat luong loi nhuan",
    "cfo_margin_pct": "cfo/doanh thu|cfo / doanh thu|cfo margin",
    "free_cash_flow_vnd_mn": "free cash flow|dong tien tu do|fcf",
    "dso_days": "dso|so ngay thu tien|ky thu tien",
    "inventory_days": "inventory days|so ngay ton kho",
    "dpo_days": "dpo|so ngay tra tien|so ngay phai tra",
    "interest_coverage_x": "interest coverage|kha nang tra lai|he so tra lai|icr",
    "working_capital_vnd_mn": "working capital|von luu dong rong|von luu dong",
    "revenue_growth_pct": "tang truong doanh thu|toc do tang doanh thu|revenue growth",
}
_FIELD_SYN = {   # tên ngắn trong finreport_metrics.C
    "rev": "doanh thu|revenue", "cogs": "gia von|cost of goods", "gp": "loi nhuan gop|gross profit",
    "op": "loi nhuan hoat dong|operating profit", "ni": "loi nhuan sau thue|lnst|net income",
    "int_exp": "chi phi lai vay|interest expense", "cash": "tien va tuong duong tien|cash and cash equivalents",
    "ar": "khoan phai thu|phai thu|accounts receivable", "inv": "hang ton kho|ton kho|inventory",
    "ap": "phai tra nguoi ban|accounts payable", "ta": "tong tai san|total assets",
    "tl": "tong no phai tra|total liabilities", "te": "von chu so huu|total equity",
    "cfo": "luu chuyen tien thuan tu hoat dong kinh doanh|cfo", "capex": "capex|capital expenditure",
    "end": "ending cash|tien cuoi ky", "tca": "tai san ngan han", "tcl": "no ngan han",
    "debt": "tong no vay|total debt",
}


def _strip(s: str) -> str:
    s = _ud.normalize("NFD", str(s).lower().replace("đ", "d"))
    return "".join(ch for ch in s if _ud.category(ch) != "Mn")


def _patterns():
    pats = []
    for mid, syn in _METRIC_SYN.items():
        names = syn.split("|") + [_strip(fm.METRIC_BY_ID[mid].name_vi)]
        pats += [(p, "metric", mid) for p in names]
    for k, syn in _FIELD_SYN.items():
        pats += [(p, "field", k) for p in syn.split("|")]
    for col, syn in _NOTES.items():
        pats += [(p, "note", col) for p in syn.split("|")]
    for k, col in C.items():                                         # tên cột gốc cũng nhận dạng được
        pats.append((col, "field", k))
    pats.sort(key=lambda x: -len(x[0]))
    return pats


_PATS = None


def _match(t: str):
    global _PATS
    _PATS = _PATS or _patterns()
    taken, hits = [], []
    for p, kind, target in _PATS:
        start = 0
        while (i := t.find(p, start)) >= 0:
            j = i + len(p)
            word_ok = (i == 0 or not t[i - 1].isalnum()) and (j == len(t) or not t[j].isalnum())
            if word_ok and not any(a < j and i < b for a, b in taken):
                taken.append((i, j)); hits.append((i, kind, target))
            start = j
    return [h[1:] for h in sorted(hits)]


def parse_question_vi(text: str, companies: pd.DataFrame | None = None) -> dict:
    """Chuyển câu hỏi tiếng Việt/Anh tự do thành dict cùng schema questions_sample (luật, không LLM).
    Trả thêm khóa 'parse_note' mô tả cách hiểu câu hỏi (để người dùng kiểm tra)."""
    t = _strip(text)
    cids = re.findall(r"\bc\d{3}\b", t)
    if companies is not None and not cids:
        generic = {"packaged", "foods", "food", "nutrition", "industries", "manufacturing", "consumer", "products", "jsc"}
        for r in companies.itertuples():
            core = " ".join(w for w in _strip(r.company_name).split() if w not in generic)
            if re.search(rf"\b{str(r.ticker_simulated).lower()}\b", t) or (core and re.search(rf"\b{re.escape(core)}\b", t)):
                cids.append(r.company_id.lower())
    cid = cids[0].upper() if cids else ""
    years = sorted(set(int(y) for y in re.findall(r"\b(20\d\d)\b", t)))
    hits = _match(t)
    metrics = [x for k, x in hits if k == "metric"]
    fields = [x for k, x in hits if k == "field"]
    notes = [x for k, x in hits if k == "note"]
    expand = lambda k: [C["std"], C["ltd"]] if k == "debt" else [C[k]]
    hint, qtype, src, exp = "", None, [], "numeric_ratio"

    def metric_src(mid):
        return [C[f] for f in fm.METRIC_BY_ID[mid].fields]

    neg = re.search(r"\bam\b|negative", t)
    if ("bang" in t or "khop" in t) and "hay khong" in t and len(fields) >= 2:
        qtype, src, exp = "RECONCILIATION", expand(fields[0]) + expand(fields[1]), "boolean"
    elif "hay khong" in t and re.search(r"nhanh hon|cao hon|lon hon", t):
        f2 = [f for f in fields] + (["rev"] if "revenue_growth_pct" in metrics else [])
        qtype, src, exp = "BOOLEAN_ANALYSIS", [C[f] for f in f2[:2]], "boolean"
    elif cid and re.search(r"mo ta|xu huong", t):
        qtype, src, exp = "TREND_ANALYSIS", [C["rev"], C["cfo"], C["ar"]], "short_text"
        years = years if len(years) >= 2 else [max(years[0] - 2, 2021), years[0]] if years else [2023, 2025]
    elif not cid and metrics and re.search(r"manh nhat|nhieu nhat", t) and len(years) >= 2:
        qtype, src, exp = "TREND_ANALYSIS", metric_src(metrics[0]), "company_id"
        hint = " giảm" if re.search(r"giam|suy", t) else " tăng"
    elif cid and metrics and re.search(r"diem phan tram|bao nhieu diem", t) and len(years) >= 2:
        qtype, src, exp = "CHANGE_CALCULATION", metric_src(metrics[0]), "numeric_percentage_point"
        hint = " giảm" if re.search(r"giam", t) else ""
    elif not cid and (metrics or fields) and re.search(r"cao nhat|thap nhat|lon nhat|nho nhat|xep hang|top", t):
        qtype = "RANKING"
        src = metric_src(metrics[0]) if metrics else expand(fields[0])
        exp = "ordered_company_id_list" if re.search(r"\d+\s*doanh nghiep|top\s*\d", t) else "company_id"
        hint = " thấp nhất" if re.search(r"thap nhat|nho nhat", t) else ""
        if (m := re.search(r"top\s*(\d+)", t)):
            hint += f" {m.group(1)} doanh nghiệp"
    elif not cid and (fields or metrics) and re.search(r"(nhung|cac) doanh nghiep nao|doanh nghiep nao co", t) and neg:
        qtype, src, exp, hint = "LIST_FILTER", expand(fields[0]) if fields else metric_src(metrics[0]), "company_id_list", " âm"
    elif cid and re.search(r"tang truong|toc do tang", t) and (fields or "revenue_growth_pct" in metrics) \
            and not [m for m in metrics if m != "revenue_growth_pct"]:
        qtype = "GROWTH_CALCULATION"
        src = expand(fields[0]) if fields and "revenue_growth_pct" not in metrics else [C["rev"]]
        exp = "numeric_percentage"
    elif cid and metrics:
        qtype, src = "RATIO_CALCULATION", metric_src(metrics[0])
        unit = fm.METRIC_BY_ID[metrics[0]].unit
        exp = {"pct": "numeric_percentage", "x": "numeric_ratio", "days": "numeric_days", "vnd_mn": "numeric_vnd_mn"}[unit]
    elif cid and notes:
        qtype, src, exp = "DIRECT_VALUE", [notes[0]], "numeric_percentage"
    elif cid and fields:
        qtype, src, exp = "DIRECT_VALUE", expand(fields[0])[:1], "numeric_vnd_mn"
    if qtype is None:
        return {"question_id": "ASK", "question_type": "UNKNOWN", "question_text_vi": text,
                "parse_note": "Chưa hiểu câu hỏi: cần mã DN (vd C003), năm và tên chỉ tiêu."}
    if qtype not in ("RANKING", "LIST_FILTER", "TREND_ANALYSIS") and not years:
        years = [2025]
    if qtype in ("RANKING", "LIST_FILTER") and years:
        years = [max(years)]
    file_of = lambda col: (fm.SRC.get(_F.get(col, ""), "financial_notes.csv"))
    q = {"question_id": "ASK", "question_type": qtype, "question_text_vi": text + hint,
         "expected_answer_type": exp, "target_company_id": cid,
         "target_fiscal_year": "-".join(str(y) for y in years) if len(years) > 1 else (str(years[0]) if years else ""),
         "source_files": ";".join(sorted({file_of(c) for c in src})), "source_fields": ";".join(src)}
    q["parse_note"] = (f"Hiểu là: {qtype} · DN={cid or 'tất cả'} · năm={q['target_fiscal_year'] or '-'} · "
                       f"trường={q['source_fields']}")
    return q


def answer_free_text(engine: "QAEngine", text: str, companies: pd.DataFrame | None = None) -> dict:
    q = parse_question_vi(text, companies)
    if q["question_type"] == "UNKNOWN":
        return {**q, "answer": "", "explanation": q["parse_note"], "confidence": 0.0}
    r = engine.answer(q)
    r["parse_note"] = q["parse_note"]
    r["question_type"] = q["question_type"]
    return r
