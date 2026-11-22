"""Integração participantes <-> atividades com o provedor real (core.integracoes / participantes.provedor).

Cobre o contrato do provedor, RN-PAR-04 (faltas não desligam), RN-PAR-02 (nada some em cascata),
a consulta atividades.consultas_participante.frequencia_do_participante e a independência de imports.
Dados fictícios (RN-SEG-02).
"""

import ast
import re
from datetime import date, time
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from atividades.consultas_participante import PERMISSOES_HISTORICO_FREQUENCIA, frequencia_do_participante
from atividades.espera import adicionar_espera
from atividades.integracoes.participantes import obter_provedor
from atividades.models import Atividade, EsperaAtividade, Frequencia, Inscricao
from atividades.services import cancelar_aula, inscrever_participante, registrar_aula, registrar_frequencias
from core.integracoes import ParticipanteResumo
from participantes.categorias import StatusParticipante, TipoMovimentacao
from participantes.models import Movimentacao, Participante, RegistroParticipante
from participantes.movimentacoes import movimentar_participante
from participantes.provedor import ProvedorParticipantes
from participantes.services import cadastrar_participante

PROVEDOR_REAL = "participantes.provedor.ProvedorParticipantes"

PERMISSOES_ATIVIDADES = ("view_atividade", "view_aula", "view_inscricao", "view_frequencia", "add_frequencia",
                         "add_inscricao", "add_aula", "cancelar_aula")


def dados_participante(nome, nascimento=date(1952, 6, 20)):
    return dict(nome_completo=nome, data_nascimento=nascimento, sexo="M", raca_cor="branca",
                identidade_genero="cisgenero", telefone_celular="(61) 91234-5678", telefone_residencial="",
                origem_encaminhamento="cras", endereco="Quadra Fictícia 10, Casa 1", ensino_medio_completo=False,
                observacao_encaminhamento="")


class IntegracaoBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="integracao_ficticio")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=PERMISSOES_ATIVIDADES))
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="participantes", codename__in=("add_participante", "change_participante")))
        cls.usuario = get_user_model().objects.get(pk=cls.usuario.pk)
        cls.participante = cadastrar_participante(usuario=cls.usuario, data_entrada=date(2024, 1, 8),
                                                  **dados_participante("Joaquim Fictício da Silva"))
        cls.outro = cadastrar_participante(usuario=cls.usuario, data_entrada=date(2024, 1, 8),
                                           **dados_participante("Benedita Fictícia Souza", date(1948, 2, 2)))
        cls.atividade = Atividade.objects.create(nome="Alongamento fictício", local="Sala A", monitor="Monitor fictício")

    def inscrever(self, participante, atividade=None):
        return inscrever_participante(usuario=self.usuario, atividade_id=(atividade or self.atividade).pk,
                                      participante_referencia=str(participante.pk))

    def aula(self, dia, atividade=None):
        return registrar_aula(usuario=self.usuario, atividade_id=(atividade or self.atividade).pk,
                              data=date(2024, 3, dia), inicio=time(9), fim=time(10))

    def lancar(self, aula, registros, atividade=None):
        return registrar_frequencias(usuario=self.usuario, atividade_id=(atividade or self.atividade).pk,
                                     aula_id=aula.pk, registros=registros)


