"""Configuração do banco a partir de DATABASE_URL (hospedagem) ou de POSTGRES_* (Docker local).

Em produção/teste hospedado o provedor entrega um único endereço, por exemplo
`postgresql://usuario:senha@host:5432/banco?sslmode=require`. Localmente continuam valendo as variáveis
`POSTGRES_*` do `.env` (docker-compose). Sem dependência extra: só a biblioteca padrão.
"""

from urllib.parse import parse_qsl, unquote, urlsplit

ESQUEMAS = {"postgres", "postgresql"}


def banco_de_url(url, *, conn_max_age=0):
    """Converte DATABASE_URL no dicionário de `DATABASES['default']` do Django."""
    partes = urlsplit(url)
    if partes.scheme not in ESQUEMAS:
        raise ValueError(f"DATABASE_URL precisa começar com postgres:// ou postgresql://, não {partes.scheme}://.")
    nome = unquote(partes.path.lstrip("/"))
    if not nome:
        raise ValueError("DATABASE_URL sem o nome do banco.")
    banco = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": nome,
        "USER": unquote(partes.username or ""),
        "PASSWORD": unquote(partes.password or ""),
        "HOST": partes.hostname or "",
        "PORT": str(partes.port or 5432),
        # Reaproveita conexões entre requisições (0 = abre e fecha a cada requisição).
        "CONN_MAX_AGE": conn_max_age,
        "CONN_HEALTH_CHECKS": conn_max_age > 0,
    }
    # Parâmetros da URL (sslmode, channel_binding...) vão para o psycopg como OPTIONS.
    opcoes = dict(parse_qsl(partes.query))
    if opcoes:
        banco["OPTIONS"] = opcoes
    return banco


def banco_local(ambiente):
    """Banco do docker-compose local, pelas variáveis POSTGRES_* (comportamento de antes)."""
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": ambiente["POSTGRES_DB"],
        "USER": ambiente["POSTGRES_USER"],
        "PASSWORD": ambiente["POSTGRES_PASSWORD"],
        "HOST": ambiente.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": ambiente.get("POSTGRES_PORT", "5433"),
    }
