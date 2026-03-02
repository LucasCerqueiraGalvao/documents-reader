# Roteiro de Passos - Implementacao Exportation (Incremental)

## 1. Contexto

Este documento organiza a implementacao do fluxo `exportation` em etapas pequenas e executaveis, para evitar novos travamentos e reduzir risco de regressao no fluxo `importation`.

Objetivo final:
- Ter `importation` e `exportation` funcionando no mesmo produto (pipeline, API e UI Electron).
- Permitir alternancia de modo na interface (botao/select de modo).
- Garantir que cada modo mostre os tipos de documento corretos e rode os stages corretos.

## 2. Diagnostico Atual (estado real)

### Ja feito
- Pipeline Python com suporte a `flow=importation|exportation`.
- Stage 01/02/03/04 para exportation.
- Stage 02 exportation com engine `regex` e `llm`.
- Teste smoke do pipeline exportation passando.
- Teste de contrato do Stage 02 LLM exportation passando.

### Faltando / incompleto
- UI Electron ainda hardcoded em `importation`.
- Nao existe seletor de modo `importation/exportation` na interface.
- Tipos de documento da UI sao apenas os de importation.
- Progresso/log da UI nao trata corretamente prefixos de log de exportation (`[Stage02-LLM-EXPORT]`).
- Caminhos de entrada/saida no Electron ainda usam pastas `importation`.

## 3. Escopo Final Esperado

Ao concluir todos os passos:
- Usuario escolhe o modo (`importation` ou `exportation`) na UI.
- UI ajusta tipos de documentos de acordo com o modo.
- Pipeline roda com `--flow` correto.
- Relatorios abrem da pasta correta (`.../<flow>/...`).
- Stage 02 pode rodar em `regex` ou `llm` para ambos os fluxos.
- Regressao de importation coberta por teste.

## 3.1 Catalogo de documentos - Exportation

Tipos canonicos aceitos no fluxo `exportation`:
- `commercial_invoice`
- `packing_list`
- `draft_bl`
- `certificate_of_origin`
- `container_data`

Aliases aceitos para `doc_kind_hint`:
- `invoice` -> `commercial_invoice`
- `packing list`, `pl` -> `packing_list`
- `bl`, `bill_of_lading` -> `draft_bl`
- `co` -> `certificate_of_origin`

Padrao de arquivo de entrada:
- Stage 01 recebe PDFs (`.pdf`).
- Stage 01 gera `*_extracted.json`.
- Stage 02 le `*_extracted.json` e gera `*_fields.json`.

## 3.2 Captura de dados - Stage 02 (Exportation)

Contrato estrutural por campo:
- Cada campo sai como `present`, `required`, `value`, `evidence`, `method`.
- Campos ausentes obrigatorios entram em `missing_required_fields`.
- Engine pode ser `regex` ou `llm`, mas o contrato de saida deve ser o mesmo.

### Documento: `commercial_invoice`

Campos obrigatorios:
- `invoice_number`
- `invoice_date`
- `country_of_origin`
- `transport_mode`
- `port_of_loading`
- `port_of_destination`
- `gross_weight_kg`
- `net_weight_kg`
- `incoterm`
- `currency`
- `ncm`
- `container_count`
- `exporter_cnpj`
- `exporter_name`
- `importer_name`

Campos opcionais:
- `payment_terms`

### Documento: `packing_list`

Campos obrigatorios:
- `packing_list_number`
- `packing_date`
- `gross_weight_kg`
- `net_weight_kg`
- `ncm`
- `incoterm`
- `container_count`
- `containers`

Campos opcionais:
- nenhum

### Documento: `draft_bl`

Campos obrigatorios:
- `freight_mode`
- `incoterm`
- `ncm`
- `due`
- `ruc`
- `wooden_packing`
- `containers`
- `total_cartons`
- `net_weight_kg_total`
- `gross_weight_kg_total`
- `cubic_meters_total`
- `exporter_cnpj`
- `exporter_name`
- `importer_name`
- `notify_party_name`

Campos opcionais:
- `booking_number`
- `phones_found`

