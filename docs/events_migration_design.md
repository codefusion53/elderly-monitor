# Migracao para Eventos (Tuya) - Fase 4

Este documento explica a migracao da recolha de dados "por pergunta" (polling)
para "por eventos", em duas camadas: primeiro em linguagem simples, para
qualquer pessoa perceber; depois o detalhe tecnico, para quem vai manter o
codigo.

================================================================
PARTE 1 - EXPLICACAO SIMPLES (para qualquer pessoa)
================================================================

## O problema, numa frase

O sistema estava a "perguntar" as tomadas o seu estado a cada minuto, todos os
minutos. Isso faz demasiadas perguntas por mes e esgota a quota gratuita da
Tuya, deixando o sistema sem dados ate ao mes seguinte.

## Uma analogia

Imagine que quer saber quando alguem chega a casa.

- Metodo antigo (polling): telefonar para casa a cada minuto a perguntar
  "ja chegaste?". Mesmo quando nao chegou ninguem, gasta uma chamada. Ao fim
  do mes sao milhares de chamadas, a maioria com a resposta "ainda nao".

- Metodo novo (eventos): pedir que a casa LHE telefone so quando alguem chegar.
  Nao gasta nada enquanto nao acontece nada; recebe um aviso apenas quando ha
  mesmo uma novidade.

A migracao para eventos e exatamente isto: em vez de o nosso sistema perguntar
constantemente, a Tuya passa a avisar-nos so quando algo muda numa tomada (ligou,
desligou, mudou o consumo, ficou offline). Muito menos "chamadas", logo cabe
dentro da quota gratuita.

## Porque isto resolve o problema da quota

Uma cafeteira muda de estado poucas vezes por dia (liga quando se faz cafe,
desliga a seguir). Com eventos, recebemos uma mao-cheia de mensagens por dia em
vez de 1440 perguntas. O consumo cai drasticamente e deixa de esgotar a quota.

## O que muda e o que NAO muda

- MUDA: apenas a forma como os dados ENTRAM no sistema (eventos em vez de
  perguntas).
- NAO MUDA: tudo o resto. O painel, os alertas, a aprendizagem da rotina, o
  relatorio e as definicoes continuam exatamente iguais, porque continuam a ler
  os mesmos dados na mesma base de dados. So trocamos a "porta de entrada" dos
  dados; a casa por dentro fica igual.

## Um detalhe importante de seguranca do sistema

Com o metodo antigo, "nao receber dados ha 10 minutos" significava que algo
estava mal (sistema cego). Com eventos, o silencio e NORMAL: se a pessoa nao
usou nenhum aparelho, nao ha eventos, e isso nao e uma avaria. Por isso a forma
de detetar "o sistema esta mesmo offline" tem de ser repensada (ver Parte 2),
para nao confundir "esta tudo calmo" com "o sistema avariou".

================================================================
PARTE 2 - DETALHE TECNICO (para quem mantem o codigo)
================================================================

## Porque
Polling consome ~170k chamadas API/mes (2 dispositivos x ~2 chamadas/min).
A quota gratuita do IoT Core e 25k/mes, logo esgota a meio do mes. Mesmo a
otimizacao de polling (ja feita, ~40% menos) continua muito acima. A solucao
estrutural e subscrever o Message Service da Tuya (Pulsar): a Tuya envia um
evento so quando um dispositivo muda de estado.

## Como funciona o Message Service da Tuya
- A Tuya envia eventos por uma fila de mensagens Pulsar.
- Subscreve-se com o Access ID / Access Secret ja existentes.
- Endpoint EU: pulsar+ssl://mqe.tuyaeu.com:7285/ (espelha TUYA_REGION=eu;
  outras regioes: tuyaus, tuyacn).
- Tipos de evento relevantes:
    dp_report -> o dispositivo reportou dados (potencia / switch) => uma leitura
    online    -> dispositivo ficou online                         => conectividade
    offline   -> dispositivo ficou offline                        => conectividade
- O corpo da mensagem traz um campo "data" encriptado. A chave de desencriptacao
  sao os caracteres 8..24 (16 chars) do Access Secret. Depois de desencriptar,
  o JSON tem devId, productKey e status (os data points).
