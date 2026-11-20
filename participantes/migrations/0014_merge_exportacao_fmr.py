# Junta a exportação CSV (develop) com as migrations do FMR (main).

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("participantes", "0009_exportacao"),
        ("participantes", "0013_perfil_demografico_vigente"),
    ]

    operations = []
