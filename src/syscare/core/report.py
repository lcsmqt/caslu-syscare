"""Export scan results to JSON or a standalone HTML report (for clients/audits)."""
from __future__ import annotations

import datetime as dt
import html
import json

from .. import APP_NAME
from . import sysinfo
from .analyzer import ScanResult


def to_json(res: ScanResult, startup: list | None = None) -> str:
    return json.dumps({
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "system": sysinfo.summary(),
        "health_score": res.health_score,
        "reclaimable_mem_mb": round(res.reclaimable_mem_mb, 1),
        "findings": [f.to_dict() for f in res.findings if f.category in ("Desnecessário", "Revisar")],
        "startup": [s.to_dict() for s in (startup or [])],
    }, indent=2, ensure_ascii=False)


def to_html(res: ScanResult, startup: list | None = None) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(f.name)}</td><td>{e(f.category)}</td><td>{f.cpu:.1f}%</td>"
        f"<td>{f.mem_mb:.0f} MB</td><td>{e(f.reason)}</td></tr>"
        for f in res.findings if f.category in ("Desnecessário", "Revisar"))
    srows = "".join(
        f"<tr><td>{e(s.name)}</td><td>{e(s.location)}</td><td>{'sim' if s.flagged else ''}</td>"
        f"<td>{e(s.reason)}</td></tr>" for s in (startup or []))
    sysrows = "".join(f"<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>" for k, v in sysinfo.summary().items())
    color = "#22c55e" if res.health_score >= 75 else "#f59e0b" if res.health_score >= 50 else "#ef4444"
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Relatório {APP_NAME}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#111}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}td,th{{border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:14px}}
th{{background:#f3f4f6}}.score{{font-size:3rem;font-weight:700;color:{color}}}</style>
<h1>Relatório de Análise do Sistema</h1><p>Gerado em {dt.datetime.now():%d/%m/%Y %H:%M}</p>
<p>Saúde do sistema: <span class="score">{res.health_score}/100</span></p>
<p>RAM recuperável ao encerrar programas desnecessários: <b>{res.reclaimable_mem_mb:.0f} MB</b></p>
<h2>Sistema</h2><table>{sysrows}</table>
<h2>Programas desnecessários / para revisar</h2>
<table><tr><th>Programa</th><th>Categoria</th><th>CPU</th><th>RAM</th><th>Motivo</th></tr>{rows}</table>
<h2>Inicialização</h2>
<table><tr><th>Nome</th><th>Origem</th><th>Sinalizado</th><th>Motivo</th></tr>{srows}</table>
</html>"""


# ====================================================================== full professional report
from .issues import SEVERITY_LABEL  # noqa: E402
from .storage_health import STATUS_LABEL  # noqa: E402
from .safeaction import RISK_LABEL  # noqa: E402,F401

TECH_FIELDS = [("customer", "Cliente"), ("device", "Equipamento"), ("technician", "Técnico"),
               ("ticket", "Chamado"), ("reported_issue", "Problema relatado"), ("diagnosis", "Diagnóstico"),
               ("actions", "Ações realizadas"), ("recommendations", "Recomendações do técnico")]

_CSS = """
:root{--fg:#111827;--mut:#6b7280;--line:#e5e7eb;--ac:#4f46e5}
*{box-sizing:border-box}body{font-family:'Segoe UI',system-ui,sans-serif;color:var(--fg);max-width:920px;margin:2rem auto;padding:0 1.2rem;line-height:1.45}
h1{margin:0 0 .2rem;font-size:1.7rem}h2{margin:1.8rem 0 .5rem;font-size:1.15rem;border-bottom:2px solid var(--ac);padding-bottom:.2rem}
.sub{color:var(--mut);font-size:.9rem}table{border-collapse:collapse;width:100%;margin:.4rem 0;font-size:.88rem}
td,th{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}th{background:#f3f4f6}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.78rem;font-weight:600;color:#fff}
.high,.CRITICAL{background:#dc2626}.medium,.ATTENTION{background:#d97706}.low{background:#2563eb}.info,.UNKNOWN{background:#6b7280}.HEALTHY,.success{background:#16a34a}.warning{background:#d97706}.failed{background:#dc2626}
.score{font-size:2.6rem;font-weight:700}.note{background:#f9fafb;border-left:3px solid var(--ac);padding:.5rem .8rem;margin:.4rem 0;white-space:pre-wrap}
.blank{min-height:3.2rem}footer{margin-top:2rem;color:var(--mut);font-size:.8rem;border-top:1px solid var(--line);padding-top:.6rem}
@media print{body{margin:0;max-width:none}h2{break-after:avoid}table,.note{break-inside:avoid}a{color:inherit;text-decoration:none}}
"""


def _e(x) -> str:
    return html.escape(str(x))


def _kv(d: dict) -> str:
    return "<table>" + "".join(f"<tr><th style='width:34%'>{_e(k)}</th><td>{_e(v)}</td></tr>"
                               for k, v in d.items()) + "</table>"


def _table(headers: list[str], rows: list[list[str]], raw_cols: tuple[int, ...] = ()) -> str:
    if not rows:
        return "<p class='sub'>Nenhum item.</p>"
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c if i in raw_cols else _e(c)}</td>" for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _tag(cls: str, text: str) -> str:
    return f"<span class='tag {_e(cls)}'>{_e(text)}</span>"


def _p1_score(snap: dict) -> str:
    sc = snap.get("score")
    if not sc:
        return ""
    rows = [[r["category"], f"{r['max']}", ("-" + str(r["deduction"])) if r["evaluated"] else "não avaliado",
             "; ".join(r["reasons"]) if r["reasons"] else ("—" if r["evaluated"] else "")] for r in sc["breakdown"]]
    return (f"<h2>Pontuação de saúde</h2><p><span class='score'>{sc['score']}/100</span> — cobertura da avaliação: "
            f"{sc['coverage_pct']}%. Áreas não avaliadas não penalizam a nota.</p>"
            + _table(["Categoria", "Peso", "Dedução", "Motivos"], rows))


def _p1_recs(snap: dict) -> str:
    recs = snap.get("recommendations") or []
    if not recs:
        return ""
    return "<h2>Recomendações priorizadas</h2>" + _table(
        ["Prioridade", "Área", "Achado", "Recomendação", "Evidência"],
        [[_tag(r["priority"], SEVERITY_LABEL.get(r["priority"], r["priority"])), r["area"], r["finding"],
          r["recommendation"], r["reason"]] for r in recs], raw_cols=(0,))


def _p1_details(snap: dict) -> str:
    out = []
    perf = snap.get("performance")
    if perf and perf.get("sufficient"):
        def fmt(k):
            s = perf.get(k)
            return f"média {s['avg']} / p95 {s['p95']} / máx {s['max']}" if s else "Indisponível"
        out.append(f"<h2>Desempenho medido</h2><p class='sub'>Amostragem de {perf['duration_s']:.0f} s "
                   f"({perf['samples']} amostras). Reflete apenas este intervalo.</p>" + _kv({
                       "CPU (%)": fmt("cpu"), "RAM (%)": fmt("mem"), "Disco (MB/s)": fmt("disk_mbps"),
                       "Disco ocupado (%)": fmt("disk_busy"), "Rede (MB/s)": fmt("net_mbps")}))
    fs = snap.get("free_space")
    if fs:
        out.append(f"<p>Espaço livre em {_e(fs['path'])}: <b>{fs['free_gb']} GB</b> de {fs['total_gb']} GB ({fs['free_pct']}%).</p>")
    st = snap.get("stability")
    if st:
        out.append("<h2>Estabilidade</h2>")
        if st.get("message"):
            out.append(f"<p class='sub'>{_e(st['message'])}</p>")
        else:
            out.append(_kv({f"Telas azuis ({st['days']} dias)": len(st["bugchecks"]),
                            "Desligamentos inesperados": len(st["unexpected_shutdowns"]),
                            "Falhas de aplicativos": len(st["app_crashes"]),
                            "Falhas de serviços": len(st["service_failures"]),
                            "Minidumps encontrados": len(st.get("minidumps", []))}))
            if st["bugchecks"]:
                out.append(_table(["Data/hora", "Código", "Nome"],
                                  [[b["time"], b["code"], b["name"]] for b in st["bugchecks"]]))
    wu = snap.get("windows_update")
    if wu:
        rows = dict(wu.get("version", {}))
        rows.update({"Última instalação": wu.get("last_install") or "Indisponível",
                     "Última verificação": wu.get("last_search") or "Indisponível",
                     "Reinicialização pendente": ", ".join(wu.get("reboot_reasons", [])) or "Não"})
        out.append("<h2>Windows Update</h2>" + (_e(wu["message"]) if wu.get("message") else "") + _kv(rows))
    cmp_ = snap.get("comparison")
    if cmp_:
        out.append(f"<h2>Antes e depois</h2><p class='sub'>Antes: {_e(cmp_['before_taken'])} • Depois: "
                   f"{_e(cmp_['after_taken'])}. Somente valores medidos; 'não medido' quando faltou dado.</p>"
                   + _table(["Indicador", "Antes", "Depois", "Variação", "Resultado"],
                            [[r["metric"], r["before"] if r["before"] is not None else "—",
                              r["after"] if r["after"] is not None else "—",
                              r["delta"] if r["delta"] is not None else "—", r["verdict"]] for r in cmp_["rows"]]))
    return "".join(out)


def to_json_full(snap: dict, res: ScanResult | None = None, startup: list | None = None,
                 technician: dict | None = None) -> str:
    data = dict(snap)
    if res is not None:
        data["process_analysis"] = {"health_score": res.health_score,
                                    "reclaimable_mem_mb": round(res.reclaimable_mem_mb, 1),
                                    "findings": [f.to_dict() for f in res.findings
                                                 if f.category in ("Desnecessário", "Revisar")]}
    if startup is not None:
        data["startup"] = [s.to_dict() for s in startup]
    if technician:
        data["technician"] = technician
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def to_html_full(snap: dict, res: ScanResult | None = None, startup: list | None = None,
                 technician: dict | None = None) -> str:
    parts: list[str] = []
    sysd = snap.get("system", {})
    parts.append(f"<h1>Relatório de Diagnóstico do Computador</h1><div class='sub'>Gerado em "
                 f"{_e(snap.get('generated', ''))} • {APP_NAME} {_e(snap.get('app_version', ''))}</div>")
    t = {k: v for k, v in (technician or {}).items() if v}
    if t:
        rows = [(lbl, t[k]) for k, lbl in TECH_FIELDS[:4] if k in t]
        parts.append("<h2>Atendimento</h2>" + _kv(dict(rows)))
    if t.get("reported_issue"):
        parts.append(f"<h2>Problema relatado</h2><div class='note'>{_e(t['reported_issue'])}</div>")

    issues = snap.get("issues", [])
    counts = {s: sum(1 for i in issues if i["severity"] == s) for s in ("high", "medium", "low")}
    parts.append("<h2>Resumo</h2>")
    if res is not None:
        parts.append(f"<p>Análise de processos: <span class='score'>{res.health_score}/100</span> — "
                     f"RAM potencialmente recuperável: <b>{res.reclaimable_mem_mb:.0f} MB</b></p>")
    parts.append(f"<p>Problemas detectados: {_tag('high', 'ALTA')} {counts['high']} &nbsp; "
                 f"{_tag('medium', 'MÉDIA')} {counts['medium']} &nbsp; {_tag('low', 'BAIXA')} {counts['low']}</p>")

    parts.append(_p1_score(snap))
    parts.append("<h2>Máquina e sistema operacional</h2>" + _kv(sysd))

    hw = snap.get("hardware")
    if hw:
        rows = []
        from .hardware import flatten
        rows = flatten(hw)
        parts.append("<h2>Hardware</h2>" + _table(["Componente", "Item", "Valor"], rows))
        for n in hw.get("notes", []):
            parts.append(f"<p class='sub'>{_e(n)}</p>")

    disks = snap.get("storage", [])
    parts.append("<h2>Saúde dos discos</h2>")
    if disks:
        rows = []
        for d in disks:
            m = d["metrics"]
            life = m.get("remaining_life_pct")
            used = m.get("percentage_used")
            wear = f"{used:.0f}% usado" if isinstance(used, (int, float)) else \
                f"{life:.0f}% restante" if isinstance(life, (int, float)) else "Indisponível"
            rows.append([f"{d['model']} ({d['media_type']}, {d['capacity_gb'] or '?'} GB)",
                         _tag(d["status"], STATUS_LABEL.get(d["status"], d["status"])),
                         f"{m['temperature_c']} °C" if m.get("temperature_c") is not None else "Indisponível",
                         f"{m['power_on_hours']} h" if m.get("power_on_hours") is not None else "Indisponível",
                         wear, d["source"] or "-"])
        parts.append(_table(["Disco", "Estado", "Temperatura", "Horas ligado", "Desgaste", "Fonte"], rows,
                            raw_cols=(1,)))
        for d in disks:
            for r in d["reasons"]:
                parts.append(f"<div class='note'><b>{_e(d['model'])}</b>: {_e(r['text'])}</div>")
            if d.get("note") and d["status"] == "UNKNOWN":
                parts.append(f"<p class='sub'>{_e(d['model'])}: {_e(d['note'])}</p>")
    else:
        parts.append("<p class='sub'>Nenhum disco reportado.</p>")

    b = snap.get("battery", {})
    if b.get("present"):
        rows = {"Carga atual": f"{b['charge_pct']}%", "Estado": b["state"],
                "Saúde da bateria": f"{b['health_pct']}%" if b.get("health_pct") is not None else "Indisponível",
                "Desgaste": f"{b['wear_pct']}%" if b.get("wear_pct") is not None else "Indisponível",
                "Ciclos de carga": b.get("cycle_count") or "Indisponível", "Autonomia estimada": b.get("runtime")}
        parts.append("<h2>Bateria</h2>" + _kv(rows))

    sec = snap.get("security", {}).get("summary", {})
    if sec:
        parts.append("<h2>Segurança</h2>" + _kv(sec))

    dv = snap.get("devices", {})
    parts.append("<h2>Dispositivos e drivers</h2>")
    if dv.get("message"):
        parts.append(f"<p class='sub'>{_e(dv['message'])}</p>")
    else:
        parts.append(f"<p class='sub'>{dv.get('total_devices', 0)} dispositivos, {dv.get('total_drivers', 0)} drivers analisados.</p>")
        parts.append(_table(["Dispositivo", "Categoria", "Estado", "Código", "Explicação"],
                            [[p["name"], p["category"], p["state"], p["code"] or "", p["explanation"]]
                             for p in dv.get("problems", [])]))

    parts.append(_p1_details(snap))
    parts.append(_p1_recs(snap))
    parts.append("<h2>Problemas detectados</h2>")
    parts.append(_table(["Prioridade", "Área", "Achado", "Detalhe", "Recomendação"],
                        [[_tag(i["severity"], SEVERITY_LABEL.get(i["severity"], i["severity"])), i["area"],
                          i["title"], i["detail"], i["recommendation"]] for i in issues], raw_cols=(0,)))

    if res is not None:
        rows = [[f.name, f.category, f"{f.cpu:.1f}%", f"{f.mem_mb:.0f} MB", f.reason]
                for f in res.findings if f.category in ("Desnecessário", "Revisar")]
        parts.append("<h2>Análise de processos</h2>" + _table(["Programa", "Categoria", "CPU", "RAM", "Motivo"], rows))
    if startup is not None:
        parts.append("<h2>Programas de inicialização</h2>" + _table(
            ["Nome", "Origem", "Impacto estimado", "Sinalizado", "Motivo"],
            [[s.name, s.location, s.impact, "sim" if s.flagged else "", s.reason] for s in startup]))

    rh = snap.get("repair_history", [])
    acts = snap.get("recent_actions", [])
    parts.append("<h2>Ações realizadas</h2>")
    rows = [[e["timestamp"], e["action"], e["target"], e["result"]] for e in rh + acts]
    parts.append(_table(["Data/hora", "Ação", "Alvo", "Resultado"], rows))
    if t.get("actions"):
        parts.append(f"<div class='note'>{_e(t['actions'])}</div>")

    if snap.get("errors"):
        parts.append("<h2>Seções não coletadas</h2>" + _kv(snap["errors"]))

    parts.append("<h2>Diagnóstico e recomendações do técnico</h2>")
    for k, lbl in TECH_FIELDS[5:]:
        parts.append(f"<b>{_e(lbl)}</b><div class='note blank'>{_e(t.get(k, ''))}</div>")
    if t.get("technician"):
        parts.append(f"<p>Técnico responsável: <b>{_e(t['technician'])}</b></p>")

    parts.append("<footer>Relatório gerado localmente. Nenhum dado foi enviado para a internet. "
                 "Os resultados refletem o momento da coleta; indicadores isolados não confirmam falhas de hardware."
                 " Para salvar em PDF, use Imprimir → Salvar como PDF.</footer>")
    return (f"<!doctype html><html lang='pt-BR'><meta charset='utf-8'><title>Relatório de Diagnóstico</title>"
            f"<style>{_CSS}</style><body>{''.join(parts)}</body></html>")
