# Progresso — Atividades e frequência

**Legenda:** [ ] não concluído; [x] concluído e testado. Não marcar concluído sem evidência de teste.

## Contrato provisório de `Atividade`

Para iniciar o RF-ATV-01, foi autorizado pelo responsável da área o uso de um contrato provisório: `Atividade` terá, inicialmente, os campos `nome`, `local` e `monitor`. Este contrato ainda precisa ser alinhado com o outro desenvolvedor antes de ser considerado estável ou consumido por outros apps. Não define ainda categoria FMR, grade, participantes, autenticação ou auditoria.

O contrato segue provisório. A migration inicial, escrita manualmente, foi posteriormente conferida com `makemigrations atividades --check --dry-run` e aplicada com sucesso no PostgreSQL local.

## Commits iniciais

- `d8797da`: documentação de requisitos e contratos.
- `81c4a63`: dependências e configuração do ambiente Django/PostgreSQL.
- O modelo, a migration inicial, o registro do app e este progresso compõem o commit de início do RF-ATV-01, ainda parcial. Autoria vinculada à conta GitHub `liphecodez`. Commits locais na branch `atividades_frequencia`.

### Verificação do ambiente — 07/11/2026

- Remoto `origin` confirmado: `https://github.com/piressktrr/nci-idosos.git`. Consulta `git ls-remote --heads origin` e busca `git fetch origin develop` realizadas com sucesso.
- Branch local `atividades_frequencia` criada a partir de `origin/develop` (commit `8bed795`), preservando as alterações locais. Ainda não publicada no remoto.
- `git fsck --no-reflogs` e `git diff --check` executados sem erros.
- A primeira verificação foi limitada pelo sandbox: Python não estava acessível nele. Fora do sandbox foi confirmado Python 3.14.3 já instalado; não foi necessário reinstalá-lo.

### Instalação e configuração local — 07/11/2026

- Ambiente `.venv` criado com Python 3.14.3; Django 6.1.3, psycopg 3.3.8 e python-dotenv 1.2.4 instalados e fixados em `requirements.txt`.
- PostgreSQL 17.11 instalado pelos binários oficiais EDB em `%LOCALAPPDATA%\NCI\PostgreSQL17`; dados fora do OneDrive, escuta somente em `127.0.0.1:5433`. Banco `nci_dev`, usuário próprio sem superusuário e com CREATEDB para bancos de teste.
- `settings.py` configurado para PostgreSQL via variáveis de ambiente/`.env`; segredos locais aleatórios, ausentes do código; `.env.example` disponível. Removida a rota inválida `polls.urls`. README e scripts de preparação/controle do banco adicionados.
- `python -m pip check`: sem conflitos. `python -m compileall -q atividades scripts nci-cidade-dourada`: sem erros de sintaxe. Comandos executados com o Python da `.venv`.
- `python manage.py check`: nenhum problema; `python manage.py makemigrations atividades --check --dry-run`: nenhuma alteração; `python manage.py migrate atividades`: `0001_initial` aplicada.
- Verificação via `python manage.py shell -c ...`: conexão PostgreSQL, validação, gravação/leitura Unicode de atividade fictícia e rollback sem deixar registros; HTTP `/admin/` respondeu 302 e `/admin/login/` respondeu 200 via cliente Django. Isso não valida administração de contas nem substitui testes completos do RF-ATV-01.
- `git check-ignore .env .venv`: ambos ignorados; `git diff --check`: sem erros. Nesta etapa de instalação, as migrations de autenticação foram adiadas; a decisão e aplicação posteriores estão registradas abaixo.

### Decisão atual de modelo de usuário

- O responsável definiu explicitamente o uso, no momento, do usuário padrão do Django. `settings.py` explicita `AUTH_USER_MODEL = 'auth.User'`; contrato registrado em `docs/dependencias.md` e instruções do README atualizadas.
- `python manage.py migrate`: migrations nativas de `auth`, `contenttypes`, `admin` e `sessions` aplicadas com sucesso no PostgreSQL local. Nenhum modelo de usuário próprio ou migration adicional foi criado.
- `python manage.py check`: nenhum problema. `python manage.py makemigrations --check --dry-run`: nenhuma alteração. `python manage.py showmigrations`: todas aplicadas.
- Verificação via `python manage.py shell -c ...`: confirmou `auth.User`, hash de senha, autenticação válida, rejeição de senha incorreta, redirecionamento anônimo e acesso de staff a `/admin/`. Conta fictícia e sessão revertidas por rollback; nenhuma conta administrativa permanente criada.
- A definição do modelo de usuário deixa de bloquear a integração. Perfis de negócio, fluxos de contas e auditoria continuam no escopo da área de usuários, sem marcar requisitos dela como concluídos por esta configuração.

| Feito | ID | Estado da definição | Implementação | Evidência / teste | Commit / PR | Dependências ou bloqueios |
|---|---|---|---|---|---|---|
| [ ] | RF-ATV-01 | Confirmado | Parcial: modelo mínimo e migration inicial validados no PostgreSQL; fluxo de cadastro, autorização e auditoria pendentes | `check`, `makemigrations --check`, `migrate atividades` e gravação/leitura com rollback passaram | — | Contrato `Atividade` provisório; alinhar antes de estabilizar/consumir |
| [ ] | RF-ATV-02 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-03 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-04 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-05 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-06 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-07 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-08 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-09 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-10 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-11 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-12 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-13 | Confirmado | Não iniciado | — | — | — |
| [ ] | RF-ATV-14 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-01 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-02 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-03 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-04 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-05 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-06 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-07 | Confirmado | Não iniciado | — | — | — |
| [ ] | RN-ATV-08 | Confirmado | Não iniciado | — | — | — |

> Marque `[x]` apenas depois de implementar, testar e documentar os vínculos entre módulos. Se o requisito for pendente, não o implemente por suposição; registre a dúvida na coluna de bloqueios.
