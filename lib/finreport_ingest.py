"""finreport_ingest.py – Bước 0: tiếp nhận & kiểm tra toàn vẹn Data Pack (G1–G8) + hợp nhất master_panel.

Cùng logic với notebook NB0_Ingest, đóng gói thành module để run_pipeline.py và dashboard dùng lại.
Mỗi hàm nhận data_dir làm tham số -> chạy được trên bản sao (kiểm thử âm).
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pandas as pd

from finreport_common import (CORE_FILES, KEY, LABEL_FILES, METADATA_FILES, TEMPLATE_FILES, YEARS,
                              CheckLog, locate_pack_file, sha256_of)

GROUP_DESC = {"G1_inventory": "Kiểm kê file theo cấu trúc README",
              "G2_manifest": "SHA-256, dung lượng, encoding, số dòng/cột, kỳ dữ liệu so với manifest",
              "G3_schema": "Tên/thứ tự cột, kiểu dữ liệu, không rỗng theo data_dictionary",
              "G4_keys": "Khóa chính, đủ lưới 12×5, khóa ngoại, không có năm 2020",
              "G5_units": "Đơn vị VND_million, tiền tệ, năm tài chính, cùng phân ngành, cờ giả lập",
              "G6_overlap": "Trường trùng giữa 2 báo cáo phải bằng nhau",
              "G7_template": "Khóa template đầu ra khớp dữ liệu/câu hỏi",
              "G8_join": "Kết quả hợp nhất master_panel"}


def rd(data_dir, rel):
    path, _ = locate_pack_file(rel, data_dir)          # chịu được layout khác README (03_sample/, hậu tố _Case3)
    return pd.read_csv(path, encoding="utf-8-sig")

# ---------- G1. Kiểm kê file
def g1_inventory(log, data_dir):
    present = {}
    for files_, warn in [(CORE_FILES, False), (METADATA_FILES, False), (LABEL_FILES, True), (TEMPLATE_FILES, False)]:
        for name, rel in files_.items():
            path, how = locate_pack_file(rel, data_dir)
            ok = path is not None
            present[name] = ok
            if ok and how != "standard":                 # tìm thấy nhưng không đúng vị trí README -> WARN có ghi rõ
                log.check("G1_inventory", f"exists:{name}", rel, False, f"có, nhưng ở vị trí khác README ({how})", warn_only=True)
            else:
                log.check("G1_inventory", f"exists:{name}", rel, ok,
                          "có" if ok else ("THIẾU – các bước dùng file này sẽ hoãn" if warn else "THIẾU – file bắt buộc"),
                          warn_only=warn)
    return present

# ---------- G2. Đối chiếu manifest
def g2_manifest(log, data_dir):
    man = rd(data_dir, METADATA_FILES["dataset_manifest"])
    for _, r in man.iterrows():
        rel, fname = r["relative_path"], r["file_name"]
        p, _how = locate_pack_file(rel, data_dir)
        if p is None:
            log.check("G2_manifest", f"present:{fname}", rel, False,
                      "Có trong manifest nhưng chưa được cung cấp", warn_only=rel.startswith("03_labels_sample"))
            continue
        raw = p.read_bytes()
        sha_ok = sha256_of(p) == r["sha256"]
        log.check("G2_manifest", f"sha256:{fname}", rel, sha_ok, f"sha256 {'khớp' if sha_ok else 'KHÔNG khớp'} manifest")
        log.check("G2_manifest", f"size:{fname}", rel, len(raw) == int(r["file_size_bytes"]),
                  f"{len(raw)} / {int(r['file_size_bytes'])} bytes")
        enc_ok = raw.startswith(b"\xef\xbb\xbf") if str(r["encoding"]).upper() == "UTF-8-SIG" else True
        log.check("G2_manifest", f"encoding:{fname}", rel, enc_ok, f"kỳ vọng {r['encoding']}")
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=r["delimiter"]))
        n_rows, n_cols = len(rows) - 1, len(rows[0])
        log.check("G2_manifest", f"rows:{fname}", rel, n_rows == int(r["row_count"]), f"{n_rows} / {int(r['row_count'])} dòng")
        log.check("G2_manifest", f"cols:{fname}", rel, n_cols == int(r["column_count"]), f"{n_cols} / {int(r['column_count'])} cột")
        if pd.notna(r["period_field"]):
            df = rd(data_dir, rel)
            lo, hi = df[r["period_field"]].min(), df[r["period_field"]].max()
            log.check("G2_manifest", f"period:{fname}", rel, (lo, hi) == (int(r["period_min"]), int(r["period_max"])),
                      f"{lo}–{hi} / kỳ vọng {int(r['period_min'])}–{int(r['period_max'])}")
    listed = set(man["relative_path"])
    for name, rel in {**LABEL_FILES, **TEMPLATE_FILES}.items():
        p, _how = locate_pack_file(rel, data_dir)
        if p is not None and rel not in listed:
            log.check("G2_manifest", f"unlisted:{name}", rel, True,
                      f"Không có trong manifest; sha256={sha256_of(p)[:16]}… (ghi nhận để audit)")

# ---------- G3. Schema theo data_dictionary
def g3_schema(log, data_dir, tables):
    dd = rd(data_dir, METADATA_FILES["data_dictionary"])
    for fname, spec in dd.groupby("file_name", sort=False):
        name = fname.replace(".csv", "")
        if name not in tables:
            continue
        df, n_err = tables[name], 0
        expected = list(spec.sort_values("field_order")["field_name"])
        if list(df.columns) != expected:
            n_err += 1
            log.check("G3_schema", f"columns:{name}", fname, False,
                      f"thiếu={sorted(set(expected)-set(df.columns))} thừa={sorted(set(df.columns)-set(expected))}")
        for _, f in spec.iterrows():
            col = f["field_name"]
            if col not in df.columns:
                continue
            s = df[col]
            if f["nullable"] == "NO" and s.isna().any():
                n_err += 1; log.check("G3_schema", f"notnull:{name}.{col}", fname, False, f"{int(s.isna().sum())} giá trị rỗng")
            if f["data_type"] == "integer" and not (pd.api.types.is_integer_dtype(s) or (s.dropna() % 1 == 0).all()):
                n_err += 1; log.check("G3_schema", f"type:{name}.{col}", fname, False, "không phải số nguyên")
            if f["data_type"] == "decimal" and not pd.api.types.is_numeric_dtype(s):
                n_err += 1; log.check("G3_schema", f"type:{name}.{col}", fname, False, "không phải số")
        if n_err == 0:
            log.check("G3_schema", f"schema:{name}", fname, True, f"{len(expected)} trường đúng tên, thứ tự, kiểu, không rỗng")

# ---------- G4. Khóa & tính đầy đủ
FIN = ["income_statement", "balance_sheet", "cashflow", "financial_notes"]
def g4_keys(log, tables):
    ci = tables["company_info"]
    companies = sorted(ci["company_id"])
    log.check("G4_keys", "pk:company_info", "company_info.csv", ci["company_id"].is_unique, f"{len(companies)} company_id duy nhất")
    grid = {(c, y) for c in companies for y in YEARS}
    for name in FIN:
        df = tables[name]
        dup = int(df.duplicated(KEY).sum())
        log.check("G4_keys", f"pk:{name}", f"{name}.csv", dup == 0, f"{dup} khóa trùng")
        keys = set(map(tuple, df[KEY].values.tolist()))
        miss, extra = grid - keys, keys - grid
        log.check("G4_keys", f"grid:{name}", f"{name}.csv", not miss and not extra,
                  f"đủ {len(companies)}×{len(YEARS)}={len(grid)} company-year" if not miss and not extra
                  else f"thiếu={sorted(miss)[:5]} thừa={sorted(extra)[:5]}")
        bad = sorted(set(df["company_id"]) - set(companies))
        log.check("G4_keys", f"fk:{name}", f"{name}.csv", not bad, "mọi company_id có trong company_info" if not bad else f"lạ: {bad}")
    log.check("G4_keys", "no_2020", "01_data/*", all((tables[n]["fiscal_year"] >= 2021).all() for n in FIN),
              "Không có năm 2020 – chỉ tiêu cần năm trước để trống cho 2021")

# ---------- G5. Đơn vị & cờ giả lập
def g5_units(log, tables):
    ci = tables["company_info"]
    for col, val in [("statement_unit", "VND_million"), ("reporting_currency", "VND"),
                     ("fiscal_year_end", "12-31"), ("subindustry", "Packaged Food Manufacturing")]:
        vals = sorted(ci[col].astype(str).unique())
        log.check("G5_units", col, "company_info.csv", vals == [val], f"giá trị: {vals}")
    log.check("G5_units", "data_is_synthetic", "company_info.csv",
              ci["data_is_synthetic"].astype(str).str.upper().eq("TRUE").all(), "toàn bộ là dữ liệu giả lập")

# ---------- G6. Trường trùng giữa các báo cáo
def g6_overlap(log, tables):
    m = tables["income_statement"].merge(tables["cashflow"], on=KEY, suffixes=("_is", "_cf"))
    for col in ["net_income_vnd_mn", "depreciation_amortization_vnd_mn"]:
        diff = int((m[f"{col}_is"] != m[f"{col}_cf"]).sum())
        log.check("G6_overlap", f"same:{col}", "income_statement ↔ cashflow", diff == 0, f"{len(m)-diff}/{len(m)} dòng khớp")

# ---------- G7. Khớp template đầu ra
def g7_templates(log, tables):
    if "submission_output_template" in tables:
        t = tables["submission_output_template"]
        tk = set(map(tuple, t[KEY].values.tolist()))
        pk = set(map(tuple, tables["income_statement"][KEY].values.tolist()))
        log.check("G7_template", "keys:submission_output", "submission_output_template.csv", tk == pk, f"{len(tk)} khóa = {len(pk)} khóa dữ liệu")
        log.check("G7_template", "cols:submission_output", "submission_output_template.csv", t.shape[1] == 31, f"{t.shape[1]} cột")
    if {"qa_submission_template", "questions_sample"} <= tables.keys():
        a, b = set(tables["qa_submission_template"]["question_id"]), set(tables["questions_sample"]["question_id"])
        log.check("G7_template", "ids:qa_submission", "qa_submission_template.csv", a == b, f"{len(a)} question_id khớp questions_sample")
    if {"answer_key_sample", "questions_sample"} <= tables.keys():
        a, b = set(tables["answer_key_sample"]["question_id"]), set(tables["questions_sample"]["question_id"])
        log.check("G7_template", "ids:answer_key", "answer_key_sample.csv", a == b, f"{len(a)} câu có đáp án")

def build_master(log, tables):
    ci_cols = ["company_id", "company_name", "ticker_simulated", "company_size_band"]
    base = tables["income_statement"].copy()
    lineage = [("income_statement.csv", c, "") for c in base.columns if c not in KEY]
    for name in ["balance_sheet", "cashflow", "financial_notes"]:
        df = tables[name]
        keep = [c for c in df.columns if c not in KEY and c not in base.columns]
        dup = [c for c in df.columns if c not in KEY and c in base.columns]
        base = base.merge(df[KEY + keep], on=KEY, how="inner", validate="one_to_one")
        lineage += [(f"{name}.csv", c, "") for c in keep]
        lineage += [(f"{name}.csv", c, "trùng – dùng bản income_statement") for c in dup]
    base = tables["company_info"][ci_cols].merge(base, on="company_id", how="right", validate="one_to_many")
    lineage += [("company_info.csv", c, "") for c in ci_cols[1:]]
    base = base.sort_values(KEY).reset_index(drop=True)
    log.check("G8_join", "row_count", "master_panel", len(base) == 60, f"{len(base)} dòng (kỳ vọng 60)")
    log.check("G8_join", "no_null", "master_panel", not base.isna().any().any(), f"{base.shape[1]} cột, không rỗng do join")
    lin = pd.DataFrame(lineage, columns=["source_file", "source_field", "note"])
    lin.insert(0, "master_column", lin["source_field"])
    return base, lin

def run_step0(data_dir):
    """Chạy toàn bộ Bước 0 trên một thư mục dữ liệu. Trả về (log, master, lineage, present)."""
    log = CheckLog()
    present = g1_inventory(log, data_dir)
    if not (all(present[k] for k in CORE_FILES) and present["dataset_manifest"] and present["data_dictionary"]):
        return log, None, None, present
    g2_manifest(log, data_dir)
    tables = {n: rd(data_dir, r) for n, r in {**CORE_FILES, **LABEL_FILES, **TEMPLATE_FILES}.items() if present.get(n)}
    g3_schema(log, data_dir, tables); g4_keys(log, tables); g5_units(log, tables)
    g6_overlap(log, tables); g7_templates(log, tables)
    master, lineage = build_master(log, tables)
    return log, master, lineage, present

def data_fingerprint(data_dir) -> str:
    """SHA-256 gộp 5 file lõi (None nếu thiếu file)."""
    paths = [locate_pack_file(k, data_dir)[0] for k in sorted(CORE_FILES)]
    if any(p is None for p in paths):
        return None
    return hashlib.sha256("".join(sha256_of(p) for p in paths).encode()).hexdigest()


def negative_test(data_dir, tmp_root) -> CheckLog:
    """Sao chép Data Pack, sửa 1 triệu đồng doanh thu C006/2025 trên BẢN SAO, chạy lại Bước 0."""
    import shutil
    tmp_pack = Path(tmp_root) / "pack"
    shutil.copytree(data_dir, tmp_pack)
    f, _ = locate_pack_file("income_statement", tmp_pack)
    f.write_bytes(f.read_bytes().replace(b"C006,2025,1299735", b"C006,2025,1299736"))
    log, _, _, _ = run_step0(tmp_pack)
    return log
