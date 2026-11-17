# Progresso — Segurança e infraestrutura

**Legenda:** [ ] não concluído; [x] concluído e testado. Não marcar concluído sem evidência de teste.

| Feito | ID | Estado da definição | Implementação | Evidência / teste | Commit / PR | Dependências ou bloqueios |
|---|---|---|---|---|---|---|
| [ ] | RNF-SEG-01 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-02 | Confirmado | Não iniciado | — | — | — |
| [x] | RNF-SEG-03 | Confirmado | Implementado, sem commit | participantes/tests/test_views.py (AcessoTests, CoreTests) | — | login_required em todas as telas |
| [x] | RNF-SEG-04 | Confirmado | Implementado: permissões por ação + perfis Equipe e Administrador (core/perfis.py); só Administrador tem permissões de contas (auth.user/group) | core/tests/test_permissoes.py, core/tests/test_perfis.py, participantes/tests/test_views.py | feature/usuarios-RF-USR-02 | Telas próprias de administração de contas: RF-USR-03. Permissões de atividades nos grupos: migration do app atividades |
| [ ] | RNF-SEG-05 | Confirmado | Implementado (padrão Django), sem teste específico | — | — | Hash PBKDF2 padrão; senha mínima de 10 caracteres |
| [ ] | RNF-SEG-06 | Confirmado | Configurado, sem commit | `check --deploy` no CI | — | HTTPS/HSTS/proxy via .env; validar no ambiente de produção |
| [ ] | RNF-SEG-07 | Confirmado | Parcial, sem commit | core/tests/test_auditoria.py, participantes/tests/test_services.py | — | Cadastros e frequências auditados e imutáveis; contas só pelo LogEntry do admin |
| [ ] | RNF-SEG-08 | Confirmado | Em análise | — | — | Finalidade de endereço, ensino médio e observação a confirmar com o NCI |
| [ ] | RNF-SEG-09 | Confirmado | Não iniciado | — | — | Retenção/anonimização (Q9), inclusive dos dados na auditoria |
| [ ] | RNF-SEG-10 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-11 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-12 | Confirmado | Não iniciado | — | — | — |
| [x] | RNF-SEG-13 | Confirmado | Implementado, sem commit | Todos os testes usam dados fictícios | — | — |
| [ ] | RNF-SEG-14 | Confirmado | Parcial, sem commit | — | — | Configuração por .env e CI com banco próprio; produção ainda não existe |
| [ ] | RNF-SEG-15 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-16 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-17 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-18 | Confirmado | Parcial | — | — | Fontes ainda carregadas do Google Fonts (hospedar localmente) |
| [ ] | RN-SEG-01 | Confirmado | Não iniciado | — | — | — |
| [x] | RN-SEG-02 | Confirmado | Implementado, sem commit | Todos os testes usam dados fictícios | — | — |

> Marque `[x]` apenas depois de implementar, testar e documentar os vínculos entre módulos. Se o requisito for pendente, não o implemente por suposição; registre a dúvida na coluna de bloqueios.
