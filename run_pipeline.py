#!/usr/bin/env python3
"""run_pipeline.py – Chạy TỰ ĐỘNG toàn bộ FinReport Intelligence từ dữ liệu gốc đến file nộp.

    python run_pipeline.py                      # thư mục dự án = thư mục chứa file này
    python run_pipeline.py --project /content/drive/MyDrive/FinReport_Intelligence
    python run_pipeline.py --quick              # bỏ các kiểm thử nặng (độ nhạy, 300 câu, đột biến)

Chuỗi bước (mỗi bước ghi kết quả + 1 bản ghi audit, bước sau chỉ chạy khi bước trước đạt):
  S0 Tiếp nhận & toàn vẹn → S1 Luật kế toán → S2 Chỉ tiêu → S3 Verify & QA
  → S4 Xu hướng & đồng ngành → S5 Tín hiệu → S6 Chấm điểm & đánh giá → S7 Ghép, kiểm tra, xuất file nộp
Kết quả: 03_outputs/step*/, 05_submission/, 04_logs/audit_log.jsonl, 03_outputs/pipeline_summary.json, pipeline_report.md
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path


def _load_lib(project: Path):
    sys.path.insert(0, str(project / "lib"))
    import importlib
    mods = {}
    for name in ["finreport_common", "finreport_ingest", "finreport_metrics", "finreport_qa", "finreport_signals",
                 "finreport_submit", "finreport_assistant"]:
        mods[name] = importlib.reload(importlib.import_module(name))
    return mods


class StepFailed(RuntimeError):
    pass


def run_all(project: str | Path, quick: bool = False, verbose: bool = True, log_fn=print) -> dict:
    project = Path(project).resolve()
    L = _load_lib(project)
    cm, fi, fm, qa, fs, sb, fa = (L[k] for k in ["finreport_common", "finreport_ingest", "finreport_metrics", "finreport_qa",
                                                   "finreport_signals", "finreport_submit", "finreport_assistant"])
    import pandas as pd

    cfg = cm.setup(project)
    say = (lambda *a: log_fn(*a)) if verbose else (lambda *a: None)
    summary = {"project": str(project), "started_at": cm.now_iso(), "quick": quick, "steps": {}}
    T0 = time.perf_counter()

    def step(name, prefix, parent, fn):
        t = time.perf_counter()
        run_id = cm.new_run_id(prefix)
        say(f"▶ {name} …")
        info = fn(run_id) or {}
        ms = round((time.perf_counter() - t) * 1000, 1)
        verdict = info.pop("_verdict", "PASS")
        outputs = info.pop("_outputs", [])
        cm.append_audit({"run_id": run_id, "step": name, "parent_run": parent, "verdict": verdict,
                         "processing_time_ms": ms, "outputs": outputs, "pipeline": "run_pipeline.py", **info})
        summary["steps"][name] = {"run_id": run_id, "verdict": verdict, "ms": ms, **info}
        mark = "✗" if str(verdict).startswith("FAIL") else ("!" if verdict != "PASS" else "✓")
        say(f"  {mark} {verdict} · {ms:.0f} ms" + (f" · {info.get('headline', '')}" if info.get("headline") else ""))
        if str(verdict).startswith("FAIL"):
            raise StepFailed(f"{name}: {verdict}")
        return run_id

    ctx = {}

    # ------------------------------------------------------------------ S0
    def s0(run_id):
        log, master, lineage, present = fi.run_step0(cfg.data_dir)
        fp = fi.data_fingerprint(cfg.data_dir)
        cm.save_output(log.df(), "step0", "integrity_checks.csv")
        neg_caught = None
        if not log.failed:
            cm.save_output(master, "step0", "master_panel.csv")
            cm.save_output(lineage, "step0", "field_lineage.csv")
            if not quick:
                with tempfile.TemporaryDirectory() as tmp:
                    neg_caught = fi.negative_test(cfg.data_dir, tmp).failed
        ctx.update(master=master, fingerprint=fp)
        n = log.counts()
        return {"_verdict": log.verdict(), "checks": n, "data_fingerprint": fp, "negative_test_caught": neg_caught,
                "files_missing": [k for k, v in present.items() if not v],
                "headline": f"{n.get('PASS', 0)} PASS · {n.get('WARN', 0)} WARN · {n.get('FAIL', 0)} FAIL",
                "_outputs": ["03_outputs/step0/master_panel.csv", "03_outputs/step0/field_lineage.csv",
                             "03_outputs/step0/integrity_checks.csv"]}

    # ------------------------------------------------------------------ S1
    def s1(run_id):
        d, p = fm.prepare(ctx["master"])
        checks = fm.run_accounting_checks(d, p)
        cm.save_output(checks, "step1_3", "accounting_checks.csv")
        cm.save_output(fm.summarize_checks(checks), "step1_3", "accounting_rule_summary.csv")
        cm.save_output(fm.row_flags(d, p), "step1_3", "row_flags.csv")
        cm.save_output(fm.rule_catalog(), "step1_3", "rule_catalog.csv")
        n = checks["status"].value_counts().to_dict()
        return {"_verdict": "FAIL" if n.get("FAIL") else "PASS", "checks": n, "rules": len(fm.RULES),
                "headline": f"{len(fm.RULES)} luật · {n.get('PASS', 0)} PASS · {n.get('FAIL', 0)} FAIL · {n.get('N/A', 0)} N/A",
                "_outputs": ["03_outputs/step1_3/accounting_checks.csv", "03_outputs/step1_3/row_flags.csv"]}

    # ------------------------------------------------------------------ S2
    def s2(run_id):
        wide, long = fm.compute_metrics(ctx["master"])
        supp = fm.compute_supplementary(ctx["master"])
        cm.save_output(wide, "step1_3", "metrics_wide.csv")
        cm.save_output(long, "step1_3", "metrics_long.csv")
        cm.save_output(supp, "step1_3", "metrics_supplementary.csv")
        cm.save_output(fm.metric_catalog(), "step1_3", "metric_catalog.csv")
        ctx.update(wide=wide, long=long, supp=supp)
        flags = long["flag"].replace("", "NONE").fillna("NONE").value_counts().to_dict()
        return {"metrics": len(fm.METRIC_IDS), "cells": int(len(long)), "flags": flags,
                "headline": f"{len(fm.METRIC_IDS)} chỉ tiêu × {len(wide)} dòng",
                "_outputs": ["03_outputs/step1_3/metrics_wide.csv", "03_outputs/step1_3/metrics_long.csv"]}

    # ------------------------------------------------------------------ S3
    def s3(run_id):
        kpi = {}
        indep = fm.compute_metrics_independent(cfg.data_dir)
        verify = fm.dual_verify(ctx["wide"], indep)
        cm.save_output(indep, "step1_3", "metrics_independent.csv")
        cm.save_output(verify, "step1_3", "verify_dual.csv")
        kpi["dual_verify_agreement"] = round(verify["agree"].sum() / verify["cells"].sum(), 4)

        engine = qa.QAEngine(ctx["master"], ctx["wide"], ctx["long"])
        ctx["engine"] = engine
        qpath, _ = cm.locate_pack_file("questions_sample")
        kpath, _ = cm.locate_pack_file("answer_key_sample")
        if qpath is not None:
            questions = pd.read_csv(qpath, encoding="utf-8-sig")
            answers = engine.answer_all(questions)
            cm.save_output(answers, "step1_3", "qa_answers_detail.csv")
            ctx["qa_answers"] = answers
            if kpath is not None:
                key = pd.read_csv(kpath, encoding="utf-8-sig")
                grading = qa.grade(answers, key)
                cm.save_output(grading, "step1_3", "qa_grading.csv")
                kpi["numerical_qa_accuracy"] = round(float(grading["correct"].mean()), 4)
                g_txt, p_txt = fa.evaluate_text_only(engine, questions, key)
                cm.save_output(g_txt.merge(p_txt, on="question_id"), "step1_3", "qa_text_only_grading.csv")
                kpi["qa_text_only_accuracy"] = round(float(g_txt["correct"].mean()), 4)
        para = fa.evaluate_paraphrases(engine)
        cm.save_output(para, "step1_3", "assistant_paraphrase_test.csv")
        kpi["assistant_paraphrase_parse_accuracy"] = round(float(para["all_ok"].mean()), 4)

        mpath, _ = cm.locate_pack_file("financial_metrics_sample")
        if mpath is not None:
            cmp_ = fm.compare_with_metrics_sample(ctx["wide"], ctx["supp"], mpath)
            cm.save_output(cmp_, "step1_3", "metrics_sample_comparison.csv")
            tpl = cmp_[cmp_["in_template"]]
            kpi["calculation_accuracy"] = round(float(tpl["within_btc_tolerance"].mean()), 4)
            kpi["calculation_exact_match"] = round(float(tpl["exact_at_btc_precision"].mean()), 4)
        if not quick:
            gq, gk = qa.make_variant_suite(indep, ctx["master"], n=300, seed=2026)
            gg = qa.grade(engine.answer_all(gq), gk)
            cm.save_output(gg, "step1_3", "qa_generalization_grading.csv")
            kpi["qa_generalization_accuracy"] = round(float(gg["correct"].mean()), 4)
            mutant = [dataclasses.replace(m, func=lambda d, p: (d[fm.C["cash"]] + d[fm.C["ar"]] + d[fm.C["inv"]]) / d[fm.C["tcl"]])
                      if m.metric_id == "quick_ratio_x" else m for m in fm.METRICS]
            mw, _ = fm.compute_metrics(ctx["master"], mutant)
            kpi["mutation_caught_by_verify"] = bool((fm.dual_verify(mw, indep)["status"] == "FAIL").any())
        ok = kpi.get("dual_verify_agreement", 0) == 1 and kpi.get("numerical_qa_accuracy", 1) >= 0.85
        return {"_verdict": "PASS" if ok else "REVIEW", "kpi": kpi, "model_name": qa.QAEngine.MODEL_NAME,
                "headline": f"QA {kpi.get('numerical_qa_accuracy', float('nan')):.0%} · Calc {kpi.get('calculation_accuracy', float('nan')):.0%} · verify {kpi['dual_verify_agreement']:.0%}",
                "_outputs": ["03_outputs/step1_3/qa_grading.csv", "03_outputs/step1_3/verify_dual.csv",
                             "03_outputs/step1_3/metrics_sample_comparison.csv"]}

    # ------------------------------------------------------------------ S4 – S6
    def s4(run_id):
        f = fs.build_features(ctx["master"], ctx["wide"], ctx["supp"])
        peer = (f.groupby("fiscal_year")[["revenue_growth_pct", "gross_margin_pct", "operating_margin_pct", "current_ratio_x",
                                          "debt_to_equity_x", "interest_coverage_x", "dso_days", "inventory_days"]]
                .median().round(4).reset_index())
        cm.save_output(f, "step4_6", "features.csv")
        cm.save_output(peer, "step4_6", "peer_benchmarks.csv")
        ctx["features"] = f
        return {"features": int(f.shape[1]), "headline": f"{f.shape[1]} đặc trưng",
                "_outputs": ["03_outputs/step4_6/features.csv", "03_outputs/step4_6/peer_benchmarks.csv"]}

    def s5(run_id):
        sig = fs.detect_signals(ctx["features"])
        cm.save_output(sig, "step4_6", "signals.csv")
        ctx["signals"] = sig
        cols = [c for c in sig.columns if c.startswith("S_")]
        return {"thresholds": fs.THRESHOLDS, "signals_on": {c: int(sig[c].sum()) for c in cols},
                "headline": f"{len(cols)} tín hiệu", "_outputs": ["03_outputs/step4_6/signals.csv"]}

    def s6(run_id):
        f, sig = ctx["features"], ctx["signals"]
        pred = fs.score(f, sig)
        pred["confidence"] = fs.confidence(f)
        pred["alert_reason"], pred["evidence_fields"] = fs.explain(f, pred)
        cm.save_output(pred, "step4_6", "predictions.csv")
        ctx["pred"] = pred
        kpi, outs = {}, ["03_outputs/step4_6/predictions.csv"]
        lpath, _ = cm.locate_pack_file("financial_scenarios_sample")
        if lpath is not None:
            labels = pd.read_csv(lpath, encoding="utf-8-sig", keep_default_na=False)
            ev, eb = fs.evaluate(pred, labels), fs.evaluate(fs.baseline(f), labels)
            comp = pd.DataFrame({"system": ev, "baseline": eb}).drop("n_labels")
            cm.save_output(comp.reset_index().rename(columns={"index": "metric"}), "step4_6", "evaluation_vs_baseline.csv")
            cm.save_output(fs.compare_rows(pred, labels), "step4_6", "label_comparison.csv")
            kpi = {k: round(float(v), 4) for k, v in ev.items() if k != "n_labels"}
            kpi["baseline_tag_f1"] = round(float(eb["tag_f1_micro"]), 4)
            outs += ["03_outputs/step4_6/evaluation_vs_baseline.csv", "03_outputs/step4_6/label_comparison.csv"]
            if not quick:
                sens = fs.sensitivity(ctx["master"], ctx["wide"], ctx["supp"], labels)
                oat = fs.one_at_a_time(ctx["master"], ctx["wide"], ctx["supp"], labels)
                cm.save_output(sens, "step4_6", "sensitivity_global.csv")
                cm.save_output(oat, "step4_6", "sensitivity_one_at_a_time.csv")
                kpi["sensitivity_f1_min"] = round(float(sens["tag_f1_micro"].min()), 4)
                kpi["oat_unchanged_share"] = round(float((oat["Δf1"] == 0).mean()), 4)
        return {"kpi": kpi, "model_name": fs.MODEL_NAME, "evaluation": "in-sample (nhãn mẫu)",
                "headline": f"tag F1 {kpi.get('tag_f1_micro', float('nan')):.1%} · baseline {kpi.get('baseline_tag_f1', float('nan')):.1%}",
                "_outputs": outs}

    # ------------------------------------------------------------------ S7
    def s7(run_id):
        tpl_sub, tpl_qa = cm.read_pack("submission_output_template"), cm.read_pack("qa_submission_template")
        master = ctx["master"]
        ms_per_row, ms_total = sb.timing_per_row(master, lambda: fs.run(master, fm.compute_metrics(master)[0],
                                                                         fm.compute_supplementary(master)), repeats=3)
        sub = sb.assemble_submission(tpl_sub, ctx["wide"], ctx["pred"], fs.MODEL_NAME, ms_per_row)
        qa_sub = sb.assemble_qa(tpl_qa, ctx["qa_answers"])
        vlog = cm.CheckLog()
        sb.validate_submission(sub, tpl_sub, ctx["wide"], vlog)
        sb.validate_qa(qa_sub, tpl_qa, vlog)
        cm.save_output(vlog.df(), "step7_submit", "validation_checks.csv")
        if vlog.failed:
            return {"_verdict": vlog.verdict(), "checks": vlog.counts()}
        sp, qp = cfg.submit_dir / "submission_output.csv", cfg.submit_dir / "qa_submission.csv"
        sub.to_csv(sp, index=False, encoding="utf-8-sig")
        qa_sub.to_csv(qp, index=False, encoding="utf-8-sig")
        # chấm lại từ CHÍNH file vừa ghi
        final = {}
        kpath, _ = cm.locate_pack_file("answer_key_sample")
        if kpath is not None:
            g = sb.regrade_qa_file(pd.read_csv(qp, encoding="utf-8-sig"), pd.read_csv(kpath, encoding="utf-8-sig"))
            final["numerical_qa_accuracy_file"] = round(float(g["correct"].mean()), 4)
        sub_disk = pd.read_csv(sp, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
        mpath, _ = cm.locate_pack_file("financial_metrics_sample")
        if mpath is not None:
            c_ = fm.compare_with_metrics_sample(sub_disk[fm.KEY + fm.METRIC_IDS], ctx["supp"], mpath)
            final["calculation_accuracy_file"] = round(float(c_[c_["in_template"]]["within_btc_tolerance"].mean()), 4)
        lpath, _ = cm.locate_pack_file("financial_scenarios_sample")
        if lpath is not None:
            ev = fs.evaluate(sub_disk.assign(alert_tags=sub_disk["alert_tags"].fillna("")),
                             pd.read_csv(lpath, encoding="utf-8-sig", keep_default_na=False))
            final["alert_tag_f1_file"] = round(float(ev["tag_f1_micro"]), 4)
        man = sb.manifest({"submission_output.csv": sp, "qa_submission.csv": qp}, cm.sha256_of)
        man["run_id"], man["created_at"] = run_id, cm.now_iso()
        man.to_csv(cfg.submit_dir / "submission_manifest.csv", index=False, encoding="utf-8-sig")
        hist = cfg.submit_dir / "history" / run_id
        hist.mkdir(parents=True, exist_ok=True)
        for p_ in (sp, qp):
            shutil.copy2(p_, hist / p_.name)
        return {"_verdict": vlog.verdict(), "checks": vlog.counts(), "final_kpi_from_files": final,
                "pipeline_ms_total": round(ms_total, 1), "submission_sha256": dict(zip(man["file"], man["sha256"])),
                "headline": f"{vlog.counts().get('PASS', 0)} kiểm tra PASS · file nộp đã ghi",
                "_outputs": ["05_submission/submission_output.csv", "05_submission/qa_submission.csv",
                             "05_submission/submission_manifest.csv"]}

    status = "PASS"
    try:
        r0 = step("step0_ingest", "S0", None, s0)
        r1 = step("step1_accounting", "S1", r0, s1)
        r2 = step("step2_metrics", "S2", r1, s2)
        r3 = step("step3_verify_qa", "S3", r2, s3)
        r4 = step("step4_trend_peer", "S4", r2, s4)
        r5 = step("step5_signals", "S5", r4, s5)
        r6 = step("step6_scoring", "S6", r5, s6)
        step("step7_submit", "S7", [r3, r6], s7)
    except StepFailed as e:
        status = f"STOPPED – {e}"
        say(f"✗ Pipeline dừng: {e}")
    summary.update(finished_at=cm.now_iso(), status=status, total_ms=round((time.perf_counter() - T0) * 1000, 1))
    (cfg.out_dir / "pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str),
                                                        encoding="utf-8")
    _write_report(cfg, summary)
    say(f"■ Hoàn tất: {status} · {summary['total_ms'] / 1000:.1f} s")
    return summary


def _write_report(cfg, s):
    st = s["steps"]
    k3 = st.get("step3_verify_qa", {}).get("kpi", {})
    k6 = st.get("step6_scoring", {}).get("kpi", {})
    k7 = st.get("step7_submit", {}).get("final_kpi_from_files", {})
    pct = lambda v: "–" if v is None else f"{v:.1%}"
    L = ["# Báo cáo pipeline tự động – FinReport Intelligence", "",
         f"- **Trạng thái:** {s['status']} · **Tổng thời gian:** {s['total_ms'] / 1000:.1f} s · **Chế độ:** {'nhanh' if s['quick'] else 'đầy đủ'}",
         f"- **Bắt đầu:** {s['started_at']} · **Kết thúc:** {s['finished_at']}",
         f"- **Data fingerprint:** `{str(st.get('step0_ingest', {}).get('data_fingerprint', ''))[:24]}…`", "",
         "## Các bước", "", "| Bước | Run ID | Kết luận | Thời gian | Tóm tắt |", "|---|---|---|---:|---|"]
    L += [f"| {n} | `{v['run_id']}` | {v['verdict']} | {v['ms']:.0f} ms | {v.get('headline', '')} |" for n, v in st.items()]
    L += ["", "## KPI", "", "| KPI | Kết quả | Mục tiêu BTC |", "|---|---:|---:|",
          f"| Calculation Accuracy (metrics mẫu, dung sai BTC) | {pct(k3.get('calculation_accuracy'))} | ≥ 95% |",
          f"| Chỉ tiêu khớp tuyệt đối | {pct(k3.get('calculation_exact_match'))} | – |",
          f"| Numerical QA Accuracy (30 câu, cột cấu trúc) | {pct(k3.get('numerical_qa_accuracy'))} | ≥ 85% |",
          f"| QA chỉ dùng câu chữ (trợ lý tiếng Việt) | {pct(k3.get('qa_text_only_accuracy'))} | – |",
          f"| Trợ lý – tách đúng câu diễn đạt lại | {pct(k3.get('assistant_paraphrase_parse_accuracy'))} | – |",
          f"| QA tổng quát hóa (300 câu tự sinh) | {pct(k3.get('qa_generalization_accuracy'))} | – |",
          f"| Verify kép | {pct(k3.get('dual_verify_agreement'))} | – |",
          f"| Cảnh báo – tag F1 (18 nhãn, in-sample) | {pct(k6.get('tag_f1_micro'))} | – |",
          f"| Baseline 1 chỉ tiêu – tag F1 | {pct(k6.get('baseline_tag_f1'))} | – |",
          f"| Kịch bản / severity / health | {pct(k6.get('scenario_accuracy'))} / {pct(k6.get('severity_accuracy'))} / {pct(k6.get('health_accuracy'))} | – |",
          f"| Độ nhạy ngưỡng ×0,8–1,2: F1 thấp nhất | {pct(k6.get('sensitivity_f1_min'))} | – |",
          f"| Chấm lại từ file nộp: QA / chỉ tiêu / tag F1 | {pct(k7.get('numerical_qa_accuracy_file'))} / {pct(k7.get('calculation_accuracy_file'))} / {pct(k7.get('alert_tag_f1_file'))} | – |",
          "", "> Cảnh báo là tín hiệu hỗ trợ phân tích – không phải kết luận gian lận, kiểm toán hay khuyến nghị đầu tư."]
    (cfg.out_dir / "pipeline_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Chạy tự động toàn bộ pipeline FinReport Intelligence")
    ap.add_argument("--project", default=str(Path(__file__).resolve().parent), help="Thư mục dự án (chứa lib/, 01_datapack/)")
    ap.add_argument("--quick", action="store_true", help="Bỏ các kiểm thử nặng")
    a = ap.parse_args()
    res = run_all(a.project, quick=a.quick)
    sys.exit(0 if res["status"] == "PASS" else 1)
