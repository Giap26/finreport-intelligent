"""finreport_assistant.py – Trợ lý hỏi đáp tài chính bằng tiếng Việt tự do (không dùng LLM).

Câu hỏi chữ  ──► parse_question() ──► câu hỏi có cấu trúc (loại câu, DN, năm, trường nguồn)
             ──► QAEngine.answer()  ──► đáp án + giải thích + bằng chứng (cùng engine với file nộp)

Bộ tách dùng từ điển thuật ngữ (Việt + Anh, có/không dấu) và luật nhận dạng loại câu.
Không nhận ra được -> trả lời "chưa hiểu câu hỏi" kèm gợi ý, không đoán bừa.
"""
from __future__ import annotations

import re
import unicodedata

import finreport_metrics as fm

C = fm.C


def norm(s: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt, gộp khoảng trắng – để so khớp từ khóa bền vững."""
    s = unicodedata.normalize("NFD", str(s).lower()).replace("đ", "d")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- từ điển chỉ tiêu (dài trước, ngắn sau)
METRIC_LEXICON = [
    (["bien loi nhuan gop", "gross margin", "bien gop"], "gross_margin_pct"),
    (["bien loi nhuan hoat dong", "operating margin", "bien hoat dong"], "operating_margin_pct"),
    (["bien loi nhuan rong", "net margin", "bien rong"], "net_margin_pct"),
    (["cfo/net income", "cfo/lnst", "cfo / net income", "cfo / lnst", "cfo tren loi nhuan"], "cfo_to_net_income_x"),
    (["cfo/doanh thu", "cfo margin", "cfo / doanh thu"], "cfo_margin_pct"),
    (["current ratio", "thanh toan hien hanh"], "current_ratio_x"),
    (["quick ratio", "thanh toan nhanh"], "quick_ratio_x"),
    (["debt/assets", "debt to assets", "no vay/tong tai san", "no vay / tong tai san"], "debt_to_assets_pct"),
    (["debt/equity", "debt to equity", "no vay/von chu", "no vay / von chu", "d/e"], "debt_to_equity_x"),
    (["interest coverage", "kha nang tra lai", "he so tra lai"], "interest_coverage_x"),
    (["free cash flow", "dong tien tu do", "fcf"], "free_cash_flow_vnd_mn"),
    (["inventory days", "so ngay ton kho", "vong quay ton kho"], "inventory_days"),
    (["dso", "so ngay thu tien", "ky thu tien"], "dso_days"),
    (["dpo", "so ngay tra tien", "ky tra tien"], "dpo_days"),
    (["working capital", "von luu dong rong", "von luu dong"], "working_capital_vnd_mn"),
    (["roa"], "roa_pct"),
    (["roe"], "roe_pct"),
]
# ---------------------------------------------------------------- từ điển trường gốc
FIELD_LEXICON = [
    (["capex intensity", "cuong do capex"], ["capex_intensity_pct"]),
    (["dao han trong vong 12 thang", "dao han trong 12 thang", "den han trong 12 thang", "debt maturing"],
     ["debt_maturing_within_12m_pct"]),
    (["ending cash", "tien cuoi ky"], [C["end"]]),
    (["cash and cash equivalents", "tien va tuong duong tien"], [C["cash"]]),
    (["luu chuyen tien thuan tu hoat dong kinh doanh", "cfo"], [C["cfo"]]),
    (["tong no vay", "no vay"], [C["std"], C["ltd"]]),
    (["tong no phai tra", "no phai tra"], [C["tl"]]),
    (["tong tai san"], [C["ta"]]),
    (["von chu so huu"], [C["te"]]),
    (["loi nhuan sau thue", "net income", "lnst"], [C["ni"]]),
    (["loi nhuan gop", "gross profit"], [C["gp"]]),
    (["loi nhuan hoat dong", "operating profit"], [C["op"]]),
    (["chi phi lai vay", "lai vay"], [C["int_exp"]]),
    (["gia von", "cogs"], [C["cogs"]]),
    (["khoan phai thu", "phai thu", "accounts receivable"], [C["ar"]]),
    (["ton kho", "inventory"], [C["inv"]]),
    (["capex", "chi dau tu"], [C["capex"]]),
    (["doanh thu", "revenue"], [C["rev"]]),
]
NOTE_FIELDS = {"capex_intensity_pct", "debt_maturing_within_12m_pct", "average_borrowing_rate_pct",
               "average_customer_credit_terms_days", "inventory_policy_days_target", "export_revenue_pct",
               "major_customer_concentration_pct"}
PCT_FIELDS = {"capex_intensity_pct", "debt_maturing_within_12m_pct", "average_borrowing_rate_pct",
              "export_revenue_pct", "major_customer_concentration_pct"}
EXP_BY_UNIT = {"pct": "numeric_percentage", "x": "numeric_ratio", "days": "numeric_days", "vnd_mn": "numeric_vnd_mn"}
QTYPE_BY_METRIC = {"dso_days": "WORKING_CAPITAL_METRIC", "inventory_days": "WORKING_CAPITAL_METRIC",
                   "dpo_days": "WORKING_CAPITAL_METRIC", "free_cash_flow_vnd_mn": "CASHFLOW_CALCULATION",
                   "working_capital_vnd_mn": "LIQUIDITY_CALCULATION"}


def _find_metric(t: str):
    best = None
    for keys, mid in METRIC_LEXICON:
        for k in keys:
            m = re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t)
            if m and (best is None or len(k) > best[2]):
                best = (mid, m.start(), len(k))
    return best[0] if best else None


def _find_fields(t: str) -> list[list[str]]:
    """Tất cả trường gốc được nhắc tới, theo thứ tự xuất hiện; cụm dài thắng cụm ngắn chồng lấn."""
    hits = []
    for keys, cols in FIELD_LEXICON:
        for k in keys:
            for m in re.finditer(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t):
                hits.append((m.start(), m.end(), cols))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out, last_end = [], -1
    for s, e, cols in hits:
        if s >= last_end:
            out.append(cols); last_end = e
    return out


def _src_files(fields: list[str]) -> str:
    rev = {v: k for k, v in C.items()}
    files = []
    for f in fields:
        files.append("financial_notes.csv" if f in NOTE_FIELDS else fm.SRC.get(rev.get(f, ""), ""))
    return ";".join(dict.fromkeys(x for x in files if x))


def parse_question(text: str) -> dict:
    """Trả về câu hỏi có cấu trúc giống questions_sample.csv (thêm 'parse_note' giải thích cách hiểu)."""
    t = norm(text)
    cid = (m.group(0).upper() if (m := re.search(r"\bc\d{3}\b", t)) else "")
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", t)]
    nam = [int(y) for y in re.findall(r"nam (20\d{2})", t)]
    span = re.search(r"(?:tu|giai doan) (20\d{2}) ?(?:den|-|–) ?(20\d{2})", t) or re.search(r"(20\d{2}) ?- ?(20\d{2})", t)
    metric = _find_metric(t)
    fields_hit = _find_fields(t)
    flat = [f for cols in fields_hit for f in cols]
    q = {"question_text_vi": text, "question_type": "", "target_company_id": cid, "target_fiscal_year": "",
         "source_fields": "", "source_files": "", "expected_answer_type": "", "parse_note": ""}

    def done(qtype, fields, year, exp, note):
        q.update(question_type=qtype, source_fields=";".join(fields), source_files=_src_files(fields),
                 target_fiscal_year=str(year), expected_answer_type=exp, parse_note=note)
        return q

    def metric_fields(mid):
        return [C[k] for k in fm.METRIC_BY_ID[mid].fields]

    y_target = (nam[0] if nam else (years[-1] if years else ""))
    asks_company = bool(re.search(r"doanh nghiep nao|cong ty nao|\bdn nao", t))
    top_n = re.search(r"(\d+) doanh nghiep", t)

    # 1. Đối chiếu giữa 2 báo cáo
    if (re.search(r"co bang|khop|doi chieu", t)) and len(flat) >= 2 and cid:
        return done("RECONCILIATION", flat[:2], y_target, "boolean", "đối chiếu 2 trường")
    # 2. Mô tả xu hướng của 1 DN
    if re.search(r"mo ta|xu huong", t) and cid:
        f = flat or [C["rev"], C["cfo"]]
        if C["ar"] not in f:
            f = f + [C["ar"]]
        yr = f"{span.group(1)}-{span.group(2)}" if span else (f"{years[0]}-{years[-1]}" if len(years) > 1 else y_target)
        return done("TREND_ANALYSIS", f, yr, "short_text", "mô tả xu hướng nhiều năm")
    # 3. DN nào thay đổi mạnh nhất giữa 2 năm
    if asks_company and metric and span and re.search(r"manh nhat|nhieu nhat", t):
        return done("TREND_ANALYSIS", metric_fields(metric), f"{span.group(1)}-{span.group(2)}", "company_id",
                    "DN thay đổi mạnh nhất")
    # 4. Lọc danh sách
    if re.search(r"nhung doanh nghiep nao|cac doanh nghiep nao|doanh nghiep nao co .* (am|duong)\b", t) and flat \
            and re.search(r"\b(am|duong)\b", t):
        return done("LIST_FILTER", flat[:1], y_target, "company_id_list", "lọc theo dấu")
    # 5. Xếp hạng
    if (asks_company or top_n) and re.search(r"cao nhat|thap nhat|lon nhat|nho nhat", t) and metric:
        exp = "ordered_company_id_list" if top_n else "company_id"
        return done("RANKING", metric_fields(metric), y_target, exp, f"xếp hạng {metric}")
    # 6. So sánh tốc độ tăng (Có/Không)
    if re.search(r"hay khong", t) and re.search(r"nhanh hon|cao hon|lon hon", t) and len(fields_hit) >= 2:
        f = [fields_hit[0][0], fields_hit[1][0]]
        yr = f"{span.group(1)}-{span.group(2)}" if span else y_target
        return done("BOOLEAN_ANALYSIS", f, yr, "boolean", "so sánh tốc độ tăng 2 đại lượng")
    # 7. Thay đổi điểm phần trăm giữa 2 năm
    if metric and re.search(r"diem phan tram|bao nhieu diem", t) and len(years) >= 2:
        y1, y2 = (int(span.group(1)), int(span.group(2))) if span else (min(years), max(years))
        return done("CHANGE_CALCULATION", metric_fields(metric), f"{y1};{y2}", "numeric_percentage_point", "thay đổi giữa 2 năm")
    # 8. Tăng trưởng
    if re.search(r"toc do tang|tang truong|tang bao nhieu phan tram", t) and flat and not metric:
        f = fields_hit[0]
        return done("GROWTH_CALCULATION", f, y_target, "numeric_percentage", "tăng trưởng so với năm trước")
    # 9. Chỉ tiêu tài chính
    if metric and cid:
        meta = fm.METRIC_BY_ID[metric]
        if metric == "revenue_growth_pct":
            return done("GROWTH_CALCULATION", [C["rev"]], y_target, "numeric_percentage", "tăng trưởng doanh thu")
        return done(QTYPE_BY_METRIC.get(metric, "RATIO_CALCULATION"), metric_fields(metric), y_target,
                    EXP_BY_UNIT[meta.unit], f"chỉ tiêu {metric}")
    # 10. Tra cứu trực tiếp
    if flat and cid:
        f = fields_hit[-1] if len(fields_hit[-1]) == 1 else fields_hit[0]
        exp = "numeric_percentage" if f[0] in PCT_FIELDS else "numeric_vnd_mn"
        if len(f) > 1:          # vd "tổng nợ vay" = 2 trường -> chưa hỗ trợ tra cứu tổng trực tiếp
            return done("", f, y_target, "", "chưa hỗ trợ tra cứu tổng nhiều trường")
        return done("DIRECT_VALUE", f, y_target, exp, "tra cứu trực tiếp")
    q["parse_note"] = "chưa nhận ra loại câu hỏi"
    return q


EXAMPLES = [
    "Biên lợi nhuận gộp của C006 năm 2025 là bao nhiêu?",
    "DSO của C003 năm 2024 là bao nhiêu ngày?",
    "Doanh nghiệp nào có Debt/Assets cao nhất năm 2025?",
    "Liệt kê 3 doanh nghiệp có Current Ratio cao nhất năm 2025.",
    "Những doanh nghiệp nào có CFO âm trong năm 2024?",
    "Tốc độ tăng doanh thu của C002 năm 2025 so với 2024?",
    "Biên lợi nhuận gộp của C012 đã giảm bao nhiêu điểm phần trăm từ 2021 đến 2025?",
    "Mô tả xu hướng doanh thu và CFO của C008 giai đoạn 2022-2025.",
]


def ask(engine, text: str) -> dict:
    q = parse_question(text)
    if not q["question_type"] or not q["target_fiscal_year"]:
        return {**q, "answer": "", "explanation": "Chưa hiểu câu hỏi. Hãy nêu rõ mã DN (vd C003), năm và chỉ tiêu – xem các câu mẫu.",
                "confidence": 0.0, "ok": False}
    r = engine.answer({**q, "question_id": "ASK"})
    return {**q, **r, "ok": r.get("answer_flags") != "UNSUPPORTED"}


def evaluate_text_only(engine, questions, answer_key):
    """Chỉ đưa cột question_text_vi vào bộ tách (bỏ mọi cột cấu trúc của BTC) rồi chấm như bình thường."""
    import pandas as pd
    import finreport_qa as qa
    rows, parsed = [], []
    for r in questions.itertuples():
        q = parse_question(r.question_text_vi)
        parsed.append({"question_id": r.question_id, "text": r.question_text_vi, "parsed_type": q["question_type"],
                       "official_type": r.question_type, "parsed_fields": q["source_fields"],
                       "official_fields": r.source_fields, "parsed_year": q["target_fiscal_year"],
                       "official_year": r.target_fiscal_year, "note": q["parse_note"]})
        rows.append(engine.answer({**q, "question_id": r.question_id}))
    ans = pd.DataFrame(rows)
    g = qa.grade(ans, answer_key)
    p = pd.DataFrame(parsed)
    p["type_match"] = p["parsed_type"] == p["official_type"]
    return g, p


# ---------------------------------------------------------------- bộ câu diễn đạt lại (kiểm tra độ bền ngoài 30 câu mẫu)
PARAPHRASE_SUITE = [
    # (câu hỏi, loại mong đợi, DN, năm, chỉ tiêu/trường mong đợi)
    ("Gross margin cua C010 nam 2024 bang bao nhieu?", "RATIO_CALCULATION", "C010", "2024", "gross_margin_pct"),
    ("Cho tôi biết hệ số thanh toán nhanh của C004 năm 2023", "RATIO_CALCULATION", "C004", "2023", "quick_ratio_x"),
    ("C011 năm 2025 có khả năng trả lãi bao nhiêu lần?", "RATIO_CALCULATION", "C011", "2025", "interest_coverage_x"),
    ("Số ngày tồn kho năm 2025 của C007?", "WORKING_CAPITAL_METRIC", "C007", "2025", "inventory_days"),
    ("dong tien tu do C012 nam 2025", "CASHFLOW_CALCULATION", "C012", "2025", "free_cash_flow_vnd_mn"),
    ("Vốn lưu động ròng của C001 năm 2022 là bao nhiêu triệu đồng?", "LIQUIDITY_CALCULATION", "C001", "2022", "working_capital_vnd_mn"),
    ("ROE của C008 năm 2023?", "RATIO_CALCULATION", "C008", "2023", "roe_pct"),
    ("Debt to equity C005 năm 2024", "RATIO_CALCULATION", "C005", "2024", "debt_to_equity_x"),
    ("Biên lợi nhuận ròng của C009 năm 2022 là bao nhiêu phần trăm?", "RATIO_CALCULATION", "C009", "2022", "net_margin_pct"),
    ("Doanh thu C003 năm 2021 bao nhiêu?", "DIRECT_VALUE", "C003", "2021", "revenue_vnd_mn"),
    ("Lợi nhuận sau thuế của C012 năm 2025?", "DIRECT_VALUE", "C012", "2025", "net_income_vnd_mn"),
    ("Tồn kho của C004 năm 2025 là bao nhiêu?", "DIRECT_VALUE", "C004", "2025", "inventory_vnd_mn"),
    ("Công ty nào có ROA thấp nhất năm 2023?", "RANKING", "", "2023", "roa_pct"),
    ("Doanh nghiệp nào có số ngày tồn kho lớn nhất năm 2024?", "RANKING", "", "2024", "inventory_days"),
    ("Liệt kê 5 doanh nghiệp có biên lợi nhuận hoạt động cao nhất năm 2022", "RANKING", "", "2022", "operating_margin_pct"),
    ("Các doanh nghiệp nào có lợi nhuận sau thuế âm năm 2022?", "LIST_FILTER", "", "2022", "net_income_vnd_mn"),
    ("Tăng trưởng doanh thu của C010 năm 2023 so với 2022 là bao nhiêu?", "GROWTH_CALCULATION", "C010", "2023", "revenue_vnd_mn"),
    ("Tốc độ tăng tổng nợ vay của C012 năm 2024 so với năm 2023?", "GROWTH_CALCULATION", "C012", "2024", "short_term_debt_vnd_mn"),
    ("Biên lợi nhuận gộp của C011 đã tăng bao nhiêu điểm phần trăm từ 2021 đến 2025?", "CHANGE_CALCULATION", "C011", "2021;2025", "gross_margin_pct"),
    ("Từ 2021 đến 2025 doanh nghiệp nào có biên lợi nhuận gộp tăng mạnh nhất?", "TREND_ANALYSIS", "", "2021-2025", "gross_margin_pct"),
    ("Với C008 giai đoạn 2022-2025, phải thu có tăng nhanh hơn doanh thu hay không?", "BOOLEAN_ANALYSIS", "C008", "2022-2025", "accounts_receivable_vnd_mn"),
    ("Năm 2025, tồn kho của C007 tăng nhanh hơn doanh thu hay không?", "BOOLEAN_ANALYSIS", "C007", "2025", "inventory_vnd_mn"),
    ("Mô tả xu hướng doanh thu và CFO của C003 từ 2022 đến 2025", "TREND_ANALYSIS", "C003", "2022-2025", "revenue_vnd_mn"),
    ("Ending cash của C001 năm 2023 có bằng tiền và tương đương tiền trên bảng cân đối không?", "RECONCILIATION", "C001", "2023", "ending_cash_vnd_mn"),
    ("Tỷ lệ nợ đáo hạn trong 12 tháng của C012 năm 2023?", "DIRECT_VALUE", "C012", "2023", "debt_maturing_within_12m_pct"),
]


def evaluate_paraphrases(engine=None):
    """Đo bộ tách trên câu diễn đạt khác 30 câu mẫu: đúng loại câu, DN, năm, chỉ tiêu; và engine trả lời được."""
    import pandas as pd
    rows = []
    for text, typ, cid, yr, key in PARAPHRASE_SUITE:
        q = parse_question(text)
        ok_type = q["question_type"] == typ
        ok_cid = q["target_company_id"] == cid
        ok_year = q["target_fiscal_year"] == yr
        if key in fm.METRIC_BY_ID:          # chỉ tiêu -> so tập trường nguồn của chỉ tiêu đó
            ok_key = set(q["source_fields"].split(";")) == {C[k] for k in fm.METRIC_BY_ID[key].fields}
        else:
            ok_key = key in q["source_fields"].split(";")
        answered = None
        if engine is not None and q["question_type"]:
            r = engine.answer({**q, "question_id": "P"})
            answered = r.get("answer_flags") != "UNSUPPORTED" and str(r.get("answer", "")) != ""
        rows.append({"question": text, "expected_type": typ, "parsed_type": q["question_type"],
                     "type_ok": ok_type, "company_ok": ok_cid, "year_ok": ok_year, "metric_ok": ok_key,
                     "all_ok": ok_type and ok_cid and ok_year and ok_key, "answered": answered,
                     "parsed_fields": q["source_fields"], "parsed_year": q["target_fiscal_year"]})
    return pd.DataFrame(rows)
