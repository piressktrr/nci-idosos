# Atividades e frequência — requisitos

> Fonte: `Requisitos_NCI_RF_RNF_RN_Revisado_v2.docx` (revisão aprovada até o momento). Este arquivo descreve **o que** o sistema deve fazer; não indica que algo já foi implementado.
> Convenção: **Confirmado** = definição aceita; **Pendente** = depende de validação. **MVP/Depois** = prioridade.

## RF — Requisitos funcionais

### RF-ATV-01 — Confirmado

Cadastrar atividades com identificação, local e monitor/oficineiro responsável.

- **Prioridade:** MVP
- **Fonte:** GRADE; PROTO, §14
- **Status da definição:** Confirmado

### RF-ATV-02 — Confirmado

Cadastrar e alterar a grade de dias e horários de cada atividade.

- **Prioridade:** MVP
- **Fonte:** D07
- **Status da definição:** Confirmado

### RF-ATV-03 — Confirmado

Registrar a data e o horário efetivos de cada aula realizada.

- **Prioridade:** MVP
- **Fonte:** §5; §9; D07
- **Status da definição:** Confirmado

### RF-ATV-04 — Confirmado

Registrar aulas extras ou remarcadas fora da grade regular.

- **Prioridade:** MVP
- **Fonte:** D07
- **Status da definição:** Confirmado

### RF-ATV-05 — Confirmado

Registrar o cancelamento de uma aula, distinguindo-a de uma aula realizada.

- **Prioridade:** MVP
- **Fonte:** PROTO, §14; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RF-ATV-06 — Confirmado

Vincular participantes já cadastrados a atividades por meio de inscrições.

- **Prioridade:** MVP
- **Fonte:** D14; §9
- **Status da definição:** Confirmado

### RF-ATV-07 — Confirmado

Exibir a lista de participantes vinculados a uma atividade para efetuar a chamada.

- **Prioridade:** MVP
- **Fonte:** PROTO; E2
- **Status da definição:** Confirmado

### RF-ATV-08 — Confirmado

Registrar a frequência de cada participante por aula e data com as situações presente, ausente e ausente justificado.

- **Prioridade:** MVP
- **Fonte:** D04; §5
- **Status da definição:** Confirmado

### RF-ATV-09 — Confirmado

Registrar motivo padronizado da falta justificada e campo de observação.

- **Prioridade:** MVP
- **Fonte:** D04
- **Status da definição:** Confirmado

### RF-ATV-10 — Confirmado

Permitir que a equipe autorizada do NCI corrija registros de frequência já lançados, preservando a rastreabilidade das alterações.

- **Prioridade:** MVP
- **Fonte:** E2; PROTO, §14; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RF-ATV-11 — Confirmado

Consultar frequência mensal por atividade ou em visão geral.

- **Prioridade:** MVP
- **Fonte:** PROTO, §14; §4
- **Status da definição:** Confirmado

### RF-ATV-12 — Confirmado

Consultar o total de presenças e o histórico de frequência de cada participante por atividade.

- **Prioridade:** MVP
- **Fonte:** §4; PROTO, §14
- **Status da definição:** Confirmado

### RF-ATV-13 — Confirmado

Relacionar as aulas realizadas às categorias de atividades utilizadas no FMR, admitindo ajustes de classificação conforme a regra que vier a ser definida para seu nível de aplicação (P04).

- **Prioridade:** MVP
- **Fonte:** FMR; TAB-JUL; §7; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RF-ATV-14 — Confirmado

Controlar a lista de espera das atividades, permitindo registrar participantes em espera conforme a disponibilidade de vagas.

- **Prioridade:** MVP
- **Fonte:** GRADE; confirmação da equipe (revisão 06/11/2026)
- **Status da definição:** Confirmado

## RN — Regras de negócio

### RN-ATV-01 — Confirmado

O registro de frequência é feito pela equipe do NCI, a partir das listas assinadas; o oficineiro não é usuário do MVP.

- **Prioridade:** MVP
- **Fonte:** D03
- **Status da definição:** Confirmado

### RN-ATV-02 — Confirmado

A lista de presença física assinada permanece obrigatória e não é substituída pelo registro digital.

- **Prioridade:** MVP
- **Fonte:** §1; D03
- **Status da definição:** Confirmado

### RN-ATV-03 — Confirmado

Cada registro de chamada deve estar associado a uma atividade e a uma data de ocorrência, independentemente do dia da digitação.

- **Prioridade:** MVP
- **Fonte:** §5; §9
- **Status da definição:** Confirmado

### RN-ATV-04 — Confirmado

As situações permitidas para a frequência são presente, ausente e ausente justificado.

- **Prioridade:** MVP
- **Fonte:** D04
- **Status da definição:** Confirmado

### RN-ATV-05 — Confirmado

Uma aula fora da grade regular não deve ser impedida por incompatibilidade com dias ou horários usuais.

- **Prioridade:** MVP
- **Fonte:** D07
- **Status da definição:** Confirmado

### RN-ATV-06 — Confirmado

Uma aula cancelada não deve ser computada como aula realizada no total de atividades do FMR.

- **Prioridade:** MVP
- **Fonte:** D10; PROTO, §14; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RN-ATV-07 — Confirmado

A classificação de aulas e atividades nas categorias do FMR deve permitir ajustes para refletir a classificação efetivamente adotada pelo NCI no período de referência. O nível de aplicação da classificação (atividade, aula ou mês) ainda depende de definição (P04).

- **Prioridade:** MVP
- **Fonte:** §7.2; P04; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RN-ATV-08 — Confirmado

Ausências justificadas devem permitir associação a motivos padronizados editáveis e observação.

- **Prioridade:** MVP
- **Fonte:** D04
- **Status da definição:** Confirmado