@override_settings(NCI_PARTICIPANTES_PROVIDER=PROVEDOR_REAL)
class ContratoProvedorTests(IntegracaoBase):
    def test_obter_provedor_configurado_e_o_real(self):
        provedor = obter_provedor()
        self.assertIsInstance(provedor, ProvedorParticipantes)
        self.assertEqual(provedor.origem, "participantes")
        self.assertFalse(provedor.demonstracao)

    def test_listar_devolve_resumos_com_referencia_e_nome(self):
        resumos = ProvedorParticipantes().listar()
        self.assertIsInstance(resumos, tuple)
        self.assertTrue(all(isinstance(item, ParticipanteResumo) for item in resumos))
        # Ordenado por nome.
        self.assertEqual(resumos, (ParticipanteResumo(str(self.outro.pk), "Benedita Fictícia Souza"),
                                   ParticipanteResumo(str(self.participante.pk), "Joaquim Fictício da Silva")))

    def test_obter_devolve_resumo_com_referencia_e_nome(self):
        resumo = ProvedorParticipantes().obter(str(self.participante.pk))
        self.assertEqual(resumo, ParticipanteResumo(str(self.participante.pk), "Joaquim Fictício da Silva"))
        self.assertIsInstance(resumo.referencia, str)

    def test_obter_inexistente_ou_invalido_devolve_none(self):
        provedor = ProvedorParticipantes()
        inexistente = str(Participante.objects.order_by("-pk").values_list("pk", flat=True).first() + 1000)
        for referencia in (inexistente, "", "abc", "demo-1", "-1", "1.5", None):
            with self.subTest(referencia=referencia):
                self.assertIsNone(provedor.obter(referencia))

    def test_inscricao_grava_origem_e_referencia_do_provedor_real(self):
        inscricao = self.inscrever(self.participante)
        self.assertEqual((inscricao.origem_participante, inscricao.participante_referencia),
                         ("participantes", str(self.participante.pk)))


@override_settings(NCI_PARTICIPANTES_PROVIDER=PROVEDOR_REAL)
class FaltasNaoDesligamTests(IntegracaoBase):
    """RN-PAR-04: faltas seguidas não alteram o status nem geram desligamento."""

    def test_varias_ausencias_seguidas_nao_alteram_status_nem_criam_desligamento(self):
        inscricao = self.inscrever(self.participante)
        eventos_antes = list(RegistroParticipante.objects.filter(participante=self.participante)
                             .values_list("pk", flat=True))
        movimentacoes_antes = list(Movimentacao.objects.filter(participante=self.participante)
                                   .values_list("pk", "tipo"))
        for dia in range(1, 11):
            situacao = Frequencia.Situacao.AUSENTE if dia % 2 else Frequencia.Situacao.JUSTIFICADO
            self.lancar(self.aula(dia), {inscricao.pk: situacao})
        self.assertEqual(Frequencia.objects.filter(inscricao=inscricao).exclude(
            situacao=Frequencia.Situacao.PRESENTE).count(), 10)
        participante = Participante.objects.get(pk=self.participante.pk)
        self.assertEqual(participante.status, StatusParticipante.ATIVO)
        self.assertEqual(list(Movimentacao.objects.filter(participante=participante).values_list("pk", "tipo")),
                         movimentacoes_antes)
        self.assertEqual(list(participante.movimentacoes.values_list("tipo", flat=True)), [TipoMovimentacao.ENTRADA])
        self.assertEqual(list(RegistroParticipante.objects.filter(participante=participante)
                              .values_list("pk", flat=True)), eventos_antes)
        # A inscrição continua e o provedor segue devolvendo a pessoa.
        self.assertTrue(Inscricao.objects.filter(pk=inscricao.pk).exists())
        self.assertIsNotNone(obter_provedor().obter(str(participante.pk)))

    def test_ausencias_em_varias_atividades_nao_alteram_status(self):
        outra_atividade = Atividade.objects.create(nome="Coral fictício", local="Sala B", monitor="Monitor fictício")
        for atividade in (self.atividade, outra_atividade):
            inscricao = self.inscrever(self.participante, atividade)
            for dia in (4, 11, 18, 25):
                self.lancar(self.aula(dia, atividade), {inscricao.pk: Frequencia.Situacao.AUSENTE}, atividade)
        participante = Participante.objects.get(pk=self.participante.pk)
        self.assertEqual(participante.status, StatusParticipante.ATIVO)
        self.assertEqual(participante.movimentacoes.count(), 1)