Comportamento adicional:
- Gera warning `possible_incoterm_freight_mismatch` quando `incoterm` e `freight_mode` divergem do mapeamento esperado.

### Documento: `certificate_of_origin`

Campos obrigatorios:
- `invoice_number`
- `certificate_date`
- `transport_mode`
- `exporter_name`
- `importer_name`
- `net_weight_kg`
- `gross_weight_kg`
- `total_m2`

Campos opcionais:
- nenhum

### Documento: `container_data`

Campos obrigatorios:
- `invoice_number`
- `booking_number`
- `containers`

Campos opcionais:
- nenhum

### Estrutura esperada de `containers`

Quando houver parse de linhas de container, usar lista de objetos com:
- `container_number`
- `seal`
- `value_1`
- `value_2` (pode ser `null`)
- `raw_line`

## 3.3 Comparacoes e regras - Stage 03 (Exportation)

Tipos de resultado de check:
- `match`
- `divergent`
- `skipped` (com motivo)

Semantica dos comparadores:
- `number`: tolerancia padrao `abs_tol=1.0` e `rel_tol=0.01`.
- `string`: similaridade por token overlap (jaccard minimo 0.55).
- `cnpj`: igualdade exata por digitos.
- `docref`: normalizacao de referencia documental (ignora pontuacao e tolera sufixo `P` no final).
- `code_prefix`: igualdade por prefixo numerico (aceita prefixo de 4 ou 6 digitos).

### Pair checks (comparisons)

Par `invoice_vs_packing`:
- Invoice/Packing reference (`invoice_number` x `packing_list_number`)
- Gross weight (kg)
- Net weight (kg)
- NCM
- Incoterm
- Container count (comparacao exata, sem tolerancia)

Par `invoice_vs_draft_bl`:
- Incoterm
- NCM
- Exporter CNPJ
- Exporter name
- Importer name
- Gross weight (`gross_weight_kg` x `gross_weight_kg_total`)
- Net weight (`net_weight_kg` x `net_weight_kg_total`)

Par `packing_vs_draft_bl`:
- NCM
- Incoterm
- Gross weight (`gross_weight_kg` x `gross_weight_kg_total`)
- Net weight (`net_weight_kg` x `net_weight_kg_total`)

Par `coo_vs_invoice`:
- Invoice reference
- Exporter name
- Importer name
- Gross weight
- Net weight

Par `container_data_vs_draft_bl`:
- Booking number (`booking_number` x `booking_number`)
- Container numbers (igualdade de conjunto entre listas de containers)

Regra de pareamento:
- Primeiro tenta parear invoice x packing por referencia (`docref_close`).
- Se nao achar pares por referencia, faz fallback para pareamento cruzado (cartesiano).

### Group checks

Checks de consistencia entre documentos principais:
- `exporter_name_equal_across_invoice_bl_coo`
- `importer_name_equal_across_invoice_bl_coo`
- `exporter_cnpj_equal_across_invoice_bl`

Observacao:
- Hoje usa o primeiro documento disponivel de cada tipo relevante (`[:1]`) para cada group check.

### Rule checks

Regra `incoterm_vs_freight_mode` (invoice x draft BL):
- EXW/FCA/FOB/FAS -> esperado `COLLECT`
- CFR/CIF/CPT/CIP/DAP/DPU/DDP -> esperado `PREPAID`
- Se faltar valor ou incoterm fora do mapeamento, status `skipped`.

## 3.4 Mapeamento UI -> Backend (modo e tipo documental)

### Modo (flow)

Contrato final esperado entre renderer e main:
- Renderer envia `flow` no payload de execucao.
- Main usa `flow` para:
  - pasta de input (`input/<flow>/raw`)
  - argumento `--flow <flow>` do pipeline
  - pasta de report (`output/stage_04_report/<flow>/...`)

Payload alvo (exemplo):

```json
{
  "flow": "exportation",
  "stage2Engine": "llm",
  "files": [
    { "path": "C:/docs/COMMERCIAL INVOICE.pdf", "docType": "COMMERCIAL INVOICE" }
  ]
}
```

### Tipos documentais por modo

