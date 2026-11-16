from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("participantes", "0002_telefones")]

    operations = [
        migrations.AddField(
            model_name="participante",
            name="origem_encaminhamento",
            field=models.CharField(
                choices=[("cras", "CRAS"), ("creas", "CREAS"), ("rede", "Outro serviço da rede"),
                         ("outra", "Outra origem")],
                default="", max_length=20, verbose_name="origem do encaminhamento"),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="participante",
            constraint=models.CheckConstraint(
                condition=models.Q(origem_encaminhamento__in=["cras", "creas", "rede", "outra", ""]),
                name="participante_origem_encaminhamento_valida"),
        ),
    ]
