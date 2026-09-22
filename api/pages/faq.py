"""Support / FAQ page. Visible to caregivers and admins.

Content approved by the client, with the agreed corrections:
  - Vacation Mode question removed (that feature is Phase 4).
  - Wi-Fi re-pairing questions point to the Smart Life app (our app reads
    data, it does not manage the plugs' Wi-Fi).
  - The multi-contact question notes contacts are managed by the administrator
    in this phase.
"""
from api.pages._shared import HEAD, nav

FAQS = [
    ("Como e que a Zelo Smart sabe que esta tudo bem com o meu familiar?",
     "A Zelo Smart analisa os padroes de consumo eletrico dos eletrodomesticos "
     "do dia a dia que exigem acao direta (como o micro-ondas, a chaleira, a "
     "televisao ou a cafeteira). O sistema aprende a rotina normal do seu "
     "familiar e identifica desvios de padrao ou periodos anormais de "
     "inatividade, sem usar camaras nem invadir a privacidade."),

    ("O que significam as cores do semaforo na aplicacao?",
     "Verde (Normal): atividade recente dentro do horario e padrao habituais. "
     "Amarelo (Atencao): pequeno desvio na rotina. "
     "Vermelho (Alerta): inatividade prolongada e fora do comum. "
     "Cinzento (Sem sinal): falha tecnica de comunicacao ou corte de "
     "energia/Wi-Fi na residencia. "
     "Em aprendizagem: nos primeiros dias, enquanto o sistema conhece a rotina."),

    ("O que acontece se a internet ou a luz da casa falharem?",
     "Se todas as tomadas ficarem offline ao mesmo tempo, a aplicacao "
     "identifica que se trata de uma falha de rede/energia e nao de um problema "
     "com o seu familiar. Se a ligacao nao recuperar dentro do tempo definido, "
     "recebera um aviso critico a informar da perda de sinal na residencia."),

    ("Como funciona o periodo inicial de calibracao?",
     "Durante os primeiros dias apos a instalacao de um novo kit, a aplicacao "
     "apresenta o estado \"Em aprendizagem\". Nesse periodo, o sistema esta a "
     "aprender os horarios e habitos reais da casa para construir uma linha de "
     "base precisa. Os alertas de inatividade tornam-se mais fiaveis no fim "
     "deste periodo."),

    ("O que devo fazer se uma das tomadas perder a ligacao Wi-Fi?",
     "Se apenas uma tomada ficar offline (a app mostra um aviso tecnico), "
     "verifique se a tomada nao foi desligada da ficha de parede e se o botao "
     "do dispositivo esta ligado. Se precisar de reconfigurar o Wi-Fi da "
     "tomada, isso faz-se na app Smart Life (a app do fabricante das tomadas), "
     "onde as tomadas foram inicialmente configuradas."),

    ("A aplicacao funciona se eu estiver noutro pais ou longe de casa?",
     "Sim. Desde que o seu telemovel tenha ligacao a internet (Wi-Fi ou dados "
     "moveis), pode consultar o estado do seu familiar em tempo real e receber "
     "as notificacoes em qualquer parte do mundo."),

    ("Quantas pessoas da familia podem receber os alertas?",
     "Podem ser associados varios familiares e cuidadores. Nesta fase, a "
     "adicao de novos contactos de alerta e feita pelo administrador do "
     "sistema, que configura quem recebe as notificacoes."),

    ("Mudei o router ou a palavra-passe do Wi-Fi da casa. O que devo fazer?",
     "As tomadas precisam de acesso a rede Wi-Fi para enviar os dados. Se "
     "alterar o nome da rede ou a palavra-passe, as tomadas tem de ser ligadas "
     "a nova rede na app Smart Life (a app do fabricante), na opcao de gestao "
     "de dispositivos / atualizar Wi-Fi."),
]


def faq_html():
    items = ""
    for q, a in FAQS:
        items += (f'<div class="faq"><div class="q">{q}</div>'
                  f'<div class="a">{a}</div></div>')
    return HEAD + nav("faq") + """
 <h1>Suporte &middot; Perguntas frequentes</h1>
 <p style="color:#6b7280;font-size:.85rem">Respostas as duvidas mais comuns sobre a Zelo Smart.</p>
 <style>
  .faq{background:#fff;border-radius:12px;padding:16px 18px;margin:10px 0;box-shadow:0 1px 4px rgba(0,0,0,.05)}
  .faq .q{font-weight:600;margin-bottom:6px}
  .faq .a{color:#374151;font-size:.9rem;line-height:1.5}
 </style>
 """ + items + """
</div></body></html>"""
