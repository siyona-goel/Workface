"""Day-9 thermal certificate + CSV export from the record hash chain.

    python -m apps.api.export.certificate
    python -m apps.api.export.certificate --chain data/fixtures/record_chain_live.json

Writes under data/exports/:
  certificate_<run_id>.json   — ThermalCertificate shape
  certificate_<run_id>.csv    — one row per record entry
  certificate_<run_id>.pdf    — printable advisory certificate
"""

from __future__ import annotations

import argparse
import csv
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "data" / "fixtures"
EXPORTS = REPO / "data" / "exports"
DEFAULT_CHAIN = FIXTURES / "record_chain_live.json"
HERO_PDF = FIXTURES / "twin" / "heat_intelligence_hero.pdf"
TZ = timezone(timedelta(hours=-7))


def _load_chain(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _payload(entry: dict) -> dict:
    return entry.get("payload") or {}


def build_certificate(chain: dict[str, Any]) -> dict[str, Any]:
    """Build a ThermalCertificate-shaped dict from a RecordChain JSON."""
    entries = chain.get("entries") or []
    if not entries:
        raise ValueError("record chain has no entries — run the agent worker first")

    payloads = [_payload(e) for e in entries]
    run_id = payloads[0].get("run_id") or "unknown-run"
    site_id = chain.get("site_id") or "NPX-FAB-P2"

    # Prefer a non-compliant / escalated entry as the face of the certificate
    primary = next(
        (
            p
            for p in payloads
            if p.get("verdict") in ("non_compliant", "marginal")
            or p.get("action") in ("escalate", "mitigate", "shift")
        ),
        payloads[0],
    )

    # Synthetic hourly series for the certificate body (demo window)
    # Real thermal series can replace this when T3's bundle is wired.
    anchor = primary.get("ts") or "2026-08-24T06:00:00-07:00"
    try:
        start = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
    except ValueError:
        start = datetime(2026, 8, 24, 6, 0, tzinfo=TZ)
    if start.tzinfo is None:
        start = start.replace(tzinfo=TZ)

    hours = []
    for i in range(12):
        ts = start + timedelta(hours=i)
        # Phoenix August morning → hot afternoon pattern
        t_air = 28.0 + i * 1.4
        t_surf = t_air + 4.0 + (0.8 if 10 <= ts.hour <= 16 else 0)
        t_dew = 12.0 + i * 0.3
        wbgt = t_air - 2.5
        passed = t_surf <= 48.9 and t_surf >= t_dew + 2.8
        hours.append(
            {
                "ts": ts.isoformat(),
                "t_air_c": round(t_air, 2),
                "t_surf_c": round(t_surf, 2),
                "t_dew_c": round(t_dew, 2),
                "wbgt_c": round(wbgt, 2),
                "compliant": passed,
                "binding_constraint_id": None
                if passed
                else primary.get("binding_constraint_id"),
            }
        )

    compliant_n = sum(1 for h in hours if h["compliant"])
    cert = {
        "schema_version": "1.0.0",
        "certificate_id": f"CERT-{run_id[:20]}-{uuid.uuid4().hex[:6]}",
        "site_id": site_id,
        "issued_at": datetime.now(TZ).isoformat(),
        "run_id": run_id,
        "activity_id": primary.get("activity_id"),
        "activity_name": primary.get("activity_name"),
        "trade_id": primary.get("trade_id"),
        "trade_display_name": primary.get("trade_display_name"),
        "work_face_id": primary.get("work_face_id"),
        "work_face_name": primary.get("work_face_name"),
        "verdict": primary.get("verdict"),
        "binding_constraint_id": primary.get("binding_constraint_id"),
        "clause_cited": primary.get("clause_cited"),
        "standard_ref": primary.get("standard_ref"),
        "compliant_hours": primary.get("compliant_hours"),
        "hours_total": len(hours),
        "hours_compliant": compliant_n,
        "action": primary.get("action"),
        "gate_decision": primary.get("gate_decision"),
        "gate_rule_id": primary.get("gate_rule_id"),
        "gate_reason": primary.get("gate_reason"),
        "usd_at_risk": (primary.get("usd_exposure") or {}).get("at_risk")
        if isinstance(primary.get("usd_exposure"), dict)
        else None,
        "usd_protected": (primary.get("usd_exposure") or {}).get("protected")
        if isinstance(primary.get("usd_exposure"), dict)
        else None,
        "hours": hours,
        "fg_activity_ids": primary.get("fg_activity_ids") or [],
        "record_entry_hashes": [e.get("hash") for e in entries if e.get("hash")],
        "registry_version": primary.get("registry_version"),
        "heat_intelligence_pdf_ref": (
            "data/fixtures/twin/heat_intelligence_hero.pdf"
            if HERO_PDF.exists()
            else None
        ),
        "approver": primary.get("approver"),
        "advisory_notice": (
            "Advisory and contractual. Does not replace the field measurement "
            "the referenced standard requires."
        ),
        "chain_head_hash": chain.get("head_hash"),
        "n_record_entries": len(entries),
    }
    return cert


def write_csv(chain: dict[str, Any], path: Path) -> None:
    entries = chain.get("entries") or []
    fields = [
        "seq",
        "hash",
        "prev_hash",
        "run_id",
        "ts",
        "activity_id",
        "activity_name",
        "trade_id",
        "work_face_id",
        "verdict",
        "action",
        "gate_decision",
        "gate_rule_id",
        "binding_constraint_id",
        "standard_ref",
        "compliant_hours",
        "clause_cited",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            p = _payload(e)
            w.writerow(
                {
                    "seq": e.get("seq"),
                    "hash": e.get("hash"),
                    "prev_hash": e.get("prev_hash"),
                    "run_id": p.get("run_id"),
                    "ts": p.get("ts"),
                    "activity_id": p.get("activity_id"),
                    "activity_name": p.get("activity_name"),
                    "trade_id": p.get("trade_id"),
                    "work_face_id": p.get("work_face_id"),
                    "verdict": p.get("verdict"),
                    "action": p.get("action"),
                    "gate_decision": p.get("gate_decision"),
                    "gate_rule_id": p.get("gate_rule_id"),
                    "binding_constraint_id": p.get("binding_constraint_id"),
                    "standard_ref": p.get("standard_ref"),
                    "compliant_hours": p.get("compliant_hours"),
                    "clause_cited": (p.get("clause_cited") or "")[:200],
                }
            )


def write_pdf(cert: dict[str, Any], path: Path) -> None:
    """Minimal single-page PDF without third-party deps."""
    lines = [
        "WORKFACE THERMAL CERTIFICATE",
        f"Certificate ID: {cert.get('certificate_id')}",
        f"Site: {cert.get('site_id')}    Issued: {cert.get('issued_at')}",
        f"Run: {cert.get('run_id')}",
        "",
        f"Activity: {cert.get('activity_id')} — {cert.get('activity_name')}",
        f"Trade: {cert.get('trade_display_name')} ({cert.get('trade_id')})",
        f"Work face: {cert.get('work_face_id')} — {cert.get('work_face_name')}",
        "",
        f"Verdict: {cert.get('verdict')}",
        f"Binding constraint: {cert.get('binding_constraint_id')}",
        f"Action: {cert.get('action')}    Gate: {cert.get('gate_decision')} ({cert.get('gate_rule_id')})",
        f"Gate reason: {cert.get('gate_reason') or '—'}",
        "",
        f"Standard: {cert.get('standard_ref')}",
        "Clause:",
        str(cert.get("clause_cited") or "")[:500],
        "",
        f"Series: {cert.get('hours_compliant')}/{cert.get('hours_total')} hours compliant (certificate window)",
        f"Record entries bound: {cert.get('n_record_entries')}",
        f"Chain head: {cert.get('chain_head_hash')}",
        f"FG activity ids: {', '.join(cert.get('fg_activity_ids') or []) or '—'}",
        f"Heat intelligence PDF: {cert.get('heat_intelligence_pdf_ref') or '—'}",
        "",
        cert.get("advisory_notice") or "",
    ]
    # Escape for PDF text
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    y = 750
    content_ops = ["BT", "/F1 10 Tf", "50 770 Td", "14 TL"]
    first = True
    for line in lines:
        safe = esc(line)
        if first:
            content_ops.append(f"({safe}) Tj")
            first = False
        else:
            content_ops.append(f"T* ({safe}) Tj")
    content_ops.append("ET")
    stream = "\n".join(content_ops).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))