Importation (UI label -> `doc_kind_hint`):
- `BL` -> `bl`
- `HBL` -> `hbl`
- `INVOICE` -> `invoice`
- `PACKING LIST` -> `packing_list`
- `DI` -> `di`
- `LI` -> `li`

Exportation (UI label -> `doc_kind_hint`):
- `COMMERCIAL INVOICE` -> `commercial_invoice`
- `PACKING LIST` -> `packing_list`
- `DRAFT BL` -> `draft_bl`
- `CERTIFICATE OF ORIGIN` -> `certificate_of_origin`
- `CONTAINER DATA` -> `container_data`

Formato alvo de `_doc_type_hints.json`:

```json
{
  "COMMERCIAL INVOICE 1.pdf": "commercial_invoice",
  "PACKING LIST 1.pdf": "packing_list",
  "DRAFT BL 1.pdf": "draft_bl"
}
```

## 3.5 Contratos de saida (JSON) - Stage 02 e Stage 03

### Stage 02 - contrato minimo por documento

Top-level obrigatorio:
- `source`
- `generated_at`
- `fields`
- `missing_required_fields`
- `warnings`

Exemplo simplificado:

```json
{
  "source": {
    "stage01_file": "COMMERCIAL INVOICE_extracted.json",
    "original_file": "COMMERCIAL INVOICE.pdf",
    "doc_kind": "commercial_invoice",
    "doc_kind_hint": "commercial_invoice"
  },
  "generated_at": "2026-03-02T10:00:00",
  "fields": {
    "invoice_number": {
      "present": true,
      "required": true,
      "value": "I-0007/25",
      "evidence": ["INVOICE NR I-0007/25"],
      "method": "regex"
    }
  },
  "missing_required_fields": [],
  "warnings": []
}
```

### Stage 03 - contrato minimo de comparacao

Top-level relevantes:
- `summary`
- `comparisons`
- `group_checks`
- `rule_checks`

Exemplo simplificado de item em `comparisons`:

```json
{
  "pair": "invoice_vs_packing | A <> B",
  "check": "NCM",
  "status": "match",
  "a_key_used": "ncm",
  "b_key_used": "ncm",
  "a_value": "8703.21.00",
  "b_value": "8703.21.00",
  "evidence": { "a": ["..."], "b": ["..."] }
}
```

## 3.6 Pareamento multi-documento (Stage 03) e limitacoes atuais

Estrategia atual:
- `invoice` x `packing`:
  - tenta parear por referencia (`docref_close` entre `invoice_number` e `packing_list_number`)
  - se nao houver pares por referencia, faz pareamento cruzado (cartesiano)
- `invoice` x `draft_bl`: cartesiano entre todos os documentos disponiveis
- `packing` x `draft_bl`: cartesiano entre todos os documentos disponiveis
- `coo` x `invoice`: cartesiano entre todos os documentos disponiveis
- `container_data` x `draft_bl`: cartesiano entre todos os documentos disponiveis

Limitacao conhecida:
- Group checks usam apenas o primeiro documento de cada tipo relevante (`[:1]`).

Evolucao recomendada:
- Introduzir chave de agrupamento por embarque (ex.: booking/invoice reference) para comparacoes 1:1 por lote.

## 3.7 Politica de falha e timeout - Stage 02 LLM

Configuracoes relevantes:
- `DOCREADER_STAGE2_ENGINE=regex|llm`
- `DOCREADER_STAGE2_LLM_TIMEOUT_SEC` (default 240)
- `DOCREADER_STAGE2_LLM_MODEL` (opcional)
- `DOCREADER_STAGE2_LLM_FALLBACK_REGEX=0|1` (na politica de produto, manter `0`)
- `DOCREADER_CODEX_CLI_PATH` (opcional; default `codex`)

Comportamento esperado:
- Se engine for `regex`: segue fluxo normal sem chamada LLM.
- Se engine for `llm` e houver erro:
  - nao executar fallback automatico para `regex`.
  - Stage 02 deve falhar (`fail-fast`) e pipeline deve retornar erro.
  - UI deve informar claramente ao usuario que a extracao LLM falhou.
  - UI deve mostrar causa resumida e orientacao objetiva de acao.

