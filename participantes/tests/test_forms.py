from datetime import date

from django.test import TestCase

from participantes.forms import ParticipanteForm, SituacaoSocialForm
from participantes.models import SituacaoSocial

DADOS_FICTICIOS = {
    "nome_completo": "Maria Exemplo Ficticia", "endereco": "Rua Ficticia, 100",
    "identidade_genero": "mulher_cis", "origem_encaminhamento": "cras", "observacao_encaminhamento": "",
    "telefone_residencial": "", "telefone_celular": "(11) 91234-5678", "data_nascimento": "1950-03-10",
    "raca_cor": "parda", "sexo": "F", "ensino_medio_completo": "True", "data_entrada": "2024-01-15",
}


class ParticipanteFormTests(TestCase):
    def test_sem_campo_status(self):
        form = ParticipanteForm()
        self.assertNotIn("status", form.fields)
        self.assertNotIn('name="status"', form.as_p())

    def test_data_entrada_presente_e_confirmacao_so_quando_pedida(self):
        self.assertIn("data_entrada", ParticipanteForm().fields)
        self.assertNotIn("confirmar_duplicidade", ParticipanteForm().fields)
        self.assertIn("confirmar_duplicidade", ParticipanteForm(mostrar_confirmacao=True).fields)

    def test_telefones_com_mascara_e_sem_alpine(self):
        form = ParticipanteForm()
        for nome in ("telefone_celular", "telefone_residencial"):
            with self.subTest(campo=nome):
                attrs = form.fields[nome].widget.attrs
                self.assertEqual(attrs.get("data-mascara"), "telefone")
                self.assertFalse([chave for chave in attrs if chave.startswith("x-on") or chave.startswith("@")])
                html = str(form[nome])
                self.assertIn('data-mascara="telefone"', html)
                self.assertIn('maxlength="20"', html)
                self.assertNotIn("x-on", html)

    def test_selects_com_rotulo_selecione(self):
        form = ParticipanteForm()
        for nome in ("sexo", "raca_cor", "identidade_genero", "origem_encaminhamento"):
            with self.subTest(campo=nome):
                self.assertEqual(list(form.fields[nome].choices)[0], ("", "Selecione"))
                self.assertIn(">Selecione</option>", str(form[nome]))
                self.assertNotIn("---------", str(form[nome]))

    def test_aceita_telefone_mascarado_e_repassa_ao_servico(self):
        form = ParticipanteForm(DADOS_FICTICIOS)
        self.assertTrue(form.is_valid(), form.errors)
        dados, confirmar = form.dados_servico()
        self.assertFalse(confirmar)
        self.assertEqual(dados["data_entrada"], date(2024, 1, 15))
        self.assertIs(dados["ensino_medio_completo"], True)
        self.assertNotIn("status", dados)

    def test_confirmacao_so_vale_com_checkbox_marcado(self):
        form = ParticipanteForm({**DADOS_FICTICIOS, "confirmar_duplicidade": "on"}, mostrar_confirmacao=True)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.dados_servico()[1])
        # Sem o alerta exibido, o campo não existe e a confirmação enviada é ignorada.
        form = ParticipanteForm({**DADOS_FICTICIOS, "confirmar_duplicidade": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.dados_servico()[1])

    def test_obrigatorios_com_mensagem_em_portugues(self):
        form = ParticipanteForm({})
        self.assertFalse(form.is_valid())
        for nome in ("nome_completo", "data_nascimento", "sexo", "data_entrada", "ensino_medio_completo"):
            with self.subTest(campo=nome):
                self.assertIn("Este campo é obrigatório.", form.errors[nome])


class SituacaoSocialFormTests(TestCase):
    INDICADORES = ("mora_sozinho", "tem_apoio", "possui_deficiencia", "recebe_bpc", "imigrante_refugiado")

    def test_inicial_sem_situacao_comeca_hoje(self):
        self.assertEqual(SituacaoSocialForm.inicial_de(None, hoje=date(2024, 5, 1)), {"vigente_desde": date(2024, 5, 1)})

    def test_inicial_padrao_usa_data_local(self):
        from django.utils import timezone
        self.assertEqual(SituacaoSocialForm.inicial_de(None)["vigente_desde"], timezone.localdate())

    def test_inicial_repete_indicadores_da_situacao_atual(self):
        situacao = SituacaoSocial(vigente_desde=date(2023, 1, 1), mora_sozinho=True, tem_apoio=False,
                                  possui_deficiencia=True, recebe_bpc=False, imigrante_refugiado=True)
        inicial = SituacaoSocialForm.inicial_de(situacao, hoje=date(2024, 5, 1))
        self.assertEqual(inicial, {"vigente_desde": date(2024, 5, 1), "mora_sozinho": True, "tem_apoio": False,
                                   "possui_deficiencia": True, "recebe_bpc": False, "imigrante_refugiado": True})

    def test_indicador_nao_marcado_e_nao(self):
        form = SituacaoSocialForm({"vigente_desde": "2024-05-01", "mora_sozinho": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        dados = form.dados_servico()
        self.assertIs(dados["mora_sozinho"], True)
        for campo in self.INDICADORES[1:]:
            self.assertIs(dados[campo], False)
        self.assertEqual(dados["vigente_desde"], date(2024, 5, 1))

    def test_widgets_bootstrap(self):
        form = SituacaoSocialForm()
        self.assertEqual(form.fields["mora_sozinho"].widget.attrs.get("class"), "form-check-input")
        self.assertEqual(form.fields["vigente_desde"].widget.attrs.get("class"), "form-control")
        self.assertIn('type="date"', str(form["vigente_desde"]))
