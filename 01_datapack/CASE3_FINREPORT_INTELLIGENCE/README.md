# CASE 3 – FINREPORT INTELLIGENCE
## Festival Chuyển đổi số 2026

**Mục tiêu:** xây dựng hệ thống hỗ trợ phân tích, so sánh và cảnh báo sức khỏe tài chính doanh nghiệp dựa trên dữ liệu báo cáo tài chính giả lập.

> Toàn bộ dữ liệu trong Data Pack là dữ liệu synthetic, được tạo cho mục đích học thuật và cuộc thi. Tên doanh nghiệp, mã cổ phiếu, số liệu và tình huống tài chính không đại diện cho doanh nghiệp thực tế cụ thể.

## 1. Phạm vi dữ liệu

Data Pack gồm:
- 12 doanh nghiệp giả định cùng phân ngành **Packaged Food Manufacturing**;
- 5 năm liên tiếp: **2021–2025**;
- 60 quan sát `company_id + fiscal_year`;
- đồng tiền: VND;
- đơn vị số liệu tài chính: **triệu VND (`VND_million`)**.

Việc sử dụng doanh nghiệp cùng ngành nhằm hỗ trợ benchmark và so sánh ngang.

## 2. Cấu trúc Data Pack

```text
CASE3_FINREPORT_INTELLIGENCE/
├── README.md
├── 01_data/
│   ├── company_info.csv
│   ├── income_statement.csv
│   ├── balance_sheet.csv
│   ├── cashflow.csv
│   └── financial_notes.csv
├── 02_metadata/
│   ├── data_dictionary.csv
│   └── dataset_manifest.csv
├── 03_labels_sample/
│   ├── financial_scenarios_sample.csv
│   ├── financial_metrics_sample.csv
│   ├── questions_sample.csv
│   └── answer_key_sample.csv
└── 04_output_template/
    ├── submission_output_template.csv
    └── qa_submission_template.csv
```

BTC có thể phát các template riêng nếu cần; tên cột và schema phải được giữ nguyên.

## 3. Mô tả dữ liệu chính

### `company_info.csv`
Thông tin định danh và hồ sơ 12 doanh nghiệp giả lập.

### `income_statement.csv`
60 dòng, một dòng cho mỗi company-year. Chứa doanh thu, giá vốn, lợi nhuận gộp, chi phí hoạt động, lợi nhuận hoạt động, chi phí lãi vay, lợi nhuận trước thuế và lợi nhuận sau thuế.

### `balance_sheet.csv`
60 dòng. Chứa tiền, phải thu, tồn kho, tài sản, nợ phải trả, nợ vay và vốn chủ sở hữu.

Dữ liệu được kiểm soát để thỏa mãn:

`Total Assets = Total Liabilities + Total Equity`

### `cashflow.csv`
60 dòng. Chứa CFO, CFI, CFF, CAPEX và thay đổi tiền.

Đối chiếu bắt buộc:

`Beginning Cash + Net Change in Cash = Ending Cash`

và:

`Ending Cash = Cash and Cash Equivalents trên balance_sheet.csv`

### `financial_notes.csv`
60 dòng. Cung cấp thêm các biến:
- thời hạn tín dụng khách hàng;
- mục tiêu số ngày tồn kho;
- lãi suất vay bình quân;
- tỷ lệ nợ đáo hạn trong 12 tháng;
- mức tập trung khách hàng;
- tỷ lệ doanh thu xuất khẩu;
- cường độ CAPEX.

### `data_dictionary.csv`
Mô tả các trường dữ liệu, kiểu dữ liệu, đơn vị, miền giá trị và ghi chú sử dụng.

### `dataset_manifest.csv`
Ghi version, số dòng/cột, khóa chính, khóa ngoại, khoảng thời gian, kích thước và SHA-256.

## 4. Dữ liệu mẫu có nhãn

### `financial_scenarios_sample.csv`
Cung cấp một phần ground truth công khai với:
- `primary_scenario`;
- `alert_tags`;
- `severity`;
- `overall_health`.

