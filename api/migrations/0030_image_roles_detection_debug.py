from django.db import migrations, models
import django.db.models.deletion
import api.models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0029_detectiontask'),
    ]

    operations = [
        migrations.AddField(
            model_name='imagedata',
            name='original_file',
            field=models.FileField(blank=True, null=True, upload_to=api.models.upload_path),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='preview_file',
            field=models.ImageField(blank=True, null=True, upload_to=api.models.upload_path),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='detection_file',
            field=models.ImageField(blank=True, null=True, upload_to=api.models.upload_path),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='source_width',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='source_height',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='detection_width',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='detection_height',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='preview_scale_x',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='preview_scale_y',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='detection_scale_x',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='imagedata',
            name='detection_scale_y',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='detectiontask',
            name='debug_metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='image_scale',
            name='image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='api.imagedata'),
        ),
        migrations.AddField(
            model_name='image_scale',
            name='scale_x',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='image_scale',
            name='scale_y',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='image_scale',
            name='detection_scale_x',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='image_scale',
            name='detection_scale_y',
            field=models.FloatField(default=1),
        ),
    ]
