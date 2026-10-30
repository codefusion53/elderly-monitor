"""Account page: lets any logged-in user change their own password.

Available to both roles (caregiver and admin). Posts to /api/change-password.
"""
from api.pages._shared import HEAD


def conta_html(display_name: str):
    return HEAD + f"""
 <div class="nav"><a href="/">&larr; Voltar ao painel</a><a href="/api/logout" class="right">Sair</a></div>
 <h1>A minha conta</h1>
 <p class="muted">Sessão de {display_name}. Aqui pode alterar a sua palavra-passe.</p>
 <div class="rescard" style="max-width:420px">
   <div class="resname">Alterar palavra-passe</div>
   <label>Palavra-passe atual</label>
   <input id="old" type="password" autocomplete="current-password">
   <label style="margin-top:10px">Nova palavra-passe (mínimo 8 caracteres)</label>
   <input id="new" type="password" autocomplete="new-password">
   <label style="margin-top:10px">Confirmar nova palavra-passe</label>
   <input id="new2" type="password" autocomplete="new-password">
   <button onclick="change()">Guardar</button>
   <span id="msg" style="display:block;margin-top:12px;font-size:.85rem"></span>
 </div>
 <script>
 async function change(){{
   const msg=document.getElementById('msg');
   const oldp=document.getElementById('old').value;
   const np=document.getElementById('new').value;
   const np2=document.getElementById('new2').value;
   msg.style.color='#8a1f1f';
   if(np.length<8){{msg.textContent='A nova palavra-passe deve ter pelo menos 8 caracteres.';return;}}
   if(np!==np2){{msg.textContent='As novas palavras-passe não coincidem.';return;}}
   const r=await fetch('/api/change-password',{{method:'POST',headers:{{'Content-Type':'application/json'}},
     body:JSON.stringify({{old_password:oldp,new_password:np}})}});
   if(r.ok){{
     msg.style.color='#2e9e5b';
     msg.textContent='Palavra-passe alterada com sucesso. As outras sessões foram terminadas.';
     document.getElementById('old').value='';document.getElementById('new').value='';document.getElementById('new2').value='';
   }}else{{
     const d=await r.json().catch(()=>({{}}));
     msg.textContent=(d.error==='wrong_password')?'A palavra-passe atual está incorreta.':'Não foi possível alterar. Verifique os dados.';
   }}
 }}
 </script>
</div></body></html>"""
