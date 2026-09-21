"""Settings page: per-residence sensitivity and alert thresholds."""
from api.pages._shared import HEAD, nav


def settings_html(residences, settings_by_res):
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
    return HEAD + nav("settings") + """
 <h1>Sensibilidade por residencia</h1>
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
 document.getElementById('ok_'+rid).textContent = r.ok?'Guardado \\u2713':'Erro';
 setTimeout(()=>{document.getElementById('ok_'+rid).textContent='';},2500);
}
</script></body></html>"""