@override_settings(NCI_PARTICIPANTES_PROVIDER=PROVEDOR_REAL)
class AfastamentoEmAtividadesTests(IntegracaoBase):
    """NCI 21/11: o afastado sai da lista de espera; a justificativa escolhida pela equipe sobrevive ao retorno."""

    def test_afastamento_retira_da_espera_e_retorno_preserva_justificativa_da_equipe(self):
        self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="atividades",
                                                                 codename="add_esperaatividade"))
        usuario = get_user_model().objects.get(pk=self.usuario.pk)
        referencia = str(self.participante.pk)
        coral = Atividade.objects.create(nome="Coral fictício", local="Sala B", monitor="Monitor fictício")
        espera = adicionar_espera(usuario=usuario, atividade_id=coral.pk, participante_referencia=referencia)
        inscricao = self.inscrever(self.participante)
        movimentar_participante(usuario=usuario, participante_id=self.participante.pk, tipo="afastamento",
                                data=date(2024, 3, 1))
        espera.refresh_from_db()
        self.assertEqual(espera.situacao, EsperaAtividade.Situacao.RETIRADO)
        with self.assertRaisesMessage(ValidationError, "Registre o retorno do participante afastado"):
            adicionar_espera(usuario=usuario, atividade_id=coral.pk, participante_referencia=referencia)
        registrar_frequencias(usuario=usuario, atividade_id=self.atividade.pk, aula_id=self.aula(5).pk,
                              registros={inscricao.pk: Frequencia.Situacao.JUSTIFICADO},
                              justificativas={inscricao.pk: {"observacao": "Atestado fictício"}})
        movimentar_participante(usuario=usuario, participante_id=self.participante.pk, tipo="retorno",
                                data=date(2024, 3, 3))
        frequencia = Frequencia.objects.get(inscricao=inscricao)
        self.assertEqual((frequencia.situacao, frequencia.justificada_por_afastamento, frequencia.observacao),
                         (Frequencia.Situacao.JUSTIFICADO, False, "Atestado fictício"))
        espera.refresh_from_db()
        self.assertEqual(espera.situacao, EsperaAtividade.Situacao.RETIRADO)  # o retorno não devolve à espera


@override_settings(NCI_PARTICIPANTES_PROVIDER=PROVEDOR_REAL)
class PermanenciaTests(IntegracaoBase):
    """RN-PAR-02: participante, inscrições e frequências permanecem; sem exclusão em cascata."""

    def test_exclusao_de_participante_com_auditoria_e_bloqueada_e_nada_some(self):
        inscricao = self.inscrever(self.participante)
        frequencias = [self.lancar(self.aula(dia), {inscricao.pk: "presente"})[0].pk for dia in (5, 12)]
        with self.assertRaises(ProtectedError):
            Participante.objects.get(pk=self.participante.pk).delete()
        with transaction.atomic(), self.assertRaises(ProtectedError):
            Participante.objects.filter(pk=self.participante.pk).delete()
        self.assertTrue(Participante.objects.filter(pk=self.participante.pk).exists())
        self.assertTrue(Inscricao.objects.filter(pk=inscricao.pk).exists())
        self.assertEqual(sorted(Frequencia.objects.filter(inscricao=inscricao).values_list("pk", flat=True)),
                         sorted(frequencias))
        self.assertTrue(RegistroParticipante.objects.filter(participante=self.participante).exists())
        self.assertEqual(self.participante.movimentacoes.count(), 1)

    def test_inscricao_e_frequencia_protegem_contra_cascata(self):
        inscricao = self.inscrever(self.participante)
        aula = self.aula(6)
        self.lancar(aula, {inscricao.pk: "ausente"})
        with self.assertRaises(ProtectedError):
            Inscricao.objects.get(pk=inscricao.pk).delete()
        with self.assertRaises(ProtectedError):
            Atividade.objects.get(pk=self.atividade.pk).delete()
        self.assertTrue(Frequencia.objects.filter(inscricao=inscricao, aula=aula).exists())


