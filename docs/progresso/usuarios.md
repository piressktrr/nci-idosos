# Progresso — Usuários e controle de acesso

**Legenda:** [ ] não concluído; [x] concluído e testado. Não marcar concluído sem evidência de teste.

| Feito | ID | Estado da definição | Implementação | Evidência / teste | Commit / PR | Dependências ou bloqueios |
|---|---|---|---|---|---|---|
| [ ] | RF-USR-01 | Confirmado | Não iniciado | — | — | — |
| [x] | RF-USR-02 | Confirmado | Implementado: grupos Equipe (usuário comum) e Administrador garantidos no post_migrate e por `manage.py garantir_perfis` (core/perfis.py); critério único `core.perfis.e_administrador` | core/tests/test_perfis.py | feature/usuarios-RF-USR-02 | Site admin do Django ainda exige `is_staff` além do grupo (telas de contas: RF-USR-03). O catálogo de categorias do FMR (atividades.classificacao) usa só `is_superuser`, não `e_administrador`. Permissões de atividades nos grupos ficam para a migration de atividades |
| [ ] | RF-USR-03 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-USR-04 | Pendente (proposta do protótipo) | Não iniciado | — | — | — |
| [ ] | RF-USR-05 | Pendente | Não iniciado | — | — | — |
| [ ] | RN-USR-01 | Confirmado | Não iniciado | — | — | — |
| [x] | RN-USR-02 | Confirmado | Implementado: dados só com login e permissão; conta sem grupo não vê módulos; não há perfil de oficineiro | core/tests/test_perfis.py, core/tests/test_permissoes.py, participantes/tests/test_views.py | feature/usuarios-RF-USR-02 | Atribuição dos integrantes aos grupos é feita pelo administrador (admin do Django até o RF-USR-03) |

> Marque `[x]` apenas depois de implementar, testar e documentar os vínculos entre módulos. Se o requisito for pendente, não o implemente por suposição; registre a dúvida na coluna de bloqueios.
