# BÀN GIAO DỰ ÁN – FinReport Intelligence (Case 3, Bảng C, Festival Chuyển đổi số 2026)

> Tài liệu này tóm tắt toàn bộ công việc đã làm đến **21/10/2026 (đã xong NB3, pipeline tự động, dashboard Streamlit)**, để tiếp tục ở một đoạn chat mới.
> Kèm theo: `FinReport_Intelligence_v2.zip` – cây thư mục dự án đầy đủ (8 thư viện, `run_pipeline.py`, dashboard, 5 notebook, ảnh chụp dashboard).

---

## 1. Đề tài & mục tiêu

**Bài toán:** xây dựng hệ thống hỗ trợ phân tích, so sánh và **cảnh báo sức khỏe tài chính** doanh nghiệp từ báo cáo tài chính giả lập
(12 DN cùng ngành *Packaged Food Manufacturing*, 2021–2025 = 60 company-year, đơn vị **triệu VND**).

**Sản phẩm gồm 3 phần:**

| Đầu ra | Dạng | Vai trò |
|---|---|---|
| `submission_output_template.csv` | 60 dòng × 31 cột | BTC chấm tự động: 18 chỉ tiêu + risk_score, kịch bản, severity, health, tags, lý do, bằng chứng, rank, confidence, model_name, processing_time_ms |
| `qa_submission_template.csv` | 30 câu (+ có thể câu ẩn) | BTC chấm Numerical QA |
| Dashboard / web | Giao diện | Demo cho giám khảo: xu hướng, benchmark, thẻ cảnh báo, truy vết, hỏi đáp |

**Vòng hiện tại = Blueprint (sơ khảo):** nộp **2 file PDF**: bản đề xuất **5–10 trang** + slide **≤ 15 trang**, tên `HSSK_<TenDoi>_C.pdf`.
Thang điểm: Phù hợp/giá trị 25 · **Kỹ thuật & KPI 30** · Đầu ra & tuân thủ 20 · Kế hoạch MVP 15 · Trình bày 10.

**Mục tiêu đội: mức Gold.** Lưu ý của đề: *Silver/Gold chỉ được ghi nhận khi có minh chứng bằng KPI, thực nghiệm hoặc kiểm thử* → chiến lược là làm prototype chạy thật để có số liệu thật đưa vào PDF.

KPI mục tiêu BTC: **Calculation Accuracy ≥ 95%**, **Numerical QA Accuracy ≥ 85%**; ngoài ra P/R/F1 cảnh báo, macro recall theo kịch bản, độ đúng xếp hạng, truy vết, thời gian xử lý.

---

## 2. Dữ liệu BTC & các điểm bất thường đã xử lý

**Data Pack** (theo README): `01_data/` (company_info, income_statement, balance_sheet, cashflow, financial_notes) · `02_metadata/` (data_dictionary, dataset_manifest) · `03_labels_sample/` (financial_scenarios_sample, financial_metrics_sample, questions_sample, answer_key_sample) · `04_output_template/`.

**Thực tế BTC phát khác README** (đã chuẩn hóa thủ công trên Drive bằng cách *sao chép*, giữ bản gốc):

| README | Thực tế | Đã làm |
|---|---|---|
| `03_labels_sample/` | `03_sample/` | Chép sang `03_labels_sample/` |
| `04_output_template/submission_output_template.csv` | `submission_output_template_Case3.csv` ở thư mục gốc | Chép + đổi tên vào `04_output_template/` |
| `04_output_template/qa_submission_template.csv` | `qa_submission_template_Case3.csv` ở gốc | Như trên |
| `README.md` | `README_Case3_FINREPORT_INTELLIGENCE.md` | Chép thành `README.md` |
| — | Zip tải từ Drive bị lồng thêm 1 tầng `DataPack_CASE3_FINREPORT_INTELLIGENT/` | Đã chuyển nội dung lên đúng tầng |

- `financial_scenarios_sample.csv` **khớp SHA-256 với manifest**. `financial_metrics_sample.csv`, questions, answer_key, 2 template **không có trong manifest** → NB0 ghi dấu vân tay vào audit log.
- **Data fingerprint** (SHA-256 gộp 5 file lõi): `ffcb73450eb148d9ff4078a105a916f4…`
- ✅ Đã xử lý rủi ro layout: `locate_pack_file()` tự nhận diện file (chấp nhận `03_sample`, hậu tố `_Case3`) và NB3 ghi ánh xạ vào audit log. Đã chạy thử trọn NB0→NB3 trên cả layout README và layout gốc BTC.

