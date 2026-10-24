# FinReport Intelligence – Case 3, Bảng C (Festival Chuyển đổi số 2026)

Hệ thống hỗ trợ phân tích, so sánh và cảnh báo sức khỏe tài chính doanh nghiệp từ báo cáo tài chính giả lập.

## Chạy nhanh
```bash
pip install -r requirements.txt
python run_pipeline.py                 # S0 → S7: kiểm tra dữ liệu, tính chỉ tiêu, QA, cảnh báo, xuất file nộp
streamlit run 06_dashboard/app.py      # mở dashboard
```
Trên Google Colab: mở `02_notebooks/NB4_Dashboard.ipynb` → Run all.

## Cấu trúc
```
FinReport_Intelligence/
├── run_pipeline.py          pipeline tự động 8 bước (1 lệnh)
├── requirements.txt
├── lib/                     finreport_common · ingest · metrics · qa · assistant · signals · whatif · submit
├── 01_datapack/             Data Pack BTC (chỉ đọc; chấp nhận cả layout README lẫn layout thực tế 03_sample/ + _Case3)
├── 02_notebooks/            NB0–NB4 (cùng logic với pipeline, để trình bày từng bước)
├── 03_outputs/              kết quả từng bước + pipeline_summary.json + pipeline_report.md
├── 04_logs/audit_log.jsonl  nhật ký chỉ ghi thêm (run_id, parent_run, verdict, thời gian)
├── 05_submission/           submission_output.csv · qa_submission.csv · manifest SHA-256 · history/
└── 06_dashboard/app.py      dashboard Streamlit (7 trang)
```

## Dashboard
| Trang | Nội dung |
|---|---|
| Sổ cái rủi ro | 12 DN × 5 năm: mức độ + risk score; danh sách ưu tiên theo năm |
| Hồ sơ doanh nghiệp | Diễn biến kịch bản; chỉ tiêu so với dải P25–P75 & trung vị ngành |
| Thẻ cảnh báo & truy vết | Lý do bằng số, đóng góp risk score, bảng bằng chứng đọc thẳng dữ liệu gốc, kết quả verify |
| Mô phỏng what-if | 6 giả định (doanh thu, biên, lãi suất, nợ, DSO, tồn kho) → chạy lại toàn bộ; kiểm tra 32 luật kế toán |
| Trợ lý hỏi đáp | Câu hỏi tiếng Việt tự do → tách cấu trúc → trả lời bằng cùng công thức file nộp (không LLM) |
| Chất lượng mô hình | KPI, so với baseline, độ nhạy ngưỡng, đối chiếu nhãn & QA |
| Dữ liệu & nhật ký | Kết quả từng bước, kiểm tra toàn vẹn, 32 luật, audit log, tải file nộp |

> Cảnh báo là tín hiệu hỗ trợ phân tích – không phải kết luận gian lận, kiểm toán hay khuyến nghị đầu tư.
