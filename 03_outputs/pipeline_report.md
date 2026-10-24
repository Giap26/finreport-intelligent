# Báo cáo pipeline tự động – FinReport Intelligence

- **Trạng thái:** PASS · **Tổng thời gian:** 26.0 s · **Chế độ:** đầy đủ
- **Bắt đầu:** 2026-10-21T09:59:38+07:00 · **Kết thúc:** 2026-10-21T10:00:04+07:00
- **Data fingerprint:** `ffcb73450eb148d9ff4078a1…`

## Các bước

| Bước | Run ID | Kết luận | Thời gian | Tóm tắt |
|---|---|---|---:|---|
| step0_ingest | `S0-20261021-095938-ab5dff` | PASS | 1500 ms | 91 PASS · 0 WARN · 0 FAIL |
| step1_accounting | `S1-20261021-095940-88c99b` | PASS | 572 ms | 32 luật · 1752 PASS · 0 FAIL · 168 N/A |
| step2_metrics | `S2-20261021-095940-e0bfe7` | PASS | 494 ms | 18 chỉ tiêu × 60 dòng |
| step3_verify_qa | `S3-20261021-095941-9dec94` | PASS | 1338 ms | QA 100% · Calc 100% · verify 100% |
| step4_trend_peer | `S4-20261021-095942-56b5a8` | PASS | 236 ms | 82 đặc trưng |
| step5_signals | `S5-20261021-095942-975e9b` | PASS | 27 ms | 19 tín hiệu |
| step6_scoring | `S6-20261021-095942-d58868` | PASS | 19684 ms | tag F1 98.8% · baseline 33.3% |
| step7_submit | `S7-20261021-100002-8a692e` | PASS | 2103 ms | 27 kiểm tra PASS · file nộp đã ghi |

## KPI

| KPI | Kết quả | Mục tiêu BTC |
|---|---:|---:|
| Calculation Accuracy (metrics mẫu, dung sai BTC) | 100.0% | ≥ 95% |
| Chỉ tiêu khớp tuyệt đối | 99.7% | – |
| Numerical QA Accuracy (30 câu, cột cấu trúc) | 100.0% | ≥ 85% |
| QA chỉ dùng câu chữ (trợ lý tiếng Việt) | 100.0% | – |
| Trợ lý – tách đúng câu diễn đạt lại | 100.0% | – |
| QA tổng quát hóa (300 câu tự sinh) | 100.0% | – |
| Verify kép | 100.0% | – |
| Cảnh báo – tag F1 (18 nhãn, in-sample) | 98.8% | – |
| Baseline 1 chỉ tiêu – tag F1 | 33.3% | – |
| Kịch bản / severity / health | 100.0% / 100.0% / 100.0% | – |
| Độ nhạy ngưỡng ×0,8–1,2: F1 thấp nhất | 89.5% | – |
| Chấm lại từ file nộp: QA / chỉ tiêu / tag F1 | 100.0% / 100.0% / 98.8% | – |

> Cảnh báo là tín hiệu hỗ trợ phân tích – không phải kết luận gian lận, kiểm toán hay khuyến nghị đầu tư.