"""Charts page: routine and consumption charts (images served by app routes)."""
from api.pages._shared import HEAD, nav


def charts_html():
    return HEAD + nav("charts") + """
 <h1>Graficos</h1>
 <div class="charts">
   <h2>Rotina aprendida</h2>
   <img src="/admin/chart/routine.png" alt="Rotina aprendida">
   <div class="charthint">Padrao de atividade aprendido e validacao dia a dia.</div>
   <h2>Consumo recente</h2>
   <img src="/admin/chart/consumption.png" alt="Consumo recente">
   <div class="charthint">Potencia das tomadas nas ultimas 48h.</div>
 </div>
</div></body></html>"""