**Quan sát quan trọng về dữ liệu:**
- 5 file lõi khớp tuyệt đối 32 luật kế toán (cân đối, dòng tiền, liên kết 2 năm).
- DSO bám sát `average_customer_credit_terms_days`, Inventory days bám sát `inventory_policy_days_target` → so với chính sách không phân biệt được; tín hiệu thật là **xu hướng so với năm gốc + so đồng ngành**.
- Mỗi DN được "cài" một kịch bản: C001 ổn định · C002 tăng trưởng nóng/dòng tiền yếu · C003 phải thu · C004 tồn kho · C005 mở rộng nợ · C006 suy giảm biên · C007 thanh khoản · C008 lãi–tiền phân kỳ · C009 khủng hoảng→phục hồi · C010 vượt trội · C011 cải thiện · C012 đa yếu tố.
- **Bẫy dấu:** C012/2025 CFO/LNST = 9,27x (âm/âm) – không được hiểu là tốt.

---

## 3. Cấu trúc Google Drive

```text
MyDrive/FinReport_Intelligence/
├── 00_admin/                       đề thi, ghi chú
├── 01_datapack/CASE3_FINREPORT_INTELLIGENCE/   CHỈ ĐỌC (đã chuẩn hóa theo README)
├── run_pipeline.py · requirements.txt · README.md · .streamlit/config.toml
├── 02_notebooks/   NB0_Ingest · NB1_Calculate · NB2_Signals · NB3_Submit · NB4_Dashboard (.ipynb)
├── lib/            finreport_common · ingest · metrics · qa · assistant · signals · whatif · submit (.py)
├── 03_outputs/     step0/ · step1_3/ · step4_6/ · step7_submit/
├── 04_logs/audit_log.jsonl         nhật ký chung, chỉ ghi thêm
├── 05_submission/   submission_output.csv · qa_submission.csv · submission_manifest.csv · history/<run_id>/
├── 06_dashboard/app.py             dashboard Streamlit 7 trang
├── 07_docs/  drafts/ · figures/ · final/
└── 99_archive/                     bản cũ (notebook cũ FinReport_Step0_Ingest.ipynb – KHÔNG dùng)
```

**Ô mở đầu chuẩn của mọi notebook:**
```python
from google.colab import drive; import sys, importlib
drive.mount("/content/drive")
PROJECT = "/content/drive/MyDrive/FinReport_Intelligence"
sys.path.insert(0, PROJECT + "/lib")
from finreport_common import *
cfg = setup(PROJECT)      # bắt buộc gán vào cfg
```
Sửa file trong `lib/` → **Runtime → Restart session** rồi chạy lại.

---

## 4. Pipeline 9 bước & trạng thái

```text
[0] Ingest & Integrity → [1] Validate kế toán → [2] Calculate → [3] Verify & QA
→ [4] Trend & Peer → [5] Signals → [6] Score & Rank → [7] Explain & Trace → [8] Output & Dashboard  (+ [9] QA engine)
```

| Notebook | Bước | Trạng thái | Đọc | Ghi |
|---|---|---|---|---|
| **NB0_Ingest** | 0 | ✅ chạy trên Drive: **91 PASS, 0 WARN, 0 FAIL** | `01_datapack/` | `03_outputs/step0/` |
| **NB1_Calculate** | 1, 2, 3 (+ QA engine) | ✅ chạy trên Drive | `step0/master_panel.csv` + datapack | `03_outputs/step1_3/` |
| **NB2_Signals** | 4, 5, 6 (+ phần 7: lý do & bằng chứng) | ✅ chạy thử OK | `step0`, `step1_3`, nhãn mẫu | `03_outputs/step4_6/` |
| **NB3_Submit** | ghép & xuất 2 file nộp | ✅ chạy thử OK: 27/27 kiểm tra PASS, 6/6 kiểu lỗi bị bắt, chấm lại từ file nộp: QA 30/30, chỉ tiêu 324/324, cảnh báo F1 98,8% | step1_3 + step4_6 + templates | `05_submission/`, `03_outputs/step7_submit/` |
| **NB4_Dashboard** | 8 (+ Gold: what-if, trợ lý, audit view) | ✅ chạy `run_pipeline.py` + mở Streamlit (Colab proxy hoặc Cloudflare tunnel); đã chụp màn hình 7 trang, 0 lỗi | toàn bộ outputs | `06_dashboard/` |
| **run_pipeline.py** | S0→S7 tự động | ✅ 1 lệnh, ~10 s (đầy đủ) / ~1,6 s (`--quick`); dừng khi FAIL (đã thử dữ liệu bị sửa → dừng ở S0, không tạo file nộp); chạy được cả layout BTC gốc | datapack | toàn bộ outputs + `pipeline_summary.json` + `pipeline_report.md` |