Đây chỉ là nhãn mẫu, không phải toàn bộ ground truth.

### `financial_metrics_sample.csv`
Cung cấp một số chỉ tiêu tài chính đã tính đúng để đội thi đối chiếu công thức.

### `questions_sample.csv`
30 câu hỏi mẫu gồm:
- tra cứu số liệu;
- tỷ số tài chính;
- tăng trưởng;
- DSO, Inventory Days, DPO;
- xếp hạng;
- phân tích xu hướng;
- kiểm tra đối chiếu giữa các báo cáo.

### `answer_key_sample.csv`
Chứa đáp án tham chiếu, công thức, sai số cho phép và nguồn dữ liệu tương ứng.

## 5. Khóa dữ liệu

Khóa doanh nghiệp:

`company_id`

Khóa company-year:

`company_id + fiscal_year`

Các file tài chính có thể join trực tiếp bằng cặp khóa này.

## 6. Một số chỉ tiêu tài chính tham khảo

### Revenue Growth
`(Revenue_t - Revenue_(t-1)) / Revenue_(t-1) × 100`

### Gross Margin
`Gross Profit / Revenue × 100`

### Operating Margin
`Operating Profit / Revenue × 100`

### Net Margin
`Net Income / Revenue × 100`

### Current Ratio
`Total Current Assets / Total Current Liabilities`

### Quick Ratio
`(Cash + Accounts Receivable) / Total Current Liabilities`

### Debt/Assets
`(Short-term Debt + Long-term Debt) / Total Assets × 100`

### Debt/Equity
`(Short-term Debt + Long-term Debt) / Total Equity`

### ROA
`Net Income / Average Total Assets × 100`

### ROE
`Net Income / Average Total Equity × 100`

### CFO/Net Income
`Net Cash from Operating Activities / Net Income`

### Free Cash Flow
Do `capital_expenditure_vnd_mn` đã mang dấu âm:

`FCF = CFO + Capital Expenditure`

### DSO
`Average Accounts Receivable / Revenue × 365`

### Inventory Days
`Average Inventory / COGS × 365`

### DPO
`Average Accounts Payable / COGS × 365`

### Interest Coverage
`Operating Profit / Interest Expense`

### Working Capital
`Total Current Assets - Total Current Liabilities`

## 7. Quy ước năm 2021

Các chỉ tiêu cần dữ liệu năm trước như:
- Revenue Growth;
- ROA/ROE theo số dư bình quân;
- DSO;
- Inventory Days;
- DPO;
- tăng trưởng phải thu, tồn kho, nợ vay;

có thể để trống cho năm 2021 vì Data Pack công khai không cung cấp năm 2020.

**Không tự sinh hoặc giả định thêm số liệu 2020.**

## 8. Nhiệm vụ tối thiểu

Giải pháp cần:
1. đọc và hợp nhất dữ liệu;
2. tính các chỉ tiêu tài chính;
3. trực quan hóa xu hướng nhiều năm;
4. so sánh doanh nghiệp cùng ngành;
5. phát hiện tín hiệu đáng chú ý;
6. tạo `risk_score` hoặc mức độ ưu tiên;
7. giải thích lý do cảnh báo;
8. truy vết nhận xét về dữ liệu nguồn;
9. trả lời các câu hỏi Numerical QA.

## 9. Đầu ra chính

### `submission_output_template.csv`

Các nhóm trường:
- chỉ tiêu tài chính;
- `risk_score`;
- `predicted_primary_scenario`;
- `predicted_severity`;
- `predicted_overall_health`;
- `alert_tags`;
- `alert_reason`;
- `evidence_fields`;
- `priority_rank`;
- `confidence`;
- `model_name`;
- `processing_time_ms`.

