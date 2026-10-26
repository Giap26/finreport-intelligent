"""FinReport Intelligence – Bàn làm việc của chuyên viên phân tích (Streamlit).

Chạy:   streamlit run 06_dashboard/app.py          (từ thư mục dự án FinReport_Intelligence)
Dữ liệu: đọc kết quả của run_pipeline.py trong 03_outputs/ và 05_submission/; nếu chưa có thì bấm "Chạy pipeline".
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT = Path(os.environ.get("FINREPORT_PROJECT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(PROJECT / "lib"))
sys.path.insert(0, str(PROJECT))

import finreport_common as cm  # noqa: E402
import finreport_metrics as fm  # noqa: E402
import finreport_qa as qa  # noqa: E402
import finreport_signals as fs  # noqa: E402
import finreport_assistant as fa  # noqa: E402
import finreport_whatif as wf  # noqa: E402

st.set_page_config(page_title="FinReport Intelligence", page_icon="◆", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  /* 1. Ẩn các thành phần ở góc trên bên phải */
  [data-testid="stToolbar"], [data-testid="stAppDeployButton"],
  [data-testid="stMainMenu"], [data-testid="stDecoration"], #MainMenu { 
      display: none !important; 
  }
  
  /* 2. Ẩn footer mặc định */
  footer { visibility: hidden !important; height: 0 !important; }
  
  /* 3. Đập tan tất cả các class Profile và Badge bằng các selector của bạn + bổ sung */
  [class*="viewerBadge"], 
  [class*="_profileContainer"],
  [class*="_viewerBadge"], 
  [data-testid="appCreatorAvatar"],
  [data-testid="stViewerBadge"],
  [data-testid="stAppStatus"],
  [class*="StyledAppStatus"],
  div[class*="manageApp"],
  button[class*="manageApp"],
  a[href*="share.streamlit.io/user/"],
  a[href*="github.com/giaphvtc"],
  iframe[title="Streamlit app status"],
  div[style*="position: fixed"][style*="bottom: 0px"][style*="right: 0px"] {
      display: none !important;
      visibility: hidden !important;
      height: 0 !important;
      width: 0 !important;
      opacity: 0 !important;
      pointer-events: none !important;
  }
</style>
""", unsafe_allow_html=True)


# ================================================================== TOKENS
INK, INK2, MUTED, RULE, PAPER, PANEL = "#13223F", "#4B5870", "#7A8599", "#DCE1E8", "#F3F5F8", "#FFFFFF"
BLUE, BLUE_DARK, BAND, BAND_EDGE = "#2a78d6", "#1c5cab", "#cde2fb", "#9ec5f4"
ORANGE = "#eb6834"
STATUS = {"LOW": "#0ca30c", "MEDIUM": "#fab219", "HIGH": "#ec835a", "CRITICAL": "#d03b3b"}
TINT = {"LOW": "#e3f4e3", "MEDIUM": "#fef0d1", "HIGH": "#fbe3d9", "CRITICAL": "#f6dcdc"}
GLYPH = {"LOW": "●", "MEDIUM": "▲", "HIGH": "◆", "CRITICAL": "■"}
SEV_VI = {"LOW": "Thấp", "MEDIUM": "Trung bình", "HIGH": "Cao", "CRITICAL": "Nghiêm trọng"}
HEALTH_VI = {"HEALTHY": "Khỏe mạnh", "WATCH": "Theo dõi", "HIGH_RISK": "Rủi ro cao", "RECOVERING": "Đang phục hồi"}
SCEN_VI = {"NORMAL_STABLE": "Ổn định", "STRONG_PERFORMANCE": "Vượt trội", "OPERATIONAL_IMPROVEMENT": "Đang cải thiện",
           "FINANCIAL_RECOVERY": "Phục hồi", "DISTRESS_BASELINE": "Khủng hoảng", "REVENUE_GROWTH_WEAK_CASH": "Tăng trưởng nóng, tiền yếu",
           "RECEIVABLES_RISK": "Phải thu phình to", "INVENTORY_BUILDUP": "Tồn kho tích tụ", "DEBT_EXPANSION": "Mở rộng bằng nợ",
           "MARGIN_DETERIORATION": "Suy giảm biên", "LIQUIDITY_STRESS": "Căng thẳng thanh khoản",
           "PROFIT_CASH_DIVERGENCE": "Lãi – tiền phân kỳ", "MULTI_FACTOR_STRESS": "Đa yếu tố"}
COMP_VI = {"cash": "Dòng tiền", "coverage": "Khả năng trả lãi", "leverage": "Đòn bẩy", "margin": "Biên lợi nhuận",
           "working_capital": "Vốn lưu động", "loss": "Lỗ"}
FONT = "Be Vietnam Pro, system-ui, sans-serif"

