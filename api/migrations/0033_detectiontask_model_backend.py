from django.db import migrations, models


def add_model_backend_column(apps, schema_editor):
    table_name = 'api_detectiontask'
    column_name = 'model_backend'

    with schema_editor.connection.cursor() as cursor:
        existing_columns = [
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        ]
        if column_name in existing_columns:
            return

        schema_editor.execute(
            "ALTER TABLE {} ADD COLUMN {} varchar(30) NOT NULL DEFAULT '__main__'".format(
                schema_editor.quote_name(table_name),
                schema_editor.quote_name(column_name),
            )
        )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0032_uploadtask'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_model_backend_column, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='detectiontask',
                    name='model_backend',
                    field=models.CharField(default='__main__', max_length=30),
                ),
            ],
        ),
    ]
