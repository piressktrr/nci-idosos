# Cópia de segurança e restauração (RNF-SEG-10)

Procedimento para copiar e recuperar os dados do NCI Idade Dourada, de modo que a instituição continue
operando depois do projeto acadêmico (RNF-SEG-10) e consiga recuperar seus dados sem depender dos
desenvolvedores (RNF-SEG-11). A manutenção geral do sistema está em [manutencao.md](manutencao.md).

> **Os backups contêm dados pessoais sensíveis de idosos** (LGPD). Leia a seção
> [Cuidados com a LGPD](#cuidados-com-a-lgpd) antes de copiar qualquer arquivo para fora do servidor.

## O que precisa ser copiado

| Item | Onde está | Como copiar | Observação |
|---|---|---|---|
| **Banco de dados** (participantes, atividades, frequência, contas, auditoria) | PostgreSQL 17 (container `nci-postgres` em desenvolvimento; servidor do banco em produção) | `pg_dump`, descrito abaixo | É o único item que não pode ser recriado. |
| **Arquivo `.env`** (SECRET_KEY, senha do banco, e-mail) | Raiz do projeto no servidor | Guardar **à parte**, num cofre de senhas ou pasta restrita da conta institucional | **Nunca** no Git, nunca junto do dump no mesmo arquivo sem criptografia. |
| Código-fonte | Repositório Git (GitHub) | Já está versionado | O repositório deve pertencer à conta institucional (RNF-SEG-17). |
| Arquivos estáticos (`staticfiles/`) | Gerados por `collectstatic` | Não precisa copiar | São recriados a partir de `static/` e dos apps. |

Hoje o sistema **não recebe arquivos enviados por usuários** (não há `FileField`/`ImageField` nem
`MEDIA_ROOT`). Se isso mudar, a pasta de mídia passa a fazer parte do backup.

O volume Docker `postgres_data` guarda os arquivos internos do PostgreSQL. **Não use cópia do volume como
backup**: copiar os arquivos com o banco ligado gera cópia inconsistente. Use `pg_dump`.

## Backup no ambiente com Docker (`nci-postgres`)

O `pg_dump` roda **dentro** do container, com o usuário e o banco que o container recebeu do `.env`
(`$POSTGRES_USER` e `$POSTGRES_DB` são lidos dentro do container, por isso vão entre aspas simples). O
formato `-Fc` (custom) é compactado e é o que o `pg_restore` lê. Grave o arquivo **fora da pasta do
repositório**, para ele nunca ser commitado por engano.

**PowerShell (Windows):**

```powershell
$destino = 'D:\Backups\nci'   # pasta fora do repositório, com acesso restrito
New-Item -ItemType Directory -Force $destino | Out-Null
$arquivo = Join-Path $destino "nci_$(Get-Date -Format yyyy-MM-dd_HHmm).dump"

docker exec nci-postgres sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/backup.dump'
docker cp nci-postgres:/tmp/backup.dump $arquivo
docker exec nci-postgres sh -c 'rm -f /tmp/backup.dump'
```

> **No PowerShell, não use `>` para gravar o dump** (`docker exec ... pg_dump -Fc > arquivo.dump`). O
> Windows PowerShell 5.1 trata a saída como texto e corrompe o arquivo binário: o `pg_restore` responde
> `input file does not appear to be a valid archive`. Por isso o dump é gravado dentro do container
> (`-f`) e copiado com `docker cp`.
>
> Também evite aspas duplas dentro do `sh -c '...'` no PowerShell 5.1: ele as remove ao chamar o
> `docker`. Os comandos deste documento já foram escritos sem elas.

**bash (Linux, macOS ou Git Bash):**

```bash
destino="$HOME/backups/nci"   # pasta fora do repositório, com acesso restrito
mkdir -p "$destino" && chmod 700 "$destino"
arquivo="$destino/nci_$(date +%Y-%m-%d_%H%M).dump"

docker exec nci-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$arquivo"
```

No bash o redirecionamento `>` é seguro para arquivos binários.

> **Git Bash:** ele converte argumentos que parecem caminhos Unix (`/tmp/...`) em caminhos do Windows.
> Mantenha caminhos de dentro do container dentro do `sh -c '...'`, como acima, ou rode
> `export MSYS_NO_PATHCONV=1` antes.

## Conferir se o backup abre

Um backup só vale se abrir. Logo depois de gerar, liste o conteúdo com `pg_restore --list` (não altera
nenhum banco):

**PowerShell:**

```powershell
docker cp $arquivo nci-postgres:/tmp/restaurar.dump
docker exec nci-postgres sh -c 'pg_restore --list /tmp/restaurar.dump'
```

**bash:**

```bash
docker exec -i nci-postgres pg_restore --list < "$arquivo"
```

O cabeçalho mostra a data, o banco de origem (`dbname`) e a versão do PostgreSQL. Confira também que há
uma linha `TABLE DATA` por tabela (hoje são 23 tabelas). Se aparecer `input file does not appear to be a
valid archive`, o arquivo está corrompido ou incompleto: gere outro.

## Restauração

A restauração **substitui** os dados do banco de destino. Antes de restaurar em produção:

1. Pare a aplicação (servidor do Django), para ninguém gravar durante a restauração.
2. Faça um backup do estado atual, mesmo que pareça ruim. Ele permite desfazer a restauração.
3. Confira com `pg_restore --list` que o arquivo escolhido é o certo (data e `dbname`).

A restauração é feita num **banco vazio**. As opções `--clean --if-exists` apagam antes cada objeto que
será recriado, o que torna o comando seguro também se sobrar algo no banco; `--no-owner` faz os objetos
pertencerem ao usuário que restaura (útil quando o servidor novo tem outro nome de usuário).

### Restaurar o banco principal (Docker)

**PowerShell** (supondo o `.dump` já copiado para `/tmp/restaurar.dump`, como na seção anterior):

```powershell
# 1. Recria o banco vazio (apaga o atual: faça o backup do passo 2 antes!)
docker exec nci-postgres sh -c 'dropdb -U $POSTGRES_USER --if-exists $POSTGRES_DB'
docker exec nci-postgres sh -c 'createdb -U $POSTGRES_USER -O $POSTGRES_USER $POSTGRES_DB'

# 2. Restaura
docker exec nci-postgres sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/restaurar.dump'
docker exec nci-postgres sh -c 'rm -f /tmp/restaurar.dump'
```

**bash:**

```bash
docker exec nci-postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"'
docker exec nci-postgres sh -c 'createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"'
docker exec -i nci-postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$arquivo"
```

Se o `dropdb` recusar por haver conexões abertas, confira se o Django parou. Em último caso, use
`dropdb --force`.

Depois de restaurar, confira com o Python da `.venv`:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --check   # sai sem erro se o banco está com todas as migrations
.\.venv\Scripts\python.exe manage.py check
```

Se o backup for de uma versão anterior do código, `migrate --check` acusa migrations pendentes: rode
`manage.py migrate` para levar o banco à versão atual. Por fim, suba a aplicação, entre com uma conta de
administrador e abra a lista de participantes.

## Teste de restauração periódico

Um backup nunca restaurado não é garantia. Periodicamente (sugestão: uma vez por mês e sempre que o
sistema for atualizado), restaure o backup mais recente num **banco novo de teste**, sem tocar no banco
em uso:

**PowerShell:**

```powershell
docker cp $arquivo nci-postgres:/tmp/restaurar.dump
docker exec nci-postgres sh -c 'createdb -U $POSTGRES_USER nci_restore_teste'
docker exec nci-postgres sh -c 'pg_restore -U $POSTGRES_USER -d nci_restore_teste --clean --if-exists --no-owner /tmp/restaurar.dump'
```

**bash:**

```bash
docker exec nci-postgres sh -c 'createdb -U "$POSTGRES_USER" nci_restore_teste'
docker exec -i nci-postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d nci_restore_teste --clean --if-exists --no-owner' < "$arquivo"
```

Compare a contagem de linhas por tabela entre o banco em uso e o restaurado (as duas listas devem bater,
salvo o que foi gravado depois do backup):

```powershell
$contagem = @'
SELECT table_name,
       (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text::int
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
'@
$contagem | docker exec -i nci-postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At'
$contagem | docker exec -i nci-postgres sh -c 'psql -U $POSTGRES_USER -d nci_restore_teste -At'
```

No bash, passe a mesma consulta por *heredoc* (`docker exec -i ... psql ... <<'SQL'` ... `SQL`).

Confira também que o Django reconhece o banco restaurado, apontando-o só para este comando (a variável do
ambiente tem prioridade sobre o `.env`):

```powershell
$env:POSTGRES_DB = 'nci_restore_teste'
.\.venv\Scripts\python.exe manage.py migrate --check
Remove-Item Env:POSTGRES_DB
```

```bash
POSTGRES_DB=nci_restore_teste .venv/bin/python manage.py migrate --check
```

Ao terminar, apague o banco de teste e a cópia temporária:

```powershell
docker exec nci-postgres sh -c 'dropdb -U $POSTGRES_USER nci_restore_teste; rm -f /tmp/restaurar.dump'
```

Anote a data, o arquivo usado e o resultado (ex.: num registro de operação do NCI). Se algo falhar,
investigue antes de confiar nos backups seguintes.

## Servidor hospedado (sem Docker)

Em produção o banco costuma estar num serviço gerenciado ou noutro servidor. Os comandos são os mesmos, com
a conexão informada por variáveis de ambiente do PostgreSQL (`PGHOST`, `PGPORT`, `PGUSER`,
`PGDATABASE`). **Não coloque a senha na linha de comando** (ela fica no histórico e na lista de
processos). Use uma das opções:

- **Arquivo de senhas** (preferível em rotina agendada): `~/.pgpass` no Linux/macOS (permissão `600`)
  ou `%APPDATA%\postgresql\pgpass.conf` no Windows, com uma linha
  `servidor:porta:banco:usuario:senha`.
- **`PGPASSWORD` já definido no ambiente** pelo agendador ou cofre de segredos do serviço de hospedagem,
  nunca digitado no comando.

A opção `-w` faz o `pg_dump` falhar em vez de pedir senha, o que evita uma rotina agendada travada. Use o
`pg_dump` da **mesma versão principal do servidor ou mais nova** (hoje, 17). Se o provedor exigir
conexão criptografada, defina também `PGSSLMODE=require`.

**bash:**

```bash
export PGHOST=endereco-do-banco PGPORT=5432 PGUSER=usuario_nci PGDATABASE=nci_prod
# senha: ~/.pgpass ou PGPASSWORD fornecido pelo ambiente
pg_dump -Fc -w -f "$HOME/backups/nci/nci_$(date +%Y-%m-%d_%H%M).dump"
pg_restore --list "$HOME/backups/nci/nci_AAAA-MM-DD_HHMM.dump"
```

**PowerShell** (com as ferramentas cliente do PostgreSQL 17 instaladas):

```powershell
$env:PGHOST = 'endereco-do-banco'; $env:PGPORT = '5432'; $env:PGUSER = 'usuario_nci'; $env:PGDATABASE = 'nci_prod'
# senha: %APPDATA%\postgresql\pgpass.conf
pg_dump -Fc -w -f "D:\Backups\nci\nci_$(Get-Date -Format yyyy-MM-dd_HHmm).dump"
```

Aqui o `-f` também evita o problema do `>` no PowerShell.

Sem as ferramentas instaladas, use a imagem do PostgreSQL como cliente. O `-e VARIAVEL` sem valor repassa
a variável do ambiente atual, sem expor a senha no comando:

```bash
docker run --rm -e PGHOST -e PGPORT -e PGUSER -e PGDATABASE -e PGPASSWORD -e PGSSLMODE \
  -v "$HOME/backups/nci:/backup" postgres:17.11-alpine \
  sh -c 'pg_dump -Fc -w -f /backup/nci_$(date +%Y-%m-%d_%H%M).dump'
```

Para restaurar no servidor hospedado: crie um banco vazio pelo painel do provedor (ou `createdb`) e rode
`pg_restore -w -d nome_do_banco --clean --if-exists --no-owner arquivo.dump`, com as mesmas variáveis.
Depois rode `manage.py migrate --check` com o `.env` do servidor.

## Frequência e retenção (sugestão)

> **Sugestão a confirmar com o NCI.** A política de retenção e eliminação de dados (RNF-SEG-09, questão
> Q9) ainda está em aberto; os prazos abaixo são só um ponto de partida e devem ser ajustados quando ela
> for definida.

| Tipo | Quando | Manter por |
|---|---|---|
| Diário | Todo dia, fora do horário de atendimento | 7 dias |
| Semanal | Um por semana (ex.: sexta-feira) | 5 semanas |
| Mensal | Após o fechamento do mês (entrega do FMR) | 12 meses |
| Antes de mudanças | Antes de toda atualização do sistema ou restauração | Até a próxima mudança confirmada |

Backups antigos devem ser **eliminados de fato** ao fim do prazo, inclusive das cópias externas: manter
dados pessoais além do necessário também é problema (RNF-SEG-09). A rotina pode ser agendada no
Agendador de Tarefas do Windows ou no `cron`/serviço de hospedagem, com os comandos acima.

## Onde guardar

- **Fora do servidor** do sistema: um backup na mesma máquina se perde junto com ela.
- Numa **conta institucional do NCI** (armazenamento em nuvem ou unidade da instituição), nunca na conta
  pessoal de um desenvolvedor ou voluntário (RNF-SEG-17).
- Respeitando as restrições de local de armazenamento definidas na implantação (RNF-SEG-18).
- O `.env` fica num lugar **diferente** do dump (cofre de senhas da instituição), com acesso ainda mais
  restrito.
- Nunca dentro da pasta do repositório: o `.gitignore` não bloqueia arquivos `.dump`.

## Cuidados com a LGPD

O dump é uma cópia completa do banco: nomes, datas de nascimento, contatos, situação social, frequência e
o histórico de auditoria dos participantes.

- **Acesso restrito:** só as pessoas responsáveis pela operação, nominalmente definidas pelo NCI.
- **Criptografado** fora do servidor. Exemplos (a senha é pedida na hora, não fica no comando):
  - Windows, com 7-Zip: `& 'C:\Program Files\7-Zip\7z.exe' a -t7z -mhe=on -p arquivo.7z arquivo.dump`
  - bash, com GnuPG: `gpg --symmetric --cipher-algo AES256 arquivo.dump` (gera `arquivo.dump.gpg`)

  Depois de criptografar, apague o `.dump` em texto aberto. Guarde a senha da criptografia no cofre da
  instituição: sem ela o backup não pode ser restaurado.
- **Nunca** use um backup de produção para desenvolvimento ou testes (RNF-SEG-13, RN-SEG-02). Teste de
  restauração com dados reais só no ambiente de produção ou num ambiente igualmente protegido, e apague o
  banco de teste ao terminar.
- Não envie backups por e-mail, mensageiro ou pendrive pessoal.

## O que já foi verificado

Em 17/11/2026, no container de desenvolvimento (`nci-postgres`, PostgreSQL 17.11, dados fictícios):

- `pg_dump -Fc` dentro do container + `docker cp` (PowerShell) e `pg_dump -Fc > arquivo` (Git Bash):
  ambos geraram arquivos válidos.
- `docker exec ... pg_dump -Fc > arquivo` no **PowerShell 5.1 gerou arquivo corrompido** (motivo do
  aviso acima).
- `pg_restore --list`: 23 tabelas e 23 blocos `TABLE DATA`.
- Restauração com `--clean --if-exists --no-owner` num banco novo (`nci_restore_teste`), vazio e já
  populado: sem erros; contagem de tabelas, migrations e linhas igual à origem; `manage.py migrate
  --check` e `manage.py check` sem erros apontando para o banco restaurado. O banco de teste foi apagado.
- Conexão por TCP com autenticação por senha: sem senha falha (`no password supplied`); com
  `PGPASSWORD` herdado do ambiente e com arquivo `.pgpass` (permissão `600`) funciona; o mesmo com
  `docker run postgres:17` como cliente.

**Ainda não foi feita uma restauração real** no ambiente de produção (que ainda não existe). Isso precisa
ser executado e registrado na implantação para considerar o RNF-SEG-10 concluído.
