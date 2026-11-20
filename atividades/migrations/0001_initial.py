from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Atividade",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nome", models.CharField(max_length=150, verbose_name="identificação")),
                ("local", models.CharField(max_length=150, verbose_name="local")),
                (
                    "monitor",
                    models.CharField(
                        max_length=150,
                        verbose_name="monitor/oficineiro responsável",
                    ),
                ),
            ],
            options={
                "verbose_name": "atividade",
                "verbose_name_plural": "atividades",
                "ordering": ["nome"],
            },
        ),
    ]
