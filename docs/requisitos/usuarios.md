# Usuários e controle de acesso — requisitos

> Fonte: `Requisitos_NCI_RF_RNF_RN_Revisado_v2.docx` (revisão aprovada até o momento). Este arquivo descreve **o que** o sistema deve fazer; não indica que algo já foi implementado.
> Convenção: **Confirmado** = definição aceita; **Pendente** = depende de validação. **MVP/Depois** = prioridade.

## RF — Requisitos funcionais

### RF-USR-01 — Confirmado

Autenticar cada integrante da equipe do NCI com login individual.

- **Prioridade:** MVP
- **Fonte:** D11
- **Status da definição:** Confirmado

### RF-USR-02 — Confirmado

Distinguir os perfis de usuário comum e administrador.

- **Prioridade:** MVP
- **Fonte:** D11
- **Status da definição:** Confirmado

### RF-USR-03 — Confirmado

Permitir somente ao administrador cadastrar e administrar usuários do sistema.

- **Prioridade:** MVP
- **Fonte:** D11
- **Status da definição:** Confirmado

### RF-USR-04 — Pendente (proposta do protótipo)

Permitir ao administrador desativar um usuário preservando o histórico de suas ações.

- **Prioridade:** MVP
- **Fonte:** PROTO, §14
- **Status da definição:** Pendente (proposta do protótipo)

### RF-USR-05 — Pendente

Oferecer mecanismo de recuperação de acesso a ser definido pela equipe e pelo NCI.

- **Prioridade:** MVP
- **Fonte:** PROTO, §14
- **Status da definição:** Pendente

## RN — Regras de negócio

### RN-USR-01 — Confirmado

Somente usuários administradores podem gerenciar outras contas de acesso.

- **Prioridade:** MVP
- **Fonte:** D11
- **Status da definição:** Confirmado

### RN-USR-02 — Confirmado

O sistema deve permitir acesso aos dados apenas por integrantes autorizados da equipe do NCI; oficineiros não têm acesso no MVP.

- **Prioridade:** MVP
- **Fonte:** D03; D11
- **Status da definição:** Confirmado