Chuỗi truy vết: mỗi bước ghi 1 bản ghi vào `audit_log.jsonl` với `run_id` + `parent_run` (S0 → S1 → S2 → S3 → S4 → S5 → S6).

---

## 5. Thư viện `lib/` – chức năng chính

**`finreport_common.py`**: hằng số (`KEY`, `YEARS`, `CORE_FILES`, `LABEL_FILES`, `TEMPLATE_FILES`), `setup()`, `read_pack()`, `read_output()` (giữ nguyên chữ "N/A"), `save_output()` (UTF-8-SIG), `append_audit()`/`read_audit()`, `sha256_of()`, `new_run_id()`, `CheckLog` (PASS/WARN/FAIL).

**`finreport_metrics.py`** (một nguồn công thức duy nhất cho toàn hệ thống):
- `C` (tên ngắn→cột), `SRC` (trường→file), `prepare()` (d = năm t, p = năm t−1; 2021 → NaN), `evidence()`.
- **Bước 1:** `RULES` (32 luật: IS01–05, BS01–07, CF01–06, XP01–14), `run_accounting_checks()`, `summarize_checks()`, `rule_catalog()`, `row_flags()` (NET_LOSS, NEGATIVE_CFO, OPERATING_LOSS, OP_BELOW_INTEREST, NEGATIVE_EQUITY…).
- **Bước 2:** `METRICS` (18 chỉ tiêu, tên = cột template), `compute_metrics()` → wide (60×18) + long (1.080 ô, kèm flag/công thức/nguồn), `metric_catalog()`; guard diễn giải: CFO/NI khi NI≤0, ICR khi OP≤0, D/E & ROE khi vốn chủ ≤0.
- **Bước 3a:** `compute_metrics_independent()` (đường tính thứ 2, đọc thẳng CSV gốc), `dual_verify()`.
- `SUPPLEMENTARY` + `compute_supplementary()` (total_debt, cfo, tăng trưởng AR/tồn kho/nợ), `compare_with_metrics_sample()`.

**`finreport_qa.py`**: `QAEngine` (không LLM, không nhánh theo question_id; định tuyến theo `question_type` + `source_fields`; 10 handler: DIRECT_VALUE, RATIO, GROWTH, CHANGE, CASHFLOW, WORKING_CAPITAL, LIQUIDITY, RANKING, BOOLEAN, TREND (sinh tag bằng luật), LIST_FILTER, RECONCILIATION), `grade()` (chấm theo `answer_unit_or_type` + `numeric_tolerance`), `to_submission()`, `make_variant_suite()` (sinh 300 câu mới, seed 2026, đáp án từ đường tính độc lập).

**`finreport_common.locate_pack_file()`** (mới): tìm file theo thứ tự đường dẫn chuẩn README → cùng tên ở thư mục con (vd `03_sample/`) → tên có hậu tố (`_Case3`); `read_pack()` dùng nó. NB0–NB3 đều dùng → **chạy được trên cả layout README lẫn layout thực tế BTC** (NB0 báo WARN ghi rõ vị trí khác README thay vì FAIL).

**`finreport_submit.py`** (mới): `assemble_submission()` (giữ thứ tự dòng/cột template, làm tròn 6 chữ số), `assemble_qa()`, `validate_submission()` (18 kiểm tra), `validate_qa()` (9 kiểm tra), `regrade_qa_file()` (tách đáp án từ chữ trong file nộp rồi chấm lại), `timing_per_row()` (đo toàn pipeline ×3 lấy trung vị, chia đều 60 dòng ≈ 5 ms/dòng), `manifest()` (SHA-256).

