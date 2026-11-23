# Participantes — requisitos

> Fonte: `Requisitos_NCI_RF_RNF_RN_Revisado_v2.docx` (revisão aprovada até o momento). Este arquivo descreve **o que** o sistema deve fazer; não indica que algo já foi implementado.
> Convenção: **Confirmado** = definição aceita; **Pendente** = depende de validação. **MVP/Depois** = prioridade.

## RF — Requisitos funcionais

### RF-PAR-01 — Confirmado

Cadastrar participante uma única vez, com nome completo, data de nascimento, sexo, raça/cor autodeclarada, identidade de gênero e dados necessários aos indicadores de convivência do FMR.

- **Prioridade:** MVP
- **Fonte:** FMR; PROTO; D14
- **Status da definição:** Confirmado

### RF-PAR-02 — Confirmado

Registrar contato principal e telefone do participante.

- **Prioridade:** MVP
- **Fonte:** PROTO
- **Status da definição:** Confirmado

### RF-PAR-04 — Confirmado

Registrar situação de moradia sozinho, apoio familiar/comunitário, deficiência, recebimento de BPC e condição de imigrante/refugiado.

- **Prioridade:** MVP
- **Fonte:** FMR
- **Status da definição:** Confirmado

### RF-PAR-05 — Confirmado

Manter o histórico de vigência das informações cadastrais que podem mudar entre meses.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.1; §8
- **Status da definição:** Confirmado

### RF-PAR-06 — Confirmado

Registrar somente a categoria de origem do encaminhamento do participante (por exemplo, CRAS, CREAS, outros serviços da rede ou outra origem), sem exigir neste requisito um novo registro de entrada.

- **Prioridade:** MVP
- **Fonte:** FMR; E2
- **Status da definição:** Confirmado

### RF-PAR-07 — Confirmado

Registrar o desligamento com data e motivo selecionado da lista do FMR, mantendo o histórico.

- **Prioridade:** MVP
- **Fonte:** D05; FMR
- **Status da definição:** Confirmado. Resposta do NCI (21/11/2026) (Q3): ficam os 6 motivos já cadastrados, sem opção "Outro".

### RF-PAR-08 — Confirmado

Permitir reativar participante anteriormente desligado sem apagar seus registros anteriores.

- **Prioridade:** MVP
- **Fonte:** D05
- **Status da definição:** Confirmado

### RF-PAR-09 — Confirmado

Consultar lista de participantes e pesquisar pelo nome.

- **Prioridade:** MVP
- **Fonte:** PROTO, §14
- **Status da definição:** Confirmado

### RF-PAR-10 — Confirmado

Exibir o histórico de entradas, saídas e frequência de um participante.

- **Prioridade:** MVP
- **Fonte:** E2; §4; D05
- **Status da definição:** Confirmado

### RF-PAR-11 — Não se aplica no momento (P05)

Permitir importar participantes da planilha matriz existente, após validação de seu formato e campos.

- **Prioridade:** MVP
- **Fonte:** D08; P05
- **Status da definição:** Não se aplica no momento. Resposta do NCI (20/11/2026): o NCI não possui planilha matriz.

### RF-PAR-12 — Confirmado

Representar afastamentos temporários sem confundi-los com desligamento, conforme situações definidas pelo NCI.

- **Prioridade:** MVP
- **Fonte:** P02; §8
- **Status da definição:** Confirmado. Respostas do NCI (20 e 21/11/2026): afastamento é por problema de saúde; o participante continua no serviço, as faltas nas inscrições durante o afastamento são justificadas e ele **sai da lista de espera** (a parte da lista de espera ainda não está implementada; é da área de atividades).

### RF-PAR-13 — Confirmado (implementação adiada)

Aplicar identificação de duplicidades no cadastro por documento a ser escolhido pelo NCI.

- **Prioridade:** MVP
- **Fonte:** P18; §8
- **Status da definição:** Confirmado. Resposta do NCI (20/11/2026): o documento é o CPF, obrigatório. Implementação adiada por decisão da equipe.

### RF-PAR-14 — Confirmado

Registrar a origem de ingressantes que não vieram de CRAS, CREAS ou outros serviços da rede.

- **Prioridade:** MVP
- **Fonte:** P14
- **Status da definição:** Confirmado. Resposta do NCI (20/11/2026): texto livre, com a opção "Outros".

## RN — Regras de negócio

### RN-PAR-01 — Confirmado

O cadastro identifica uma pessoa; reingressos não devem criar automaticamente um novo participante.

- **Prioridade:** MVP
- **Fonte:** D14; §9
- **Status da definição:** Confirmado

### RN-PAR-02 — Confirmado

Um desligamento não deve excluir o cadastro nem o histórico de frequência do participante.

- **Prioridade:** MVP
- **Fonte:** D05
- **Status da definição:** Confirmado

### RN-PAR-03 — Confirmado

Cada desligamento deve conter um motivo pertencente à lista de motivos de saída do FMR.

- **Prioridade:** MVP
- **Fonte:** FMR; D05
- **Status da definição:** Confirmado. Resposta do NCI (21/11/2026) (Q3): a lista é a dos 6 motivos já cadastrados, sem "Outro".

### RN-PAR-04 — Confirmado

Não deve ocorrer desligamento automático em consequência de um número de faltas.

- **Prioridade:** MVP
- **Fonte:** D06
- **Status da definição:** Confirmado

### RN-PAR-05 — Confirmado

Os indicadores de situação de moradia, apoio, deficiência e BPC devem refletir os valores vigentes no mês do relatório, e não apenas os atuais.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.1; §8
- **Status da definição:** Confirmado

### RN-PAR-06 — Confirmado

A faixa etária deve ser derivada da data de nascimento, não armazenada como idade fixa.

- **Prioridade:** MVP
- **Fonte:** FMR; §8
- **Status da definição:** Confirmado

### RN-PAR-07 — Confirmado

A data de referência para classificar quem muda de faixa etária durante o mês deve ser validada pelo NCI.

- **Prioridade:** MVP
- **Fonte:** P01
- **Status da definição:** Confirmado. Resposta do NCI (20/11/2026): a faixa etária usa a idade no dia 1º do mês de referência.

### RN-PAR-08 — Confirmado

A reativação de participante anteriormente desligado representa somente uma mudança de status no sistema, sem contar como nova entrada nos indicadores mensais do FMR. O tempo de permanência anterior não deve ser somado ao cálculo do período mensal de referência. O histórico anterior deve ser preservado.

> Decisão (20/11/2026, Q4): mantido como está no código do relatório FMR. Na reativação, a origem do encaminhamento continua a original (Q13), como o código faz hoje.

- **Prioridade:** MVP
- **Fonte:** P03
- **Status da definição:** Confirmado

### RN-PAR-09 — Confirmado

A situação de afastado, inativo, cancelado ou desabilitado não deve ser equiparada a desligado até definição do NCI.

- **Prioridade:** MVP
- **Fonte:** P02; §8
- **Status da definição:** Confirmado. Respostas do NCI (20 e 21/11/2026): afastado = problema de saúde (continua no serviço); **cancelado = desligamento com motivo "Desistência"** (os cadastros existentes não serão convertidos por ora); **inativo** = saiu por vontade própria, tratamento a decidir em conjunto pela equipe.
