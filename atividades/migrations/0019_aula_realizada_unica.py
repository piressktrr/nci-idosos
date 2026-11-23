from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('atividades', '0018_categorias_padrao_fmr'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='aula',
            constraint=models.UniqueConstraint(condition=models.Q(('situacao', 'realizada')), fields=('atividade', 'data', 'inicio'), name='aula_realizada_unica', violation_error_message='Já existe uma aula realizada desta atividade nesta data e horário de início. Confira a lista de aulas.'),
        ),
    ]