st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"], .stMarkdown, .stDataFrame, button, input, textarea, select {{ font-family: {FONT}; }}
  .stApp {{ background: {PAPER}; color: {INK}; }}
  /* ---------- thanh bên ---------- */
  section[data-testid="stSidebar"] {{ background: linear-gradient(180deg, #0F1B33 0%, {INK} 100%); border-right: 1px solid #1d3157; }}
  section[data-testid="stSidebar"][aria-expanded="true"] {{ min-width: 296px; max-width: 296px; }}
  section[data-testid="stSidebar"] * {{ color: #E8ECF3 !important; }}
  section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.10); }}
  .brand {{ display: flex; align-items: center; gap: .75rem; padding: .3rem .1rem 1.1rem .1rem;
            border-bottom: 1px solid rgba(255,255,255,.10); margin-bottom: 1.1rem; }}
  .brand .logo {{ width: 42px; height: 42px; border-radius: 11px; flex: none; display: flex; align-items: center; justify-content: center;
                  background: linear-gradient(135deg, #3b8ae6, #1c5cab); font-size: 20px; font-weight: 700;
                  box-shadow: 0 2px 10px rgba(42,120,214,.5); }}
  .brand .name {{ font-size: 1.05rem; font-weight: 700; line-height: 1.2; color: #FFFFFF !important; }}
  .brand .tag {{ font-size: .68rem; letter-spacing: .09em; text-transform: uppercase; color: #8FB4E8 !important; margin-top: .1rem; }}
  .nav-label {{ font-size: .68rem; letter-spacing: .1em; text-transform: uppercase; font-weight: 600;
                color: #7F93B5 !important; margin: 0 0 .5rem .45rem; }}
  /* điều hướng: ẩn nút tròn, tô sáng mục đang chọn (hỗ trợ cả cấu trúc cũ và mới của Streamlit) */
  section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: .22rem; }}
  section[data-testid="stSidebar"] div[role="radiogroup"] > div {{ width: 100%; }}
  section[data-testid="stSidebar"] label[data-baseweb="radio"], section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
        width: 100%; margin: 0; padding: .6rem .8rem; border-radius: 10px; border-left: 3px solid transparent;
        cursor: pointer; transition: background .15s; box-sizing: border-box; }}
  section[data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {{ display: none; }}
  section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
  section[data-testid="stSidebar"] label[data-baseweb="radio"]:hover, section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {{ background: rgba(255,255,255,.07); }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label p {{ font-size: .95rem; font-weight: 500; margin: 0; }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{ background: rgba(42,120,214,.30); border-left-color: #5BA0F0; }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {{ font-weight: 700; color: #FFFFFF !important; }}
  section[data-testid="stSidebar"] .stButton button {{ background: #2a78d6; border: 1px solid #2a78d6; font-weight: 600; border-radius: 10px; padding: .55rem 1rem; }}
  section[data-testid="stSidebar"] .stButton button:hover {{ background: #1c5cab; border-color: #5BA0F0; }}
  .status {{ border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.045); border-radius: 12px; padding: .75rem .9rem; margin-top: .9rem; }}
  .status .r {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; font-size: .8rem; color: #B9C6DC !important; }}
  .status .r b {{ color: #FFFFFF !important; font-weight: 600; }}
  .status .r + .r {{ margin-top: .35rem; }}
  .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: .4rem; }}
  .side-foot {{ font-size: .72rem; line-height: 1.45; color: #7F93B5 !important; margin-top: 1.1rem; padding-top: .8rem; border-top: 1px solid rgba(255,255,255,.10); }}
  .block-container {{ padding-top: 1.6rem; max-width: 1320px; }}
  h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
  h1 {{ font-weight: 700; font-size: 1.85rem; margin-bottom: 0.1rem; }}
  .lede {{ color: {INK2}; font-size: .98rem; line-height: 1.55; max-width: none; margin: .3rem 0 1.3rem 0;
           background: {PANEL}; border: 1px solid {RULE}; border-left: 4px solid {BLUE}; border-radius: 10px; padding: .8rem 1.1rem; }}
  .kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 0 0 1.4rem 0; }}
  .kpi-tile {{ background: {PANEL}; border: 1px solid {RULE}; border-top: 3px solid {BLUE}; border-radius: 12px; padding: .85rem 1.1rem; }}
  .kpi-tile b {{ display: block; font-size: 1.65rem; font-weight: 700; color: {INK}; line-height: 1.15; font-variant-numeric: tabular-nums; }}
  .kpi-tile span {{ color: {INK2}; font-size: .82rem; }}
  .sec {{ margin: 1.5rem 0 .65rem 0; }}
  .sec h3 {{ margin: 0 !important; padding: 0 !important; font-size: 1.12rem; }}
  .sec .hint {{ color: {MUTED}; font-size: .86rem; margin-top: .15rem; }}
  .sec {{ line-height: 1.3; }}
  .rank-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .85rem; }}
  .rank-card {{ background: {PANEL}; border: 1px solid {RULE}; border-left: 5px solid {RULE}; border-radius: 12px; padding: .8rem 1rem; }}
  .rank-card .top {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; }}
  .rank-card .no {{ font-size: 1.35rem; font-weight: 700; color: {BLUE_DARK}; font-variant-numeric: tabular-nums; }}
  .rank-card .cid {{ font-weight: 700; margin-left: .35rem; }}
  .rank-card .nm {{ color: {MUTED}; font-size: .78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: .15rem; }}
  .rank-card .scn {{ font-weight: 600; margin-top: .45rem; }}
  .rank-card .meta {{ color: {INK2}; font-size: .8rem; margin-top: .1rem; }}
  @media (max-width: 1100px) {{ .kpi-row, .rank-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  .panel {{ background: {PANEL}; border: 1px solid {RULE}; border-radius: 10px; padding: 1rem 1.15rem; }}
  .kpis {{ display: flex; gap: 2.2rem; flex-wrap: wrap; margin: 0.2rem 0 1.2rem 0; }}
  .kpi b {{ display: block; font-size: 1.35rem; font-weight: 600; color: {INK}; font-variant-numeric: tabular-nums; }}
  .kpi span {{ color: {INK2}; font-size: 0.82rem; }}
  .badge {{ display: inline-flex; align-items: center; gap: .35rem; padding: .18rem .6rem; border-radius: 999px;
            font-size: .82rem; font-weight: 600; border: 1px solid; white-space: nowrap; }}
  .chip {{ display: inline-block; padding: .16rem .55rem; margin: .12rem .25rem .12rem 0; border-radius: 6px;
           background: #EAF1FB; color: {BLUE_DARK}; font-size: .8rem; font-weight: 500; }}
  .chip.pos {{ background: #E6F4E6; color: #0b6b0b; }}
  .reason li {{ margin-bottom: .3rem; color: {INK}; }}
  .muted {{ color: {MUTED}; font-size: .85rem; }}
  .big-answer {{ font-size: 1.6rem; font-weight: 600; color: {INK}; font-variant-numeric: tabular-nums; }}
  .timeline {{ display: flex; gap: .5rem; flex-wrap: wrap; margin: .3rem 0 1rem 0; }}
  .yr {{ border: 1px solid {RULE}; background: {PANEL}; border-radius: 8px; padding: .45rem .6rem; min-width: 120px; }}
  .yr .y {{ font-size: .78rem; color: {INK2}; }}
  .yr .s {{ font-size: .86rem; font-weight: 600; color: {INK}; }}
  :focus-visible {{ outline: 2px solid {BLUE}; outline-offset: 2px; }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
""", unsafe_allow_html=True)


def badge(sev: str) -> str:
    return (f"<span class='badge' style='color:{INK};background:{TINT[sev]};border-color:{STATUS[sev]}'>"
            f"<span style='color:{STATUS[sev]}'>{GLYPH[sev]}</span>{SEV_VI[sev]}</span>")


def health_badge(h: str) -> str:
    col = {"HEALTHY": STATUS["LOW"], "WATCH": STATUS["MEDIUM"], "HIGH_RISK": STATUS["CRITICAL"], "RECOVERING": BLUE}[h]
    return f"<span class='badge' style='color:{INK};background:{PANEL};border-color:{col}'>{HEALTH_VI[h]}</span>"


def pretty(res: dict) -> str:
    """Hiển thị đáp án kèm đơn vị; giữ nguyên chữ với câu xếp hạng/văn bản."""
    exp, ans = res.get("expected_answer_type", ""), str(res.get("answer", ""))
    try:
        v = float(ans)
    except ValueError:
        return ans.replace(";", "<br>")
    fmt = {"numeric_vnd_mn": f"{v:,.0f} triệu VND", "numeric_percentage": f"{v:,.2f}%", "numeric_ratio": f"{v:,.3f} lần",
           "numeric_days": f"{v:,.1f} ngày", "numeric_percentage_point": f"{v:,.2f} điểm %"}
    return fmt.get(exp, ans)


def style_fig(fig, height=360, legend=True):
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=8, r=8, t=36, b=8),
                      font=dict(family=FONT, color=INK2, size=12), paper_bgcolor=PANEL, plot_bgcolor=PANEL,
                      hoverlabel=dict(bgcolor=PANEL, bordercolor=RULE, font=dict(family=FONT, color=INK)),
                      showlegend=legend, legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, font=dict(color=INK2)))
    fig.update_xaxes(showgrid=False, linecolor=RULE, tickfont=dict(color=INK2), type="category")
    fig.update_yaxes(gridcolor="#EDF0F4", gridwidth=1, zeroline=False, linecolor=RULE, tickfont=dict(color=INK2))
    return fig


# ================================================================== DỮ LIỆU
@st.cache_data(show_spinner=False)
def load_all(stamp: float):
    cm.setup(PROJECT)
    out = PROJECT / "03_outputs"
    rd = lambda step, f: pd.read_csv(out / step / f, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    D = {"summary": json.loads((out / "pipeline_summary.json").read_text(encoding="utf-8"))}
    for key, step, f in [("master", "step0", "master_panel.csv"), ("integrity", "step0", "integrity_checks.csv"),
                         ("lineage", "step0", "field_lineage.csv"), ("rules", "step1_3", "accounting_rule_summary.csv"),
                         ("acc", "step1_3", "accounting_checks.csv"), ("wide", "step1_3", "metrics_wide.csv"),
                         ("long", "step1_3", "metrics_long.csv"), ("supp", "step1_3", "metrics_supplementary.csv"),
                         ("catalog", "step1_3", "metric_catalog.csv"), ("qa_grading", "step1_3", "qa_grading.csv"),
                         ("verify", "step1_3", "verify_dual.csv"), ("msample", "step1_3", "metrics_sample_comparison.csv"),
                         ("para", "step1_3", "assistant_paraphrase_test.csv"), ("features", "step4_6", "features.csv"),
                         ("pred", "step4_6", "predictions.csv"), ("eval", "step4_6", "evaluation_vs_baseline.csv"),
                         ("labels_cmp", "step4_6", "label_comparison.csv"), ("sens", "step4_6", "sensitivity_global.csv")]:
        p = out / step / f
        D[key] = rd(step, f) if p.exists() else None
    for df in [D["master"], D["wide"], D["pred"], D["features"], D["long"], D["supp"]]:
        if df is not None:
            df["fiscal_year"] = df["fiscal_year"].astype(int)
    D["pred"]["alert_tags"] = D["pred"]["alert_tags"].fillna("")
    D["long"]["flag"] = D["long"]["flag"].fillna("")
    D["names"] = dict(zip(D["master"]["company_id"], D["master"]["company_name"]))
    D["audit"] = cm.read_audit()
    man = PROJECT / "05_submission" / "submission_manifest.csv"
    D["manifest"] = pd.read_csv(man, encoding="utf-8-sig") if man.exists() else None
    return D


@st.cache_resource(show_spinner=False)
def get_engine(stamp: float):
    D = load_all(stamp)
    return qa.QAEngine(D["master"], D["wide"], D["long"])


summary_path = PROJECT / "03_outputs" / "pipeline_summary.json"

# ------------------------------------------------------------------ thanh bên
PAGES = ["Sổ cái rủi ro", "Hồ sơ doanh nghiệp", "Thẻ cảnh báo & truy vết", "Mô phỏng what-if",
         "Trợ lý hỏi đáp", "Chất lượng mô hình", "Dữ liệu & nhật ký"]
NAV_ICON = {"Sổ cái rủi ro": "grid_view", "Hồ sơ doanh nghiệp": "domain", "Thẻ cảnh báo & truy vết": "fact_check",
            "Mô phỏng what-if": "tune", "Trợ lý hỏi đáp": "forum", "Chất lượng mô hình": "monitoring",
            "Dữ liệu & nhật ký": "database"}
with st.sidebar:
    st.markdown("<div class='brand'><div class='logo'>◆</div><div><div class='name'>SÁU CHÚ VỊT HỒNG</div>"
                "<div class='tag'>fESTIVAL CĐS</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='nav-label'>Điều hướng</div>", unsafe_allow_html=True)
    page = st.radio("Trang", PAGES, format_func=lambda p: f":material/{NAV_ICON[p]}:  {p}", label_visibility="collapsed")
    st.markdown("<div class='nav-label' style='margin-top:1.5rem'>Pipeline</div>", unsafe_allow_html=True)
    quick = st.toggle("Chạy nhanh (bỏ kiểm thử nặng)", value=True)
    if st.button("Chạy lại pipeline", use_container_width=True, icon=":material/play_arrow:"):
        import run_pipeline
        logs = []
        with st.spinner("Đang chạy 8 bước…"):
            res = run_pipeline.run_all(PROJECT, quick=quick, log_fn=logs.append)
        st.cache_data.clear(); st.cache_resource.clear()
        (st.success if res["status"] == "PASS" else st.error)(f"{res['status']} · {res['total_ms'] / 1000:.1f} s")
    if summary_path.exists():
        s_ = json.loads(summary_path.read_text(encoding="utf-8"))
        ok_ = s_["status"] == "PASS"
        st.markdown(f"<div class='status'>"
                    f"<div class='r'><span>Trạng thái</span><b><span class='dot' style='background:{'#2fbf71' if ok_ else '#e5534b'}'></span>{s_['status']}</b></div>"
                    f"<div class='r'><span>Chạy gần nhất</span><b style='white-space:nowrap'>{s_['finished_at'][:16].replace('T', ' ')}</b></div>"
                    f"<div class='r'><span>Phạm vi</span><b>12 DN · 2021–2025</b></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='side-foot'>Dữ liệu giả lập. Cảnh báo chỉ là tín hiệu hỗ trợ phân tích, "
                "không phải kết luận kiểm toán, gian lận hay khuyến nghị đầu tư.</div>", unsafe_allow_html=True)

if not summary_path.exists():
    st.title("Chưa có kết quả phân tích")
    st.markdown("<p class='lede'>Bấm <b>Chạy lại pipeline</b> ở thanh bên để xử lý Data Pack trong "
                "<code>01_datapack/</code>. Toàn bộ 8 bước mất khoảng 10 giây.</p>", unsafe_allow_html=True)
    st.stop()

STAMP = summary_path.stat().st_mtime
D = load_all(STAMP)
pred, wide, master, feats = D["pred"], D["wide"], D["master"], D["features"]
YEARS = sorted(pred["fiscal_year"].unique())
COMPANIES = sorted(pred["company_id"].unique())
label = lambda c: f"{c} · {D['names'].get(c, '')}"
S = D["summary"]["steps"]
K3, K6 = S.get("step3_verify_qa", {}).get("kpi", {}), S.get("step6_scoring", {}).get("kpi", {})


def row(cid, y):
    return pred[(pred["company_id"] == cid) & (pred["fiscal_year"] == y)].iloc[0]


# ================================================================== 1. SỔ CÁI RỦI RO
if page == "Sổ cái rủi ro":
    st.title("Sổ cái rủi ro")
    st.markdown("<p class='lede'>Mỗi ô là một doanh nghiệp trong một năm: màu và ký hiệu cho mức độ cảnh báo, con số là "
                "risk score (0–1). Đọc theo hàng để thấy doanh nghiệp xấu đi hay phục hồi; đọc theo cột để so sánh trong năm.</p>",
                unsafe_allow_html=True)

    # ---- Hàng 1: chỉ số tổng quan
    st.markdown(f"<div class='kpi-row'>"
                f"<div class='kpi-tile'><b>{K3.get('calculation_accuracy', 0):.0%}</b><span>Calculation Accuracy</span></div>"
                f"<div class='kpi-tile'><b>{K3.get('numerical_qa_accuracy', 0):.0%}</b><span>Numerical QA</span></div>"
                f"<div class='kpi-tile'><b>{K6.get('tag_f1_micro', 0):.1%}</b><span>Tag F1 (18 nhãn mẫu)</span></div>"
                f"<div class='kpi-tile'><b>{D['summary']['total_ms'] / 1000:.1f} s</b><span>Toàn pipeline</span></div></div>",
                unsafe_allow_html=True)

    # ---- Hàng 2: ma trận sức khỏe doanh nghiệp (toàn chiều rộng)
    sev_n = pred.assign(s=pred["predicted_severity"].map(fs.SEV_ORDER))
    z = sev_n.pivot(index="company_id", columns="fiscal_year", values="s").loc[COMPANIES[::-1]]
    score = pred.pivot(index="company_id", columns="fiscal_year", values="risk_score").loc[COMPANIES[::-1]]
    scen = pred.pivot(index="company_id", columns="fiscal_year", values="predicted_primary_scenario").loc[COMPANIES[::-1]]
    sevs = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    cscale = []
    for i, s_ in enumerate(sevs):
        cscale += [[i / 4, TINT[s_]], [(i + 1) / 4, TINT[s_]]]
    hover = [[f"<b>{c}</b> · {y}<br>{SEV_VI[sevs[int(z.loc[c, y])]]} · risk {score.loc[c, y]:.2f}<br>{SCEN_VI[scen.loc[c, y]]}"
              for y in z.columns] for c in z.index]
    fig = go.Figure(go.Heatmap(z=z.values, x=[str(y) for y in z.columns], y=[label(c) for c in z.index],
                               colorscale=cscale, zmin=-0.5, zmax=3.5, showscale=False, xgap=3, ygap=3,
                               text=hover, hovertemplate="%{text}<extra></extra>"))
    for ci, c in enumerate(z.index):
        for yi, y in enumerate(z.columns):
            s_ = sevs[int(z.loc[c, y])]
            fig.add_annotation(x=yi, y=ci, showarrow=False,      # vị trí danh mục (chuỗi "2023" bị hiểu là số)
                               text=f"<span style='color:{STATUS[s_]}'>{GLYPH[s_]}</span> {score.loc[c, y]:.2f}",
                               font=dict(family=FONT, size=14, color=INK))
    style_fig(fig, height=640, legend=False)
    fig.update_xaxes(side="top", tickfont=dict(size=14, color=INK))
    fig.update_yaxes(tickfont=dict(size=13, color=INK), gridcolor=PANEL, automargin=True)
    st.markdown("<div class='sec'><h3>Ma trận sức khỏe doanh nghiệp</h3>"
                "<div class='hint'>12 doanh nghiệp × 5 năm · ký hiệu và màu = mức độ cảnh báo · số = risk score</div></div>",
                unsafe_allow_html=True)
    with st.container(border=True):
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown(" ".join(badge(s_) for s_ in sevs) + "<span class='muted'>&nbsp; mức độ cảnh báo</span>", unsafe_allow_html=True)

    # ---- Hàng 3: xếp hạng ưu tiên
    h1, h2 = st.columns([3, 1], vertical_alignment="bottom")
    with h2:
        y_sel = st.selectbox("Năm xếp hạng", YEARS[::-1], index=0)
    with h1:
        st.markdown(f"<div class='sec' style='margin-top:1.1rem'><h3>Xếp hạng ưu tiên năm {y_sel}</h3>"
                    f"<div class='hint'>8 doanh nghiệp cần xem trước · xếp theo mức độ, sau đó theo risk score</div></div>",
                    unsafe_allow_html=True)
    top = pred[pred["fiscal_year"] == y_sel].sort_values("priority_rank_in_year").head(8)
    cards = "".join(
        f"<div class='rank-card' style='border-left-color:{STATUS[r.predicted_severity]}'>"
        f"<div class='top'><div><span class='no'>#{r.priority_rank_in_year}</span><span class='cid'>{r.company_id}</span></div>{badge(r.predicted_severity)}</div>"
        f"<div class='nm'>{D['names'].get(r.company_id, '')}</div>"
        f"<div class='scn'>{SCEN_VI[r.predicted_primary_scenario]}</div>"
        f"<div class='meta'>risk {r.risk_score:.2f} · tin cậy {r.confidence:.2f}</div></div>"
        for r in top.itertuples())
    st.markdown(f"<div class='rank-grid'>{cards}</div>", unsafe_allow_html=True)

    # ---- Hàng 4: phân bố kịch bản và số DN theo mức độ
    st.markdown("<div class='sec'><h3>Phân bố kịch bản và mức độ</h3>"
                "<div class='hint'>Kịch bản chính của năm mới nhất và số doanh nghiệp theo mức độ từng năm</div></div>",
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        yy = YEARS[-1]
        cnt = pred[pred["fiscal_year"] == yy]["predicted_primary_scenario"].map(SCEN_VI).value_counts().sort_values()
        f2 = go.Figure(go.Bar(x=cnt.values, y=cnt.index, orientation="h", marker=dict(color=BLUE, cornerradius=4),
                              width=0.55, text=cnt.values, textposition="outside", textfont=dict(color=INK2),
                              hovertemplate="%{y}: %{x} DN<extra></extra>"))
        style_fig(f2, height=330, legend=False).update_layout(title=dict(text=f"Kịch bản chính năm {yy}", font=dict(color=INK, size=14)))
        f2.update_xaxes(visible=False, type="linear")
        with st.container(border=True):
            st.plotly_chart(f2, use_container_width=True, config={"displayModeBar": False})
    with c2:
        tab = pd.crosstab(pred["fiscal_year"], pred["predicted_severity"]).reindex(columns=sevs, fill_value=0)
        tab.columns = [f"{GLYPH[s_]} {SEV_VI[s_]}" for s_ in sevs]
        with st.container(border=True):
            st.markdown("**Số doanh nghiệp theo mức độ, từng năm**")
            st.dataframe(tab, use_container_width=True)

# ================================================================== 2. HỒ SƠ DOANH NGHIỆP
elif page == "Hồ sơ doanh nghiệp":
    cid = st.selectbox("Doanh nghiệp", COMPANIES, format_func=label)
    info = master[master["company_id"] == cid].iloc[0]
    st.title(f"{cid} · {info['company_name']}")
    st.markdown(f"<p class='lede'>Mã {info['ticker_simulated']} · quy mô {info['company_size_band']} · "
                f"so với 11 doanh nghiệp cùng ngành. Dải xanh nhạt là khoảng P25–P75 của ngành, đường gạch là trung vị.</p>",
                unsafe_allow_html=True)
    tl = "".join(f"<div class='yr'><div class='y'>{r.fiscal_year}</div><div class='s'>{SCEN_VI[r.predicted_primary_scenario]}</div>"
                 f"<div style='margin-top:.3rem'>{badge(r.predicted_severity)}</div></div>"
                 for r in pred[pred["company_id"] == cid].sort_values("fiscal_year").itertuples())
    st.markdown(f"<div class='timeline'>{tl}</div>", unsafe_allow_html=True)

    def trend_chart(mid, height=250, title=None):
        meta = fm.METRIC_BY_ID[mid]
        q = wide.groupby("fiscal_year")[mid].quantile([0.25, 0.5, 0.75]).unstack()
        me = wide[wide["company_id"] == cid].set_index("fiscal_year")[mid]
        x = [str(y) for y in q.index]
        f = go.Figure()
        f.add_trace(go.Scatter(x=x, y=q[0.75], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        f.add_trace(go.Scatter(x=x, y=q[0.25], mode="lines", fill="tonexty", fillcolor="rgba(42,120,214,0.10)", line=dict(width=0),
                               name="P25–P75 ngành", hoverinfo="skip"))
        f.add_trace(go.Scatter(x=x, y=q[0.5], mode="lines", line=dict(color=MUTED, width=1.5, dash="dash"), name="Trung vị ngành",
                               hovertemplate="Trung vị %{y:.2f}<extra></extra>"))
        f.add_trace(go.Scatter(x=[str(y) for y in me.index], y=me.values, mode="lines+markers", name=cid,
                               line=dict(color=BLUE, width=2), marker=dict(size=8, color=BLUE, line=dict(color=PANEL, width=2)),
                               hovertemplate=f"{cid} %{{y:.2f}}<extra></extra>"))
        last = me.dropna()
        if len(last):
            f.add_annotation(x=x.index(str(last.index[-1])), y=last.iloc[-1], text=f"{last.iloc[-1]:.2f}", showarrow=False,
                             xshift=22, font=dict(color=INK, size=12))
        style_fig(f, height=height, legend=title is None)
        f.update_layout(title=dict(text=title or f"{meta.name_vi} ({meta.unit})", font=dict(color=INK, size=13)),
                        hovermode="x unified")
        return f

    mids = {fm.METRIC_BY_ID[m].name_vi: m for m in fm.METRIC_IDS}
    pick = st.selectbox("Chỉ tiêu", list(mids), index=list(mids.values()).index("cfo_to_net_income_x"))
    st.plotly_chart(trend_chart(mids[pick], height=330), use_container_width=True, config={"displayModeBar": False})
    st.markdown("**Sáu chỉ tiêu then chốt** – mỗi biểu đồ một trục riêng")
    grid = ["gross_margin_pct", "cfo_to_net_income_x", "dso_days", "inventory_days", "debt_to_equity_x", "interest_coverage_x"]
    for i in range(0, 6, 3):
        cols = st.columns(3)
        for c_, m_ in zip(cols, grid[i:i + 3]):
            c_.plotly_chart(trend_chart(m_, height=230, title=fm.METRIC_BY_ID[m_].name_vi), use_container_width=True,
                            config={"displayModeBar": False})
    flags = D["long"][(D["long"]["company_id"] == cid) & (D["long"]["flag"].isin(["NON_POSITIVE_NET_INCOME", "NON_POSITIVE_OPERATING_PROFIT", "NEGATIVE_EQUITY_DENOMINATOR"]))]
    if len(flags):
        st.warning("Lưu ý diễn giải: " + "; ".join(f"{r.metric_id} năm {r.fiscal_year} = {r.value:.2f} ({r.flag})" for r in flags.itertuples())
                   + ". Giá trị đúng công thức nhưng mẫu số âm/bằng 0 nên không đọc theo nghĩa thông thường.")

# ================================================================== 3. THẺ CẢNH BÁO & TRUY VẾT
elif page == "Thẻ cảnh báo & truy vết":
    st.title("Thẻ cảnh báo & truy vết")
    st.markdown("<p class='lede'>Mỗi cảnh báo đi kèm lý do bằng số liệu và đường dẫn về đúng file, trường, năm trong dữ liệu gốc. "
                "Bảng bằng chứng bên dưới đọc thẳng từ báo cáo tài chính, không qua bước tính trung gian.</p>", unsafe_allow_html=True)
    order = pred.sort_values("priority_rank")
    opts = [(r.company_id, r.fiscal_year) for r in order.itertuples()]
    c_, y_ = st.selectbox("Chọn company-year (xếp theo mức ưu tiên)", opts,
                          format_func=lambda t: f"#{int(row(*t).priority_rank)} · {t[0]} · {t[1]} · {SEV_VI[row(*t).predicted_severity]}")
    r = row(c_, y_)
    a, b = st.columns([1.2, 1])
    with a:
        st.markdown(f"<div class='panel'><div style='display:flex;gap:.5rem;align-items:center;flex-wrap:wrap'>"
                    f"<h3 style='margin:0'>{c_} · {y_}</h3>{badge(r.predicted_severity)}{health_badge(r.predicted_overall_health)}</div>"
                    f"<p style='margin:.5rem 0 .2rem 0'><b>{SCEN_VI[r.predicted_primary_scenario]}</b> "
                    f"<span class='muted'>({r.predicted_primary_scenario})</span></p>"
                    f"<p class='muted'>risk score {r.risk_score:.2f} · độ tin cậy {r.confidence:.2f} · ưu tiên #{int(r.priority_rank)} toàn danh mục, "
                    f"#{int(r.priority_rank_in_year)} trong năm</p>"
                    + "".join(f"<span class='chip{' pos' if t in fs.POSITIVE_TAGS else ''}'>{t}</span>" for t in r.alert_tags.split(";") if t)
                    + "<ul class='reason' style='margin-top:.7rem'>"
                    + "".join(f"<li>{x.strip()}</li>" for x in r.alert_reason.split("] ", 1)[-1].split(";"))
                    + "</ul></div>", unsafe_allow_html=True)
    with b:
        comp = pd.Series({COMP_VI[k]: r[f"rc_{k}"] * w for k, w in fs.RISK_WEIGHTS.items()}).sort_values()
        f3 = go.Figure(go.Bar(x=comp.values, y=comp.index, orientation="h", marker=dict(color=BLUE, cornerradius=4), width=0.55,
                              text=[f"{v:.3f}" for v in comp.values], textposition="outside", textfont=dict(color=INK2),
                              hovertemplate="%{y}: %{x:.3f}<extra></extra>"))
        style_fig(f3, height=300, legend=False).update_layout(
            title=dict(text=f"Đóng góp vào risk score {r.risk_score:.2f}", font=dict(color=INK, size=13)))
        f3.update_xaxes(range=[0, max(0.21, comp.max() * 1.25)], showgrid=True, gridcolor="#EDF0F4", type="linear")
        st.plotly_chart(f3, use_container_width=True, config={"displayModeBar": False})
        acc = D["acc"]
        ar = acc[(acc["company_id"] == c_) & (acc["fiscal_year"] == y_)]["status"].value_counts().to_dict()
        st.markdown(f"<span class='muted'>Verify trước khi nhận xét: {ar.get('PASS', 0)} luật kế toán PASS · "
                    f"{ar.get('FAIL', 0)} FAIL · {ar.get('N/A', 0)} N/A cho dòng này.</span>", unsafe_allow_html=True)
    st.subheader("Bằng chứng từ dữ liệu gốc")
    ev = []
    for item in str(r.evidence_fields).split("|"):
        parts = item.split(":")
        if len(parts) != 4:
            continue
        file, cc, yrs, field = parts
        y0, y1 = (int(yrs.split("-")[0]), int(yrs.split("-")[-1]))
        vals = master[(master["company_id"] == cc) & master["fiscal_year"].between(y0, y1)].set_index("fiscal_year")
        rec = {"file": file, "trường": field}
        for yv in range(y0, y1 + 1):
            rec[str(yv)] = vals.at[yv, field] if field in vals.columns and yv in vals.index else np.nan
        ev.append(rec)
    evdf = pd.DataFrame(ev)
    st.dataframe(evdf, use_container_width=True, hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="%,.0f") for c in evdf.columns if c.isdigit()})
    st.caption("Chuỗi truy vết gốc: " + r.evidence_fields.replace("|", " · "))

# ================================================================== 4. WHAT-IF
elif page == "Mô phỏng what-if":
    st.title("Mô phỏng what-if")
    st.markdown("<p class='lede'>Thay đổi một vài giả định cho một company-year, hệ thống điều chỉnh các khoản mục liên quan "
                "theo quan hệ kế toán, chạy lại toàn bộ chỉ tiêu và cảnh báo, rồi kiểm tra kịch bản vẫn đúng 32 luật kế toán. "
                "Đây là mô phỏng hỗ trợ phân tích, không phải dự báo.</p>", unsafe_allow_html=True)
    a, b = st.columns([1, 2])
    with a:
        cid = st.selectbox("Doanh nghiệp", COMPANIES, format_func=label, index=COMPANIES.index("C003") if "C003" in COMPANIES else 0)
        yr = st.selectbox("Năm", YEARS[1:][::-1])
        lev = {}
        for k, (name, lo, hi, dv, help_) in wf.LEVERS.items():
            lev[k] = st.slider(name, float(lo), float(hi), float(dv), step=1.0 if hi - lo > 20 else 0.5, help=help_)
        cur = wide[(wide["company_id"] == cid) & (wide["fiscal_year"] == yr)].iloc[0]
        st.caption(f"Hiện tại: DSO {cur['dso_days']:.0f} ngày · tồn kho {cur['inventory_days']:.0f} ngày · ICR {cur['interest_coverage_x']:.1f}x")
    with b:
        res = wf.simulate(master, cid, yr, lev)
        o = res["outcome"]
        s0, s1 = o.loc["predicted_severity", "trước"], o.loc["predicted_severity", "sau"]
        st.markdown(f"<div class='panel'><div style='display:flex;gap:1.6rem;flex-wrap:wrap;align-items:center'>"
                    f"<div><div class='muted'>Trước</div>{badge(s0)}<div class='big-answer'>{o.loc['risk_score', 'trước']:.2f}</div>"
                    f"<div class='muted'>{SCEN_VI[o.loc['predicted_primary_scenario', 'trước']]}</div></div>"
                    f"<div style='font-size:1.6rem;color:{MUTED}'>→</div>"
                    f"<div><div class='muted'>Sau</div>{badge(s1)}<div class='big-answer'>{o.loc['risk_score', 'sau']:.2f}</div>"
                    f"<div class='muted'>{SCEN_VI[o.loc['predicted_primary_scenario', 'sau']]}</div></div>"
                    f"<div class='muted' style='max-width:34ch'>Kiểm tra kế toán của kịch bản: "
                    f"<b style='color:{INK}'>{res['identity_pass']}/{res['identity_pass'] + res['identity_fail']}</b> luật PASS</div>"
                    f"</div><p class='muted' style='margin-top:.6rem'>Lý do sau mô phỏng: {res['reason_after']}</p></div>",
                    unsafe_allow_html=True)
        comp = res["components"]
        f4 = go.Figure()
        for col_, color, nm in [("trước", BLUE, "Trước"), ("sau", ORANGE, "Sau")]:
            f4.add_trace(go.Bar(y=[COMP_VI[x] for x in comp["thành phần"]], x=comp[col_], name=nm, orientation="h",
                                marker=dict(color=color, cornerradius=4), hovertemplate=f"{nm} %{{x:.2f}}<extra>%{{y}}</extra>"))
        style_fig(f4, height=320).update_layout(barmode="group", bargap=0.5, bargroupgap=0.15,
                                                title=dict(text="Thành phần rủi ro (0–1)", font=dict(color=INK, size=13)))
        f4.update_xaxes(range=[0, 1.05], showgrid=True, gridcolor="#EDF0F4", type="linear")
        st.plotly_chart(f4, use_container_width=True, config={"displayModeBar": False})
        mt = res["metrics"]
        mt = mt[mt["thay đổi"].abs() > 1e-6]
        if len(mt):
            st.markdown("**Chỉ tiêu thay đổi**")
            st.dataframe(mt.drop(columns="metric_id"), hide_index=True, use_container_width=True,
                         column_config={k: st.column_config.NumberColumn(format="%.2f") for k in ["trước", "sau", "thay đổi"]})
        else:
            st.info("Chưa thay đổi giả định nào – kéo thanh trượt bên trái để bắt đầu.")

# ================================================================== 5. TRỢ LÝ
elif page == "Trợ lý hỏi đáp":
    st.title("Trợ lý hỏi đáp")
    st.markdown("<p class='lede'>Hỏi bằng tiếng Việt (có hoặc không dấu). Trợ lý tách câu hỏi thành mã doanh nghiệp, năm, chỉ tiêu, "
                "rồi trả lời bằng cùng bộ công thức với file nộp – không dùng mô hình ngôn ngữ, nên mỗi con số đều truy được nguồn.</p>",
                unsafe_allow_html=True)
    engine = get_engine(STAMP)
    if "qhist" not in st.session_state:
        st.session_state.qhist = []
    st.markdown("Câu mẫu:")
    ex_cols = st.columns(4)
    chosen = None
    for i, ex in enumerate(fa.EXAMPLES):
        if ex_cols[i % 4].button(ex, key=f"ex{i}", use_container_width=True):
            chosen = ex
    text = st.text_input("Câu hỏi", value=chosen or "", placeholder="Ví dụ: DSO của C003 năm 2024 là bao nhiêu ngày?")
    if text and text != st.session_state.get("last_q"):
        st.session_state.last_q = text
        st.session_state.qhist.insert(0, (text, fa.ask(engine, text)))
    for i, (t, res) in enumerate(st.session_state.qhist[:6]):
        with st.container(border=True):
            st.markdown(f"**{t}**")
            if not res["ok"]:
                st.warning(res["explanation"])
                continue
            a, b = st.columns([1.3, 1])
            with a:
                st.markdown(f"<div class='big-answer'>{pretty(res)}</div>", unsafe_allow_html=True)
                st.markdown(f"<p style='color:{INK2}'>{res['explanation']}</p>", unsafe_allow_html=True)
            with b:
                st.markdown(f"<span class='muted'>Cách hiểu câu hỏi</span><br>"
                            f"Loại: <b>{res['question_type']}</b><br>Doanh nghiệp: <b>{res['target_company_id'] or 'toàn ngành'}</b> · "
                            f"Năm: <b>{res['target_fiscal_year']}</b><br>Nguồn: <code>{res['evidence_source_files']}</code><br>"
                            f"<span class='muted'>{res['evidence_source_fields']}</span><br>Độ tin cậy {res['confidence']:.2f}",
                            unsafe_allow_html=True)
            if i == 0 and len(st.session_state.qhist) > 1:
                st.caption("Các câu hỏi trước hiển thị bên dưới.")

# ================================================================== 6. CHẤT LƯỢNG MÔ HÌNH
elif page == "Chất lượng mô hình":
    st.title("Chất lượng mô hình")
    st.markdown("<p class='lede'>Mọi con số dưới đây đo lại ở mỗi lần chạy pipeline. Phần cảnh báo đánh giá trên 18 nhãn mẫu của BTC – "
                "luật được thiết kế khi đã xem các nhãn này nên đây là kết quả trong mẫu; độ nhạy ngưỡng là bằng chứng độ bền.</p>",
                unsafe_allow_html=True)
    K7 = S.get("step7_submit", {}).get("final_kpi_from_files", {})
    rows = [("Calculation Accuracy (metrics mẫu, dung sai BTC)", K3.get("calculation_accuracy"), "≥ 95%"),
            ("Chỉ tiêu khớp tuyệt đối", K3.get("calculation_exact_match"), ""),
            ("Numerical QA Accuracy", K3.get("numerical_qa_accuracy"), "≥ 85%"),
            ("QA chỉ dùng câu chữ (trợ lý)", K3.get("qa_text_only_accuracy"), ""),
            ("Trợ lý – câu diễn đạt lại", K3.get("assistant_paraphrase_parse_accuracy"), ""),
            ("QA 300 câu tự sinh", K3.get("qa_generalization_accuracy"), ""),
            ("Verify kép", K3.get("dual_verify_agreement"), ""),
            ("Cảnh báo – tag F1", K6.get("tag_f1_micro"), ""),
            ("Recall HIGH/CRITICAL", K6.get("high_critical_recall"), ""),
            ("Chấm lại từ file nộp – QA", K7.get("numerical_qa_accuracy_file"), "")]
    kt = pd.DataFrame([(n, v, t) for n, v, t in rows if v is not None], columns=["KPI", "kết quả", "mục tiêu BTC"])
    a, b = st.columns([1, 1.1])
    with a:
        st.dataframe(kt, hide_index=True, use_container_width=True,
                     column_config={"kết quả": st.column_config.NumberColumn(format="percent"),
                                    "mục tiêu BTC": st.column_config.TextColumn("mục tiêu")})
    with b:
        ev = D["eval"].set_index("metric")
        keep = {"tag_f1_micro": "Tag F1", "scenario_accuracy": "Kịch bản", "severity_accuracy": "Mức độ",
                "health_accuracy": "Sức khỏe", "high_critical_recall": "Bắt ca nặng"}
        f5 = go.Figure()
        for col_, color, nm in [("system", BLUE, "Luật đa tín hiệu"), ("baseline", ORANGE, "Baseline 1 chỉ tiêu")]:
            vals = [float(ev.at[k, col_]) for k in keep]
            f5.add_trace(go.Bar(x=list(keep.values()), y=vals, name=nm, marker=dict(color=color, cornerradius=4),
                                text=[f"{v:.0%}" for v in vals], textposition="outside", textfont=dict(color=INK2, size=11),
                                cliponaxis=False, hovertemplate=f"{nm}: %{{y:.1%}}<extra>%{{x}}</extra>"))
        style_fig(f5, height=330).update_layout(barmode="group", bargap=0.45, bargroupgap=0.15, uniformtext=dict(minsize=10, mode="show"),
                                                title=dict(text="So với baseline trên 18 nhãn mẫu", font=dict(color=INK, size=13)))
        f5.update_yaxes(range=[0, 1.15], tickformat=".0%")
        f5.update_xaxes(tickangle=0)
        st.plotly_chart(f5, use_container_width=True, config={"displayModeBar": False})
    if D["sens"] is not None:
        sn = D["sens"]
        f6 = go.Figure()
        for col_, color, nm in [("tag_f1_micro", BLUE, "Tag F1"), ("scenario_accuracy", ORANGE, "Kịch bản đúng")]:
            f6.add_trace(go.Scatter(x=sn["threshold_factor"], y=sn[col_], mode="lines+markers", name=nm,
                                    line=dict(color=color, width=2), marker=dict(size=8, color=color, line=dict(color=PANEL, width=2)),
                                    hovertemplate=f"×%{{x}}: %{{y:.1%}}<extra>{nm}</extra>"))
        style_fig(f6, height=300).update_layout(title=dict(text="Độ nhạy: nhân đồng loạt mọi ngưỡng ×0,8 → ×1,2", font=dict(color=INK, size=13)),
                                                hovermode="x unified")
        f6.update_yaxes(range=[0.5, 1.05], tickformat=".0%")
        f6.update_xaxes(type="linear", tickvals=list(sn["threshold_factor"]), ticktext=[f"×{v}" for v in sn["threshold_factor"]])
        st.plotly_chart(f6, use_container_width=True, config={"displayModeBar": False})
    t1, t2, t3 = st.tabs(["So sánh với 18 nhãn", "30 câu QA", "Ngưỡng cảnh báo"])
    with t1:
        lc = D["labels_cmp"]
        st.dataframe(lc[["company_id", "fiscal_year", "primary_scenario", "predicted_primary_scenario", "severity", "predicted_severity",
                         "overall_health", "predicted_overall_health", "tags_missing", "tags_extra"]], hide_index=True, use_container_width=True)
    with t2:
        st.dataframe(D["qa_grading"][["question_id", "question_type", "our_normalized", "reference_normalized", "tolerance", "correct"]],
                     hide_index=True, use_container_width=True)
    with t3:
        st.dataframe(pd.Series(fs.THRESHOLDS, name="giá trị").to_frame(), use_container_width=True)

# ================================================================== 7. DỮ LIỆU & NHẬT KÝ
elif page == "Dữ liệu & nhật ký":
    st.title("Dữ liệu & nhật ký")
    st.markdown("<p class='lede'>Mỗi lần chạy để lại dấu vết: dấu vân tay dữ liệu, kết luận từng bước, file đầu ra và SHA-256 của file nộp. "
                "Bước sau chỉ chạy khi bước trước đạt.</p>", unsafe_allow_html=True)
    stp = pd.DataFrame([{"bước": k, "run_id": v["run_id"], "kết luận": v["verdict"], "ms": v["ms"], "tóm tắt": v.get("headline", "")}
                        for k, v in S.items()])
    st.dataframe(stp, hide_index=True, use_container_width=True)
    a, b = st.columns(2)
    with a:
        st.markdown("**Kiểm tra toàn vẹn Data Pack (Bước 0)**")
        st.dataframe(D["integrity"].groupby(["group", "status"]).size().unstack(fill_value=0), use_container_width=True)
    with b:
        st.markdown("**32 luật kế toán (Bước 1)**")
        st.dataframe(D["rules"][["rule_id", "description", "PASS", "FAIL", "N/A"]], hide_index=True, use_container_width=True, height=260)
    st.markdown("**File nộp BTC**")
    if D["manifest"] is not None:
        st.dataframe(D["manifest"], hide_index=True, use_container_width=True)
        c1, c2 = st.columns(2)
        for c_, f_ in zip((c1, c2), ("submission_output.csv", "qa_submission.csv")):
            p = PROJECT / "05_submission" / f_
            if p.exists():
                c_.download_button(f"Tải {f_}", p.read_bytes(), file_name=f_, mime="text/csv", use_container_width=True)
    st.markdown("**Nhật ký audit (30 bản ghi gần nhất)**")
    au = D["audit"]
    if len(au):
        st.dataframe(au.tail(30)[[c for c in ["timestamp", "run_id", "step", "parent_run", "verdict", "processing_time_ms"] if c in au.columns]]
                     .iloc[::-1], hide_index=True, use_container_width=True)