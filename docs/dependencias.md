# Dependências, contratos e decisões de integração

## Estado dos contratos

**Proposto — alinhar entre os dois desenvolvedores antes de implementar modelos/migrations.** Os nomes de classes abaixo são sugestões de arquitetura, não requisitos confirmados pela instituição.

**Decisão atual sobre usuários:** por orientação explícita do responsável nesta sessão, utilizar o modelo padrão do Django (`AUTH_USER_MODEL = 'auth.User'`). Essa escolha libera as migrations nativas de autenticação. Os contratos restantes continuam propostos; perfis de negócio, autorização e auditoria ainda precisam de implementação. Relações futuras devem usar `settings.AUTH_USER_MODEL`, e consultas ao modelo devem usar `get_user_model()`.

| Dono | Entidade/contrato proposto | Consumidor | Dependência a respeitar |
|---|---|---|---|
| `usuarios` | Modelo padrão `auth.User`; perfis e serviços de autenticação ainda a implementar | Todos os apps | Modelo definido nesta sessão; usar `settings.AUTH_USER_MODEL` nas relações. Não criar tabela de usuários duplicada. |
| `participantes` | Identidade estável do `Participante`, histórico de situação e retorno; origem | `atividades`, `relatorios` | Não duplicar cadastro; expor identificador persistente e funções de consulta para o período. |
| `atividades` | `Atividade`, `Inscricao`, `Aula`, `Frequencia` | `relatorios` | Registrar aula concreta por data; frequência identificável por participante e aula; cancelamentos explícitos. |
| `relatorios` | Serviços de agregação mensal para o FMR parcial | Outros apps, relatórios | **Consumir** participantes e atividades, nunca possuir seus modelos; não presumir FMR completo. |
| Infraestrutura/segurança | Configuração PostgreSQL, migrações, auditoria, proteção de dados | Todos | Definir configuração comum, sem segredos em código. |

## Dependências de negócio confirmadas

- FMR exige dados cadastrais com vigência e eventos de frequência; **não é totalmente implementável antes de haver contratos para ambos**. Pode começar com testes usando dados fictícios e serviços simulados.
- Cadastro de participante é independente da tela de chamada; chamada/inscrição **referencia** participante preexistente.
- Aulas podem ocorrer fora da grade; aula cancelada não entra como realizada; faltas admitem situações e justificativas definidas nos requisitos.
- Retorno de participante desligado (**RN-PAR-08**) = alteração de status, **não** nova entrada para o FMR mensal; tempo anterior não se soma ao período mensal de referência. Não reinterpretar sem solicitação.
- O MVP só cobre **parte calculável** dos indicadores de convivência do FMR; não prometer preencher integralmente o FMR nem integrar ao portal SMADS.
- Visitantes não inscritos não participam do fluxo do MVP; RF-ATV-15 foi removido.
- RF-PAR-03 foi removido; não restaurar a coleta de campos por conta própria para satisfazer relatórios.

## Fronteiras a validar em conjunto antes de editar o código

1. **Usuário:** modelo padrão `auth.User` definido; continuam a alinhar a organização do app de serviços, permissões e relações auditáveis.
2. **Participante:** chave primária, assinatura de consulta de status vigente, distinção entre afastado/desligado e formato do retorno.
3. **Inscrição/frequência:** FK de participante, tratamento de aula extra/remarcada/cancelada, semântica de presença e motivo.
4. **FMR:** APIs de leitura por mês, definição das categorias e fontes de cada indicador; nunca consultar diretamente modelos privados de outro app sem contrato combinado.
5. **Migrations:** nomes de apps, dependências entre migrations, estratégia de resolução de conflitos e ordem de merge.

## Registro de interface acordada

Preencher em conjunto **antes** da implementação dependente:

| Contrato | Responsável | Consumidor | Assinatura/modelo aprovado | Versão/data | Estado |
|---|---|---|---|---|---|
| Modelo de usuário | Área de usuários | Todos | `auth.User`; FK por `settings.AUTH_USER_MODEL`, consultas por `get_user_model()` | Decisão desta sessão | Padrão Django adotado no momento; perfis e fluxos ainda pendentes |
| Identidade de participante | A definir | Atividades/FMR | A definir | — | A combinar |
| Consulta de situação mensal | A definir | FMR | A definir | — | A combinar |
| Registro de aula/frequência | A definir | FMR | A definir | — | A combinar |
| Consulta agregada FMR | A definir | Relatórios | A definir | — | A combinar |

**Regra:** alterações incompatíveis em um contrato acordado precisam ser combinadas e integradas em uma branch compartilhada antes de avançar em dependências. Não modificar a implementação do colega para destravar sua tarefa sem coordenação.