Observacao de UX:
- UI deve mostrar explicitamente:
  - engine solicitada
  - engine efetiva
  - erro da LLM (mensagem amigavel + detalhe tecnico resumido)
  - que nao houve fallback automatico

## 4. Como vamos executar no chat

Fluxo combinado de execucao:
1. Voce pede: `faca o passo 1`.
2. Eu implemento apenas o Passo 1 e paro.
3. Eu te aviso o que foi feito e pergunto: `posso ir para o passo 2?`
4. So continuo para o proximo passo com sua aprovacao explicita.

Regra de controle:
- Um passo por vez.
- Sem adiantar etapa.
- Sempre com validacao antes de seguir.

## 5. Passos de implementacao (um por vez)

## Passo 1 - Congelar baseline e reduzir risco

Objetivo:
- Criar uma base confiavel antes de novas mudancas.

Tarefas:
- Registrar snapshot do estado atual (arquivos alterados, testes que passam/falham).
- Executar e salvar resultado de:
  - smoke importation
  - smoke exportation
  - contrato Stage 02 LLM importation/exportation
- Definir criterio de rollback (quais arquivos reverter se algo quebrar).

Entrega:
- Relatorio curto de baseline com comandos e resultados.

Criterio de aceite:
- Baseline documentado e reproduzivel.

## Passo 2 - Habilitar modo na UI Electron

Objetivo:
- Inserir alternancia de modo na interface.

Tarefas:
- Adicionar controle de modo no `renderer` (select ou toggle).
- Persistir ultima escolha de modo no estado da UI.
- Enviar `flow` no payload da execucao para o `main process`.
- Exibir no log/status qual modo esta ativo.
- Seguir estritamente o contrato da secao 3.4.

Entrega:
- UI com controle de modo funcional.

Criterio de aceite:
- Usuario consegue alternar modo sem editar codigo.

## Passo 3 - Adequar mapeamento de tipos por modo

Objetivo:
- Cada modo mostrar e mapear os tipos corretos de documentos.

Tarefas:
- Definir lista de tipos para `importation`:
  - BL, HBL, INVOICE, PACKING LIST, DI, LI
- Definir lista de tipos para `exportation`:
  - COMMERCIAL INVOICE, PACKING LIST, DRAFT BL, CERTIFICATE OF ORIGIN, CONTAINER DATA
- Usar a secao 3.1 como fonte unica para tipos e aliases.
- Ajustar funcoes de:
  - sugestao por nome de arquivo
  - validacao de tipo selecionado
  - conversao para `doc_kind_hint`
- Garantir que `_doc_type_hints.json` use aliases aceitos pelo backend.

Entrega:
- Tela de tipos muda conforme o modo selecionado.

Criterio de aceite:
- Nenhum tipo invalido chega ao Stage 01/02 para cada modo.

## Passo 4 - Wiring completo do flow no Electron main

Objetivo:
- Eliminar hardcode de `importation` nos caminhos e argumentos.

Tarefas:
- Substituir caminhos fixos:
  - `input/<flow>/raw`
  - `output/stage_04_report/<flow>/...`
  - `output/stage_05_debug_report/<flow>/...` (quando existir)
- Passar `--flow <flow>` no comando do pipeline.
- Ajustar abertura automatica de relatorio para o flow ativo.
- Tratar ausencia do Stage 05 em exportation sem erro de UX.
- Preservar contrato de saida da secao 3.5 para ambos os flows.

Entrega:
- Execucao ponta-a-ponta com flow dinamico.

Criterio de aceite:
- Mesma UI roda ambos os fluxos corretamente.

## Passo 5 - Ajustes de progresso/log e UX operacional

Objetivo:
- Evitar sensacao de travamento durante execucao.

Tarefas:
- Atualizar parser de logs para reconhecer:
  - `[Stage02-LLM]`
  - `[Stage02-LLM-EXPORT]`
- Ajustar labels de progresso por flow.
- Melhorar mensagens de erro de preflight (Codex CLI, auth, timeout).
- Exibir claramente qual engine Stage 02 foi usada no run.
- Em falha LLM, exibir erro claro ao usuario sem fallback automatico (secao 3.7).