@override_settings(NCI_PARTICIPANTES_PROVIDER=PROVEDOR_REAL)
class FrequenciaDoParticipanteTests(IntegracaoBase):
    def consultar(self, participante=None, usuario=None, origem="participantes"):
        return frequencia_do_participante(usuario=usuario or get_user_model().objects.get(pk=self.usuario.pk),
                                          origem=origem, referencia=str((participante or self.participante).pk))

    def test_permissao_exigida(self):
        sem = get_user_model().objects.create_user(username="sem_atividades_ficticio")
        with self.assertRaisesMessage(PermissionDenied, "Você não tem permissão para ver a frequência em atividades."):
            self.consultar(usuario=sem)
        with self.assertRaises(PermissionDenied):
            frequencia_do_participante(usuario=AnonymousUser(), origem="participantes",
                                       referencia=str(self.participante.pk))

    def test_cada_permissao_do_historico_e_necessaria(self):
        for faltando in PERMISSOES_HISTORICO_FREQUENCIA:
            with self.subTest(faltando=faltando):
                usuario = get_user_model().objects.create_user(username=f"parcial_{faltando.split('.')[1]}")
                usuario.user_permissions.add(*Permission.objects.filter(
                    content_type__app_label="atividades",
                    codename__in=[p.split(".")[1] for p in PERMISSOES_HISTORICO_FREQUENCIA if p != faltando]))
                with self.assertRaises(PermissionDenied):
                    self.consultar(usuario=usuario)

    def test_usuario_inativo_e_negado(self):
        usuario = get_user_model().objects.get(pk=self.usuario.pk)
        get_user_model().objects.filter(pk=usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=usuario)

    def test_totais_por_situacao_so_de_aulas_realizadas(self):
        inscricao = self.inscrever(self.participante)
        situacoes = ["presente", "presente", "presente", "ausente", "ausente", "ausente_justificado"]
        aulas = []
        for dia, situacao in enumerate(situacoes, start=1):
            aula = self.aula(dia)
            self.lancar(aula, {inscricao.pk: situacao})
            aulas.append(aula)
        # Cancela uma aula com presença e outra com ausência justificada: saem dos totais.
        cancelar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=aulas[0].pk)
        cancelar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=aulas[5].pk)
        [linha] = self.consultar()
        self.assertEqual(linha["inscricao_id"], inscricao.pk)
        self.assertEqual(linha["atividade_id"], self.atividade.pk)
        self.assertEqual(linha["atividade_nome"], "Alongamento fictício")
        self.assertEqual((linha["presentes"], linha["ausentes"], linha["justificados"], linha["total"]), (2, 2, 0, 4))
        self.assertEqual(linha["situacao"], "Inscrito(a)")
        self.assertEqual(linha["inscrita_em"], inscricao.cadastrada_em)
        self.assertIn(str(inscricao.pk), linha["url_historico"])
        # As frequências das aulas canceladas continuam gravadas.
        self.assertEqual(Frequencia.objects.filter(inscricao=inscricao).count(), 6)

    def test_inscricao_sem_frequencia_aparece_zerada(self):
        inscricao = self.inscrever(self.participante)
        [linha] = self.consultar()
        self.assertEqual(linha["inscricao_id"], inscricao.pk)
        self.assertEqual((linha["presentes"], linha["ausentes"], linha["justificados"], linha["total"]), (0, 0, 0, 0))

    def test_nao_mistura_participantes(self):
        meu = self.inscrever(self.participante)
        alheio = self.inscrever(self.outro)
        for dia in (1, 2, 3):
            self.lancar(self.aula(dia), {meu.pk: "presente", alheio.pk: "ausente"})
        outra_atividade = Atividade.objects.create(nome="Dança fictícia", local="Sala C", monitor="Monitor fictício")
        so_alheio = self.inscrever(self.outro, outra_atividade)
        self.lancar(self.aula(4, outra_atividade), {so_alheio.pk: "presente"}, outra_atividade)

        [linha] = self.consultar()
        self.assertEqual(linha["inscricao_id"], meu.pk)
        self.assertEqual((linha["presentes"], linha["ausentes"]), (3, 0))
        linhas_outro = self.consultar(self.outro)
        self.assertEqual([item["inscricao_id"] for item in linhas_outro], sorted(
            [alheio.pk, so_alheio.pk], key=lambda pk: Inscricao.objects.get(pk=pk).atividade.nome))
        self.assertEqual({item["inscricao_id"]: (item["presentes"], item["ausentes"]) for item in linhas_outro},
                         {alheio.pk: (0, 3), so_alheio.pk: (1, 0)})

    def test_nao_mistura_origens(self):
        self.inscrever(self.participante)
        Inscricao.objects.create(atividade=Atividade.objects.create(nome="Outra origem", local="Sala D",
                                                                    monitor="Monitor fictício"),
                                 origem_participante="placeholder", participante_referencia=str(self.participante.pk),
                                 cadastrada_por=self.usuario)
        self.assertEqual(len(self.consultar()), 1)
        self.assertEqual(len(self.consultar(origem="placeholder")), 1)
        self.assertEqual(self.consultar(origem="inexistente"), [])

    def test_sem_inscricoes_devolve_lista_vazia(self):
        self.assertEqual(self.consultar(), [])

    def test_ordenado_pelo_nome_da_atividade(self):
        nomes = ["Yoga fictícia", "Artesanato fictício", "Música fictícia"]
        for nome in nomes:
            self.inscrever(self.participante, Atividade.objects.create(nome=nome, local="Sala", monitor="Fictício"))
        self.assertEqual([linha["atividade_nome"] for linha in self.consultar()], sorted(nomes))

    def _preparar_inscricoes(self, quantidade, inicio=0):
        for indice in range(inicio, inicio + quantidade):
            atividade = Atividade.objects.create(nome=f"Atividade fictícia {indice}", local="Sala",
                                                 monitor="Fictício")
            inscricao = self.inscrever(self.participante, atividade)
            for dia in (1, 2):
                self.lancar(self.aula(dia + indice * 2, atividade), {inscricao.pk: "presente" if dia == 1 else "ausente"},
                            atividade)

    def _contar_consultas(self):
        usuario = get_user_model().objects.get(pk=self.usuario.pk)
        with CaptureQueriesContext(connection) as consultas:
            linhas = frequencia_do_participante(usuario=usuario, origem="participantes",
                                                referencia=str(self.participante.pk))
        return len(consultas), linhas

    def test_numero_de_consultas_nao_cresce_com_as_inscricoes(self):
        self._preparar_inscricoes(1)
        com_uma, linhas = self._contar_consultas()
        self.assertEqual(len(linhas), 1)
        self._preparar_inscricoes(2, inicio=1)
        com_tres, linhas = self._contar_consultas()
        self.assertEqual(len(linhas), 3)
        self.assertEqual(com_tres, com_uma)
        self.assertTrue(all((linha["presentes"], linha["ausentes"]) == (1, 1) for linha in linhas))


