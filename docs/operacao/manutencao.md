# Operação, manutenção e transferência (RNF-SEG-12)

Guia para a equipe do NCI (ou quem ela indicar) manter o sistema NCI Idade Dourada funcionando depois do
projeto acadêmico: subir o ambiente, atualizar o código, criar contas administrativas, entender as
configurações e receber o sistema dos desenvolvedores. Backup e restauração estão em
[backup.md](backup.md).

## Visão geral

Sistema web em **Django 6.1** (Python 3.14) com banco **PostgreSQL 17**. O navegador é o único requisito
nos computadores do NCI (RNF-SEG-01). Em desenvolvimento só o banco roda no Docker
(`docker-compose.yaml`, container `nci-postgres`); o Django roda pela `.venv`.

| Pasta | O que é |
|---|---|
| `config/` | Configurações (`settings.py`, lidas do `.env`), rotas principais (`urls.py`) e ponto de entrada WSGI (`config.wsgi.application`). |
| `core/` | Núcleo comum: tela inicial, auditoria (`EventoAuditoria`, que registra quem mudou o quê e quando e impede apagar registros auditados), verificação de permissões e contratos de leitura entre apps. |
| `participantes/` | Cadastro de participantes, situação social, movimentações (entrada, desligamento, retorno) e o histórico de auditoria do cadastro. |
| `usuarios/` | Gestão de colaboradores (contas, perfis, nova senha, desativação) e o "esqueci minha senha", com auditoria das contas. |
| `atividades/` | Atividades, grade de horários, aulas, inscrições, chamada/frequência e os dados usados no FMR. Documentados à parte, em `docs/requisitos/` e `docs/progresso/`. |
| `relatorios/` | Tela do FMR mensal (`/fmr/`): junta os dados de participantes e atividades para a transcrição no portal da SMADS. |
| `templates/`, `static/` | Telas (HTML) e arquivos de estilo, scripts e imagens. |
| `docs/` | Requisitos, progresso por área, contratos entre apps, fluxo Git e este guia. |

Rotas: `/` (início), `/entrar/` (com "Esqueci minha senha") e `/sair/`, `/participantes/`, `/atividades/`,
`/colaboradores/` (contas, só administradores), `/fmr/` e `/admin/` (administração do Django, só leitura para os
dados do sistema; contas e grupos não aparecem nele). Todas as telas exigem login (RNF-SEG-03), exceto a entrada e
a recuperação de senha.

## Subir o ambiente

