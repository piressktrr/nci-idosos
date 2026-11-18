from django.db import migrations


# Lista do formulário FMR fornecida e autorizada pelo responsável.
MOTIVOS_FMR = (
    "Mudança de endereço",
    "Oferta do serviço em domicílio",
    "Transferência para outro serviço",
    "Óbito",
    "Desistência",
    "Excesso de faltas",
)


def cadastrar_motivos(apps, schema_editor):
    motivo = apps.get_model("participantes", "MotivoDesligamento")
    banco = schema_editor.connection.alias
    for descricao in MOTIVOS_FMR:
        motivo.objects.using(banco).get_or_create(descricao=descricao, defaults={"ativo": True})


class Migration(migrations.Migration):
    dependencies = [
        ("participantes", "0009_motivodesligamento_registromotivodesligamento_and_more"),
    ]

    # Reverter a migration não deve excluir catálogo que já pode estar em uso.
    operations = [migrations.RunPython(cadastrar_motivos, migrations.RunPython.noop)]