**Mới (21/10):**
- **`finreport_ingest.py`**: logic NB0 (G1–G8, build_master, run_step0, data_fingerprint, negative_test) thành module.
- **`finreport_assistant.py`**: trợ lý tiếng Việt tự do (không LLM): `norm()` bỏ dấu, từ điển chỉ tiêu/trường Việt–Anh, `parse_question()` nhận 10 loại câu → câu hỏi có cấu trúc → `QAEngine`. Đo: 30 câu mẫu **chỉ dùng chữ** 30/30; 25 câu diễn đạt lại 25/25 (`PARAPHRASE_SUITE`, `evaluate_paraphrases()`; tự soạn nên cũng là trong mẫu). Câu thiếu thông tin → từ chối kèm hướng dẫn. Lấp giới hạn #3 cũ.
- **`finreport_whatif.py`**: 6 đòn bẩy (doanh thu %, biên gộp đ%, lãi suất đ%, nợ vay %, DSO mục tiêu, ngày tồn kho mục tiêu) → `apply_scenario()` sửa bản sao giữ đúng quan hệ kế toán (cập nhật cash_effect, CFO, CFF, tiền, LN giữ lại) → `simulate()` chạy lại toàn pipeline + `check_identities()` (16 kịch bản thử đều 32/32 luật PASS). Chỉ sửa năm được chọn.
- **Dashboard** `06_dashboard/app.py` (Streamlit + Plotly 5.24.1 – **bắt buộc ghim**, Plotly 6+/7 mã hóa mảng `bdata` làm biểu đồ hiển thị sai trong Streamlit; annotation trên trục danh mục phải dùng vị trí số, không dùng chuỗi năm). Thiết kế: nền xanh xám lạnh #F3F5F8, chữ xanh mực #13223F, thanh bên #13223F, phông Be Vietnam Pro, màu trạng thái chuẩn (●Thấp #0ca30c, ▲Trung bình #fab219, ◆Cao #ec835a, ■Nghiêm trọng #d03b3b) luôn kèm ký hiệu + nhãn, chuỗi xanh #2a78d6 / cam #eb6834 (đã kiểm định bảng màu). 7 trang: Sổ cái rủi ro (heatmap 12×5) · Hồ sơ DN (dải P25–P75 ngành) · Thẻ cảnh báo & truy vết (bảng bằng chứng từ dữ liệu gốc) · What-if · Trợ lý · Chất lượng mô hình · Dữ liệu & nhật ký (tải file nộp). Nút "Chạy lại pipeline" ở thanh bên.

**`finreport_signals.py`**:
- `THRESHOLDS` (mọi ngưỡng ở một chỗ, tự đặt theo thông lệ), `build_features()` (82 đặc trưng: so năm gốc, TB 2 năm, peer median/P25/P75 theo năm, không nhìn tương lai), `detect_signals()` (19 tín hiệu S_*), `_scenario()` (13 kịch bản theo thứ tự nguyên nhân gốc), `_tags()` (tag theo kịch bản – đúng từ vựng BTC), `score()` (risk_score 6 thành phần, severity, health, priority_rank toàn 60 dòng + priority_rank_in_year), `confidence()`, `explain()` (alert_reason + evidence_fields dạng `file:DN:năm-năm:trường`), `run()`, `baseline()`, `evaluate()`, `compare_rows()`, `sensitivity()`, `one_at_a_time()`.

**13 kịch bản (tên từ BTC):** NORMAL_STABLE, STRONG_PERFORMANCE, OPERATIONAL_IMPROVEMENT, FINANCIAL_RECOVERY, DISTRESS_BASELINE, REVENUE_GROWTH_WEAK_CASH, RECEIVABLES_RISK, INVENTORY_BUILDUP, DEBT_EXPANSION, MARGIN_DETERIORATION, LIQUIDITY_STRESS, PROFIT_CASH_DIVERGENCE, MULTI_FACTOR_STRESS.
Thứ tự ưu tiên: Distress → Recovery → Strong → Multi → Liquidity → Profit-cash divergence → Revenue-growth-weak-cash → Receivables → Inventory → Debt → Margin → Improvement → Normal.

