"""finreport_common.py – Hàm & cấu hình dùng chung cho mọi notebook FinReport Intelligence.

Cách dùng trong notebook:
    import sys; sys.path.insert(0, "/content/drive/MyDrive/FinReport_Intelligence/lib")
    from finreport_common import *
    cfg = setup("/content/drive/MyDrive/FinReport_Intelligence")
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

__all__ = [
    "TZ", "KEY", "YEARS", "CORE_FILES", "METADATA_FILES", "LABEL_FILES", "TEMPLATE_FILES",
    "Config", "setup", "cfg",
    "sha256_of", "now_iso", "new_run_id", "append_audit", "read_audit",
    "read_pack", "read_output", "save_output", "locate_pack_file",
    "CheckLog",
]

# ------------------------------------------------------------------ Hằng số dự án
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
KEY = ["company_id", "fiscal_year"]
YEARS = list(range(2021, 2026))          # Không có 2020 – không tự sinh

CORE_FILES = {
    "company_info": "01_data/company_info.csv",
    "income_statement": "01_data/income_statement.csv",
    "balance_sheet": "01_data/balance_sheet.csv",
    "cashflow": "01_data/cashflow.csv",
    "financial_notes": "01_data/financial_notes.csv",
}
METADATA_FILES = {
    "data_dictionary": "02_metadata/data_dictionary.csv",
    "dataset_manifest": "02_metadata/dataset_manifest.csv",
}
LABEL_FILES = {
    "financial_scenarios_sample": "03_labels_sample/financial_scenarios_sample.csv",
    "financial_metrics_sample": "03_labels_sample/financial_metrics_sample.csv",
    "questions_sample": "03_labels_sample/questions_sample.csv",
    "answer_key_sample": "03_labels_sample/answer_key_sample.csv",
}
TEMPLATE_FILES = {
    "submission_output_template": "04_output_template/submission_output_template.csv",
    "qa_submission_template": "04_output_template/qa_submission_template.csv",
}


# ------------------------------------------------------------------ Cấu hình đường dẫn
@dataclass
class Config:
    project: Path
    data_dir: Path        # 01_datapack/CASE3_FINREPORT_INTELLIGENCE (chỉ đọc)
    out_dir: Path         # 03_outputs
    log_dir: Path         # 04_logs
    audit_log: Path       # 04_logs/audit_log.jsonl
    submit_dir: Path      # 05_submission
    fig_dir: Path         # 07_docs/figures

    def step_dir(self, step: str) -> Path:
        """Thư mục kết quả của một bước, vd cfg.step_dir('step0'). Tự tạo nếu chưa có."""
        p = self.out_dir / step
        p.mkdir(parents=True, exist_ok=True)
        return p


cfg: Config | None = None


def setup(project: str | Path, pack_name: str = "CASE3_FINREPORT_INTELLIGENCE") -> Config:
    """Khởi tạo cấu hình đường dẫn cho cả dự án. Gọi 1 lần ở đầu mỗi notebook."""
    global cfg
    project = Path(project)
    cfg = Config(
        project=project,
        data_dir=project / "01_datapack" / pack_name,
        out_dir=project / "03_outputs",
        log_dir=project / "04_logs",
        audit_log=project / "04_logs" / "audit_log.jsonl",
        submit_dir=project / "05_submission",
        fig_dir=project / "07_docs" / "figures",
    )
    for d in (cfg.out_dir, cfg.log_dir, cfg.submit_dir, cfg.fig_dir):
        d.mkdir(parents=True, exist_ok=True)
    print(f"PROJECT  : {cfg.project}")
    print(f"DATA_DIR : {cfg.data_dir}  ({'có' if cfg.data_dir.exists() else 'CHƯA CÓ'})")
    return cfg


def _need_cfg() -> Config:
    if cfg is None:
        raise RuntimeError("Chưa gọi setup(PROJECT) ở đầu notebook")
    return cfg


# ------------------------------------------------------------------ Tiện ích
def sha256_of(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def new_run_id(prefix: str) -> str:
    """vd new_run_id('S0') -> 'S0-20261019-231500-a1b2c3'"""
    return f"{prefix}-{datetime.now(TZ).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


# ------------------------------------------------------------------ Audit log (append-only)
def append_audit(record: dict) -> None:
    c = _need_cfg()
    record = {"timestamp": now_iso(), **record}
    with open(c.audit_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_audit() -> pd.DataFrame:
    c = _need_cfg()
    if not c.audit_log.exists():
        return pd.DataFrame()
    return pd.read_json(c.audit_log, lines=True)


# ------------------------------------------------------------------ Đọc / ghi dữ liệu
def locate_pack_file(name_or_rel: str, data_dir: str | Path | None = None) -> tuple[Path | None, str]:
    """Tìm 1 file trong Data Pack, chịu được layout khác README.
    Thứ tự: (1) đúng đường dẫn chuẩn README; (2) cùng tên ở bất kỳ thư mục con nào (vd 03_sample/);
    (3) tên có hậu tố (vd submission_output_template_Case3.csv). Trả về (đường dẫn | None, cách tìm thấy)."""
    data_dir = Path(data_dir) if data_dir else _need_cfg().data_dir
    all_files = {**CORE_FILES, **METADATA_FILES, **LABEL_FILES, **TEMPLATE_FILES}
    rel = all_files.get(name_or_rel, name_or_rel)
    std = data_dir / rel
    if std.exists():
        return std, "standard"
    fname, stem = Path(rel).name, Path(rel).stem
    same = sorted(data_dir.rglob(fname))
    if same:
        return same[0], f"same-name:{same[0].relative_to(data_dir)}"
    pref = sorted(p for p in data_dir.rglob(f"{stem}*.csv") if p.stem.startswith(stem + "_") or p.stem.startswith(stem + "-"))
    if len(pref) == 1:
        return pref[0], f"suffix:{pref[0].relative_to(data_dir)}"
    return None, "not-found" if not pref else f"ambiguous:{[str(p.relative_to(data_dir)) for p in pref]}"


def read_pack(name_or_rel: str) -> pd.DataFrame:
    """Đọc 1 file trong Data Pack theo tên ngắn ('balance_sheet') hoặc đường dẫn tương đối.
    Nếu không có ở vị trí chuẩn, tự tìm theo locate_pack_file (03_sample/, hậu tố _Case3...)."""
    path, how = locate_pack_file(name_or_rel)
    if path is None:
        raise FileNotFoundError(f"Không tìm thấy '{name_or_rel}' trong Data Pack ({how})")
    if how != "standard":
        print(f"[read_pack] '{name_or_rel}' lấy từ {how}")
    return pd.read_csv(path, encoding="utf-8-sig")


def read_output(step: str, filename: str) -> pd.DataFrame:
    """Đọc kết quả của bước trước, vd read_output('step0', 'master_panel.csv')."""
    c = _need_cfg()
    p = c.out_dir / step / filename
    if not p.exists():
        raise FileNotFoundError(f"Chưa có {p} – hãy chạy bước '{step}' trước")
    # chỉ ô rỗng mới là NaN; giữ nguyên các chữ như "N/A" (trạng thái luật kế toán)
    return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def save_output(df: pd.DataFrame, step: str, filename: str) -> Path:
    """Ghi kết quả 1 bước (UTF-8 có BOM để mở đúng tiếng Việt trong Excel)."""
    p = _need_cfg().step_dir(step) / filename
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p


# ------------------------------------------------------------------ Sổ ghi kiểm tra
class CheckLog:
    """Ghi lại từng phép kiểm tra: group, check_id, target, status, detail.

    log = CheckLog()
    log.check("G2_manifest", "rows:x.csv", "01_data/x.csv", ok=True, detail="60 / 60 dòng")
    log.check(..., ok=False, warn_only=True)   # lỗi không nghiêm trọng -> WARN thay vì FAIL
    """

    def __init__(self):
        self.rows: list[dict] = []

    def check(self, group: str, check_id: str, target: str, ok: bool,
              detail: str = "", warn_only: bool = False) -> bool:
        status = "PASS" if ok else ("WARN" if warn_only else "FAIL")
        self.rows.append({"group": group, "check_id": check_id, "target": target,
                          "status": status, "detail": detail})
        return bool(ok)

    def df(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["group", "check_id", "target", "status", "detail"])

    def counts(self) -> dict:
        return self.df()["status"].value_counts().to_dict() if self.rows else {}

    def summary(self) -> pd.DataFrame:
        return (self.df().groupby(["group", "status"]).size().unstack(fill_value=0)
                .reindex(columns=["PASS", "WARN", "FAIL"], fill_value=0))

    def issues(self) -> pd.DataFrame:
        d = self.df()
        return d[d["status"] != "PASS"]

    @property
    def failed(self) -> bool:
        return any(r["status"] == "FAIL" for r in self.rows)

    def verdict(self) -> str:
        c = self.counts()
        return "FAIL – dừng pipeline" if c.get("FAIL") else ("PASS kèm cảnh báo" if c.get("WARN") else "PASS")
