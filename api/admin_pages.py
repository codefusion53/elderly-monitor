"""Phase 3 - HTML for login and the admin settings screen (kept out of app.py)."""

LOGIN_HTML = """<!doctype html><html lang="pt"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zelo Smart - Entrar</title>
<style>
 :root{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
 body{margin:0;background:#f4f6f9;display:flex;min-height:100vh;align-items:center;justify-content:center}
 .box{background:#fff;padding:32px 28px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.08);width:320px}
 h1{font-size:1.2rem;margin:0 0 4px}.sub{color:#6b7280;font-size:.85rem;margin-bottom:20px}
 label{display:block;font-size:.8rem;color:#374151;margin:12px 0 4px}
 input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:.95rem}
 button{width:100%;margin-top:20px;padding:11px;background:#2e6da4;color:#fff;border:0;border-radius:8px;font-size:.95rem;font-weight:600;cursor:pointer}
 .err{background:#fde8e8;color:#8a1f1f;padding:10px;border-radius:8px;font-size:.85rem;margin-top:12px;display:none}
</style></head><body>
<div class="box">
 <h1>Zelo Smart</h1><div class="sub">Monitorizacao de bem-estar</div>
 <label>Utilizador</label><input id="u" autocomplete="username">
 <label>Palavra-passe</label><input id="p" type="password" autocomplete="current-password">
 <button onclick="go()">Entrar</button>
 <div class="err" id="e">Credenciais invalidas.</div>
</div>
<script>
async function go(){
 const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({username:document.getElementById('u').value,password:document.getElementById('p').value})});
 if(r.ok){location.href='/';}else{document.getElementById('e').style.display='block';}
}
document.getElementById('p').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
</script></body></html>"""


def admin_html(residences, settings_by_res):
    rows = ""
    for r in residences:
        rid = r["id"]; s = settings_by_res.get(rid, {})
        rows += f"""
        <div class="rescard">
          <div class="resname">{r['name']}</div>
          <div class="grid">
            <label>Sensibilidade amarelo (fracao do limite)
              <input type="number" step="0.05" min="0.1" max="0.95"
                     value="{s.get('yellow_fraction',0.75)}" id="yf_{rid}"></label>
            <label>Tolerancia offline (min)
              <input type="number" min="1" max="240"
                     value="{s.get('offline_tolerance_min',20)}" id="ot_{rid}"></label>
            <label>Dados considerados desatualizados apos (min)
              <input type="number" min="2" max="120"
                     value="{s.get('stale_after_min',10)}" id="sa_{rid}"></label>
            <label>Limite manual de silencio (min, vazio = automatico)
              <input type="number" min="10" placeholder="automatico"
                     value="{s.get('ceiling_override_min') or ''}" id="co_{rid}"></label>
            <label>Alerta critico: tomada isolada offline apos (min)
              <input type="number" min="20" max="1440"
                     value="{s.get('extended_offline_min',180)}" id="eo_{rid}"></label>
            <label>Alerta critico: TODAS as tomadas offline apos (min)
              <input type="number" min="5" max="720"
                     value="{s.get('total_offline_critical_min',40)}" id="to_{rid}"></label>
          </div>
          <button onclick="save({rid})">Guardar</button>
          <span class="ok" id="ok_{rid}"></span>
        </div>"""
    return """<!doctype html><html lang="pt"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zelo Smart - Administracao</title>
<style>
 :root{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
 body{margin:0;background:#f4f6f9;color:#1f2a37}
 .wrap{max-width:720px;margin:0 auto;padding:24px 16px 48px}
 h1{font-size:1.25rem}.nav a{color:#2e6da4;text-decoration:none;font-size:.85rem;margin-right:14px}
 .rescard{background:#fff;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 4px rgba(0,0,0,.05)}
 .resname{font-weight:600;margin-bottom:10px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 label{display:block;font-size:.78rem;color:#374151}
 input{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;margin-top:4px}
 button{margin-top:14px;padding:9px 16px;background:#2e6da4;color:#fff;border:0;border-radius:8px;font-weight:600;cursor:pointer}
 .ok{color:#2e9e5b;font-size:.82rem;margin-left:10px}
 @media(max-width:520px){.grid{grid-template-columns:1fr}}
</style></head><body>
<div class="wrap">
 <div class="nav"><a href="/">&larr; Painel</a><a href="/api/logout">Sair</a></div>
 <h1>Administracao &middot; Sensibilidade por residencia</h1>
 <p style="color:#6b7280;font-size:.85rem">Ajuste as margens que definem quando o sistema passa a amarelo/vermelho e quando considera os dados desatualizados. As alteracoes aplicam-se de imediato.</p>
 """ + rows + """
</div>
<script>
async function save(rid){
 const body={
  yellow_fraction:parseFloat(document.getElementById('yf_'+rid).value),
  offline_tolerance_min:parseInt(document.getElementById('ot_'+rid).value),
  stale_after_min:parseInt(document.getElementById('sa_'+rid).value),
  ceiling_override_min: document.getElementById('co_'+rid).value?parseInt(document.getElementById('co_'+rid).value):null,
  extended_offline_min:parseInt(document.getElementById('eo_'+rid).value),
  total_offline_critical_min:parseInt(document.getElementById('to_'+rid).value)
 };
 const r=await fetch('/api/settings/'+rid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 document.getElementById('ok_'+rid).textContent = r.ok?'Guardado \u2713':'Erro';
 setTimeout(()=>{document.getElementById('ok_'+rid).textContent='';},2500);
}
</script></body></html>"""