- Nota de encriptacao: o formato classico do IoT Core usa AES-ECB; versoes mais
  recentes podem usar AES-GCM (a consola deste projeto indica AES-GCM). O codigo
  tenta ECB e deve ter um fallback para GCM; confirmar com um evento real.
- Faturado por numero de mensagens reenviadas. Precisa de estar ativo e
  autorizado no projeto (ja esta).

## Mudanca de arquitetura
Antes:  um ciclo temporizado chama a API da Tuya a cada 60s (pull).
Depois: um consumidor de longa duracao mantem uma ligacao Pulsar e reage aos
        eventos recebidos (listen).

O resto do sistema NAO muda:
- tabelas readings, devices, connectivity_events: iguais.
- inferencia (baseline, deviation), api, alerting: iguais, leem as mesmas
  tabelas. Esta e a grande vantagem: so muda a camada de recolha.

Componente novo: collector/events.py (consumidor Pulsar) que, a cada evento,
escreve na mesma base de dados pelas mesmas funcoes de db.py, para que tudo a
jusante seja identico ao que o polling produzia.

### Mapeamento eventos -> esquema existente
- dp_report: ler os data points (cur_power, cur_voltage, add_ele, switch_1),
  converter unidades exatamente como o tuya_client faz hoje, inserir uma linha
  em readings. Marcar online=True (um dispositivo que reporta esta online).
- online:  connectivity.on_poll_result(poll_ok=True, reported_online=True)
- offline: connectivity.on_poll_result(poll_ok=False, reported_online=False)
  (alimenta a MESMA maquina de estados, portanto offline_confirmed / back_online
  e a janela de tolerancia continuam a funcionar sem alteracoes.)

### Requisitos de fiabilidade (a engenharia real)
1. Reconexao automatica se a ligacao Pulsar cair, sem perder mensagens (o Pulsar
   retem mensagens nao confirmadas; so confirmar (ack) apos escrita com sucesso
   na base de dados).
2. Repensar a detecao de "sistema sem dados". Com eventos, silencio e normal,
   por isso NAO se pode tratar "sem evento ha N minutos" como "sistema em baixo".
   Em vez disso:
   - usar os eventos online/offline da Tuya para a conectividade, e
   - manter uma verificacao de vida de baixa frequencia (ex.: uma chamada cloud
     a cada 30-60 min) OU usar a saude da ligacao Pulsar como sinal de "sistema
     a funcionar".
   ESTE E UM PONTO DE DESENHO CHAVE: a migracao e mais do que trocar o transporte,
   a logica de frescura/saude tem de ser pensada para um mundo de eventos.
3. Correr como o seu proprio servico no docker-compose (substituindo, ou a
   funcionar em paralelo durante a transicao, o servico collector).

## Plano de transicao
1. Provar a ligacao: collector/pulsar_test.py conecta e desencripta UM evento
   real (ja construido; a logica de desencriptacao esta testada).
2. Construir events.py completo; correr primeiro no canal de TESTE (MQ_ENV_TEST)
   para validar o parsing sem tocar nos dados de producao.
3. Correr events e polling em paralelo brevemente; comparar que os eventos
   produzem leituras equivalentes.
4. Cutover: trocar o servico de recolha de polling para o consumidor de eventos;
   manter uma verificacao de vida minima para a saude do sistema.
5. Confirmar com dados reais que o volume de chamadas fica abaixo das 25k/mes.

## Dependencias
- SDK tuya-pulsar (github.com/tuya/tuya-pulsar-sdk-python) + pycryptodome.
- Message Service ativo e autorizado no projeto Tuya do cliente (ja esta).
- Confirmacao de que o volume de mensagens fica dentro do plano gratuito
  (confirmado: faturado por mensagem, volume muito baixo para 2 tomadas).

## Estado atual (Fase 4)
- Desenho: completo (este documento).
- Desencriptacao AES (chave = Access Secret[8..24]): implementada e testada em
  round-trip.
- Mapeamento evento -> leitura/conectividade: implementado e testado em
  collector/events.py (funcao handle_event).
- Ligacao Pulsar real: collector/pulsar_test.py pronto para validar com um
  evento real das tomadas.
- Em falta (trabalho da Fase 4 a concluir): consumidor de producao completo com
  reconexao, rework da logica de frescura, cutover do polling, testes ponta a
  ponta e documentacao final de entrega.
