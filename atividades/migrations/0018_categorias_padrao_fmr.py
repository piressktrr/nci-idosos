from django.db import migrations


CATEGORIAS_FMR = (
    "Ações em campanhas comunitárias (direitos dos idosos etc.)",
    "Artesanato (bijuterias, pintura em tecido, bordado, crochê etc.)",
    "Atividades de arte e cultura (pintura, circo, dança, teatro, trabalhos em papel etc.)",
    "Atividades de estimulação cognitiva",
    "Atividades de inclusão digital",
    "Atividades de linguagem (produção de texto, contação de histórias, roda de conversa etc.)",
    "Atividades esportivas",
    "Atividades externas",
    "Atividades que envolvam manipulação de alimentos (culinária, hortas etc.)",
    "Atividades recreativas (jogos diversos, campeonatos – xadrez, dama, sudoku, palavras cruzadas, games etc.)",
    "Atividades sobre sustentabilidade ambiental",
    "Musicalidade (cantar, tocar instrumentos etc.)",
)


def cadastrar_categorias(apps, schema_editor):
    categoria = apps.get_model("atividades", "CategoriaFMR")
    catalogo = categoria.objects.using(schema_editor.connection.alias)
    for nome in CATEGORIAS_FMR:
        if not catalogo.filter(nome=nome).exists():
            catalogo.create(nome=nome, ativa=True)


class Migration(migrations.Migration):
    dependencies = [("atividades", "0017_frequencia_justificada_por_afastamento")]
    operations = [migrations.RunPython(cadastrar_categorias, migrations.RunPython.noop)]
