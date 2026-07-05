

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_userworkspace_ownership'),
    ]

    operations = [
        migrations.AddField(
            model_name='temp_data',
            name='image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='api.imagedata'),
        ),
    ]
