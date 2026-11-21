# Progresso — Participantes

**Legenda:** [ ] não concluído; [x] concluído e testado. Não marcar concluído sem evidência de teste.

| Feito | ID | Estado da definição | Implementação | Evidência / teste | Commit / PR | Dependências ou bloqueios |
|---|---|---|---|---|---|---|
| [x] | RF-PAR-01 | Confirmado | Implementado, sem commit | participantes/tests/test_models.py, test_services.py, test_views.py | — | Categorias de raça/cor e identidade de gênero provisórias (Q1/Q2) |
| [x] | RF-PAR-02 | Confirmado | Implementado, sem commit | participantes/tests/test_regras.py (TelefoneTests), test_models.py, test_views.py | — | Pelo menos um telefone do próprio participante (Q10) |
| [x] | RF-PAR-04 | Confirmado | Implementado, sem commit | participantes/tests/test_models.py (SituacaoSocialTests), test_services.py | — | Situação social opcional no cadastro (Q12) |
| [x] | RF-PAR-05 | Confirmado | Implementado, sem commit Perfil demográfico vale desde a entrada, inclusive quando ela é antecipada; vigência pode ser inserida entre perfis. | participantes/tests/test_models.py (vigente_em), test_services.py, test_views.py; test_services.py (PerfilDemograficoRetroativoTests) | — | Vigência por data de início |
| [x] | RF-PAR-06 | Confirmado | Implementado, sem commit | participantes/tests/test_models.py, test_services.py | — | Categorias provisórias até a lista do FMR (Q11) |
| [x] | RF-PAR-07 | Confirmado | Implementado (PR #8) | participantes/tests/test_movimentacoes.py | — | Motivos cadastrados pelo administrador; resposta da Q3 a registrar nos requisitos |
| [x] | RF-PAR-08 | Confirmado | Implementado (PR #8) | participantes/tests/test_movimentacoes.py (reativação preserva identidade) | — | Resposta da Q4 a registrar nos requisitos |
| [x] | RF-PAR-09 | Confirmado | Implementado, sem commit | participantes/tests/test_services.py (PesquisaTests), test_views.py (ListaTests) | — | Pesquisa no banco por `nome_busca` |
| [x] | RF-PAR-10 | Confirmado | Implementado | participantes/tests/test_views.py (MovimentacoesNoDetalheTests), test_integracao_atividades.py | — | Entradas, saídas e afastamentos e frequência por atividade no detalhe |
| [ ] | RF-PAR-11 | Pendente (P05) | Não se aplica no momento | — | — | NCI não possui planilha matriz (P05, 20/11/2026) |
| [x] | RF-PAR-12 | Pendente (P02) | Implementado (PR #8) | participantes/tests/test_movimentacoes.py (afastamento e retorno) | — | Resposta da P02 a registrar nos requisitos |
| [ ] | RF-PAR-13 | Pendente (P18) | Adiado | — | — | CPF obrigatório confirmado (P18, 20/11/2026); implementação adiada pela equipe |
| [x] | RF-PAR-14 | Pendente (P14) | Implementado | participantes/tests/test_models.py (OrigemOutrosTests), test_views.py (OrigemOutrosViewTests), test_exportacao.py | — | Origem "Outros" com descrição em texto livre, obrigatória no formulário; cadastros antigos e outros módulos não são bloqueados |
| [x] | RN-PAR-01 | Confirmado | Implementado, sem commit | participantes/tests/test_services.py (DuplicidadeTests), test_views.py | — | Alerta por nome + nascimento; documento depende da P18 |
| [x] | RN-PAR-02 | Confirmado | Implementado | participantes/tests/test_movimentacoes.py, test_integracao_atividades.py, core/tests/test_auditoria.py | — | Desligamento só muda status e grava movimentação; exclusão bloqueada |
| [x] | RN-PAR-03 | Confirmado | Implementado (PR #8) | participantes/tests/test_movimentacoes.py | — | Motivo obrigatório no desligamento (constraint); lista mantida pelo administrador |
| [x] | RN-PAR-04 | Confirmado | Implementado, sem commit | participantes/tests/test_integracao_atividades.py (FaltasNaoDesligamTests) | — | Nenhum código desliga por faltas; teste trava a regra |
| [x] | RN-PAR-05 | Confirmado | Implementado | participantes/tests/test_consultas.py; participantes/relatorios.py usa situacoes_vigentes_em | — | — |
| [x] | RN-PAR-06 | Confirmado | Implementado, sem commit | participantes/tests/test_regras.py (FaixaEtariaFmrTests), test_models.py | — | Data de referência de aniversário depende da P01 |
| [x] | RN-PAR-07 | Pendente (P01) | Implementado | participantes/tests/test_regras.py (FaixaEtariaNoMesTests), test_models.py | — | Faixa etária pela idade no dia 1º do mês (P01, 20/11/2026); o relatório FMR já usava o dia 1º |
| [x] | RN-PAR-08 | Confirmado | Implementado (PR #8) | participantes/tests/test_movimentacoes.py | — | Entrada única por constraint; reativação e retorno não contam como ingresso |
| [x] | RN-PAR-09 | Pendente (P02) | Implementado (PR #8) | participantes/tests/test_movimentacoes.py (afastado permanece no serviço) | — | Inativo/Cancelado são legados sem equivalência (P02) |

> Marque `[x]` apenas depois de implementar, testar e documentar os vínculos entre módulos. Se o requisito for pendente, não o implemente por suposição; registre a dúvida na coluna de bloqueios.
