# Báo cáo pipeline tự động – FinReport Intelligence

- **Trạng thái:** PASS · **Tổng thời gian:** 36.6 s · **Chế độ:** đầy đủ
- **Bắt đầu:** 2026-10-25T11:34:54+07:00 · **Kết thúc:** 2026-10-25T11:35:31+07:00
- **Data fingerprint:** `ffcb73450eb148d9ff4078a1…`

## Các bước

| Bước | Run ID | Kết luận | Thời gian | Tóm tắt |
|---|---|---|---:|---|
| step0_ingest | `S0-20261025-113454-3b1d83` | PASS | 2060 ms | 91 PASS · 0 WARN · 0 FAIL |
| step1_accounting | `S1-20261025-113456-ad1c07` | PASS | 1864 ms | 32 luật · 1752 PASS · 0 FAIL · 168 N/A |
| step2_metrics | `S2-20261025-113458-14d91b` | PASS | 1131 ms | 18 chỉ tiêu × 60 dòng |
| step3_verify_qa | `S3-20261025-113459-9b4903` | PASS | 3240 ms | QA 100% · Calc 100% · verify 100% |
| step4_trend_peer | `S4-20261025-113502-09e0ef` | PASS | 604 ms | 82 đặc trưng |
| step5_signals | `S5-20261025-113503-83dc57` | PASS | 52 ms | 19 tín hiệu |
| step6_scoring | `S6-20261025-113503-7d497f` | PASS | 24854 ms | tag F1 98.8% · baseline 33.3% |
| step7_submit | `S7-20261025-113528-6ec93d` | PASS | 2767 ms | 27 kiểm tra PASS · file nộp đã ghi |

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