from datetime import date, datetime, time, timezone
from importlib import import_module

from django.contrib.auth import get_user_model
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase

from atividades.models import (Atividade, EventoAuditoria, RegistroCadastroAtividade,
                     RegistroGradeAtividade, RegistroLancamentoFrequencia)


class AuditoriaUnificadaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="auditoria_ficticia")
        self.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")

    def test_proxies_compartilham_tabela_e_isolam_eventos(self):
        evento = RegistroCadastroAtividade.objects.create(atividade=self.atividade, usuario=self.usuario, dados={"nome": "Fictício"})
        self.assertEqual(EventoAuditoria.objects.get().novos, evento.dados)
        self.assertEqual(RegistroCadastroAtividade._meta.db_table, EventoAuditoria._meta.db_table)
        self.assertFalse(RegistroGradeAtividade.objects.exists())
        self.assertFalse(RegistroLancamentoFrequencia.objects.exists())
        self.assertEqual(self.atividade.registro_cadastro.pk, evento.pk)

    def test_banco_rejeita_tipo_alvo_incoerente_e_duplicacao(self):
        for dados in ({"tipo": "desconhecido", "atividade": self.atividade},
                      {"tipo": "RegistroGradeAtividade", "atividade": self.atividade},
                      {"tipo": "RegistroCadastroAtividade"}):
            with self.subTest(dados=dados), self.assertRaises(IntegrityError), transaction.atomic():
                EventoAuditoria.objects.create(usuario=self.usuario, novos={}, **dados)
        RegistroCadastroAtividade.objects.create(atividade=self.atividade, usuario=self.usuario, dados={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistroCadastroAtividade.objects.create(atividade=self.atividade, usuario=self.usuario, dados={})

    def test_alvo_e_usuario_permanecem_protegidos(self):
        RegistroCadastroAtividade.objects.create(atividade=self.atividade, usuario=self.usuario, dados={})
        with self.assertRaises(ProtectedError):
            self.atividade.delete()
        with self.assertRaises(ProtectedError):
            self.usuario.delete()

    def test_frequencia_sem_auditoria_inicial_continua_consultavel(self):
        from atividades.models import Aula, Inscricao, Frequencia
        aula = Aula.objects.create(atividade=self.atividade, data=date(2024, 1, 1), inicio=time(9), fim=time(10))
        inscricao = Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
            participante_referencia="demo-1", cadastrada_por=self.usuario)
        frequencia = Frequencia.objects.create(aula=aula, inscricao=inscricao, situacao="presente")
        self.assertIsNone(getattr(frequencia, "registro_lancamento", None))


class AuditoriaMigrationTests(TransactionTestCase):
    antiga = [("atividades", "0012_esperaatividade_registroesperaatividade_and_more")]
    nova = [("atividades", "0013_remove_registrocancelamentoaula_aula_and_more")]

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate(destino)
        return executor.loader.project_state(destino).apps

    def test_todas_fontes_preservadas_e_reversao_inclui_eventos_novos(self):
        fontes = import_module("atividades.migrations.0013_remove_registrocancelamentoaula_aula_and_more").FONTES
        try:
            apps = self.migrar(self.antiga)
            def criar(modelo, **dados):
                return apps.get_model("atividades", modelo).objects.create(**dados)
            usuario = apps.get_model("auth", "User").objects.create(username="legado_ficticio")
            atividade = criar("Atividade", nome="Fictícia", local="Sala", monitor="Fictício")
            horario = criar("HorarioAtividade", atividade=atividade, dia_semana=0, inicio=time(9), fim=time(10))
            aula = criar("Aula", atividade=atividade, data=date(2024, 1, 1), inicio=time(9), fim=time(10))
            inscricao = criar("Inscricao", atividade=atividade, origem_participante="placeholder",
                participante_referencia="demo-1", cadastrada_por=usuario)
            frequencia = criar("Frequencia", aula=aula, inscricao=inscricao, situacao="presente")
            motivo = criar("MotivoFalta", descricao="Fictício")
            categoria = criar("CategoriaFMR", nome="Fictícia")
            classificacao = criar("ClassificacaoAtividade", atividade=atividade, categoria=categoria,
                categoria_nome=categoria.nome, inicio=date(2024, 1, 1))
            espera = criar("EsperaAtividade", atividade=atividade, origem_participante="placeholder", participante_referencia="demo-2")
            alvos = dict(atividade=atividade, horario=horario, aula=aula, frequencia=frequencia,
                         motivo=motivo, categoria=categoria, classificacao=classificacao, espera=espera)
            instante = datetime(2024, 1, 2, 12, 34, 56, 123456, tzinfo=timezone.utc)
            esperados = {}
            for nome, alvo, antes, depois in fontes:
                dados = {alvo: alvos[alvo], depois: {"texto": "ação fictícia", "itens": [1, None]}}
                if antes:
                    dados[antes] = None if nome == "RegistroCancelamentoAula" else {"valor": "antes"}
                if nome == "RegistroGradeAtividade":
                    dados["acao"] = "alteracao"
                registro = criar(nome, usuario=usuario, **dados)
                apps.get_model("atividades", nome).objects.filter(pk=registro.pk).update(registrado_em=instante)
                esperados[nome] = (registro.pk, alvos[alvo].pk, dados.get(antes), dados[depois])
            apps = self.migrar(self.nova)
            Evento = apps.get_model("atividades", "EventoAuditoria")
            self.assertEqual(Evento.objects.count(), len(fontes))
            tabelas = connection.introspection.table_names()
            for nome, alvo, _, _ in fontes:
                self.assertNotIn("atividades_" + nome.lower(), tabelas)
                registro = Evento.objects.get(tipo=nome)
                pk, alvo_id, antes, depois = esperados[nome]
                self.assertEqual((registro.origem_id, getattr(registro, alvo + "_id"), registro.anteriores, registro.novos),
                                 (pk, alvo_id, antes, depois))
                self.assertEqual(registro.registrado_em, instante)
                self.assertEqual(registro.usuario_id, usuario.pk)
            Evento.objects.create(tipo="RegistroGradeAtividade", horario_id=horario.pk, usuario_id=usuario.pk,
                registrado_em=instante, anteriores={"novo": False}, novos={"novo": True}, acao="alteracao")
            apps = self.migrar(self.antiga)
            for nome, alvo, antes, depois in fontes:
                Fonte = apps.get_model("atividades", nome)
                registro = Fonte.objects.get(pk=esperados[nome][0])
                self.assertEqual(registro.registrado_em, instante)
                self.assertEqual(getattr(registro, depois), esperados[nome][3])
                self.assertEqual(registro.usuario_id, usuario.pk)
            self.assertEqual(apps.get_model("atividades", "RegistroGradeAtividade").objects.count(), 2)
            apps = self.migrar(self.nova)
            self.assertEqual(apps.get_model("atividades", "EventoAuditoria").objects.count(), len(fontes) + 1)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
