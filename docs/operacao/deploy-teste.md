# Deploy do ambiente de TESTE no Render

Ambiente para o NCI experimentar o sistema. **Somente dados fictícios (RN-SEG-02):** o servidor fica fora do
Brasil e o plano gratuito não tem backup. A produção com dados reais será em outra hospedagem, combinada com o NCI.

## Como funciona

```
navegador ──HTTPS──> Render: serviço web (gunicorn + Django + whitenoise) ──rede interna──> Render: PostgreSQL
                         ▲
                 GitHub: cada merge na main publica uma nova versão
```

- **`render.yaml`** (raiz do repositório) descreve tudo: o banco `nci-idosos-db` e o serviço web `nci-idosos`,
  ambos no plano gratuito, na região Virginia.
- **Build:** `pip install -r requirements.txt` e `collectstatic` (copia `static/` para `staticfiles/`, com hash no
  nome dos arquivos e versões comprimidas).
- **Partida:** `migrate` (cria/atualiza as tabelas e os grupos Equipe e Administrador) e depois o `gunicorn`.
- **Banco:** o Render entrega o endereço interno do banco na variável `DATABASE_URL`, lida por `config/banco.py`.
  Localmente nada muda: sem `DATABASE_URL`, o sistema usa as `POSTGRES_*` do `.env` (Docker).
- **Arquivos estáticos:** o `whitenoise` serve CSS, JS, fontes e imagens pelo próprio Django.

## Variáveis de ambiente (definidas no `render.yaml`)

| Variável | Valor | Para quê |
|---|---|---|
| `PYTHON_VERSION` | `3.14.6` | Versão do Python no Render |
| `DATABASE_URL` | vem do banco `nci-idosos-db` | Conexão com o PostgreSQL |
| `DJANGO_DB_CONN_MAX_AGE` | `60` | Reaproveita conexões por 60 s |
| `DJANGO_SECRET_KEY` | gerada pelo Render | Chave de assinatura de sessões e tokens; nunca copiar para outro lugar |
| `DJANGO_DEBUG` | `False` | Liga o HTTPS obrigatório, HSTS e cookies seguros |
| `DJANGO_SECURE_PROXY_SSL_HEADER` | `HTTP_X_FORWARDED_PROTO` | O Render recebe o HTTPS e avisa o Django por esse cabeçalho |
| `DJANGO_STATIC_MANIFEST` | `True` | Usa os arquivos com hash e comprimidos do `collectstatic` |
| `DJANGO_EMAIL_BACKEND` | console | Sem serviço de e-mail por enquanto: e-mails só aparecem no log |
| `DJANGO_SESSION_COOKIE_AGE` | `28800` | Sessão de 8 horas |
| `RENDER_EXTERNAL_HOSTNAME` | definida pelo Render | O domínio `*.onrender.com` entra sozinho em `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` |

## Passo a passo (primeira vez)

1. **Conta no Render:** crie em <https://render.com> e conecte o GitHub, dando acesso ao repositório
   `piressktrr/nci-idosos`.
2. **Blueprint:** no painel, **New → Blueprint**, escolha o repositório e a branch `main`. O Render lê o
   `render.yaml` e mostra o que vai criar (o banco e o serviço). Confirme.
3. **Aguarde o primeiro deploy.** Acompanhe em **nci-idosos → Logs**. No fim aparece o endereço,
   por exemplo `https://nci-idosos.onrender.com` (se o nome estiver ocupado, o Render acrescenta um sufixo).
4. **Primeiro administrador.** O plano gratuito não tem terminal no servidor; rode no seu computador, apontando
   para o banco do Render:
   - No painel do banco **nci-idosos-db → Connect**, copie a **External Database URL**.
   - No PowerShell, dentro da pasta `nci-idosos` (a URL fica só nesta janela do terminal; não grave em arquivo):
     ```powershell
     $env:DATABASE_URL = "<cole aqui a External Database URL>?sslmode=require"
     .\.venv\Scripts\python.exe manage.py createsuperuser
     Remove-Item Env:DATABASE_URL
     ```
   - Entre em `https://<seu-endereço>/entrar/` e cadastre as demais contas em **Gestão de Colaboradores**.
5. **Dados de demonstração (fictícios):** com a mesma `DATABASE_URL` na sessão, rode o comando de carga fictícia
   do FMR (`carregar_fmr_teste`) quando ele estiver na `main`.

## Publicar uma nova versão

Mescle a `develop` na `main` (PR). O Render faz o build e a partida sozinho; as migrations rodam na partida.
Se o build falhar, a versão anterior continua no ar e o erro aparece em **Logs**.

## Limitações do plano gratuito

- **O banco expira 30 dias após a criação.** Antes disso, ou mude a `DATABASE_URL` para outro banco (Neon, por
  exemplo) ou apague e recrie o banco pelo Blueprint e refaça os passos 4 e 5. Os dados de teste se perdem.
- Sem backup do banco.
- O serviço "dorme" após cerca de 15 minutos sem acesso; o próximo acesso demora até 1 minuto.
- Sem "esqueci minha senha" até configurar um serviço de e-mail: um administrador define a nova senha em
  `/colaboradores/`.

## Conferir depois do deploy

- `https://<endereço>/entrar/` abre com o visual completo (CSS e fontes carregados).
- Login do administrador, lista de participantes, cadastro, Gestão de Colaboradores e FMR.
- `http://` redireciona para `https://`.
