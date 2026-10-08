"""Login page (standalone; does not use the admin nav)."""

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
 <div style="text-align:center;margin-top:18px"><a href="/privacidade" style="color:#9aa2ad;font-size:.78rem;text-decoration:none">Politica de Privacidade</a></div>
</div>
<script>
async function go(){
 const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({username:document.getElementById('u').value,password:document.getElementById('p').value})});
 if(r.ok){location.href='/';}else{document.getElementById('e').style.display='block';}
}
document.getElementById('p').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
</script></body></html>"""
