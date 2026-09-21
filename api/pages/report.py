"""Report page: routine summary + connectivity + alert history (configurable window)."""
from api.pages._shared import HEAD, nav

STATE_COLORS = {"GREEN": "#2e9e5b", "YELLOW": "#e6b800",
                "RED": "#d64545", "SEM DADOS": "#b0b7c0"}


def report_html(data):
    def hm(h): return f"{h:02d}h"

    parts = [HEAD, nav("report"),
             f'<h1>Relatorio</h1>',
             f'<p style="color:#6b7280;font-size:.85rem">Gerado em {data["generated"]} '
             f'&middot; ultimos {data["window_days"]} dias.</p>',
             '<div class="winsel">Periodo: '
             + " ".join(
                 f'<a href="/admin/report?days={d}"'
                 + (' class="on"' if d == data["window_days"] else '')
                 + f'>{d} dias</a>' for d in (7, 14, 30, 90))
             + '</div>']

    for r in data["routines"]:
        parts.append('<div class="rescard">')
        parts.append(f'<div class="resname">{r["device"]}</div>')
        if not r.get("signal"):
            parts.append(f'<div class="muted">{r["reason"]}</div></div>')
            continue
        parts.append(
            f'<div class="muted">Rotina aprendida ao longo de {r["days_observed"]} dias, '
            f'{r["events"]} eventos de atividade.</div>')
        parts.append(
            f'<div class="kv"><b>Horas de pico:</b> '
            f'{", ".join(hm(h) for h in r["peak_hours"]) or "-"}</div>')
        parts.append(
            f'<div class="kv"><b>Intervalo tipico entre eventos:</b> {r["typical_gap_min"]} min '
            f'&middot; <b>limite de silencio normal:</b> {r["ceiling_min"]} min</div>')
        parts.append(
            f'<div class="kv"><b>Horas habitualmente calmas:</b> '
            f'{", ".join(hm(h) for h in r["quiet_hours"]) or "nenhuma"}</div>')
        strip = '<div class="strip">'
        for day, n, worst, flag in r["days"]:
            lbl = flag.replace("SEM DADOS", "s/d")
            strip += (f'<div class="cell" style="background:{STATE_COLORS[flag]};'
                      f'color:{"#5a4a00" if flag=="YELLOW" else "white"}">'
                      f'<div class="d">{day.strftime("%d/%m")}</div>'
                      f'<div class="f">{lbl}</div></div>')
        strip += '</div>'
        parts.append(strip)
        parts.append('</div>')

    parts.append('<div class="rescard"><div class="resname">Historico de conectividade</div>')
    if data["connectivity"]:
        parts.append('<table class="log"><tr><th>Quando</th><th>Tomada</th><th>Evento</th><th>Detalhe</th></tr>')
        for e in data["connectivity"]:
            label = "Offline" if e["type"] == "offline_confirmed" else "Voltou online"
            parts.append(f'<tr><td>{e["ts"]}</td><td>{e["device"]}</td>'
                         f'<td>{label}</td><td class="muted">{e["detail"] or ""}</td></tr>')
        parts.append('</table>')
    else:
        parts.append('<div class="muted">Sem eventos de conectividade registados.</div>')
    parts.append('</div>')

    parts.append('<div class="rescard"><div class="resname">Historico de alertas</div>')
    if data["alerts"]:
        parts.append('<table class="log"><tr><th>Quando</th><th>Canal</th><th>Para</th>'
                     '<th>Nivel</th><th>Estado</th><th>Assunto</th><th>OK</th></tr>')
        for a in data["alerts"]:
            ok = "sim" if a["ok"] else "falha"
            parts.append(f'<tr><td>{a["ts"]}</td><td>{a["channel"]}</td>'
                         f'<td class="muted">{a["to"] or ""}</td><td>{a["tier"]}</td>'
                         f'<td>{a["state"]}</td><td class="muted">{a["subject"] or ""}</td>'
                         f'<td>{ok}</td></tr>')
        parts.append('</table>')
    else:
        parts.append('<div class="muted">Ainda nao foram enviados alertas.</div>')
    parts.append('</div>')

    parts.append('</div></body></html>')
    return "".join(parts)
