# NCI Idade Dourada

Backend Django com PostgreSQL. O app `atividades` e seu modelo `Atividade` ainda são um contrato provisório.

## Desenvolvimento no Windows

Requisitos: Python 3.14 e PostgreSQL 17. As bibliotecas estão fixadas em `requirements.txt`.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Neste computador, os binários PostgreSQL foram instalados em `%LOCALAPPDATA%\NCI\PostgreSQL17\pgsql`. O banco fica em `%LOCALAPPDATA%\NCI\PostgreSQL17\data`, fora do OneDrive.

Em outro computador, baixe os binários Windows x86-64 da versão 17 na [página oficial da EDB](https://www.enterprisedb.com/download-postgresql-binaries) e extraia a pasta `pgsql` para esse mesmo local. Inicialize o banco local:

```powershell
.\.venv\Scripts\python.exe scripts\setup_database.py
```

O script cria `.env` com credenciais aleatórias, sem sobrescrever um arquivo existente. O banco aceita apenas conexões locais na porta 5433. O usuário da aplicação pode criar bancos para os testes Django, mas não é superusuário. `.env` e `.venv` são ignorados pelo Git. `.env.example` documenta as variáveis necessárias para usar outro PostgreSQL.

Após reiniciar o computador, inicie o PostgreSQL antes do Django:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\postgres.ps1 start
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Use `scripts\postgres.ps1 status` para consultar e `scripts\postgres.ps1 stop` para parar o banco. O parâmetro `-ExecutionPolicy Bypass` acima vale somente para aquele processo PowerShell.

O projeto utiliza atualmente o usuário padrão do Django (`auth.User`). As migrations nativas de autenticação, sessões e administração podem ser aplicadas com `migrate`. Perfis e fluxos de acesso específicos do NCI ainda estão em desenvolvimento. Para criar sua conta administrativa local, execute interativamente:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

## Verificações

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations atividades --check --dry-run
```