O passo a passo completo, com os comandos para Windows/PowerShell, está no [README](../../README.md#como-rodar-windows--powershell).
Em resumo:

```powershell
Copy-Item .env.example .env            # e troque os valores de exemplo
docker compose up -d                   # PostgreSQL em 127.0.0.1:5433
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

`docker compose stop` para o banco mantendo os dados. **Não use `docker compose down -v`**: o `-v` apaga
o volume `postgres_data`, ou seja, o banco inteiro.

> As variáveis `POSTGRES_DB`, `POSTGRES_USER` e `POSTGRES_PASSWORD` só são aplicadas pelo container na
> **primeira** criação do volume. Mudar a senha no `.env` depois disso não muda a senha no banco (veja
> [Troca de senhas](#troca-de-senhas)).

A forma de hospedar a produção (servidor de aplicação, proxy HTTPS, banco gerenciado) ainda não foi
definida (RNF-SEG-02, RNF-SEG-16). Quando for, registre aqui o serviço, como reiniciar a aplicação e onde
ficam os logs.

## Atualizar o código

Em produção, só atualize a partir da `main` (versão estável; veja `docs/workflow_git.md`). Antes de
tudo, **faça um backup** ([backup.md](backup.md)): migrations alteram o banco.

```powershell
git status                                   # não deve haver alterações locais no servidor
git fetch
git switch main
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate --plan   # mostra o que será aplicado, sem aplicar
.\.venv\Scripts\python.exe manage.py migrate
```

Só em produção (`DJANGO_DEBUG=False`):

```powershell
.\.venv\Scripts\python.exe manage.py collectstatic --noinput   # atualiza staticfiles/
.\.venv\Scripts\python.exe manage.py check --deploy
```

Depois reinicie o servidor da aplicação e confira o login e uma tela de cada área. Em Linux/bash troque
`.\.venv\Scripts\python.exe` por `.venv/bin/python`.

O `check --deploy` deve sair **sem erros**. Os avisos `security.W005` (HSTS sem subdomínios) e
`security.W021` (sem preload) são esperados: é uma decisão documentada em `config/settings.py`. Qualquer
outro aviso deve ser corrigido antes de publicar; por exemplo, `security.W009` indica `DJANGO_SECRET_KEY`
curta ou de exemplo.

Se algo der errado depois de `migrate`, volte o código ao commit anterior (`git switch --detach <commit>`)
e restaure o backup feito antes da atualização. Não tente desfazer migrations à mão.

## Criar o primeiro administrador

Num banco novo não há contas. Crie a primeira conta administrativa pelo terminal:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

O comando pede usuário, e-mail e senha (mínimo de 10 caracteres, não pode ser comum, só numérica ou
parecida com o usuário). Entre no sistema com essa conta e cadastre as demais em **Gestão de Colaboradores**
(`/colaboradores/`), escolhendo o perfil **Equipe** (usuário comum) ou **Administrador** (também administra as
contas). Os grupos e suas permissões são criados automaticamente a cada `migrate`; para recriá-los à mão, use
`manage.py garantir_perfis`. Cada conta precisa de um e-mail próprio (é por ele que chega o "esqueci minha senha").

Outros comandos úteis:

```powershell
.\.venv\Scripts\python.exe manage.py changepassword nome_do_usuario   # redefine a senha de uma conta
.\.venv\Scripts\python.exe manage.py showmigrations                   # migrations aplicadas
```

Para tirar o acesso de alguém, **desative a conta** em `/colaboradores/` → a conta → "Situação" em vez de
apagá-la: a auditoria aponta para quem fez cada alteração, e a desativação encerra as sessões abertas daquela conta.

## Variáveis do `.env`

O `.env` fica na raiz do projeto, **nunca vai para o Git** (está no `.gitignore`) e é guardado à parte
([backup.md](backup.md#o-que-precisa-ser-copiado)). O modelo comentado é o `.env.example`.

| Variável | Para que serve | Observação |
|---|---|---|
| `DJANGO_SECRET_KEY` | Chave que assina sessões, tokens de redefinição de senha e CSRF. | **Obrigatória.** Única por ambiente, secreta. Gere com o comando do README. |
| `DJANGO_DEBUG` | `True` = desenvolvimento; `False` = produção. | Em produção **sempre** `False`: com `True` erros mostram detalhes internos. Com `False` passam a valer HTTPS obrigatório, cookies seguros e HSTS. |
| `DJANGO_ALLOWED_HOSTS` | Domínios aceitos pelo Django, separados por vírgula. | Em produção, o domínio do sistema. Padrão: `localhost,127.0.0.1`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origens confiáveis para formulários, com esquema. | Em produção: `https://seu-dominio`. |
| `DJANGO_SESSION_COOKIE_AGE` | Duração máxima da sessão, em segundos. | Padrão 28800 (8 horas). A sessão também acaba ao fechar o navegador. |
| `DJANGO_SECURE_HSTS_SECONDS` | Tempo em que o navegador só aceita HTTPS. | Só com `DEBUG=False`. Comece com 3600 e suba aos poucos. |
| `DJANGO_SECURE_PROXY_SSL_HEADER` | Cabeçalho que indica HTTPS atrás de proxy. | Use `HTTP_X_FORWARDED_PROTO` só se houver proxy reverso que termina o HTTPS; sem proxy, vazio. |
| `DJANGO_ADMINS` | E-mails que recebem aviso de erro 500. | Só com `DEBUG=False`. Use e-mail institucional. |
| `DJANGO_EMAIL_BACKEND` | Como o sistema envia e-mail. | Vazio = console em desenvolvimento e SMTP em produção. |
| `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT` | Servidor SMTP e porta. | Padrão `localhost` e `587`. |
| `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD` | Conta e senha do SMTP. | Senha secreta; conta institucional. |
| `DJANGO_EMAIL_USE_TLS` | Criptografia no envio de e-mail. | Padrão `True`. |
| `DJANGO_DEFAULT_FROM_EMAIL` | Remetente dos e-mails do sistema. | |
| `DJANGO_SERVER_EMAIL` | Remetente dos avisos de erro. | Se vazio, usa `DJANGO_DEFAULT_FROM_EMAIL`. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Banco, usuário e senha do PostgreSQL. | **Obrigatórias.** Usadas pelo Django e, na primeira criação, pelo `docker-compose.yaml`. |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Endereço e porta do banco. | Padrão `127.0.0.1` e `5433` (porta publicada pelo Docker). Em produção, os do servidor do banco. |

Sem uma variável obrigatória o Django não inicia (`KeyError`). Variáveis definidas no ambiente do sistema
têm prioridade sobre o `.env`.

## Integração contínua (CI)

O GitHub Actions roda `.github/workflows/django.yml` (**nci-CI**) em todo pull request e push para `main`
e `develop`:

- **Lint (ruff):** bloqueia erros críticos (sintaxe, nomes indefinidos); as regras completas e a
  formatação são só informativas.
- **Testes (Django + PostgreSQL 17.11):** `manage.py check`, migrations em dia com os models
  (`makemigrations --check`), migrations aplicando do zero, `check --deploy` com `DEBUG=False` (falha só
  em erro) e os testes com cobertura. O relatório de cobertura aparece no resumo da execução.

O CI usa só valores fictícios e uma SECRET_KEY descartável; nenhum segredo real é necessário.

Onde ver: na aba **Actions** do repositório no GitHub, ou nos *checks* de cada pull request. Pelo
terminal, com o GitHub CLI: `gh run list --workflow django.yml` e `gh run view <id> --log-failed`.

Os mesmos testes rodam localmente (com o container no ar): veja "Testes e verificações" no README.

## Logs

- **Aplicação:** erros de requisição e de segurança (CSRF, host inválido etc.) vão para a **saída do
  console** do processo do Django (`django.request` e `django.security`, nível WARNING ou acima). Em
  desenvolvimento aparecem no terminal do `runserver`; em produção, onde o servidor de aplicação ou o
  serviço do sistema guardar a saída (ex.: `journalctl -u <servico>` no Linux, ou o painel de logs do
  provedor). Não há arquivo de log próprio.
- **Erros 500 em produção:** também são enviados por e-mail para `DJANGO_ADMINS` (exige o SMTP
  configurado).
- **Banco de dados:** `docker logs nci-postgres` (use `--since 1h` ou `--tail 100` para limitar).
- **Quem alterou o quê:** não é log, fica no banco. Alterações em cadastros e frequências ficam na
  auditoria do sistema (tabela `core_eventoauditoria`, mostrada no histórico do participante e nas telas
  de atividades), e mudanças de conta ficam no histórico do colaborador em `/colaboradores/`; ações feitas pelo
  `/admin/` ficam no histórico do admin (`django_admin_log`).

Logs podem conter dados pessoais (ex.: endereços de páginas): trate-os com o mesmo cuidado dos backups.

## Exportação de dados

Os participantes podem ser exportados em CSV (abre direto no Excel: UTF-8 com BOM e separador `;`), com uma
linha por pessoa: dados do cadastro, data de entrada e a situação social vigente no dia (RNF-SEG-11). Só
contas com a permissão **"Pode exportar participantes"** exportam; o grupo Administrador já a tem, a Equipe
não. Pela tela: botão **Exportar CSV** na lista de participantes. Pelo terminal, sem depender da interface:

```powershell
.\.venv\Scripts\python.exe manage.py exportar_participantes --usuario nome_do_administrador --saida participantes.csv
```

O comando recusa substituir um arquivo existente (use `--sobrescrever` para isso). Cada exportação, pela tela
ou pelo terminal, fica registrada na auditoria (quem, quando e quantos participantes). Atividades e
frequência ainda não têm exportação própria; para recuperar tudo, use o backup ([backup.md](backup.md)).

> **LGPD:** o arquivo contém dados pessoais sensíveis (raça/cor, identidade de gênero, deficiência, endereço,
> telefones). Guarde-o só em local com acesso restrito, não envie por e-mail ou aplicativo de mensagens sem
> necessidade e **apague-o (inclusive da lixeira e da pasta Downloads) assim que terminar de usar**.

## Restaurar os dados

Procedimento completo, com os comandos de backup, conferência e restauração: [backup.md](backup.md).

## Checklist de transferência para o NCI

Usar na entrega do sistema e sempre que alguém com acesso deixar a equipe. Registre a data e quem fez cada
item.

**Contas institucionais (RNF-SEG-17)**

- [ ] Repositório do código numa organização/conta do NCI no GitHub, com pelo menos duas pessoas do NCI
      como administradoras.
- [ ] Hospedagem, banco de dados e domínio em contas do NCI, não de desenvolvedores; contratação paga só
      com autorização prévia da gestora e nota fiscal (RN-SEG-01).
- [ ] E-mail de envio (SMTP) e e-mails de `DJANGO_ADMINS` institucionais.
- [ ] Local dos backups numa conta do NCI ([backup.md](backup.md#onde-guardar)).
- [ ] Cofre de senhas da instituição com: `.env` de produção, senha do banco, senha da criptografia dos
      backups e acessos das contas acima.

**Quem tem acesso**

- [ ] Lista nominal de quem acessa: servidor, banco, hospedagem, GitHub, cofre de senhas, backups e
      contas de administrador do sistema.
- [ ] Desenvolvedores e voluntários do projeto acadêmico removidos (ou rebaixados) em cada serviço acima.
- [ ] Contas do sistema de quem saiu desativadas em `/colaboradores/` (não apagadas).
- [ ] Pelo menos duas pessoas do NCI com conta de administrador, para não haver ponto único de falha.

**Troca de segredos (depois que os desenvolvedores perderem o acesso)**

- [ ] Nova `DJANGO_SECRET_KEY` no `.env` de produção (comando no README) e reinício da aplicação.
      Efeito esperado: todos precisam entrar de novo e links de redefinição de senha antigos deixam de
      valer. As senhas dos usuários **não** são afetadas.
- [ ] Nova senha do usuário do banco (veja abaixo) e `POSTGRES_PASSWORD` atualizada no `.env`.
- [ ] Senhas das contas de administrador do sistema trocadas (`manage.py changepassword` ou em `/colaboradores/`).
- [ ] Senha do SMTP, das contas de hospedagem, domínio e GitHub trocadas; autenticação em dois fatores
      ligada onde houver.
- [ ] Nova senha para criptografar os backups a partir de agora.

**Funcionamento**

- [ ] Backup feito, conferido e **restaurado com sucesso** num banco de teste pela equipe do NCI
      ([teste de restauração](backup.md#teste-de-restauração-periódico)).
- [ ] Atualização feita pela equipe do NCI seguindo [Atualizar o código](#atualizar-o-código), com
      `check --deploy` sem erros.
- [ ] A equipe sabe onde ver o CI e os logs.

### Troca de senhas

**Usuário do banco no Docker.** A senha é trocada dentro do PostgreSQL; o comando `\password` pede a
senha nova sem mostrá-la e sem gravá-la no histórico:

```powershell
docker exec -it nci-postgres psql -U nci_dev -d nci_dev
```

```text
\password nci_dev
\q
```

(use o usuário e o banco do seu `.env`). Depois atualize `POSTGRES_PASSWORD` no `.env` e reinicie o
Django. Não é preciso recriar o container. No banco hospedado, use a opção de troca de senha do painel do
provedor, ou o mesmo `\password` conectado pelo `psql`.

**Contas do sistema:** em `/colaboradores/` → a conta → "Nova senha" (por um administrador), pelo "Esqueci minha
senha" da tela de entrada, ou `manage.py changepassword nome_do_usuario` no servidor.
