"""Politica de Privacidade - pagina publica (nao exige login).

ESTADO: ESQUELETO / A AGUARDAR VERSAO FINAL DO ADVOGADO.

Como colocar a versao final no ar (passo unico):
  1. Poe PENDING = False.
  2. Preenche o corpo de cada seccao em SECTIONS com o texto portugues
     aprovado pelo advogado (uma entrada por seccao; cada entrada e uma
     lista de paragrafos). Os titulos ja estao alinhados com a estrutura
     do rascunho ingles entregue ao cliente (seccoes 1-19 + aviso final);
     ajusta-os se o advogado renumerar ou renomear.
  3. Atualiza LAST_UPDATED e VERSION.
Nao e preciso mexer no app.py nem no _shared.py - a rota e o link ja estao
ligados. Enquanto PENDING for True, a pagina mostra um aviso claro de que
o texto esta em revisao juridica e lista apenas os titulos previstos.
"""
from api.pages._shared import HEAD

# --- metadados editaveis ---------------------------------------------------
PENDING = True                 # True = esqueleto; False = politica em vigor
VERSION = "rascunho"           # ex.: "1.0"
LAST_UPDATED = "a definir"     # ex.: "08/10/2026"
CONTROLLER = "a definir pelo cliente / advogado"

# --- conteudo --------------------------------------------------------------
# Cada seccao: (titulo, [paragrafo, paragrafo, ...]).
# Corpo vazio => aparece como "(a preencher)" enquanto PENDING for True.
SECTIONS = [
    ("1. Visao Geral", []),
    ("2. Responsavel pelo Tratamento dos Dados", []),
    ("3. Que Dados o Sistema Trata", []),
    ("   3.1 Tomadas inteligentes e telemetria eletrica", []),
    ("   3.2 Ligacao dos dispositivos e atualidade dos dados", []),
    ("   3.3 Inferencias de atividade e de rotina", []),
    ("   3.4 Configuracao da residencia e da monitorizacao", []),
    ("   3.5 Conta de utilizador e autenticacao", []),
    ("   3.6 Contactos de alerta", []),
    ("   3.7 Tratamento e historico das notificacoes", []),
    ("   3.8 Registos tecnicos e operacionais", []),
    ("4. Informacao que a Aplicacao Nao Recolhe Intencionalmente", []),
    ("5. Finalidades do Tratamento dos Dados", []),
    ("6. Como os Dados Circulam no Sistema", []),
    ("7. Servicos de Terceiros e Tratamento Externo", []),
    ("   7.1 Tuya", []),
    ("   7.2 Fornecedor de email / SMTP", []),
    ("   7.3 Fornecedor de WhatsApp", []),
    ("   7.4 Fornecedor de alojamento", []),
    ("8. Quem Pode Aceder aos Dados", []),
    ("9. Medidas de Seguranca", []),
    ("10. Conservacao dos Dados", []),
    ("11. Eliminacao e Encerramento de Conta", []),
    ("12. Privacidade e Direitos do Titular dos Dados", []),
    ("13. Fundamento Juridico e Consentimento", []),
    ("14. Decisoes Automatizadas e Definicao de Perfis", []),
    ("15. Membros do Agregado e Outras Pessoas", []),
    ("16. Tratamento e Transferencias Internacionais", []),
    ("17. Disponibilidade e Limitacoes", []),
    ("18. Alteracoes a Esta Politica", []),
    ("19. Contacto", []),
    ("Aviso", []),
]


def _para_block(paras):
    if not paras:
        return '<p class="todo">(a preencher)</p>'
    return "".join(f"<p>{p}</p>" for p in paras)


def privacidade_html():
    # Barra de topo minima: pagina publica, sem a navegacao de admin.
    topbar = ('<div class="nav">'
              '<a href="/login">&larr; Voltar</a>'
              '<span class="right muted">Zelo Smart</span>'
              '</div>')

    if PENDING:
        banner = ('<div class="pend">Este texto esta em revisao juridica. '
                  'A versao final da Politica de Privacidade sera publicada '
                  'apos aprovacao. Abaixo encontra-se apenas a estrutura '
                  'prevista.</div>')
        meta = ''
    else:
        banner = ''
        meta = (f'<p class="muted">Versao {VERSION} &middot; '
                f'Ultima atualizacao: {LAST_UPDATED} &middot; '
                f'Responsavel: {CONTROLLER}</p>')

    body = ""
    for title, paras in SECTIONS:
        sub = title.startswith(" ")
        cls = "sec sub" if sub else "sec"
        body += (f'<div class="{cls}"><h2>{title.strip()}</h2>'
                 f'{_para_block(paras)}</div>')

    return HEAD + topbar + """
 <h1>Politica de Privacidade</h1>
 """ + meta + banner + """
 <style>
  .pend{background:#fff3cd;color:#7a5c00;border:1px solid #ffe08a;border-radius:10px;
        padding:12px 16px;margin:12px 0 18px;font-size:.88rem;font-weight:600}
  .sec{background:#fff;border-radius:12px;padding:14px 18px;margin:10px 0;
       box-shadow:0 1px 4px rgba(0,0,0,.05)}
  .sec.sub{margin-left:14px;background:#fbfcfe}
  .sec h2{font-size:1rem;margin:0 0 6px}
  .sec.sub h2{font-size:.9rem;color:#374151}
  .sec p{color:#374151;font-size:.9rem;line-height:1.55;margin:6px 0}
  .sec p.todo{color:#9aa2ad;font-style:italic}
 </style>
 """ + body + """
</div></body></html>"""
