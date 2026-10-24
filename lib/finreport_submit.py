"""finreport_submit.py – Ghép, kiểm tra và xuất 2 file nộp BTC.

  * assemble_submission : metrics_wide (NB1) + predictions (NB2) -> đúng 31 cột / 60 dòng của template
  * assemble_qa         : câu trả lời QA -> đúng 8 cột / thứ tự question_id của template
  * validate_*          : kiểm tra schema, khóa, miền giá trị, quy ước 2021 TRƯỚC khi ghi file
  * regrade_qa_file     : đọc lại CHÍNH file sẽ nộp, tách đáp án từ chữ, chấm lại với answer key
  * manifest            : SHA-256 + kích thước file nộp (audit)
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

import finreport_metrics as fm

KEY = fm.KEY
SEVERITY = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
HEALTH = {"HEALTHY", "WATCH", "HIGH_RISK", "RECOVERING"}
PRED_COLS = ["risk_score", "predicted_primary_scenario", "predicted_severity", "predicted_overall_health",
             "alert_tags", "alert_reason", "evidence_fields", "priority_rank", "confidence"]
NEEDS_PREV = [m.metric_id for m in fm.METRICS if m.needs_prev]
DECIMALS = 6


# ================================================================== GHÉP
def assemble_submission(template: pd.DataFrame, metrics_wide: pd.DataFrame, predictions: pd.DataFrame,
                        model_name: str, ms_per_row: pd.Series | float) -> pd.DataFrame:
    """Giữ nguyên thứ tự dòng & cột của template; chỉ điền giá trị."""
    out = template[KEY].copy()
    out["fiscal_year"] = out["fiscal_year"].astype(int)
    m = metrics_wide.copy(); m["fiscal_year"] = m["fiscal_year"].astype(int)
    p = predictions.copy(); p["fiscal_year"] = p["fiscal_year"].astype(int)
    out = out.merge(m, on=KEY, how="left", validate="one_to_one")
    out = out.merge(p[KEY + PRED_COLS], on=KEY, how="left", validate="one_to_one")
    out["model_name"] = model_name
    if isinstance(ms_per_row, pd.Series):
        out["processing_time_ms"] = out.set_index(KEY).index.map(ms_per_row).values
    else:
        out["processing_time_ms"] = float(ms_per_row)
    num = [c for c in out.columns if c in fm.METRIC_IDS or c in ("risk_score", "confidence", "processing_time_ms")]
    out[num] = out[num].astype(float).round(DECIMALS)
    out["priority_rank"] = out["priority_rank"].astype("Int64")
    out["alert_tags"] = out["alert_tags"].fillna("")
    return out[template.columns.tolist()]


def assemble_qa(template: pd.DataFrame, answers: pd.DataFrame) -> pd.DataFrame:
    a = answers.set_index("question_id")
    out = template[["question_id"]].copy()
    for col in template.columns[1:]:
        out[col] = out["question_id"].map(a[col]) if col in a.columns else np.nan
    return out[template.columns.tolist()]


# ================================================================== KIỂM TRA
def validate_submission(sub: pd.DataFrame, template: pd.DataFrame, metrics_wide: pd.DataFrame, log) -> None:
    G = "V1_submission"
    cols_ok = list(sub.columns) == list(template.columns)
    missing, extra = sorted(set(template.columns) - set(sub.columns)), sorted(set(sub.columns) - set(template.columns))
    log.check(G, "columns", "submission_output", cols_ok,
              f"{sub.shape[1]} cột, đúng tên & thứ tự template" if cols_ok
              else f"thiếu={missing} thừa={extra}" + ("" if missing or extra else " (sai thứ tự)"))
    if missing:
        return                                   # thiếu cột -> các kiểm tra sau không có nghĩa
    same_keys = sub[KEY].astype(str).values.tolist() == template[KEY].astype(str).values.tolist()
    log.check(G, "rows_keys", "submission_output", same_keys,
              f"{len(sub)} dòng, đúng thứ tự company_id + fiscal_year của template" if same_keys else "khóa/thứ tự lệch template")
    log.check(G, "no_dup_keys", "submission_output", not sub.duplicated(KEY).any(), "không trùng khóa")
    # 2021: chỉ tiêu cần năm trước phải trống; năm khác phải có
    y21 = sub["fiscal_year"].astype(int) == 2021
    blank_ok = sub.loc[y21, NEEDS_PREV].isna().all().all()
    log.check(G, "2021_blank", "submission_output", blank_ok,
              f"2021: {len(NEEDS_PREV)} chỉ tiêu cần năm trước để trống (không tự sinh 2020)")
    filled = sub.loc[~y21, fm.METRIC_IDS].notna().all().all() and sub.loc[y21, [c for c in fm.METRIC_IDS if c not in NEEDS_PREV]].notna().all().all()
    log.check(G, "metrics_filled", "submission_output", filled, "mọi ô chỉ tiêu còn lại đều có giá trị")
    # đúng bằng giá trị NB1 (không bị lệch khi ghép)
    w = metrics_wide.set_index(KEY)
    s = sub.assign(fiscal_year=sub["fiscal_year"].astype(int)).set_index(KEY)
    diff = (s[fm.METRIC_IDS] - w.loc[s.index, fm.METRIC_IDS]).abs().max().max()
    log.check(G, "metrics_match_nb1", "submission_output", bool(diff < 1e-5),
              f"khớp bảng chỉ tiêu NB1, lệch lớn nhất {diff:.1e} (do làm tròn {DECIMALS} chữ số)")
    # miền giá trị
    for col, lo, hi in [("risk_score", 0, 1), ("confidence", 0, 1)]:
        ok = sub[col].between(lo, hi).all()
        log.check(G, f"range:{col}", "submission_output", bool(ok), f"{col} ∈ [{lo}, {hi}]: min {sub[col].min():.3f}, max {sub[col].max():.3f}")
    for col, allowed in [("predicted_severity", SEVERITY), ("predicted_overall_health", HEALTH)]:
        bad = sorted(set(sub[col].dropna()) - allowed)
        log.check(G, f"enum:{col}", "submission_output", not bad and sub[col].notna().all(),
                  f"chỉ dùng {sorted(allowed)}" if not bad else f"giá trị lạ: {bad}")
    pr = sub["priority_rank"]
    log.check(G, "priority_rank", "submission_output", bool(pr.notna().all() and (pr >= 1).all() and pr.is_unique),
              f"số nguyên dương, duy nhất, {int(pr.min())}…{int(pr.max())}")
    for col in ["predicted_primary_scenario", "alert_reason", "evidence_fields", "model_name"]:
        log.check(G, f"not_empty:{col}", "submission_output", bool((sub[col].astype(str).str.len() > 0).all()), "không rỗng")
    # nhất quán nội bộ
    pos = sub["predicted_overall_health"] == "HEALTHY"
    log.check(G, "consistency:healthy_low", "submission_output", bool((sub.loc[pos, "predicted_severity"] == "LOW").all()),
              "HEALTHY ⇒ severity LOW")
    crit = sub["predicted_severity"] == "CRITICAL"
    log.check(G, "consistency:critical_highrisk", "submission_output",
              bool((sub.loc[crit, "predicted_overall_health"] == "HIGH_RISK").all()), "CRITICAL ⇒ HIGH_RISK")
    ev_ok = sub["evidence_fields"].str.contains(r"\.csv:C\d{3}:\d{4}", regex=True).all()
    log.check(G, "evidence_format", "submission_output", bool(ev_ok), "evidence dạng file.csv:Cxxx:năm:trường")


def validate_qa(qa: pd.DataFrame, template: pd.DataFrame, log) -> None:
    G = "V2_qa"
    cols_ok = list(qa.columns) == list(template.columns)
    log.check(G, "columns", "qa_submission", cols_ok, f"{qa.shape[1]} cột, đúng template" if cols_ok
              else f"thiếu={sorted(set(template.columns) - set(qa.columns))}")
    if set(template.columns) - set(qa.columns):
        return
    log.check(G, "question_ids", "qa_submission", qa["question_id"].tolist() == template["question_id"].tolist(),
              f"{len(qa)} question_id, đúng thứ tự template")
    for col in ["answer", "evidence_source_files", "evidence_source_fields", "explanation", "model_name"]:
        empty = int((qa[col].astype(str).str.strip().isin(["", "nan"])).sum())
        log.check(G, f"not_empty:{col}", "qa_submission", empty == 0, "đủ cả câu" if empty == 0 else f"{empty} câu rỗng",
                  warn_only=(col == "answer"))
    log.check(G, "range:confidence", "qa_submission", bool(qa["confidence"].between(0, 1).all()), "confidence ∈ [0, 1]")
    files_ok = qa["evidence_source_files"].astype(str).str.split(";").apply(
        lambda xs: all(x.strip().endswith(".csv") for x in xs if x.strip())).all()
    log.check(G, "evidence_files", "qa_submission", bool(files_ok), "nguồn là tên file .csv của Data Pack")


# ================================================================== CHẤM LẠI CHÍNH FILE NỘP
def _parse_answer(text: str, explanation: str, typ: str):
    t = str(text).strip()
    if typ in ("VND_million", "percent", "x", "percentage_point", "days"):
        m = re.search(r"-?\d+(?:\.\d+)?", t.replace(",", ""))
        return float(m.group()) if m else np.nan
    if typ == "company_id":
        m = re.search(r"C\d{3}", t)
        return m.group() if m else ""
    if typ in ("ordered_company_id_list", "company_id_list"):
        return ";".join(re.findall(r"C\d{3}", t))
    if typ == "boolean":
        return {"có": True, "co": True, "true": True, "không": False, "khong": False, "false": False}.get(t.lower(), None)
    if typ == "short_text":
        m = re.search(r"Tag:\s*([A-Z_;]+)", str(explanation))
        return m.group(1) if m else ""
    return t


def regrade_qa_file(qa_file: pd.DataFrame, answer_key: pd.DataFrame) -> pd.DataFrame:
    """Không dùng giá trị trong bộ nhớ: tách đáp án từ cột 'answer' của file nộp rồi chấm lại."""
    import finreport_qa as qa
    k = answer_key.set_index("question_id")
    parsed = qa_file[["question_id", "answer", "confidence"]].copy()
    parsed["normalized"] = [_parse_answer(a, e, k.at[q, "answer_unit_or_type"])
                            for q, a, e in zip(qa_file["question_id"], qa_file["answer"], qa_file["explanation"])]
    return qa.grade(parsed, answer_key)


# ================================================================== THỜI GIAN XỬ LÝ / MANIFEST
def timing_per_row(master, run_pipeline, repeats: int = 3) -> tuple[pd.Series, float]:
    """Đo thời gian chạy lại toàn pipeline (chỉ tiêu + tín hiệu + giải thích) rồi chia đều cho 60 dòng.
    Lý do chia đều: tín hiệu dùng benchmark cả ngành, không tách riêng từng dòng được."""
    import time
    ts = []
    for _ in range(repeats):
        t0 = time.perf_counter(); run_pipeline(); ts.append((time.perf_counter() - t0) * 1000)
    total = float(np.median(ts))
    per = total / len(master)
    idx = pd.MultiIndex.from_frame(master[KEY].assign(fiscal_year=master["fiscal_year"].astype(int)))
    return pd.Series(per, index=idx), total


def manifest(paths: dict, sha256_of) -> pd.DataFrame:
    rows = []
    for name, p in paths.items():
        d = pd.read_csv(p, encoding="utf-8-sig")
        rows.append({"file": name, "rows": len(d), "columns": d.shape[1], "bytes": p.stat().st_size, "sha256": sha256_of(p)})
    return pd.DataFrame(rows)