**risk_score** = 0,20·cash + 0,20·coverage + 0,15·leverage + 0,15·margin + 0,15·working_capital + 0,15·loss (mỗi thành phần ∈ [0,1]).
**Severity:** tích cực → LOW; phục hồi → LOW/MEDIUM; rủi ro: CRITICAL nếu ICR < 3 hoặc lỗ; HIGH nếu ≥ 2 tag rủi ro; MEDIUM nếu 1.
**Health:** HIGH_RISK nếu CRITICAL / biên HĐ giảm ≥ 3đ% / đa yếu tố / CFO/doanh thu < 2%; còn lại WATCH; tích cực → HEALTHY; phục hồi → RECOVERING.

---

## 6. Kết quả đã đạt (minh chứng KPI cho hồ sơ)

| KPI | Kết quả | Ghi chú |
|---|---|---|
| Toàn vẹn dữ liệu (NB0) | 91/91 PASS | SHA-256, schema, khóa, đơn vị, template; kiểm thử âm: sửa 1 triệu đồng → FAIL |
| Luật kế toán (NB1-B1) | 32 luật: 1.752 PASS · 0 FAIL · 168 N/A | N/A = luật 2 năm không áp dụng cho 2021 |
| **Calculation Accuracy** (financial_metrics_sample, 18 chỉ tiêu) | **324/324 = 100%** trong dung sai BTC · 323/324 = 99,7% khớp tuyệt đối | Ô lệch: C009/2022 revenue_growth −1,525003 vs BTC −1,52 (làm tròn) |
| 5 chỉ tiêu bổ sung | 90/90 khớp tuyệt đối | |
| Verify kép | 1.080/1.080 ô khớp | Kiểm thử đột biến (Quick Ratio sai) bị bắt ở cả verify & QA |
| **Numerical QA Accuracy** | **30/30 = 100%** | 0,3 ms/câu, không dùng LLM |
| Tổng quát hóa QA | 300/300 câu tự sinh | |
| Cảnh báo – 18 nhãn mẫu (**in-sample**) | Tag F1 98,8% (P 100%, R 97,6%) · kịch bản 100% · severity 100% · health 100% · recall HIGH/CRITICAL 100% · báo động nhầm 0% · Spearman risk~severity 0,88 | Sai duy nhất: C012/2025 thiếu LEVERAGE_RISK (giữ nguyên ngưỡng, không ép khớp) |
| Baseline 1 chỉ tiêu | Tag F1 33,3% · kịch bản 38,9% · severity 61,1% | Đối chứng mức Silver |
| Độ nhạy ngưỡng | ×0,8…×1,2 đồng loạt: F1 0,90–0,99 · đổi từng ngưỡng ±20%: 85% không đổi | |
| Nhất quán thời gian (42 dòng không nhãn) | 83% DN giữ kịch bản 2023–2025; 7 lần nhảy ≥ 2 bậc (chủ yếu 2022→2023 do tín hiệu cần 2 năm dữ liệu) | |

---

## 7. Quy ước & quyết định thiết kế (phải giữ nhất quán)

- Khóa: `company_id + fiscal_year`. Không đổi `company_id`, `fiscal_year`, `question_id`. Giữ nguyên schema template.
- **Không tạo dữ liệu 2020.** Chỉ tiêu cần năm trước → để trống cho 2021, cờ `INSUFFICIENT_HISTORY`.
- Quy ước dấu Data Pack: CAPEX & cổ tức âm → FCF = CFO + CAPEX; `cash_effect_*` âm khi tài sản tăng.
- Bình quân đầu–cuối năm cho ROA, ROE, DSO, Inventory Days, DPO.
- Giá trị chỉ tiêu luôn đúng công thức BTC; mẫu số bất thường → **giữ giá trị + gắn cờ diễn giải** (không tự để trống).
- Chuỗi Gold: **Calculate → Verify → Explain**; `assert` chặn pipeline nếu bước trước FAIL.
- `priority_rank` hiện xếp trên **toàn 60 dòng** (severity trước, rồi risk_score); có thêm `priority_rank_in_year`. *Có thể đổi nếu BTC hiểu khác.*
- Confidence: 2021 = 0,6; 2022 = 0,8; còn lại 0,95; trừ 0,08 cho mỗi tín hiệu sát ngưỡng (±10%), tối đa 3.
- Cảnh báo chỉ là tín hiệu hỗ trợ phân tích – không phải kết luận gian lận/kiểm toán/khuyến nghị đầu tư.

