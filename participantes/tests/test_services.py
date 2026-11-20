from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import EventoAuditoria
from participantes import auditoria
from participantes.categorias import StatusParticipante, TipoMovimentacao
from participantes.models import Movimentacao, Participante, RegistroParticipante, SituacaoSocial
from participantes.services import (cadastrar_participante, corrigir_participante, pesquisar_participantes,
                                    possiveis_duplicados, registrar_situacao_social)

# RN-SEG-02: somente dados fictícios.
DADOS = {
    "nome_completo": "Maria Fictícia da Silva",
    "data_nascimento": date(1950, 3, 10),
    "sexo": "F",
    "raca_cor": "parda",
    "identidade_genero": "cisgenero",
    "telefone_celular": "61912345678",
    "telefone_residencial": "",
    "origem_encaminhamento": "cras",
    "endereco": "Rua Fictícia, 100",
    "ensino_medio_completo": True,
    "observacao_encaminhamento": "",
}
ENTRADA = date(2024, 1, 15)
INDICADORES = {"mora_sozinho": True, "tem_apoio": False, "possui_deficiencia": False,
               "recebe_bpc": True, "imigrante_refugiado": False}


def criar_usuario(username, *codenames, ativo=True):
    usuario = get_user_model().objects.create_user(username=username, is_active=ativo)
    usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="participantes",
                                                            codename__in=codenames))
    return usuario


def eventos(participante):
    return list(RegistroParticipante.objects.filter(alvo_id=participante.pk).order_by("registrado_em", "pk"))


class CadastroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = criar_usuario("equipe_cadastro_ficticia", "add_participante")

    def cadastrar(self, data_entrada=ENTRADA, **dados):
        return cadastrar_participante(usuario=self.usuario, data_entrada=data_entrada, **(DADOS | dados))

    def test_exige_permissao_de_cadastro(self):
        sem_permissao = criar_usuario("sem_permissao_ficticia", "change_participante", "view_participante")
        inativo = criar_usuario("inativo_ficticio", "add_participante", ativo=False)
        for usuario in (None, AnonymousUser(), sem_permissao, inativo):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                cadastrar_participante(usuario=usuario, data_entrada=ENTRADA, **DADOS)
        self.assertFalse(Participante.objects.exists())
        self.assertFalse(Movimentacao.objects.exists())
        self.assertFalse(RegistroParticipante.objects.exists())

    def test_cadastro_nasce_ativo_com_entrada(self):
        participante = self.cadastrar()
        participante.refresh_from_db()
        self.assertEqual(participante.status, StatusParticipante.ATIVO)
        entrada = Movimentacao.objects.get(participante=participante)
        self.assertEqual(entrada.tipo, TipoMovimentacao.ENTRADA)
        self.assertEqual(entrada.data, ENTRADA)
        self.assertEqual(entrada.usuario, self.usuario)
        self.assertEqual(participante.data_entrada, ENTRADA)

    def test_status_nao_e_dado_de_cadastro(self):
        # RN-PAR-09/P02: o status não vem do cadastro; o serviço recusa o campo e nada é gravado.
        with self.assertRaises(ValidationError):
            self.cadastrar(status=StatusParticipante.INATIVO)
        self.assertFalse(Participante.objects.exists())

    def test_data_entrada_invalida_vira_erro_no_campo(self):
        amanha = timezone.localdate() + timedelta(days=1)
        for data in (amanha, DADOS["data_nascimento"] - timedelta(days=1)):
            with self.subTest(data=data), self.assertRaises(ValidationError) as erro:
                self.cadastrar(data_entrada=data)
            self.assertIn("data_entrada", erro.exception.message_dict)
            self.assertNotIn("data", erro.exception.message_dict)
        self.assertFalse(Participante.objects.exists())

    def test_data_entrada_ausente_vira_erro_no_campo(self):
        with self.assertRaises(ValidationError) as erro:
            self.cadastrar(data_entrada=None)
        self.assertIn("data_entrada", erro.exception.message_dict)

    def test_dados_incompletos_sao_recusados(self):
        dados = dict(DADOS)
        dados.pop("endereco")
        with self.assertRaises(ValidationError):
            cadastrar_participante(usuario=self.usuario, data_entrada=ENTRADA, **dados)
        self.assertFalse(Participante.objects.exists())

    def test_falha_na_auditoria_desfaz_tudo(self):
        with patch("participantes.services.registrar", side_effect=RuntimeError("falha fictícia")):
            with self.assertRaises(RuntimeError):
                self.cadastrar()
        self.assertFalse(Participante.objects.exists())
        self.assertFalse(Movimentacao.objects.exists())
        self.assertFalse(EventoAuditoria.objects.exists())

    def test_auditoria_de_cadastro_com_dados_novos(self):
        participante = self.cadastrar(telefone_celular="(61) 91234-5678", nome_completo="  Maria   Fictícia da Silva ")
        evento, = eventos(participante)
        self.assertEqual(evento.acao, "cadastro")
        self.assertEqual(evento.usuario, self.usuario)
        self.assertIsNone(evento.anteriores)
        esperado = DADOS | {"origem_descricao": "", "data_nascimento": "1950-03-10", "status": StatusParticipante.ATIVO,
                            "data_entrada": ENTRADA.isoformat()}
        self.assertEqual(evento.novos, esperado)


class DuplicidadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = criar_usuario("equipe_duplicidade_ficticia", "add_participante", "change_participante")
        cls.existente = cadastrar_participante(usuario=cls.usuario, data_entrada=ENTRADA, **DADOS)

    def test_mesmo_nome_variando_acento_caixa_espacos_e_mesma_data_e_duplicidade(self):
        for nome in ("Maria Ficticia da Silva", "MARIA FICTÍCIA DA SILVA", "  maria   fictícia  da silva "):
            with self.subTest(nome=nome), self.assertRaises(ValidationError) as erro:
                cadastrar_participante(usuario=self.usuario, data_entrada=ENTRADA, **(DADOS | {"nome_completo": nome}))
            self.assertEqual(erro.exception.error_list[0].code, "possivel_duplicado")
        self.assertEqual(Participante.objects.count(), 1)

    def test_confirmar_duplicidade_cadastra(self):
        outro = cadastrar_participante(usuario=self.usuario, data_entrada=ENTRADA, confirmar_duplicidade=True,
                                       **(DADOS | {"nome_completo": "MARIA FICTICIA DA SILVA"}))
        self.assertEqual(Participante.objects.count(), 2)
        self.assertNotEqual(outro.pk, self.existente.pk)

    def test_confirmacao_precisa_ser_explicita(self):
        with self.assertRaises(ValidationError):
            cadastrar_participante(usuario=self.usuario, data_entrada=ENTRADA, confirmar_duplicidade="sim", **DADOS)

    def test_outra_data_de_nascimento_nao_e_duplicidade(self):
        cadastrar_participante(usuario=self.usuario, data_entrada=ENTRADA,
                               **(DADOS | {"data_nascimento": date(1950, 3, 11)}))
        self.assertEqual(Participante.objects.count(), 2)

    def test_possiveis_duplicados_com_excluir_id(self):
        argumentos = {"nome_completo": "maria ficticia  DA silva", "data_nascimento": DADOS["data_nascimento"]}
        self.assertEqual(possiveis_duplicados(**argumentos), [self.existente])
        self.assertEqual(possiveis_duplicados(**argumentos, excluir_id=self.existente.pk), [])
        self.assertEqual(possiveis_duplicados(nome_completo="Outra Fictícia",
                                              data_nascimento=DADOS["data_nascimento"]), [])
        self.assertEqual(possiveis_duplicados(nome_completo=None, data_nascimento=None), [])

    def test_correcao_para_nome_de_outro_participante_e_duplicidade(self):
        outro = cadastrar_participante(usuario=self.usuario, data_entrada=ENTRADA,
                                       **(DADOS | {"nome_completo": "Joana Fictícia"}))
        with self.assertRaises(ValidationError) as erro:
            corrigir_participante(usuario=self.usuario, participante_id=outro.pk, data_entrada=ENTRADA, **DADOS)
        self.assertEqual(erro.exception.error_list[0].code, "possivel_duplicado")
        corrigir_participante(usuario=self.usuario, participante_id=outro.pk, data_entrada=ENTRADA,
                              confirmar_duplicidade=True, **DADOS)
        outro.refresh_from_db()
        self.assertEqual(outro.nome_completo, DADOS["nome_completo"])


class CorrecaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = criar_usuario("equipe_correcao_ficticia", "add_participante", "change_participante")
        cls.so_cadastro = criar_usuario("so_cadastro_ficticio", "add_participante", "view_participante")

    def setUp(self):
        self.participante = cadastrar_participante(usuario=self.usuario, data_entrada=ENTRADA, **DADOS)

    def corrigir(self, data_entrada=ENTRADA, usuario=None, **dados):
        return corrigir_participante(usuario=usuario or self.usuario, participante_id=self.participante.pk,
                                     data_entrada=data_entrada, **(DADOS | dados))

    def test_exige_permissao_de_correcao(self):
        inativo = criar_usuario("inativo_correcao_ficticio", "change_participante", ativo=False)
        for usuario in (AnonymousUser(), self.so_cadastro, inativo):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                corrigir_participante(usuario=usuario, participante_id=self.participante.pk, data_entrada=ENTRADA,
                                      **(DADOS | {"raca_cor": "preta"}))
        self.participante.refresh_from_db()
        self.assertEqual(self.participante.raca_cor, "parda")
        self.assertEqual(len(eventos(self.participante)), 1)

    def test_audita_anteriores_e_novos(self):
        self.corrigir(raca_cor="preta", identidade_genero="agenero")
        cadastro, correcao = eventos(self.participante)
        self.assertEqual(correcao.acao, "correcao")
        self.assertEqual(correcao.usuario, self.usuario)
        self.assertEqual(correcao.anteriores["raca_cor"], "parda")
        self.assertEqual(correcao.novos["raca_cor"], "preta")
        self.assertEqual(correcao.anteriores["identidade_genero"], "cisgenero")
        self.assertEqual(correcao.novos["identidade_genero"], "agenero")
        self.assertEqual(correcao.anteriores, cadastro.novos | {"perfil_vigente_desde": ENTRADA.isoformat()})
        alterados = {campo for campo in correcao.novos if correcao.novos[campo] != correcao.anteriores[campo]}
        self.assertEqual(alterados, {"raca_cor", "identidade_genero", "perfil_vigente_desde"})
        self.participante.refresh_from_db()
        self.assertEqual(self.participante.raca_cor, "preta")
        rotulos = {rotulo for rotulo, _, _ in auditoria.diferencas(correcao)}
        self.assertEqual(rotulos, {"Raça/cor autodeclarada", "Identidade de gênero", "Vigência do perfil no FMR"})

    def test_sem_mudanca_nao_grava_evento(self):
        # Valores equivalentes após a normalização (espaços e máscara) não são mudança.
        self.corrigir(nome_completo="  Maria  Fictícia da Silva", telefone_celular="(61) 91234-5678")
        self.assertEqual(len(eventos(self.participante)), 1)

    def test_corrige_data_de_entrada_com_auditoria(self):
        nova = date(2024, 2, 1)
        self.corrigir(data_entrada=nova)
        self.assertEqual(Movimentacao.objects.filter(participante=self.participante).count(), 1)
        self.assertEqual(self.participante.data_entrada, nova)
        correcao = eventos(self.participante)[-1]
        self.assertEqual(correcao.anteriores["data_entrada"], ENTRADA.isoformat())
        self.assertEqual(correcao.novos["data_entrada"], nova.isoformat())
        self.assertIn(("Data de entrada", ENTRADA.isoformat(), nova.isoformat()), auditoria.diferencas(correcao))

    def test_data_entrada_invalida_na_correcao(self):
        for data in (timezone.localdate() + timedelta(days=1), date(1949, 1, 1)):
            with self.subTest(data=data), self.assertRaises(ValidationError) as erro:
                self.corrigir(data_entrada=data)
            self.assertIn("data_entrada", erro.exception.message_dict)
        # Nascimento corrigido para depois da entrada também invalida a entrada.
        with self.assertRaises(ValidationError) as erro:
            self.corrigir(data_nascimento=date(2024, 6, 1))
        self.assertIn("data_entrada", erro.exception.message_dict)
        self.assertEqual(self.participante.data_entrada, ENTRADA)
        self.assertEqual(len(eventos(self.participante)), 1)

    def test_status_nao_muda_por_correcao(self):
        Participante.objects.filter(pk=self.participante.pk).update(status=StatusParticipante.INATIVO)
        self.corrigir(endereco="Rua Fictícia, 200")
        self.participante.refresh_from_db()
        self.assertEqual(self.participante.status, StatusParticipante.INATIVO)
        with self.assertRaises(ValidationError):
            self.corrigir(status=StatusParticipante.ATIVO)
        self.participante.refresh_from_db()
        self.assertEqual(self.participante.status, StatusParticipante.INATIVO)

    def test_nome_busca_atualizado(self):
        self.corrigir(nome_completo="Joana Fictícia Pereira")
        self.participante.refresh_from_db()
        self.assertEqual(self.participante.nome_busca, "joana ficticia pereira")
        self.assertEqual(list(pesquisar_participantes("joana")), [self.participante])
        self.assertFalse(pesquisar_participantes("maria").exists())

    def test_cadastro_sem_entrada_ganha_entrada_na_correcao(self):
        avulso = Participante.objects.create(**(DADOS | {"nome_completo": "Avulsa Fictícia"}))
        corrigir_participante(usuario=self.usuario, participante_id=avulso.pk, data_entrada=ENTRADA,
                              **(DADOS | {"nome_completo": "Avulsa Fictícia"}))
        self.assertEqual(avulso.data_entrada, ENTRADA)
        evento, = eventos(avulso)
        self.assertIsNone(evento.anteriores["data_entrada"])
        self.assertEqual(evento.novos["data_entrada"], ENTRADA.isoformat())

    def test_falha_na_auditoria_desfaz_correcao(self):
        with patch("participantes.services.registrar", side_effect=RuntimeError("falha fictícia")):
            with self.assertRaises(RuntimeError):
                self.corrigir(raca_cor="preta", data_entrada=date(2024, 2, 1))
        self.participante.refresh_from_db()
        self.assertEqual(self.participante.raca_cor, "parda")
        self.assertEqual(self.participante.data_entrada, ENTRADA)


class PesquisaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = Participante.objects.create(**(DADOS | {"nome_completo": "Ana Fictícia Silva"}))
        cls.joao = Participante.objects.create(**(DADOS | {"nome_completo": "João Fictício Souza"}))
        cls.analia = Participante.objects.create(**(DADOS | {"nome_completo": "Anália Fictícia Costa"}))

    def assertEncontra(self, termo, *esperados):
        self.assertEqual(set(pesquisar_participantes(termo)), set(esperados), termo)

    def test_termo_vazio_devolve_todos(self):
        for termo in ("", "   ", None):
            with self.subTest(termo=termo):
                self.assertEncontra(termo, self.ana, self.joao, self.analia)

    def test_cada_palavra_precisa_aparecer_em_qualquer_ordem(self):
        self.assertEncontra("silva ana", self.ana)
        self.assertEncontra("ana silva", self.ana)
        self.assertEncontra("ana", self.ana, self.analia)
        self.assertEncontra("ana souza")
        self.assertEncontra("souza joao", self.joao)

    def test_ignora_acentos_caixa_e_espacos(self):
        self.assertEncontra("  JOÃO   fictício ", self.joao)
        self.assertEncontra("joao ficticio", self.joao)
        self.assertEncontra("ANALIA", self.analia)
        self.assertEncontra("anália", self.analia)


class SituacaoSocialServicoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = criar_usuario("equipe_situacao_ficticia", "change_participante")
        cls.so_cadastro = criar_usuario("so_cadastro_situacao_ficticio", "add_participante", "view_participante")
        cls.participante = Participante.objects.create(**DADOS)

    def registrar(self, vigente_desde=date(2024, 1, 1), usuario=None, **indicadores):
        return registrar_situacao_social(usuario=usuario or self.usuario, participante_id=self.participante.pk,
                                         vigente_desde=vigente_desde, **(INDICADORES | indicadores))

    def test_exige_permissao_de_alteracao(self):
        inativo = criar_usuario("inativo_situacao_ficticio", "change_participante", ativo=False)
        for usuario in (AnonymousUser(), self.so_cadastro, inativo):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                self.registrar(usuario=usuario)
        self.assertFalse(SituacaoSocial.objects.exists())

    def test_nova_data_cria_registro_e_mantem_anteriores(self):
        primeira = self.registrar()
        segunda = self.registrar(vigente_desde=date(2024, 3, 1), mora_sozinho=False)
        self.assertNotEqual(primeira.pk, segunda.pk)
        self.assertEqual(SituacaoSocial.objects.filter(participante=self.participante).count(), 2)
        self.assertTrue(SituacaoSocial.vigente_em(self.participante, date(2024, 2, 1)).mora_sozinho)
        self.assertFalse(SituacaoSocial.vigente_em(self.participante, date(2024, 3, 1)).mora_sozinho)
        primeiro, segundo = eventos(self.participante)
        self.assertEqual(primeiro.acao, "situacao")
        self.assertIsNone(primeiro.anteriores)
        self.assertEqual(primeiro.novos, {"vigente_desde": "2024-01-01", **INDICADORES})
        self.assertIsNone(segundo.anteriores)
        self.assertEqual(segundo.usuario, self.usuario)

    def test_mesma_data_corrige_registro_com_anteriores(self):
        original = self.registrar()
        corrigida = self.registrar(recebe_bpc=False)
        self.assertEqual(corrigida.pk, original.pk)
        self.assertEqual(SituacaoSocial.objects.count(), 1)
        original.refresh_from_db()
        self.assertFalse(original.recebe_bpc)
        _, correcao = eventos(self.participante)
        self.assertEqual(correcao.anteriores, {"vigente_desde": "2024-01-01", **INDICADORES})
        self.assertEqual(correcao.novos, {"vigente_desde": "2024-01-01", **(INDICADORES | {"recebe_bpc": False})})

    def test_mesma_data_sem_mudanca_nao_grava_evento(self):
        self.registrar()
        self.registrar()
        self.assertEqual(len(eventos(self.participante)), 1)

    def test_vigente_desde_invalida(self):
        for data in (timezone.localdate() + timedelta(days=1), date(1949, 12, 31)):
            with self.subTest(data=data), self.assertRaises(ValidationError) as erro:
                self.registrar(vigente_desde=data)
            self.assertIn("vigente_desde", erro.exception.message_dict)
        self.assertFalse(SituacaoSocial.objects.exists())
        self.assertFalse(RegistroParticipante.objects.exists())

    def test_indicadores_incompletos_ou_nao_booleanos(self):
        indicadores = dict(INDICADORES)
        indicadores.pop("recebe_bpc")
        with self.assertRaises(ValidationError):
            registrar_situacao_social(usuario=self.usuario, participante_id=self.participante.pk,
                                      vigente_desde=date(2024, 1, 1), **indicadores)
        with self.assertRaises(ValidationError):
            self.registrar(mora_sozinho="sim")
        self.assertFalse(SituacaoSocial.objects.exists())

    def test_falha_na_auditoria_desfaz_situacao(self):
        with patch("participantes.services.registrar", side_effect=RuntimeError("falha fictícia")):
            with self.assertRaises(RuntimeError):
                self.registrar()
        self.assertFalse(SituacaoSocial.objects.exists())


class HistoricoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = criar_usuario("equipe_historico_ficticia", "add_participante", "change_participante")
        cls.participante = cadastrar_participante(usuario=cls.usuario, data_entrada=ENTRADA, **DADOS)
        cls.outro = cadastrar_participante(usuario=cls.usuario, data_entrada=ENTRADA,
                                           **(DADOS | {"nome_completo": "Outra Fictícia"}))

    def test_exige_permissao_de_correcao(self):
        so_ver = criar_usuario("so_ver_historico_ficticio", "view_participante", "add_participante")
        inativo = criar_usuario("inativo_historico_ficticio", "change_participante", ativo=False)
        for usuario in (None, AnonymousUser(), so_ver, inativo):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                auditoria.historico(self.participante, usuario=usuario)

    def test_ordem_cronologica_e_so_eventos_do_participante(self):
        corrigir_participante(usuario=self.usuario, participante_id=self.participante.pk, data_entrada=ENTRADA,
                              **(DADOS | {"raca_cor": "preta"}))
        registrar_situacao_social(usuario=self.usuario, participante_id=self.participante.pk,
                                  vigente_desde=date(2024, 1, 1), **INDICADORES)
        corrigir_participante(usuario=self.usuario, participante_id=self.outro.pk, data_entrada=ENTRADA,
                              **(DADOS | {"nome_completo": "Outra Fictícia", "raca_cor": "branca"}))
        # Evento de outro tipo com o mesmo alvo_id não pertence ao histórico do participante.
        EventoAuditoria.objects.create(tipo="RegistroCadastroAtividade", alvo_id=self.participante.pk,
                                       usuario=self.usuario, novos={"nome": "Atividade fictícia"})
        historico = list(auditoria.historico(self.participante, usuario=self.usuario))
        self.assertEqual([evento.acao for evento in historico], ["cadastro", "correcao", "situacao"])
        self.assertTrue(all(evento.alvo_id == self.participante.pk for evento in historico))
        self.assertTrue(all(evento.tipo == "RegistroParticipante" for evento in historico))
        momentos = [(evento.registrado_em, evento.pk) for evento in historico]
        self.assertEqual(momentos, sorted(momentos))


class PerfilDemograficoRetroativoTests(TestCase):
    """RF-PAR-05 / RN-FMR-12: o perfil demográfico vale desde a entrada, também depois de corrigi-la."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = criar_usuario("equipe_perfil_ficticia", "add_participante", "change_participante")

    def setUp(self):
        self.participante = cadastrar_participante(usuario=self.usuario, data_entrada=date(2024, 3, 10), **DADOS)

    def corrigir(self, **extra):
        dados = DADOS | {k: v for k, v in extra.items() if k in DADOS}
        opcoes = {k: v for k, v in extra.items() if k not in DADOS}
        return corrigir_participante(usuario=self.usuario, participante_id=self.participante.pk, **dados,
                                     **({"data_entrada": date(2024, 3, 10)} | opcoes))

    def perfis(self):
        return list(self.participante.perfis_demograficos.order_by("vigente_desde")
                    .values_list("vigente_desde", "raca_cor"))

    def test_antecipar_a_entrada_leva_o_inicio_do_perfil_junto(self):
        self.corrigir(data_entrada=date(2024, 1, 15))
        self.assertEqual(self.perfis(), [(date(2024, 1, 15), "parda")])
        correcao = RegistroParticipante.objects.filter(participante=self.participante, acao="correcao").get()
        self.assertEqual(correcao.anteriores["perfil_inicio"], "2024-03-10")
        self.assertEqual(correcao.novos["perfil_inicio"], "2024-01-15")

    def test_vigencia_entre_perfis_existentes_e_aceita(self):
        self.corrigir(raca_cor="preta", perfil_vigente_desde=date(2024, 6, 1))
        self.corrigir(raca_cor="branca", perfil_vigente_desde=date(2024, 4, 1))
        self.assertEqual(self.perfis(), [(date(2024, 3, 10), "parda"), (date(2024, 4, 1), "branca"),
                                         (date(2024, 6, 1), "preta")])

    def test_vigencia_antes_da_entrada_ou_no_futuro_e_recusada(self):
        for vigencia in (date(2024, 3, 9), timezone.localdate() + timedelta(days=1)):
            with self.subTest(vigencia=vigencia), self.assertRaises(ValidationError) as erro:
                self.corrigir(raca_cor="preta", perfil_vigente_desde=vigencia)
            self.assertIn("perfil_vigente_desde", erro.exception.message_dict)

    def test_cadastro_sem_perfil_ganha_perfil_desde_a_entrada_com_os_valores_anteriores(self):
        self.participante.perfis_demograficos.all().delete()
        self.corrigir(raca_cor="preta")
        self.assertEqual(self.perfis(), [(date(2024, 3, 10), "parda"), (timezone.localdate(), "preta")])
