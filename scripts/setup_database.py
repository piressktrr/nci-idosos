"""Inicializa somente o PostgreSQL local de desenvolvimento no Windows."""

import os
from pathlib import Path
import secrets
import subprocess

from dotenv import dotenv_values
import psycopg
from psycopg import sql


def main():
    root = Path(__file__).resolve().parents[1]
    local_root = Path(os.environ["LOCALAPPDATA"]) / "NCI" / "PostgreSQL17"
    bin_dir = local_root / "pgsql" / "bin"
    data_dir = local_root / "data"
    if not (bin_dir / "initdb.exe").exists():
        raise SystemExit(f"Instale os binários PostgreSQL 17 em {local_root} primeiro.")

    def run(name, *args, check=True, quiet=False):
        return subprocess.run(
            [str(bin_dir / f"{name}.exe"), *map(str, args)],
            check=check,
            stdout=subprocess.DEVNULL if quiet else None,
            stderr=subprocess.DEVNULL if quiet else None,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    env_file = root / ".env"
    if not env_file.exists():
        env_file.write_text(
            f"DJANGO_SECRET_KEY={secrets.token_urlsafe(48)}\n"
            "DJANGO_DEBUG=True\nDJANGO_ALLOWED_HOSTS=localhost,127.0.0.1\n"
            "POSTGRES_DB=nci_dev\nPOSTGRES_USER=nci_dev\n"
            f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n"
            "POSTGRES_HOST=127.0.0.1\nPOSTGRES_PORT=5433\n",
            encoding="utf-8",
        )
    config = dotenv_values(env_file)
    if config.get("POSTGRES_HOST") != "127.0.0.1" or config.get("POSTGRES_PORT") != "5433":
        raise SystemExit("Este script aceita apenas o banco local 127.0.0.1:5433.")

    password_file = local_root / "admin-password.txt"
    if not (data_dir / "PG_VERSION").exists():
        if not password_file.exists():
            password_file.write_text(secrets.token_urlsafe(32), encoding="ascii")
        run("initdb", "-D", data_dir, "-U", "nci_local_admin", "--pwfile", password_file,
            "--auth-host=scram-sha-256", "--auth-local=scram-sha-256", "--encoding=UTF8")
        with (data_dir / "postgresql.conf").open("a", encoding="utf-8") as settings:
            settings.write("\nlisten_addresses = '127.0.0.1'\nport = 5433\n")

    if run("pg_ctl", "-D", data_dir, "status", check=False, quiet=True).returncode:
        run("pg_ctl", "-D", data_dir, "-l", local_root / "postgres.log", "-w", "start")

    with psycopg.connect(
        host="127.0.0.1", port=5433, dbname="postgres", user="nci_local_admin",
        password=password_file.read_text(encoding="ascii").strip(), autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            user = config["POSTGRES_USER"]
            database = config["POSTGRES_DB"]
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
            if not cursor.fetchone():
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN CREATEDB PASSWORD {}").format(
                    sql.Identifier(user), sql.Literal(config["POSTGRES_PASSWORD"])))
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            if not cursor.fetchone():
                cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database), sql.Identifier(user)))
    print("PostgreSQL local pronto em 127.0.0.1:5433; credenciais no .env ignorado pelo Git.")


if __name__ == "__main__":
    main()
