from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0030_image_roles_detection_debug'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExportTask',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('celery_task_id', models.CharField(blank=True, max_length=255)),
                ('image_name', models.CharField(max_length=500)),
                ('timestamp', models.CharField(max_length=80)),
                ('coordinates', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('STARTED', 'Started'), ('SUCCESS', 'Success'), ('FAILURE', 'Failure')], default='PENDING', max_length=20)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('message', models.CharField(blank=True, max_length=255)),
                ('error', models.TextField(blank=True)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('updated_on', models.DateTimeField(auto_now=True)),
                ('image', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='api.imagedata')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_on'],
            },
        ),
    ]
