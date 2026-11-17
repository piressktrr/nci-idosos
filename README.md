# NCI Idade Dourada

Sistema web em Django para o NCI: cadastro de participantes e gestão de atividades (inscrição, chamada e
frequência), com PostgreSQL.

## Requisitos

- Python 3.14
- Docker (com Docker Compose) para o PostgreSQL 17 de desenvolvimento

As bibliotecas Python estão fixadas em `requirements.txt`. O Django roda fora do container, pela `.venv`;
só o banco roda no Docker.

## Como rodar (Windows / PowerShell)

1. Crie o `.env` a partir do modelo e troque os valores de exemplo:

   ```powershell
   Copy-Item .env.example .env
   ```

   Para gerar a `DJANGO_SECRET_KEY` (depois do passo 3):

   ```powershell
   .\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

2. Suba o PostgreSQL (lê `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_PORT` do `.env`):

   ```powershell
   docker compose up -d
   ```

   O banco fica acessível só nesta máquina, em `127.0.0.1:5433`. Use `docker compose stop` para parar
   (os dados ficam no volume `postgres_data`).

3. Crie o ambiente virtual e instale as dependências:

   ```powershell
   py -3.14 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Aplique as migrations e crie sua conta administrativa:

   ```powershell
   .\.venv\Scripts\python.exe manage.py migrate
   .\.venv\Scripts\python.exe manage.py createsuperuser
   ```

5. Rode o servidor de desenvolvimento:

   ```powershell
   .\.venv\Scripts\python.exe manage.py runserver
   ```

   Acesse <http://localhost:8000> e entre em <http://localhost:8000/entrar/>.

> **Use sempre o Python da `.venv`** (`.\.venv\Scripts\python.exe`). Com o Python do sistema, o Django
> não encontra as dependências e falha com `ModuleNotFoundError: No module named 'dotenv'`.

O projeto usa o usuário padrão do Django (`auth.User`). Senhas precisam ter pelo menos 10 caracteres.

## Perfis de acesso

Há dois grupos, criados automaticamente a cada `migrate`:

- **Equipe** (usuário comum): consulta, cadastra e corrige participantes.
- **Administrador**: tudo de participantes e a administração de contas e grupos (ver, criar e alterar;
  contas são desativadas, não excluídas).

Para conceder um perfil, inclua a pessoa no grupo (pelo admin do Django, por enquanto; para abrir o admin
a conta também precisa de "membro da equipe"/`is_staff`). Conta sem grupo não acessa nenhum módulo.
Para recriar os grupos ou repor permissões mínimas removidas (por exemplo, em produção), rode:

```powershell
.\.venv\Scripts\python.exe manage.py garantir_perfis
```

O comando é idempotente e não remove permissões acrescentadas à mão aos grupos.

## Testes e verificações

Os testes rodam no PostgreSQL do Docker (o Django cria e apaga um banco de teste), então o container
precisa estar no ar.

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
```

## Produção

Com `DJANGO_DEBUG=False` passam a valer HTTPS obrigatório, cookies seguros e HSTS. Antes de publicar,
preencha no `.env` `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, as variáveis de e-mail e
`DJANGO_ADMINS` (veja `.env.example`), rode `manage.py collectstatic` (gera `staticfiles/`) e confira:

```powershell
.\.venv\Scripts\python.exe manage.py check --deploy
```
