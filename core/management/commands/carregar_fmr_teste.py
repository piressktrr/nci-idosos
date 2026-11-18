"""Cenário fictício reproduzível de outubro de 2026 para a branch versao-teste."""
from datetime import date, time, timedelta
from random import Random
from secrets import token_urlsafe

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from atividades.classificacao import classificar_atividade
from atividades.models import Atividade, CategoriaFMR
from atividades.services import (cadastrar_atividade, cadastrar_horario, inscrever_participante,
                                 registrar_aula, registrar_frequencias)
from participantes.categorias import OrigemEncaminhamento, RacaCor
from participantes.models import MotivoDesligamento, Participante
from participantes.movimentacoes import movimentar_participante
from participantes.provedor import ProvedorParticipantes
from participantes.services import cadastrar_participante, registrar_situacao_social


INICIO = date(2026, 10, 1)
BANCO = "nci_fmr_demonstracao"
OFICINAS = (
    ("Direitos e cidadania", "Ações em campanhas"), ("Ateliê de bordado", "Artesanato"),
    ("Dança de salão", "Atividades de arte"), ("Oficina de memória", "Atividades de estimulação"),
    ("Celular no dia a dia", "Atividades de inclusão"), ("Roda de leitura", "Atividades de linguagem"),
    ("Ginástica adaptada", "Atividades esportivas"), ("Passeio cultural", "Atividades externas"),
    ("Cozinha compartilhada", "Atividades que envolvam"), ("Jogos de mesa", "Atividades recreativas"),
    ("Horta sustentável", "Atividades sobre sustentabilidade"), ("Coral do núcleo", "Musicalidade"),
)


def cadastrar_turma(autor, sorteio):
    pessoas = []
    for i in range(120):
        sexo = "M" if i % 5 == 0 else "F"
        nomes = ("Ari", "Bento", "Caio", "Davi") if sexo == "M" else ("Ana", "Célia", "Eva", "Rosa", "Lia")
        origem = OrigemEncaminhamento.values[i % 4]
        # Os primeiros oito vínculos cobrem as quatro faixas de duração nas saídas.
        dias = (80, 235, 650, 1620)[i % 4] if i < 8 else sorteio.randint(90, 1800)
        entrada = INICIO - timedelta(days=dias)
        if i >= 108:
            entrada = INICIO + timedelta(days=i - 108)
        idade = 62 + i % 23
        pessoa = cadastrar_participante(
            usuario=autor, data_entrada=entrada, nome_completo=f"{sorteio.choice(nomes)} Exemplo {i+1:03d}",
            data_nascimento=date(2026-idade, sorteio.randint(1, 9), sorteio.randint(1, 28)),
            sexo=sexo, raca_cor=sorteio.choices(RacaCor.values, weights=(48, 12, 30, 6, 1, 3))[0],
            identidade_genero={7: "agenero", 18: "transgenero", 26: "nao_declarado"}.get(i, "cisgenero"),
            endereco=f"Rua Fictícia do Jardim, {10+i}", telefone_celular=f"1190000{i:04d}",
            telefone_residencial="", ensino_medio_completo=i % 3 != 0,
            origem_encaminhamento=origem, observacao_encaminhamento="")
        registrar_situacao_social(usuario=autor, participante_id=pessoa.pk, vigente_desde=entrada,
            mora_sozinho=sorteio.random() < .57, tem_apoio=sorteio.random() < .55,
            possui_deficiencia=i % 11 == 0, recebe_bpc=i % 8 == 0, imigrante_refugiado=i % 21 == 0)
        pessoas.append(pessoa)
    return pessoas


