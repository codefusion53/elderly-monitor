"""Shared page chrome: the <head> styles block and the top nav bar."""

HEAD = """<!doctype html><html lang="pt"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zelo Smart - Administracao</title>
<style>
 :root{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
 body{margin:0;background:#f4f6f9;color:#1f2a37}
 .wrap{max-width:720px;margin:0 auto;padding:20px 16px 48px}
 h1{font-size:1.25rem;margin:6px 0 2px}
 .nav{display:flex;gap:16px;margin-bottom:14px;border-bottom:1px solid #e5e7eb;padding-bottom:10px}
 .nav a{color:#2e6da4;text-decoration:none;font-size:.9rem}
 .nav a.active{font-weight:700;color:#1f3a5f}
 .nav a.right{margin-left:auto;color:#9aa2ad}
 .rescard{background:#fff;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 4px rgba(0,0,0,.05)}
 .resname{font-weight:600;margin-bottom:10px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 label{display:block;font-size:.78rem;color:#374151}
 input{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;margin-top:4px}
 button{margin-top:14px;padding:9px 16px;background:#2e6da4;color:#fff;border:0;border-radius:8px;font-weight:600;cursor:pointer}
 .ok{color:#2e9e5b;font-size:.82rem;margin-left:10px}
 .charts h2{font-size:1rem;margin:18px 0 8px}
 .charts img{width:100%;border:1px solid #e5e7eb;border-radius:10px;background:#fff}
 .charthint{color:#9aa2ad;font-size:.75rem;margin-top:4px;margin-bottom:8px}
 .muted{color:#6b7280;font-size:.82rem}
 .kv{font-size:.85rem;margin:4px 0}
 .strip{display:flex;gap:4px;flex-wrap:wrap;margin-top:10px}
 .cell{border-radius:6px;padding:6px 4px;min-width:52px;text-align:center}
 .cell .d{font-size:.68rem;opacity:.9}.cell .f{font-size:.66rem;font-weight:700}
 table.log{width:100%;border-collapse:collapse;font-size:.8rem;margin-top:6px}
 table.log th{text-align:left;color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;padding:6px 8px}
 table.log td{border-bottom:1px solid #f0f2f5;padding:6px 8px}
 .winsel{font-size:.82rem;color:#6b7280;margin-bottom:14px}
 .winsel a{color:#2e6da4;text-decoration:none;margin:0 6px;padding:2px 6px;border-radius:6px}
 .winsel a.on{background:#2e6da4;color:#fff;font-weight:600}
 @media(max-width:520px){.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap">"""


def nav(active):
    def cls(name): return ' class="active"' if name == active else ''
    return (f'<div class="nav">'
            f'<a href="/">Painel</a>'
            f'<a href="/admin"{cls("settings")}>Definicoes</a>'
            f'<a href="/admin/charts"{cls("charts")}>Graficos</a>'
            f'<a href="/admin/report"{cls("report")}>Relatorio</a>'
            f'<a href="/suporte"{cls("faq")}>Suporte</a>'
            f'<a href="/api/logout" class="right">Sair</a>'
            f'</div>')