class IndependenciaDeImportsTests(TestCase):
    """participantes depende só de core: nem atividades (contrato em core.integracoes) nem usuarios
    (critério de administrador em core.perfis/core.permissoes/core.decorators)."""

    PROIBIDOS = ("atividades", "usuarios")
    PADRAO = re.compile(r"^\s*(?:import|from)\s+(?:atividades|usuarios)\b", re.MULTILINE)

    def arquivos(self):
        raiz = Path(apps.get_app_config("participantes").path)
        return [caminho for caminho in raiz.rglob("*.py")
                if "tests" not in caminho.relative_to(raiz).parts and "__pycache__" not in caminho.parts]

    def test_arquivos_encontrados(self):
        nomes = {caminho.name for caminho in self.arquivos()}
        self.assertTrue({"models.py", "provedor.py", "views.py", "services.py"} <= nomes)
        self.assertNotIn("test_integracao_atividades.py", nomes)

    def test_participantes_nao_importa_atividades_nem_usuarios(self):
        violacoes = []
        for caminho in self.arquivos():
            texto = caminho.read_text(encoding="utf-8")
            for numero, linha in enumerate(texto.splitlines(), start=1):
                if self.PADRAO.match(linha):
                    violacoes.append(f"{caminho}:{numero}: {linha.strip()}")
            # Também pega formas que a regex não vê (ex.: "import os, atividades").
            for no in ast.walk(ast.parse(texto, filename=str(caminho))):
                modulos = []
                if isinstance(no, ast.Import):
                    modulos = [alias.name for alias in no.names]
                elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                    modulos = [no.module]
                if any(modulo.split(".", 1)[0] in self.PROIBIDOS for modulo in modulos):
                    violacoes.append(f"{caminho}:{no.lineno}: import de {modulos}")
        self.assertEqual(violacoes, [], "participantes não deve importar atividades nem usuarios:\n" + "\n".join(violacoes))
