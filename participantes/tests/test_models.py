from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from participantes.categorias import (IdentidadeGenero, OrigemEncaminhamento, RacaCor, Sexo, StatusParticipante,
                                      TipoMovimentacao)
from participantes.models import Movimentacao, Participante, SituacaoSocial

NASCIMENTO = date(1955, 4, 20)


def dados_participante(**extras):
    """Cadastro fictício válido (RN-SEG-02)."""
    dados = dict(nome_completo="Zuleica Fictícia Teste", data_nascimento=NASCIMENTO, sexo=Sexo.FEMININO,
                 raca_cor=RacaCor.PARDA, identidade_genero=IdentidadeGenero.MULHER_CIS,
                 endereco="Rua Inventada, 123", ensino_medio_completo=False, telefone_celular="61900000001",
                 origem_encaminhamento=OrigemEncaminhamento.CRAS)
    dados.update(extras)
    return dados


def novo_participante(**extras):
    return Participante(**dados_participante(**extras))


def criar_participante(**extras):
    return Participante.objects.create(**dados_participante(**extras))


class ParticipanteValidacaoTests(TestCase):
    def erros(self, participante):
        with self.assertRaises(ValidationError) as contexto:
            participante.full_clean()
        return contexto.exception.message_dict

    def test_cadastro_ficticio_valido_passa_no_full_clean(self):
        participante = novo_participante()
        participante.full_clean()
        self.assertEqual(participante.status, StatusParticipante.ATIVO)

    def test_nome_vazio_ou_so_espacos_e_rejeitado(self):
        for nome in ("", "   ", "\t\n"):
            with self.subTest(nome=repr(nome)):
                self.assertIn("nome_completo", self.erros(novo_participante(nome_completo=nome)))

    def test_nome_tem_espacos_normalizados_e_nome_busca_recalculado_no_clean(self):
        participante = novo_participante(nome_completo="  Zuleica   FICTÍCIA  ")
        participante.full_clean()
        self.assertEqual(participante.nome_completo, "Zuleica FICTÍCIA")
        self.assertEqual(participante.nome_busca, "zuleica ficticia")

    def test_nascimento_no_futuro_e_rejeitado(self):
        amanha = timezone.localdate() + timedelta(days=1)
        self.assertIn("data_nascimento", self.erros(novo_participante(data_nascimento=amanha)))

    def test_nascimento_antes_da_data_minima_e_rejeitado(self):
        self.assertIn("data_nascimento", self.erros(novo_participante(data_nascimento=date(1899, 12, 31))))
        novo_participante(data_nascimento=date(1900, 1, 1)).full_clean()

    def test_exige_pelo_menos_um_telefone(self):
        erros = self.erros(novo_participante(telefone_celular="", telefone_residencial=""))
        self.assertIn("telefone_celular", erros)

    def test_somente_residencial_e_suficiente(self):
        novo_participante(telefone_celular="", telefone_residencial="6131234567").full_clean()

    def test_celular_invalido_e_rejeitado(self):
        for numero in ("6181234567", "61812345678", "(61) 1234-5678", "0191234567"):
            with self.subTest(numero=numero):
                self.assertIn("telefone_celular", self.erros(novo_participante(telefone_celular=numero)))

    def test_residencial_invalido_e_rejeitado(self):
        for numero in ("6191234567", "61312345678", "6161234567", "(61) 91234-5678"):
            with self.subTest(numero=numero):
                erros = self.erros(novo_participante(telefone_residencial=numero))
                self.assertIn("telefone_residencial", erros)

    def test_telefones_com_mascara_sao_aceitos_e_gravados_so_com_digitos(self):
        participante = novo_participante(telefone_celular="(61) 90000-0001", telefone_residencial="(61) 3000-0001")
        participante.full_clean()
        self.assertEqual(participante.telefone_celular, "61900000001")
        self.assertEqual(participante.telefone_residencial, "6130000001")
        participante.save()
        participante.refresh_from_db()
        self.assertEqual(participante.telefone_celular, "61900000001")
        self.assertEqual(participante.telefone_residencial, "6130000001")

    def test_mascara_e_retirada_no_clean_fields_antes_do_limite_de_tamanho(self):
        participante = novo_participante(telefone_celular="(61) 90000-0001")
        participante.clean_fields()
        self.assertEqual(participante.telefone_celular, "61900000001")

    def test_endereco_e_obrigatorio(self):
        self.assertIn("endereco", self.erros(novo_participante(endereco="")))

    def test_endereco_so_com_espacos_e_rejeitado(self):
        self.assertIn("endereco", self.erros(novo_participante(endereco="   ")))

    def test_endereco_tem_espacos_normalizados(self):
        participante = novo_participante(endereco="  Rua   Inventada,  123 ")
        participante.full_clean()
        self.assertEqual(participante.endereco, "Rua Inventada, 123")

    def test_observacao_do_encaminhamento_e_aparada(self):
        participante = novo_participante(observacao_encaminhamento="  Encaminhamento fictício.\n ")
        participante.full_clean()
        self.assertEqual(participante.observacao_encaminhamento, "Encaminhamento fictício.")

    def test_origem_do_encaminhamento_e_obrigatoria_no_cadastro(self):
        self.assertIn("origem_encaminhamento", self.erros(novo_participante(origem_encaminhamento="")))

    def test_ensino_medio_deve_ser_informado(self):
        self.assertIn("ensino_medio_completo", self.erros(novo_participante(ensino_medio_completo=None)))

    def test_valores_fora_das_choices_sao_rejeitados_no_full_clean(self):
        for campo in ("sexo", "raca_cor", "identidade_genero", "origem_encaminhamento", "status"):
            with self.subTest(campo=campo):
                self.assertIn(campo, self.erros(novo_participante(**{campo: "x"})))


