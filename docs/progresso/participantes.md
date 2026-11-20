# Progresso — Participantes

**Legenda:** [ ] não concluído; [x] concluído e testado. Não marcar concluído sem evidência de teste.

| Feito | ID | Estado da definição | Implementação | Evidência / teste | Commit / PR | Dependências ou bloqueios |
|---|---|---|---|---|---|---|
| [x] | RF-PAR-01 | Confirmado | Implementado, sem commit | participantes/tests/test_models.py, test_services.py, test_views.py | — | Categorias de raça/cor e identidade de gênero provisórias (Q1/Q2) |
| [x] | RF-PAR-02 | Confirmado | Implementado, sem commit | participantes/tests/test_regras.py (TelefoneTests), test_models.py, test_views.py | — | Pelo menos um telefone do próprio participante (Q10) |
| [x] | RF-PAR-04 | Confirmado | Implementado, sem commit | participantes/tests/test_models.py (SituacaoSocialTests), test_services.py | — | Situação social opcional no cadastro (Q12) |
| [x] | RF-PAR-05 | Confirmado | Implementado, sem commit | participantes/tests/test_models.py (vigente_em), test_services.py, test_views.py | — | Vigência por data de início |
| [x] | RF-PAR-06 | Confirmado | Implementado, sem commit | participantes/tests/test_models.py, test_services.py | — | Categorias provisórias até a lista do FMR (Q11) |
| [ ] | RF-PAR-07 | Confirmado | Não iniciado | — | — | Bloqueado: motivos de desligamento (Q3) |
| [ ] | RF-PAR-08 | Confirmado | Não iniciado | — | — | Bloqueado: reativação na equação do FMR (Q4) |
| [x] | RF-PAR-09 | Confirmado | Implementado, sem commit | participantes/tests/test_services.py (PesquisaTests), test_views.py (ListaTests) | — | Pesquisa no banco por `nome_busca` |
| [x] | RF-PAR-10 | Confirmado | Implementado | participantes/tests/test_views.py (MovimentacoesNoDetalheTests), test_integracao_atividades.py | — | Entradas, saídas e afastamentos e frequência por atividade no detalhe |
| [ ] | RF-PAR-11 | Pendente (P05) | Não iniciado | — | — | — |
| [ ] | RF-PAR-12 | Pendente (P02) | Não iniciado | — | — | — |
| [ ] | RF-PAR-13 | Pendente (P18) | Não iniciado | — | — | — |
| [ ] | RF-PAR-14 | Pendente (P14) | Não iniciado | — | — | — |
| [x] | RN-PAR-01 | Confirmado | Implementado, sem commit | participantes/tests/test_services.py (DuplicidadeTests), test_views.py | — | Alerta por nome + nascimento; documento depende da P18 |
| [ ] | RN-PAR-02 | Confirmado | Parcial, sem commit | participantes/tests/test_models.py (ExclusaoParticipanteTests), test_integracao_atividades.py | — | Exclusão bloqueada e histórico preservado; desligamento em si depende da Q3 |
| [ ] | RN-PAR-03 | Confirmado | Não iniciado | — | — | Bloqueado: lista de motivos do FMR (Q3) |
| [x] | RN-PAR-04 | Confirmado | Implementado, sem commit | participantes/tests/test_integracao_atividades.py (FaltasNaoDesligamTests) | — | Nenhum código desliga por faltas; teste trava a regra |
| [ ] | RN-PAR-05 | Confirmado | Parcial, sem commit | participantes/tests/test_consultas.py, test_models.py | — | `situacoes_vigentes_em` pronta; falta o relatório do FMR usar |
| [x] | RN-PAR-06 | Confirmado | Implementado, sem commit | participantes/tests/test_regras.py (FaixaEtariaFmrTests), test_models.py | — | Data de referência de aniversário depende da P01 |
| [ ] | RN-PAR-07 | Pendente (P01) | Não iniciado | — | — | — |
| [ ] | RN-PAR-08 | Confirmado | Não iniciado | — | — | Bloqueado: Q4 |
| [ ] | RN-PAR-09 | Pendente (P02) | Não iniciado | — | — | Pendente (P02); status travado como Ativo, só leitura |

> Marque `[x]` apenas depois de implementar, testar e documentar os vínculos entre módulos. Se o requisito for pendente, não o implemente por suposição; registre a dúvida na coluna de bloqueios.
