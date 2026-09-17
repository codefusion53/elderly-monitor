"""
Phase 3 - FastAPI app: auth, caregiver dashboard, admin settings.

Roles:
  caregiver - sees the semaforo dashboard (scoped to their residence)
  admin     - sees the dashboard + /admin settings (all residences)

Run:  pip install fastapi uvicorn bcrypt
      uvicorn api.app:app --host 127.0.0.1 --port 8000

First-run: create an admin user from a shell:
      python -c "from api.auth import create_user; create_user('admin','CHANGE_ME',role='admin')"
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from api.state_service import compute_all_states
from api.admin_pages import LOGIN_HTML, admin_html
from api import auth
from interface.data_access import connect

app = FastAPI(title="Zelo Smart")

COOKIE = "zs_session"


def _current_user(request: Request):
    return auth.user_for_token(request.cookies.get(COOKIE))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    token = auth.authenticate(body.get("username", ""), body.get("password", ""))
    if not token:
        return JSONResponse({"error": "invalid"}, status_code=401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=60*60*24*7)
    return resp


@app.get("/api/logout")
def logout(request: Request):
    tok = request.cookies.get(COOKIE)
    if tok:
        auth.logout(tok)
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_HTML


@app.get("/api/state")
def state(request: Request):
    if not _current_user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        return JSONResponse(compute_all_states())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    # show an admin link if applicable
    admin_link = ('<a href="/admin" style="color:#2e6da4;font-size:.85rem">Administracao</a>'
                  if user["role"] == "admin" else "")
    return DASHBOARD_HTML.replace("<!--ADMINLINK-->", admin_link) \
                         .replace("<!--USER-->", user.get("display_name") or user["username"])


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return HTMLResponse("<h3>Acesso restrito ao administrador.</h3>", status_code=403)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM residences ORDER BY id")
            residences = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    finally:
        conn.close()
    settings = {r["id"]: auth.get_settings(r["id"]) for r in residences}
    return admin_html(residences, settings)


@app.post("/api/settings/{residence_id}")
async def save_settings(residence_id: int, request: Request):
    user = _current_user(request)
    if not user or user["role"] != "admin":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await request.json()
    auth.update_settings(residence_id, **body)
    return JSONResponse({"ok": True})


DASHBOARD_HTML = """<!doctype html>
<html lang="pt"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zelo Smart - Estado</title>
<style>
 :root{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
 body{margin:0;background:#f4f6f9;color:#1f2a37}
 .wrap{max-width:640px;margin:0 auto;padding:24px 16px 48px}
 .bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
 .bar .who{color:#6b7280;font-size:.8rem}
 h1{font-size:1.25rem;font-weight:600;margin:0}
 .sub{color:#6b7280;font-size:.85rem;margin-bottom:16px}
 .big{border-radius:16px;padding:28px 22px;color:#fff;margin-bottom:20px;box-shadow:0 2px 10px rgba(0,0,0,.06)}
 .big .label{font-size:.8rem;opacity:.9;letter-spacing:.04em;text-transform:uppercase}
 .big .state{font-size:2rem;font-weight:700;margin:6px 0}.big .reason{font-size:.95rem;opacity:.95}
 .GREEN{background:#2e9e5b}.YELLOW{background:#e6b800;color:#3a2f00}
 .RED{background:#d64545}.SYSTEM{background:#4b5563}.UNKNOWN{background:#9aa2ad}
 .card{background:#fff;border-radius:12px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,.05)}
 .card .top{display:flex;align-items:center;gap:14px}
 .dot{width:14px;height:14px;border-radius:50%;flex:none}
 .d-GREEN{background:#2e9e5b}.d-YELLOW{background:#e6b800}.d-RED{background:#d64545}.d-UNKNOWN{background:#9aa2ad}
 .card .name{font-weight:600}.card .meta{color:#6b7280;font-size:.82rem;margin-top:2px}
 .chips{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}
 .chip{background:#eef2f7;color:#374151;border-radius:20px;padding:3px 10px;font-size:.72rem}
 .banner{border-radius:12px;padding:12px 16px;margin-bottom:16px;font-size:.9rem;font-weight:600}
 .banner.warn{background:#fff3cd;color:#7a5c00;border:1px solid #ffe08a}
 .banner.okb{background:#e7f6ec;color:#1e6b3a;border:1px solid #b7e4c7}
 .foot{color:#9aa2ad;font-size:.75rem;text-align:center;margin-top:18px}
 .foot a{color:#9aa2ad}
 .err{background:#fde8e8;color:#8a1f1f;padding:12px;border-radius:10px}
</style></head><body>
<div class="wrap">
 <div class="bar"><h1>Estado da casa</h1><div class="who"><!--ADMINLINK--> &middot; <!--USER--> &middot; <a href="/api/logout" style="color:#9aa2ad">Sair</a></div></div>
 <div class="sub" id="updated">A carregar...</div>
 <div id="banner"></div><div id="main"></div>
 <div class="foot">Atualiza automaticamente a cada 60 segundos.</div>
</div>
<script>
const TITLE={GREEN:"Tudo normal",YELLOW:"Sem atividade recente",RED:"Alerta",SYSTEM:"Sistema sem dados",UNKNOWN:"Sem dados"};
function hm(h){return String(h).padStart(2,'0')+"h";}
async function load(){
 try{
  const r=await fetch('/api/state');
  if(r.status===401){location.href='/login';return;}
  const d=await r.json();
  if(d.error){document.getElementById('main').innerHTML='<div class="err">Erro: '+d.error+'</div>';return;}
  const sys=d.system||{ok:true};const bn=document.getElementById('banner');
  if(!sys.ok){bn.className='banner warn';bn.textContent='\u26A0 Sistema sem dados recentes ('+(sys.stale_human||'')+'). O estado abaixo pode nao refletir a situacao atual.';}
  else{bn.className='banner okb';bn.textContent='\u2713 Sistema a receber dados em tempo real.';}
  const res=d.residence||{state:'UNKNOWN',reason:''};
  let html='<div class="big '+res.state+'"><div class="label">'+(res.category==='system'?'Estado do sistema':'Estado geral')+'</div>'
   +'<div class="state">'+(TITLE[res.state]||res.state)+'</div><div class="reason">'+(res.reason||'')+'</div></div>';
  (d.devices||[]).forEach(function(x){
   let chips='';
   if(x.peak_hours&&x.peak_hours.length){chips+='<span class="chip">Costuma ativo: '+x.peak_hours.map(hm).join(', ')+'</span>';}
   if(x.last_activity_human){chips+='<span class="chip">Ultima atividade: '+x.last_activity_human+'</span>';}
   chips+='<span class="chip">Hoje: '+(x.events_today||0)+' evento(s)</span>';
   html+='<div class="card"><div class="top"><span class="dot d-'+x.state+'"></span><div><div class="name">'+x.device+'</div>'
    +'<div class="meta">'+(x.reason||'')+(x.last_reading?' &middot; ultima leitura '+x.last_reading:'')+'</div></div></div><div class="chips">'+chips+'</div></div>';
  });
  document.getElementById('main').innerHTML=html;
  document.getElementById('updated').textContent='Atualizado agora ('+new Date().toLocaleTimeString('pt-PT')+')';
 }catch(e){document.getElementById('main').innerHTML='<div class="err">Nao foi possivel contactar o servidor.</div>';}
}
load();setInterval(load,60000);
</script></body></html>"""
