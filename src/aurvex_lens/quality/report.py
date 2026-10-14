"""Data suitability report (report.md + report.json). Reads a finalized raw
snapshot only — no MT5 connection. One result per criterion, no aggregate score."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aurvex_lens.common.config import LensConfig, load_thresholds
from aurvex_lens.common.provenance import (
    LIVE_LABEL, SYNTHETIC_LABEL, dumps, new_run_id, sha256_file, utc_iso,
)
from aurvex_lens.data.schema import TF_MINUTES
from aurvex_lens.data.snapshot import ORIGIN_SYNTHETIC, load_meta, verify_snapshot
from aurvex_lens.quality import gaps as G
from aurvex_lens.quality.costs import evaluate_c5, evaluate_c6
from aurvex_lens.quality.coverage import evaluate_c1, server_iso
from aurvex_lens.quality.freshness import evaluate_c3
from aurvex_lens.quality.result import (
    FAIL, NOT_CONNECTED, PASS, UNAPPROVED_TZ_LABEL, UNKNOWN, CriterionResult, combine, data_gate,
)
from aurvex_lens.quality.server_time import evaluate_c4, load_nfp_calendar, rule_offset_s


class ReportError(Exception):
    pass


def _read_json(d: Path, name: str) -> Any:
    p = d / name
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _read_parquet(d: Path, name: str) -> pd.DataFrame | None:
    p = d / name
    return pd.read_parquet(p) if p.exists() else None


def _gaps_csv(classified: pd.DataFrame, path: Path) -> None:
    out = classified.copy()
    if not out.empty:
        out["gap_start_server"] = out["gap_start"].map(server_iso)
        out["gap_end_server"] = out["gap_end"].map(server_iso)
        out["other_dates"] = out["other_dates"].map(lambda x: ";".join(x))
    out.to_csv(path, index=False)


def evaluate_c2(frames, cfg: LensConfig, thresholds, out_dir: Path, point) -> tuple[CriterionResult, dict, dict]:
    conf_list = cfg.confirmations.get("closures", [])
    confirmed = [G.parse_interval(s) for s in conf_list]
    holidays = set(cfg.confirmations.get("holiday_dates", []))
    present = [tf for tf in ("M1", "M5", "M15", "H1") if frames.get(tf) is not None and not frames[tf].empty]
    if not present:
        return (CriterionResult("C2", "Eksik veri", UNKNOWN, "no bars", notes=["no timeframe data"]), {}, {})
    finest = present[0]
    raw_gaps = {tf: G.find_gaps(frames[tf]["time_server"].to_numpy(), TF_MINUTES[tf] * 60) for tf in present}
    cand = G.detect_candidates(raw_gaps[finest], cfg.closure_min_recurrence)
    cand_iv = [iv for iv, _ in cand if iv not in confirmed]
    classified, summaries, evidence = {}, {}, []
    for tf in present:
        c = G.classify_gaps(raw_gaps[tf], TF_MINUTES[tf] * 60, confirmed, cand_iv, holidays)
        classified[tf] = c
        summaries[tf] = G.gap_summary(c, len(frames[tf]), TF_MINUTES[tf])
        p = out_dir / f"gaps_{tf}.csv"
        _gaps_csv(c, p)
        evidence.append(str(p))
    cand_rows = [{"pattern_server_time": iv.label(), "occurrences_in_" + finest: n,
                  "confirmed": iv in confirmed} for iv, n in cand]
    holiday_dates = sorted({d for tf in present for row in classified[tf].itertuples()
                            if row.cls == G.HOLIDAY_CANDIDATE for d in row.other_dates})
    t2 = thresholds.get("c2", {})
    subs = []
    for tf in present:
        s = summaries[tf]
        max_ratio = t2.get("max_unexplained_missing_ratio")
        max_gap = t2.get("max_single_unexplained_gap_minutes")
        unconfirmed = (s["by_class"].get(G.CLOSURE_CANDIDATE, {}).get("gaps", 0)
                       + s["by_class"].get(G.HOLIDAY_CANDIDATE, {}).get("gaps", 0))
        if max_ratio is None or max_gap is None:
            res = UNKNOWN
        elif s["unexplained_ratio"] > max_ratio or s["max_unexplained_gap_minutes"] > max_gap:
            res = FAIL
        elif t2.get("require_all_closures_confirmed", True) and unconfirmed:
            res = UNKNOWN
        else:
            res = PASS
        subs.append({"timeframe": tf, "result": res, "unexplained_ratio": round(s["unexplained_ratio"], 6),
                     "max_unexplained_gap_minutes": s["max_unexplained_gap_minutes"],
                     "unconfirmed_closure_or_holiday_gaps": unconfirmed})
    for tf in ("M1", "M5", "M15", "H1"):
        if frames.get(tf) is None:
            subs.append({"timeframe": tf, "result": UNKNOWN, "reason": "not in snapshot"})
    cross = {}
    if "M1" in present:
        for tf in ("M5", "M15", "H1"):
            if tf in present:
                cross[tf] = G.cross_tf_consistency(frames["M1"], frames[tf], TF_MINUTES[tf] * 60, point)
    max_mm = thresholds.get("extra", {}).get("cross_tf_max_price_mismatch_ratio")
    for tf, cr in cross.items():
        if cr.get("status") == "MEASURED" and max_mm is not None:
            subs.append({"check": f"cross_tf_M1_vs_{tf}", "result": PASS if cr["price_mismatch_ratio"] <= max_mm
                         else FAIL, "value": cr["price_mismatch_ratio"], "threshold": max_mm})
    cp = out_dir / "closure_candidates.json"
    cp.write_text(dumps({"candidates": cand_rows, "holiday_candidate_dates_server": holiday_dates}), encoding="utf-8")
    evidence.append(str(cp))
    res = CriterionResult(
        "C2", "Eksik veri (piyasa kapanışından ayrılmış)", combine([s["result"] for s in subs]),
        method=(f"Ardışık barlar arası > 1 TF boşluklar. Eksik slotlar haftalık kapanış aralıklarına göre sınıflanır "
                f"(server time). Aday kapanış = en ince TF ({finest}) içinde ≥{cfg.closure_min_recurrence} kez "
                "tekrar eden (başlangıç, bitiş) haftalık deseni. Kapanışa bitişik ek boşluk = HOLIDAY_CANDIDATE. "
                "Yalnızca UNEXPLAINED kesinti sayılır. TF tutarlılığı: M1'den yeniden örnekleme vs terminal OHLC."),
        metrics={"by_timeframe": summaries, "closure_candidates": cand_rows,
                 "holiday_candidate_dates_server": holiday_dates, "cross_tf_consistency": cross,
                 "confirmed_closures": conf_list, "confirmed_holiday_dates": sorted(holidays)},
        sub_results=subs, evidence=evidence,
        notes=([] if max_mm is not None else ["TF tutarlılığı için eşik tanımlı değil — yalnızca raporlanır."])
              + ["Kapanış adayları ve tatil tarihleri kullanıcı teyidi bekler (config [confirmations])."],
    )
    return res, classified, summaries


def evaluate_c7() -> CriterionResult:
    return CriterionResult("C7", "Takvim kapsamı", NOT_CONNECTED,
                           "Faz 0'da ekonomik takvim bağlı değil (O4 açık).",
                           metrics={"NEWS_CALENDAR": "NOT_CONNECTED"},
                           notes=["Bu rapordaki hiçbir bölüm 'haber açısından güvenli' anlamına gelmez.",
                                  "Haber kontrolü yapılmadı (NEWS_UNCHECKED)."])


def _threshold_status(actual: str, approved: str | None) -> str:
    if not approved:
        return "PROPOSED — user approval pending (O2)"
    if approved == actual:
        return "APPROVED"
    return f"CHANGED_SINCE_APPROVAL (approved sha256 {approved})"


def build_report(snapshot_dir: Path, cfg: LensConfig, thresholds_path: Path) -> Path:
    snapshot_dir = Path(snapshot_dir)
    meta = load_meta(snapshot_dir)
    integrity = verify_snapshot(snapshot_dir)
    if not all(x["ok"] for x in integrity):
        raise ReportError(f"snapshot integrity check failed: {[x for x in integrity if not x['ok']]}")
    thresholds = load_thresholds(thresholds_path)
    th_sha = sha256_file(thresholds_path)

    out_dir = cfg.data_dir / "reports" / meta["extraction_id"] / new_run_id("report_")
    out_dir.mkdir(parents=True, exist_ok=False)
    infos = {e["file"]: e for e in meta["files"]}
    frames, file_infos = {}, {}
    for tf in ("H1", "M15", "M5", "M1"):
        name = f"rates_{tf}.parquet"
        frames[tf] = _read_parquet(snapshot_dir, name)
        file_infos[tf] = infos.get(name)
    sym = _read_json(snapshot_dir, "symbol_snapshot.json") or {}
    si = sym.get("symbol_info") or {}
    point = si.get("point")
    live = _read_json(snapshot_dir, "live_probe.json")
    clock = _read_json(snapshot_dir, "clock_status.json")
    probes = _read_json(snapshot_dir, "tick_probes.json")
    access = _read_json(snapshot_dir, "access_probe.json")
    ticks_recent = _read_parquet(snapshot_dir, "ticks_recent.parquet")
    ticks_probe = _read_parquet(snapshot_dir, "ticks_probe.parquet")
    ev = lambda *n: [str(snapshot_dir / x) for x in n]  # noqa: E731

    c2, classified, summaries = evaluate_c2(frames, cfg, thresholds, out_dir, point)
    c1 = evaluate_c1(frames, file_infos, thresholds, summaries, probes, ticks_probe,
                     ev(*[f"rates_{tf}.parquet" for tf in ("H1", "M15", "M5", "M1")], "tick_probes.json"))
    approved = cfg.confirmations.get("server_time_rule")
    offset_fn = (lambda utc: rule_offset_s(approved, utc)) if approved else None
    confirmed = [G.parse_interval(s) for s in cfg.confirmations.get("closures", [])]
    c3 = evaluate_c3(live, offset_fn, confirmed, thresholds, ticks_recent, ev("live_probe.json",
                                                                              "ticks_recent.parquet"))
    event_tf = next((tf for tf in ("M5", "M15", "H1", "M1") if tf in classified), None)
    c4, table = evaluate_c4(event_tf, classified.get(event_tf), frames.get(event_tf), live, clock,
                            cfg.server_rule_base_offsets, cfg.reference_tz, approved,
                            set(cfg.confirmations.get("holiday_dates", [])), thresholds,
                            ev("clock_status.json", "live_probe.json"),
                            nfp_calendar=load_nfp_calendar(cfg.nfp_calendar_path))
    if not table.empty:
        p = out_dir / "c4_rule_match_weeks.csv"
        t = table.copy()
        t.index = [datetime.fromtimestamp(int((w * G.WEEK_MIN + 2 * 1440) * 60), tz=UTC).strftime("%Y-%m-%d")
                   for w in t.index]
        t.index.name = "week_start_sat_server"
        t.to_csv(p)
        c4.evidence.append(str(p))
    c5 = evaluate_c5(si, ticks_recent, frames.get("M1"), access, cfg.official_costs, thresholds,
                     ev("symbol_snapshot.json", "ticks_recent.parquet", "access_probe.json"))
    c6 = evaluate_c6(ticks_recent, frames.get("M1"), point, thresholds, ev("ticks_recent.parquet",
                                                                          "rates_M1.parquet"))
    c7 = evaluate_c7()
    criteria = [c1, c2, c3, c4, c5, c6, c7]

    synthetic = meta.get("data_origin") == ORIGIN_SYNTHETIC
    header = {
        "data_label": SYNTHETIC_LABEL if synthetic else LIVE_LABEL,
        "data_origin": meta.get("data_origin"),
        "extraction_id": meta["extraction_id"],
        "report_generated_utc": utc_iso(),
        "terminal_build": meta.get("terminal_build"),
        "metatrader5_package_version": (meta.get("versions") or {}).get("MetaTrader5"),
        "thresholds_file": str(thresholds_path),
        "thresholds_sha256": th_sha,
        "thresholds_status": _threshold_status(th_sha, cfg.confirmations.get("thresholds_approved_sha256")),
        "NEWS_CALENDAR": "NOT_CONNECTED",
        "server_time_rule": approved or "NOT_APPROVED (O3)",
        "symbol": meta.get("symbol"),
        "snapshot_integrity": "OK" if all(x["ok"] for x in integrity) else "FAIL",
        "phase1_data_gate": data_gate(criteria),
    }
    doc = {"header": header, "criteria": [asdict(c) for c in criteria],
           "access_probe_P0_7": access, "symbol_snapshot_P0_4": {
               "configured_symbol": sym.get("configured_symbol"),
               "matching_symbol_names": sym.get("matching_symbol_names")},
           "integrity": integrity,
           "note": "No aggregate quality score exists. UNKNOWN is never PASS. Phase-0 completion ≠ data suitable."}
    (out_dir / "report.json").write_text(dumps(doc), encoding="utf-8")
    (out_dir / "report.md").write_text(render_md(doc), encoding="utf-8")
    return out_dir


def _md_table(columns: list[str], rows: list[dict]) -> str:
    def cell(v):
        if isinstance(v, float):
            return f"{v:.6g}"
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False).replace("|", "/")
        return str(v).replace("|", "/")
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for r in rows:
        lines.append("| " + " | ".join(cell(r.get(c, "")) for c in columns) + " |")
    return "\n".join(lines)


def render_md(doc: dict) -> str:
    h = doc["header"]
    out = ["# Aurvex Lens — Veri Uygunluk Raporu (Faz 0)", "",
           f"**{h['data_label']}**", ""]
    for k in ("extraction_id", "report_generated_utc", "symbol", "terminal_build", "metatrader5_package_version",
              "thresholds_file", "thresholds_sha256", "thresholds_status", "server_time_rule",
              "snapshot_integrity"):
        out.append(f"- {k}: `{h[k]}`")
    out.append(f"- **NEWS_CALENDAR: {h['NEWS_CALENDAR']}**")
    gate = h["phase1_data_gate"]
    failing = ", ".join(f"{x['id']}={x['result']}" for x in gate["not_passing"]) or "-"
    out.append(f"- phase1_data_gate: **{gate['status']}** ({failing})")
    out += ["", "> Tek bir kalite skoru yoktur. Her kriter ayrı PASS / FAIL / UNKNOWN döner; UNKNOWN asla PASS "
            "sayılmaz. Faz 0 görevinin tamamlanması verinin uygun olduğu anlamına gelmez.", "",
            "> Tüm bar/tick zamanları **broker sunucu saatidir (time_server), UTC değildir**.", "",
            "## Özet", "",
            _md_table(["id", "title", "result", "blocking"],
                      [{k: c[k] for k in ("id", "title", "result", "blocking")} for c in doc["criteria"]]), ""]
    for c in doc["criteria"]:
        out += [f"## {c['id']} — {c['title']}: **{c['result']}**", "", f"**Yöntem:** {c['method']}", ""]
        if c["sub_results"]:
            cols = sorted({k for r in c["sub_results"] for k in r}, key=lambda k: (k != "timeframe", k != "check",
                                                                                   k != "result", k))
            out += [_md_table(cols, c["sub_results"]), ""]
        for t in c["tables"]:
            out += [f"### {t['title']}", ""]
            if t.get("utc") and "NOT_APPROVED" in h["server_time_rule"]:
                out += [f"**{UNAPPROVED_TZ_LABEL}**", ""]
            out += [_md_table(t["columns"], t["rows"]), ""]
        if c["metrics"]:
            out += ["<details><summary>Metrikler</summary>", "", "```json",
                    json.dumps(c["metrics"], indent=2, ensure_ascii=False, default=str), "```", "</details>", ""]
        for n in c["notes"]:
            out.append(f"- {n}")
        if c["evidence"]:
            out += ["", "**Kanıt dosyaları:**"] + [f"- `{e}`" for e in c["evidence"]]
        out.append("")
    out += ["## P0.7 — Erişim sondajı (yalnızca sayım ve alan adları)", "", "```json",
            json.dumps(doc.get("access_probe_P0_7"), indent=2, ensure_ascii=False), "```", "",
            "## P0.4 — Sembol adı eşlemesi", "", "```json",
            json.dumps(doc.get("symbol_snapshot_P0_4"), indent=2, ensure_ascii=False), "```", ""]
    return "\n".join(out)