def export_certificate_bundle(chain_path: Path, out_dir: Path | None = None) -> dict[str, Path]:
    chain = _load_chain(chain_path)
    cert = build_certificate(chain)
    out_dir = out_dir or EXPORTS
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = (cert.get("run_id") or "run").replace("/", "-")
    json_path = out_dir / f"certificate_{run_id}.json"
    csv_path = out_dir / f"certificate_{run_id}.csv"
    pdf_path = out_dir / f"certificate_{run_id}.pdf"

    json_path.write_text(json.dumps(cert, indent=2, default=str), encoding="utf-8")
    write_csv(chain, csv_path)
    write_pdf(cert, pdf_path)
    return {"json": json_path, "csv": csv_path, "pdf": pdf_path, "certificate_id": cert["certificate_id"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export thermal certificate PDF + CSV from record chain")
    ap.add_argument("--chain", type=Path, default=DEFAULT_CHAIN)
    ap.add_argument("--out", type=Path, default=EXPORTS)
    args = ap.parse_args(argv)

    if not args.chain.exists():
        raise SystemExit(
            f"missing {args.chain} — run: python -m apps.api.agent.worker"
        )
    paths = export_certificate_bundle(args.chain, args.out)
    print(f"certificate_id={paths['certificate_id']}")
    for k in ("json", "csv", "pdf"):
        print(f"  {k}: {paths[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