class ParticipantePersistenciaTests(TestCase):
    def test_nome_busca_e_calculado_no_save(self):
        participante = criar_participante(nome_completo="Óscar  Weiß Fictício")
        participante.refresh_from_db()
        self.assertEqual(participante.nome_busca, "oscar weiss ficticio")

    def test_nome_busca_e_recalculado_ao_alterar_nome(self):
        participante = criar_participante()
        participante.nome_completo = "Zélia Inventada"
        participante.save()
        participante.refresh_from_db()
        self.assertEqual(participante.nome_busca, "zelia inventada")

    def test_update_fields_com_nome_completo_tambem_grava_nome_busca(self):
        participante = criar_participante()
        participante.nome_completo = "Zélia Inventada"
        participante.save(update_fields=["nome_completo"])
        participante.refresh_from_db()
        self.assertEqual(participante.nome_completo, "Zélia Inventada")
        self.assertEqual(participante.nome_busca, "zelia inventada")

    def test_update_fields_sem_nome_completo_nao_altera_nome_no_banco(self):
        participante = criar_participante()
        participante.nome_completo = "Nome Não Salvo"
        participante.endereco = "Rua Outra Inventada, 9"
        participante.save(update_fields=["endereco"])
        participante.refresh_from_db()
        self.assertEqual(participante.nome_completo, "Zuleica Fictícia Teste")
        self.assertEqual(participante.nome_busca, "zuleica ficticia teste")
        self.assertEqual(participante.endereco, "Rua Outra Inventada, 9")

    def test_banco_rejeita_valores_fora_das_choices(self):
        invalidos = {"sexo": "X", "raca_cor": "azul", "identidade_genero": "nenhuma", "status": "desligado",
                     "origem_encaminhamento": "escola"}
        for campo, valor in invalidos.items():
            with self.subTest(campo=campo):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    criar_participante(**{campo: valor})

    def test_banco_rejeita_valor_fora_das_choices_em_update_direto(self):
        participante = criar_participante()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Participante.objects.filter(pk=participante.pk).update(sexo="X")

    def test_banco_aceita_origem_vazia_de_cadastros_antigos(self):
        participante = criar_participante(origem_encaminhamento="")
        self.assertEqual(Participante.objects.get(pk=participante.pk).origem_encaminhamento, "")


