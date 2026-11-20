# Segurança e infraestrutura — requisitos

> Fonte: `Requisitos_NCI_RF_RNF_RN_Revisado_v2.docx` (revisão aprovada até o momento). Este arquivo descreve **o que** o sistema deve fazer; não indica que algo já foi implementado.
> Convenção: **Confirmado** = definição aceita; **Pendente** = depende de validação. **MVP/Depois** = prioridade.

## RNF — Requisitos não funcionais

### RNF-SEG-01 — Confirmado

O sistema deve funcionar em navegador web, sem necessidade de instalação local nos computadores do NCI.

- **Prioridade:** MVP
- **Fonte:** D01
- **Status da definição:** Confirmado

### RNF-SEG-02 — Confirmado

A aplicação deve ser implantável em ambiente de nuvem e armazenar dados em PostgreSQL, com backend Django conforme decisão de arquitetura.

- **Prioridade:** MVP
- **Fonte:** D02; §13
- **Status da definição:** Confirmado

### RNF-SEG-03 — Confirmado

Nenhum dado pessoal deve ser disponibilizado a usuários não autenticados.

- **Prioridade:** MVP
- **Fonte:** D11; §15
- **Status da definição:** Confirmado

### RNF-SEG-04 — Confirmado

O sistema deve aplicar autorização conforme o perfil de acesso, restringindo a administração de contas aos administradores.

- **Prioridade:** MVP
- **Fonte:** D11; §15
- **Status da definição:** Confirmado

### RNF-SEG-05 — Confirmado

As senhas devem ser armazenadas de forma não reversível por função de hash adequada e nunca em texto puro.

- **Prioridade:** MVP
- **Fonte:** §15; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-06 — Confirmado

As comunicações entre navegador e servidor devem utilizar HTTPS em produção.

- **Prioridade:** MVP
- **Fonte:** §15; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-07 — Confirmado

Alterações relevantes em cadastros, frequências e contas devem ser auditáveis, com usuário, data/hora e natureza da mudança.

- **Prioridade:** MVP
- **Fonte:** §15; PROTO, §14; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-08 — Confirmado

A coleta e o armazenamento de dados pessoais devem se limitar aos dados necessários às atividades do NCI e à elaboração dos relatórios exigidos, evitando campos sem finalidade definida.

- **Prioridade:** MVP
- **Fonte:** §8; §15; §17.4; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-09 — Confirmado

Os dados necessários à operação do NCI e à prestação de contas devem ser preservados conforme sua necessidade e as obrigações aplicáveis, sem manter dados desnecessários. Prazos e procedimentos específicos de retenção e eliminação permanecem sujeitos à definição da política institucional.

- **Prioridade:** MVP
- **Fonte:** P12; §15; confirmação da equipe (revisão 06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-10 — Confirmado

Deve existir procedimento documentado de cópia de segurança e restauração para assegurar a continuidade após o projeto acadêmico.

- **Prioridade:** MVP
- **Fonte:** §13; §15; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-11 — Confirmado

A instituição deve conseguir exportar ou recuperar seus dados em formato utilizável sem depender permanentemente dos desenvolvedores.

- **Prioridade:** MVP
- **Fonte:** §13
- **Status da definição:** Confirmado

### RNF-SEG-12 — Confirmado

O sistema deve ter documentação de operação e transferência que permita manutenção básica pela equipe do NCI.

- **Prioridade:** MVP
- **Fonte:** §2; §13
- **Status da definição:** Confirmado

### RNF-SEG-13 — Confirmado

O desenvolvimento e os testes devem empregar dados fictícios, sem uso de dados reais dos participantes fora da produção.

- **Prioridade:** MVP
- **Fonte:** D15
- **Status da definição:** Confirmado

### RNF-SEG-14 — Confirmado

O ambiente de produção deve ser segregado dos ambientes de desenvolvimento e teste.

- **Prioridade:** MVP
- **Fonte:** D15; §13; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-15 — Confirmado

A interface deve ser utilizável nos computadores básicos disponíveis na instituição. Os navegadores suportados e os critérios quantitativos de desempenho serão especificados após levantamento do ambiente.

- **Prioridade:** MVP
- **Fonte:** §2; P13; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-16 — Confirmado

A hospedagem inicial deve admitir modalidade gratuita e migração posterior para modalidade paga autorizada pelo NCI.

- **Prioridade:** MVP
- **Fonte:** D02; §13
- **Status da definição:** Confirmado

### RNF-SEG-17 — Confirmado

As contas de hospedagem, banco de dados e domínio do sistema devem pertencer à instituição, não a contas pessoais dos desenvolvedores.

- **Prioridade:** MVP
- **Fonte:** §13; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

### RNF-SEG-18 — Confirmado

O tratamento e a hospedagem dos dados devem observar as restrições legais e institucionais aplicáveis, inclusive aquelas relativas ao local de armazenamento. A política específica de localização deverá ser documentada na implantação.

- **Prioridade:** MVP
- **Fonte:** §15; anexo A, questão 19; confirmação da equipe (06/11/2026)
- **Status da definição:** Confirmado

## RN — Regras de negócio

### RN-SEG-01 — Confirmado

Qualquer contratação paga de hospedagem ou infraestrutura exige autorização prévia da gestora da parceria e nota fiscal.

- **Prioridade:** MVP
- **Fonte:** E2; §13
- **Status da definição:** Confirmado

### RN-SEG-02 — Confirmado

As informações pessoais reais do NCI devem ser utilizadas apenas no ambiente de produção, e não como massa de testes.

- **Prioridade:** MVP
- **Fonte:** D15
- **Status da definição:** Confirmado