def criar_oficinas(autor, pessoas, sorteio):
    oficinas = []
    for indice, (nome, categoria) in enumerate(OFICINAS):
        dia_semana = indice % 5
        hora = 9 + 2 * (indice // 5)
        atividade = cadastrar_atividade(usuario=autor, nome=nome, local=f"Sala {1+indice%3}",
                                        monitor=f"Oficineiro Exemplo {1+indice%6}")
        cadastrar_horario(usuario=autor, atividade_id=atividade.pk, dia_semana=dia_semana,
                          inicio=time(hora), fim=time(hora+1))
        classificar_atividade(usuario=autor, atividade_id=atividade.pk, inicio=INICIO,
                              categoria_id=CategoriaFMR.objects.get(nome__startswith=categoria).pk)
        # Uma oficina principal por pessoa, mais grupos com interesses em comum.
        principais = pessoas[indice::len(OFICINAS)]
        outras = sorteio.sample([p for p in pessoas if p not in principais], 16)
        inscricoes = [inscrever_participante(usuario=autor, atividade_id=atividade.pk,
                      participante_referencia=str(p.pk)) for p in principais + outras]
        oficinas.append((atividade, dia_semana, hora, inscricoes))
    return oficinas


def movimentar_turma(autor, pessoas):
    motivos = list(MotivoDesligamento.objects.order_by("pk"))
    for i, pessoa in enumerate(pessoas[:8]):
        movimentar_participante(usuario=autor, participante_id=pessoa.pk, tipo="desligamento",
            data=INICIO + timedelta(days=14+i), motivo_id=motivos[i % len(motivos)].pk)
    for i, pessoa in enumerate(pessoas[8:11]):
        movimentar_participante(usuario=autor, participante_id=pessoa.pk, tipo="desligamento",
            data=INICIO - timedelta(days=20), motivo_id=MotivoDesligamento.objects.get(descricao="Desistência").pk)
        movimentar_participante(usuario=autor, participante_id=pessoa.pk, tipo="reativacao",
                                data=INICIO + timedelta(days=5+i))
    for pessoa in pessoas[11:15]:
        movimentar_participante(usuario=autor, participante_id=pessoa.pk, tipo="afastamento",
                                data=INICIO + timedelta(days=7))
        movimentar_participante(usuario=autor, participante_id=pessoa.pk, tipo="retorno",
                                data=INICIO + timedelta(days=20))


def realizar_chamadas(autor, oficinas, sorteio):
    provedor = ProvedorParticipantes()
    for n in range(31):
        dia = INICIO + timedelta(days=n)
        if dia.weekday() >= 5 or dia.day == 12:
            continue
        estados = provedor.situacoes_em(dia)
        for atividade, dia_semana, hora, inscricoes in oficinas:
            if dia_semana != dia.weekday():
                continue
            aula = registrar_aula(usuario=autor, atividade_id=atividade.pk, data=dia, inicio=time(hora),
                                  fim=time(hora+1), tipo="regular")
            registros = {}
            for inscricao in inscricoes:
                estado = estados[inscricao.participante_referencia]
                if estado not in ("desligamento", "nao_ingressou"):
                    registros[inscricao.pk] = "ausente" if estado == "afastamento" or sorteio.random() < .12 else "presente"
            registrar_frequencias(usuario=autor, atividade_id=atividade.pk, aula_id=aula.pk, registros=registros)


class Command(BaseCommand):
    help = "Carrega exemplos no banco local nci_fmr_demonstracao após migrate. Consulte o FMR de 2026-10."

    @transaction.atomic
    def handle(self, *args, **options):
        db = connection.settings_dict
        if not settings.DEBUG or db["NAME"] != BANCO or db["HOST"] not in ("localhost", "127.0.0.1", "::1"):
            raise CommandError(f"Use DEBUG local e POSTGRES_DB={BANCO}.")
        usuarios = get_user_model().objects
        if usuarios.filter(username="carga_ficticia_fmr").exists():
            self.stdout.write("Cenário já carregado. Consulte outubro de 2026.")
            return
        if usuarios.exists() or Participante.objects.exists() or Atividade.objects.exists():
            raise CommandError("A primeira carga requer um banco de demonstração vazio e migrado.")
        autor = usuarios.create_superuser(username="carga_ficticia_fmr", password=None)
        sorteio = Random(202610)
        pessoas = cadastrar_turma(autor, sorteio)
        oficinas = criar_oficinas(autor, pessoas, sorteio)
        movimentar_turma(autor, pessoas)
        realizar_chamadas(autor, oficinas, sorteio)
        senha = token_urlsafe(15)
        equipe = usuarios.create_user(username="equipe_teste", password=senha)
        equipe.groups.add(Group.objects.get(name="Equipe"))
        equipe.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
                                                               codename__startswith="view_"))
        self.stdout.write(f"FMR 2026-10. Login local: equipe_teste. Senha: {senha}")