class ParticipanteApresentacaoTests(TestCase):
    def test_telefones_formatados(self):
        participante = novo_participante(telefone_celular="61900000001", telefone_residencial="6130000001")
        self.assertEqual(participante.celular_formatado(), "(61) 90000-0001")
        self.assertEqual(participante.residencial_formatado(), "(61) 3000-0001")

    def test_contato_principal_prioriza_celular(self):
        participante = novo_participante(telefone_celular="61900000001", telefone_residencial="6130000001")
        self.assertEqual(participante.contato_principal_formatado(), "(61) 90000-0001")

    def test_contato_principal_usa_residencial_sem_celular(self):
        participante = novo_participante(telefone_celular="", telefone_residencial="6130000001")
        self.assertEqual(participante.contato_principal_formatado(), "(61) 3000-0001")

    def test_faixa_etaria_e_idade_derivadas_do_nascimento(self):
        participante = novo_participante(data_nascimento=date(1955, 4, 20))
        self.assertEqual(participante.idade(date(2025, 4, 19)), 69)
        self.assertEqual(participante.faixa_etaria(date(2025, 4, 19)), "65 a 69 anos")
        self.assertEqual(participante.idade(date(2025, 4, 20)), 70)
        self.assertEqual(participante.faixa_etaria(date(2025, 4, 20)), "70 a 74 anos")

    def test_faixa_etaria_sem_referencia_usa_data_de_hoje(self):
        hoje = timezone.localdate()
        participante = novo_participante(data_nascimento=date(hoje.year - 80, 1, 1))
        self.assertEqual(participante.faixa_etaria(), "75 anos ou mais")
        self.assertEqual(participante.idade(), participante.idade(hoje))

    def test_str_e_o_nome(self):
        self.assertEqual(str(novo_participante()), "Zuleica Fictícia Teste")


class MovimentacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="movimentacao_ficticia")
        cls.participante = criar_participante()

    def nova(self, **extras):
        dados = dict(participante=self.participante, tipo=TipoMovimentacao.ENTRADA, data=date(2024, 3, 1),
                     usuario=self.usuario)
        dados.update(extras)
        return Movimentacao(**dados)

    def test_entrada_valida(self):
        self.nova().full_clean()

    def test_data_no_futuro_e_rejeitada(self):
        with self.assertRaises(ValidationError) as contexto:
            self.nova(data=timezone.localdate() + timedelta(days=1)).full_clean()
        self.assertIn("data", contexto.exception.message_dict)

    def test_data_hoje_e_aceita(self):
        self.nova(data=timezone.localdate()).full_clean()

    def test_data_antes_do_nascimento_e_rejeitada(self):
        with self.assertRaises(ValidationError) as contexto:
            self.nova(data=NASCIMENTO - timedelta(days=1)).full_clean()
        self.assertIn("data", contexto.exception.message_dict)
        self.nova(data=NASCIMENTO).full_clean()

    def test_clean_aceita_participante_ainda_nao_salvo(self):
        movimentacao = Movimentacao(participante=novo_participante(), tipo=TipoMovimentacao.ENTRADA,
                                    data=NASCIMENTO - timedelta(days=1), usuario=self.usuario)
        with self.assertRaises(ValidationError):
            movimentacao.clean()
        Movimentacao(tipo=TipoMovimentacao.ENTRADA, data=date(2024, 3, 1)).clean()

    def test_no_maximo_uma_entrada_por_participante(self):
        self.nova().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.nova(data=date(2024, 5, 1)).save()

    def test_outro_participante_pode_ter_sua_propria_entrada(self):
        self.nova().save()
        outro = criar_participante(nome_completo="Outro Fictício Teste", sexo=Sexo.MASCULINO)
        self.nova(participante=outro).save()
        self.assertEqual(Movimentacao.objects.filter(tipo=TipoMovimentacao.ENTRADA).count(), 2)

    def test_tipo_fora_das_choices_e_rejeitado(self):
        with self.assertRaises(ValidationError) as contexto:
            self.nova(tipo="desligamento").full_clean()
        self.assertIn("tipo", contexto.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.nova(tipo="desligamento").save()

    def test_entrada_e_data_entrada_do_participante(self):
        self.assertIsNone(self.participante.entrada)
        self.assertIsNone(self.participante.data_entrada)
        movimentacao = self.nova()
        movimentacao.save()
        self.assertEqual(self.participante.entrada, movimentacao)
        self.assertEqual(self.participante.data_entrada, date(2024, 3, 1))

    def test_participante_nao_salvo_nao_tem_entrada(self):
        participante = novo_participante()
        self.assertIsNone(participante.entrada)
        self.assertIsNone(participante.data_entrada)

    def test_participante_com_movimentacao_nao_pode_ser_excluido(self):
        self.nova().save()
        with self.assertRaises(ProtectedError):
            self.participante.delete()


class SituacaoSocialTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participante = criar_participante()

    def nova(self, vigente_desde, participante=None, **extras):
        dados = dict(mora_sozinho=False, tem_apoio=True, possui_deficiencia=False, recebe_bpc=False,
                     imigrante_refugiado=False)
        dados.update(extras)
        return SituacaoSocial(participante=participante or self.participante, vigente_desde=vigente_desde, **dados)

    def test_situacao_valida(self):
        self.nova(date(2024, 1, 1)).full_clean()

    def test_vigencia_no_futuro_e_rejeitada(self):
        with self.assertRaises(ValidationError) as contexto:
            self.nova(timezone.localdate() + timedelta(days=1)).full_clean()
        self.assertIn("vigente_desde", contexto.exception.message_dict)
        self.nova(timezone.localdate()).full_clean()

    def test_vigencia_antes_do_nascimento_e_rejeitada(self):
        with self.assertRaises(ValidationError) as contexto:
            self.nova(NASCIMENTO - timedelta(days=1)).full_clean()
        self.assertIn("vigente_desde", contexto.exception.message_dict)
        self.nova(NASCIMENTO).full_clean()

    def test_uma_situacao_por_participante_e_data(self):
        self.nova(date(2024, 1, 1)).save()
        with self.assertRaises(ValidationError):
            self.nova(date(2024, 1, 1), mora_sozinho=True).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.nova(date(2024, 1, 1), mora_sozinho=True).save()

    def test_mesma_data_em_participantes_diferentes_e_permitida(self):
        outro = criar_participante(nome_completo="Outro Fictício Teste")
        self.nova(date(2024, 1, 1)).save()
        self.nova(date(2024, 1, 1), participante=outro).save()

    def test_vigente_em_respeita_a_data_de_inicio_de_cada_registro(self):
        primeira = self.nova(date(2024, 1, 10), mora_sozinho=False)
        primeira.save()
        segunda = self.nova(date(2024, 6, 1), mora_sozinho=True)
        segunda.save()
        esperado = {
            date(2024, 1, 9): None,
            date(2024, 1, 10): primeira,
            date(2024, 3, 15): primeira,
            date(2024, 5, 31): primeira,
            date(2024, 6, 1): segunda,
            date(2025, 1, 1): segunda,
        }
        for data, situacao in esperado.items():
            with self.subTest(data=data):
                self.assertEqual(SituacaoSocial.vigente_em(self.participante, data), situacao)

    def test_vigente_em_nao_mistura_participantes(self):
        outro = criar_participante(nome_completo="Outro Fictício Teste")
        self.nova(date(2024, 1, 1), participante=outro).save()
        self.assertIsNone(SituacaoSocial.vigente_em(self.participante, date(2024, 6, 1)))

    def test_participante_com_situacao_social_nao_pode_ser_excluido(self):
        self.nova(date(2024, 1, 1)).save()
        with self.assertRaises(ProtectedError):
            self.participante.delete()