Entrega:
- Barra de progresso e logs coerentes para os dois fluxos.

Criterio de aceite:
- Execucao LLM exportation nao aparenta travar por falta de interpretacao do log.

## Passo 6 - Testes e validacao de regressao

Objetivo:
- Garantir estabilidade antes de liberar.

Tarefas:
- Adicionar/ajustar testes automatizados:
  - smoke importation
  - smoke exportation
  - testes de UI logic (modo + tipos + payload)
- Rodar checklist manual:
  - importation regex
  - importation llm
  - exportation regex
  - exportation llm
- Validar output de Stage 04 para ambos os fluxos.
- Executar matriz da secao 9 e anexar evidencias.

Entrega:
- Matriz de testes com status.

Criterio de aceite:
- Nenhuma regressao critica em importation e exportation funcional.

## Passo 7 - Documentacao e handoff

Objetivo:
- Consolidar uso e manutencao.

Tarefas:
- Atualizar README com exemplos de UI e CLI por flow.
- Documentar variaveis de ambiente do Stage 02 LLM.
- Criar secao de troubleshooting (travamentos comuns e como diagnosticar).

Entrega:
- Documentacao final de operacao.

Criterio de aceite:
- Time consegue operar e debugar sem depender de contexto historico.

## 6. Ordem recomendada de execucao

1. Passo 1 - Baseline
2. Passo 2 - Controle de modo na UI
3. Passo 3 - Tipos por modo
4. Passo 4 - Wiring de flow no Electron main
5. Passo 5 - Progresso/log
6. Passo 6 - Testes e regressao
7. Passo 7 - Documentacao final

## 7. Regras de implementacao (para evitar novo caos)

- Implementar apenas um passo por PR/commit logico.
- Rodar testes ao fim de cada passo.
- Nao misturar refactor amplo com mudanca funcional na mesma etapa.
- Em qualquer regressao de importation, parar e corrigir antes de avancar.
- Registrar evidencias (comandos e resultados) a cada passo concluido.

## 8. Definicao de pronto (Done)

Projeto sera considerado pronto quando:
- UI alternar entre `importation` e `exportation`.
- Ambos os modos rodarem Stage 01-04 sem ajuste manual.
- Stage 02 `llm` e `regex` funcionarem para ambos os modos.
- Importation permanecer estavel (sem regressao funcional).
- Documentacao de operacao estiver atualizada.

## 9. Matriz de testes executavel (comandos)

Backend (Python):
1. `python -m unittest src/stage_02_field_extract/importation/test_stage_02_llm.py -v`
2. `python -m unittest src/stage_02_field_extract/exportation/test_stage_02_llm.py -v`
3. `python -m unittest src/test_pipeline_exportation_smoke.py -v`
4. `python src/pipeline.py --input data/input/importation --output <TMP_OUT> --flow importation --json`
5. `python src/pipeline.py --input data/input/exportation --output <TMP_OUT> --flow exportation --json`

Electron (Node):
1. `cd examples/electron_app`
2. `npm install`
3. `npm run smoke`
4. Adicionar smoke dedicado de exportation e executar (ex.: `npm run smoke:exportation`)

Checklist manual minimo:
1. UI com modo `importation` + Stage 02 `regex`
2. UI com modo `importation` + Stage 02 `llm`
3. UI com modo `exportation` + Stage 02 `regex`
4. UI com modo `exportation` + Stage 02 `llm`

## 10. Rollout e rollback

Rollout recomendado:
1. Entregar Passos 2-5 atras de feature flag de UI (seletor de modo).
2. Validar em ambiente interno com dataset real de exportation.
3. Liberar gradualmente para usuarios.

Rollback rapido:
1. Desabilitar seletor de modo na UI.
2. Forcar `flow=importation` no main process temporariamente.
3. Forcar `DOCREADER_STAGE2_ENGINE=regex` para reduzir risco operacional.
4. Manter backend exportation no codigo, mas sem exposicao na UI ate estabilizar.