Quy ước:
- `risk_score`: [0,1];
- `confidence`: [0,1];
- `predicted_severity`: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`;
- `predicted_overall_health`: `HEALTHY`, `WATCH`, `HIGH_RISK`, `RECOVERING`;
- `priority_rank`: số nguyên dương, số nhỏ hơn = ưu tiên cao hơn.

### `qa_submission_template.csv`

Mỗi dòng tương ứng một `question_id`, với:
- `answer`;
- `evidence_source_files`;
- `evidence_source_fields`;
- `explanation`;
- `confidence`;
- `model_name`;
- `processing_time_ms`.

## 10. KPI gợi ý

- Calculation Accuracy;
- Numerical QA Accuracy;
- Precision, Recall, F1 cho cảnh báo;
- Macro Recall theo loại tình huống;
- độ đúng xếp hạng;
- độ chính xác truy vết;
- thời gian xử lý.

Mục tiêu tham khảo:
- **Calculation Accuracy ≥ 95%**
- **Numerical QA Accuracy ≥ 85%**

## 11. Bronze / Silver / Gold

### Bronze
- tính đúng các tỷ số chính;
- phân tích xu hướng;
- so sánh doanh nghiệp;
- phát hiện các cảnh báo cơ bản;
- có dashboard/giao diện;
- giải thích được cảnh báo;
- có đánh giá định lượng.

### Silver
Có thể bổ sung:
- benchmark động;
- anomaly detection;
- scoring đa tiêu chí;
- calibration/threshold tuning;
- feature importance;
- giảm false positive;
- so sánh nhiều mô hình/phương pháp.

### Gold
Có thể bổ sung:
- explainability nâng cao;
- truy vết tự động từ nhận xét tới số liệu nguồn;
- analyst assistant;
- natural-language financial QA;
- audit log;
- scenario simulation hoặc stress testing;
- graph/relationship view.

Không bắt buộc deep learning, LLM hoặc GNN.

## 12. Nguyên tắc cảnh báo

Cảnh báo chỉ là tín hiệu hỗ trợ phân tích, không phải:
- kết luận gian lận;
- kết luận kiểm toán;
- khuyến nghị đầu tư;
- mô tả về một doanh nghiệp thực tế.

## 13. Yêu cầu truy vết

Mọi nhận xét quan trọng nên truy vết được về:
- file nguồn;
- trường dữ liệu;
- năm tài chính;
- công thức hoặc chuỗi số liệu.

Ví dụ:

`C006 | 2021-2025 | income_statement.csv | gross_profit_vnd_mn + revenue_vnd_mn | Gross Margin giảm mạnh`

## 14. Công cụ

BTC không thiên vị công cụ. Có thể sử dụng:
- Excel/Power BI;
- Python/R;
- SQL;
- no-code/low-code;
- machine learning;
- LLM/RAG/agent;
- hoặc kết hợp.

Điểm tập trung vào độ chính xác, giá trị giải pháp, khả năng giải thích, truy vết và vận hành.

## 15. Checklist trước khi nộp

- [ ] Đọc `data_dictionary.csv`.
- [ ] Kiểm tra đơn vị `VND_million`.
- [ ] Join đúng theo `company_id + fiscal_year`.
- [ ] Không tự tạo dữ liệu năm 2020.
- [ ] Kiểm tra công thức các tỷ số.
- [ ] Phân tích nhiều năm, không chỉ một năm đơn lẻ.
- [ ] Có benchmark đồng ngành.
- [ ] Giữ nguyên schema output template.
- [ ] Có bằng chứng cho nhận xét.
- [ ] Không thay đổi `company_id`, `fiscal_year`, `question_id`.
- [ ] Ghi rõ công cụ/mô hình sử dụng.

## 16. Ghi chú cuối

Data Pack được thiết kế để thể hiện nhiều trạng thái tài chính khác nhau: doanh nghiệp khỏe, tăng trưởng ổn định, suy giảm biên lợi nhuận, tăng nợ, tích tụ tồn kho, tăng phải thu, chất lượng dòng tiền yếu, căng thẳng thanh khoản và phục hồi.

Một chỉ tiêu đơn lẻ không đủ để kết luận. Giải pháp tốt nên kết hợp:

**xu hướng theo thời gian + so sánh đồng ngành + nhiều chỉ tiêu + bằng chứng nguồn**.