---

## 8. Giới hạn đã biết (nên nêu trung thực trong hồ sơ)

1. Đánh giá cảnh báo trên 18 nhãn là **in-sample** (luật thiết kế khi đã xem nhãn) → bù bằng độ nhạy ngưỡng + nhất quán thời gian.
2. Hệ thống chỉ biết **13 kịch bản** có trong mẫu; kịch bản ẩn khác sẽ bị xếp vào kịch bản gần nhất.
3. ~~QA cần cột cấu trúc~~ → đã có trợ lý tách câu tiếng Việt tự do; vẫn có thể gặp cách diễn đạt chưa có trong từ điển (khi đó từ chối chứ không đoán).
4. Bộ 300 câu tự sinh chưa có 4 dạng: BOOLEAN, TREND, CHANGE, RECONCILIATION (các dạng này có trong 30 câu mẫu và bộ 25 câu diễn đạt lại).
5. Câu `short_text` (Q025) tự chấm bằng tag; BTC có thể chấm lời văn bằng người/LLM.
6. Tín hiệu xu hướng cần ≥ 2 năm → năm 2021–2022 ít tín hiệu hơn.

---

## 9. Bước tiếp theo

### 9.1 NB3_Submit – ✅ ĐÃ XONG
Ghép đúng template, kiểm tra trước khi ghi, đọc lại file nộp để chấm, kiểm thử âm 6 kiểu lỗi, manifest SHA-256, lưu bản theo run_id trong `05_submission/history/`.
Việc còn có thể làm thêm: bảng `THRESHOLD_SOURCES` (nguồn gốc từng ngưỡng: tham khảo Damodaran/Piotroski/Beneish · thông lệ · hiệu chỉnh theo dữ liệu); cân nhắc thay ngưỡng cố định nhạy (`maturity_12m_pct`, `cfo_ni_liquidity`, `inv_gap_pp`) bằng ngưỡng theo phân phối ngành (P75).

### 9.2 NB4_Dashboard – ✅ ĐÃ XONG
Có thể làm thêm: bảng `THRESHOLD_SOURCES`; ngưỡng theo phân phối ngành cho 3 ngưỡng nhạy; triển khai Streamlit Community Cloud (repo GitHub) để có link cố định; ảnh chụp dashboard đã có trong `07_docs/figures/` để đưa vào PDF.

### 9.3 Hồ sơ PDF
**Bản đề xuất 10 trang:** 1) Bối cảnh–vấn đề–insight · 2) Mục tiêu & phạm vi · 3) Dữ liệu & kiểm soát chất lượng · 4) Kiến trúc pipeline · 5) Phương pháp (công thức, luật, scoring, verify, confidence, what-if) · 6) KPI & thực nghiệm (bảng mục 6, baseline, độ nhạy, phân tích lỗi) · 7) Đầu ra & giao diện · 8) Kế hoạch MVP 2–3 tuần · 9) Rủi ro, đạo đức, giới hạn · Phụ lục (32 luật, 18 công thức, output mẫu, audit log mẫu).

**Slide 15 trang:** Bìa · Vấn đề · Insight dữ liệu · Giải pháp tổng quan · Kiến trúc pipeline · Dữ liệu & QC · Chỉ tiêu & Verify · Tín hiệu & scoring · Explainability & truy vết · KPI & kết quả · Đầu ra · Mockup & demo flow · What-if & trợ lý · Kế hoạch MVP · Rủi ro & đạo đức.

---

## 10. Cách tiếp tục ở chat mới

1. Tải lên chat mới: **file này** + `finreport_code_bundle.zip` (+ README/đề thi PDF nếu cần đối chiếu).
2. Nếu cần dữ liệu để chạy thử: zip thư mục `01_datapack/CASE3_FINREPORT_INTELLIGENCE/` trên Drive và tải lên.
3. Yêu cầu mẫu: *"Đọc HANDOFF và gói dự án, viết hồ sơ PDF theo mục 9.3 (bản đề xuất 10 trang + 15 slide), dùng số liệu KPI ở mục 6 và ảnh trong 07_docs/figures/."*

Người dùng làm việc bằng tiếng Việt, chạy trên Google Colab + Google Drive; ưa giải thích dễ hiểu kèm ví dụ số liệu thật.
