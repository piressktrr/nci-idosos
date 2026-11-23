# Progresso — Segurança e infraestrutura

**Legenda:** [ ] não concluído; [x] concluído e testado. Não marcar concluído sem evidência de teste.

| Feito | ID | Estado da definição | Implementação | Evidência / teste | Commit / PR | Dependências ou bloqueios |
|---|---|---|---|---|---|---|
| [ ] | RNF-SEG-01 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-02 | Confirmado | Não iniciado | — | — | — |
| [x] | RNF-SEG-03 | Confirmado | Implementado | participantes/tests/test_views.py (AcessoTests), core/tests/test_views.py (CoreTests) | — | login_required em todas as telas |
| [ ] | RNF-SEG-04 | Confirmado | Implementado: permissões por ação + perfis Equipe e Administrador (core/perfis.py); só Administrador tem permissões de contas (auth.user/group) | core/tests/test_permissoes.py, core/tests/test_perfis.py, participantes/tests/test_views.py | feature/usuarios-RF-USR-02 | Equipe e Administrador ainda sem as permissões operacionais de atividades (o app atividades não as concede); hoje só superusuário usa atividades/frequência. Catálogo FMR exige `is_superuser` |
| [x] | RNF-SEG-05 | Confirmado | Concluído: senha guardada só com hash do hasher principal do Django (PBKDF2) e AUTH_PASSWORD_VALIDATORS ativos (mínimo de 10, semelhança, comum, numérica), usados pelos serviços de colaboradores Relatórios de erro (e-mail aos ADMINS) sem campos de formulário, cookies nem variáveis com senha (`core.relatorio_erros`). | core/tests/test_senhas.py; core/tests/test_relatorio_erros.py | feature/seguranca-RNF-SEG-05-07 | — |
| [ ] | RNF-SEG-06 | Confirmado | Configurado, sem commit | `check --deploy` no CI | — | HTTPS/HSTS/proxy via .env; validar no ambiente de produção |
| [ ] | RNF-SEG-07 | Confirmado | Parcial: cadastros, frequências e contas auditados e imutáveis (core.EventoAuditoria); contas pelo proxy `usuarios.RegistroConta` (cadastro, correção só do que mudou, nova senha sem senha nem hash), com histórico na tela de edição do colaborador; `auth.User` e `auth.Group` retirados do admin do Django, então contas só mudam pelas telas próprias auditadas | core/tests/test_auditoria.py, participantes/tests/test_services.py, usuarios/tests/test_services.py, usuarios/tests/test_admin.py | feature/usuarios-RF-USR-03 (contas), feature/seguranca-RNF-SEG-05-07 (admin) | Superusuário ainda altera outros modelos pelo admin do Django (só LogEntry); revisar antes de marcar [x] |
| [ ] | RNF-SEG-08 | Confirmado | Finalidades definidas (NCI 20/11/2026) | — | — | Endereço completo (preenchido pela equipe, sem consulta externa), ensino médio (campo do FMR a ampliar) e observação do encaminhamento (acesso restrito) têm finalidade registrada em docs/requisitos |
| [ ] | RNF-SEG-09 | Confirmado | Definido: anonimizar 1 ano após o desligamento, apagando todos os dados da pessoa (Resposta do NCI (21/11/2026)) | — | — | Falta implementar (campos, auditoria imutável, backups e efeito nos meses antigos do FMR) |
| [ ] | RNF-SEG-10 | Confirmado | Documentado, sem teste de restauração real | docs/operacao/backup.md; pg_dump, `pg_restore --list` e restauração num banco de teste validados no container de desenvolvimento (17/11/2026) | — | Falta executar uma restauração de verdade no ambiente de produção para marcar [x]; frequência/retenção dependem de RNF-SEG-09 (Q9) |
| [ ] | RNF-SEG-11 | Confirmado | Parcial: participantes exportáveis em CSV (UTF-8 com BOM, ";") pela lista (botão "Exportar CSV") e por `manage.py exportar_participantes`; permissão própria `participantes.exportar_participante` (só Administrador); cada exportação auditada (`RegistroExportacao`, só quantidade e formato) | participantes/tests/test_exportacao.py; docs/operacao/manutencao.md#exportação-de-dados | feature/seguranca-RNF-SEG-11 | Exportação de atividades/frequência fica com o dono do módulo de atividades; backup completo do banco em docs/operacao/backup.md (RNF-SEG-10) |
| [ ] | RNF-SEG-12 | Confirmado | Documentado, sem teste de restauração real | docs/operacao/manutencao.md | — | Falta a equipe do NCI executar uma restauração de verdade e a transferência (checklist) para marcar [x]; forma de hospedagem ainda indefinida |
| [ ] | RNF-SEG-13 | Confirmado | Adotado em todos os testes | Prática de revisão; sem verificação automática | — | — |
| [ ] | RNF-SEG-14 | Confirmado | Parcial, sem commit | — | — | Configuração por .env e CI com banco próprio; produção ainda não existe |
| [ ] | RNF-SEG-15 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-16 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-17 | Confirmado | Não iniciado | — | — | — |
| [ ] | RNF-SEG-18 | Confirmado | Parcial | core/tests/test_fontes.py | — | Fontes externas removidas: Poppins 700 e Questrial 400 servidas de static/vendor/fonts (@fontsource 5.3.0, OFL 1.1), sem Google Fonts; falta documentar a política de local de armazenamento/hospedagem dos dados na implantação |
| [ ] | RN-SEG-01 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-SEG-02 | Confirmado | Adotado em todos os testes | Prática de revisão; sem verificação automática | — | — |

> Marque `[x]` apenas depois de implementar, testar e documentar os vínculos entre módulos. Se o requisito for pendente, não o implemente por suposição; registre a dúvida na coluna de bloqueios.
