from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from pathlib import Path
import os

# Create your models here.

def upload_path(instance, filename):
    filename = filename.split("/")[-1].split("\\")[-1]
    if instance.owner_id:
        workspace = get_user_workspace(instance.owner)
        return '/'.join(['accounts', workspace.folder_name, filename])
    return filename

class UserWorkspace(models.Model):
    class Role(models.TextChoices):
        USER = 'user', _('User')
        VIEWER = 'viewer', _('Viewer')
        ADMIN = 'admin', _('Admin')

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    folder_name = models.SlugField(max_length=160, unique=True)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return '{} ({})'.format(self.user.username, self.role)

    @property
    def relative_path(self):
        return os.path.join('accounts', self.folder_name)

    @property
    def absolute_path(self):
        return os.path.join(settings.MEDIA_ROOT, self.relative_path)

    def ensure_folders(self):
        for folder in ['', 'tempIMG', 'gdalIMG', 'media', 'zip']:
            os.makedirs(os.path.join(self.absolute_path, folder), exist_ok=True)


def get_user_workspace(user):
    base_name = slugify(user.email.split('@')[0] if user.email else user.username) or 'user'
    folder_name = '{}-{}'.format(base_name, user.id)
    role = UserWorkspace.Role.ADMIN if user.is_staff or user.is_superuser else UserWorkspace.Role.USER
    workspace, created = UserWorkspace.objects.get_or_create(
        user=user,
        defaults={'folder_name': folder_name, 'role': role},
    )
    if workspace.role != UserWorkspace.Role.ADMIN and role == UserWorkspace.Role.ADMIN:
        workspace.role = role
        workspace.save(update_fields=['role'])
    workspace.ensure_folders()
    return workspace

class ImageData(models.Model):
    id = models.AutoField(primary_key=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    uploaded_on = models.DateTimeField(auto_now_add=True)
    image_width = models.PositiveIntegerField(blank=True, null=True)
    image_height = models.PositiveIntegerField(blank=True, null=True)
    image_file = models.ImageField(blank=True, null=True, upload_to=upload_path, height_field="image_height", width_field="image_width")
    original_file = models.FileField(blank=True, null=True, upload_to=upload_path)
    preview_file = models.ImageField(blank=True, null=True, upload_to=upload_path)
    detection_file = models.ImageField(blank=True, null=True, upload_to=upload_path)
    source_width = models.PositiveIntegerField(blank=True, null=True)
    source_height = models.PositiveIntegerField(blank=True, null=True)
    detection_width = models.PositiveIntegerField(blank=True, null=True)
    detection_height = models.PositiveIntegerField(blank=True, null=True)
    preview_scale_x = models.FloatField(default=1)
    preview_scale_y = models.FloatField(default=1)
    detection_scale_x = models.FloatField(default=1)
    detection_scale_y = models.FloatField(default=1)
    
class Plot_Coordinate(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    ids = models.IntegerField()
    X_Coordinate = models.FloatField()
    Y_Coordinate = models.FloatField()
    Scale = models.FloatField()
    X_Pixel = models.FloatField()
    Y_Pixel = models.FloatField()
    
    class Meta:
        ordering = ['ids']
    
    
    def __str__(self):
        return str(self.ids)
    
    
    
class Annotate_Data(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    filename = models.TextField()
    width = models.IntegerField()
    height = models.IntegerField()
    classes = models.TextField()
    xmin = models.IntegerField()
    ymin = models.IntegerField()
    xmax = models.IntegerField()
    ymax = models.IntegerField()
    
    
    class Meta:
        ordering = ['filename']
    
    
    def __str__(self):
        return str(self.filename)
    
    
class Temp_Data(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    image = models.ForeignKey(ImageData, blank=True, null=True, on_delete=models.CASCADE)
    lat = models.FloatField()
    lng = models.FloatField()


class DetectionTask(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        STARTED = 'STARTED', _('Started')
        SUCCESS = 'SUCCESS', _('Success')
        FAILURE = 'FAILURE', _('Failure')

    DEFAULT_MODEL_BACKEND = '__main__'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    image = models.ForeignKey(ImageData, blank=True, null=True, on_delete=models.CASCADE)
    celery_task_id = models.CharField(max_length=255, blank=True)
    image_name = models.CharField(max_length=500)
    timestamp = models.CharField(max_length=80)
    model_backend = models.CharField(max_length=30, default=DEFAULT_MODEL_BACKEND)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    debug_metadata = models.JSONField(default=dict, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']


class UploadTask(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        STARTED = 'STARTED', _('Started')
        SUCCESS = 'SUCCESS', _('Success')
        FAILURE = 'FAILURE', _('Failure')

    class Kind(models.TextChoices):
        IMAGE = 'IMAGE', _('Image')
        REVIEW = 'REVIEW', _('Review')

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    image = models.ForeignKey(ImageData, blank=True, null=True, on_delete=models.CASCADE)
    celery_task_id = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.IMAGE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    csv_data = models.JSONField(default=list, blank=True)
    preview_scale = models.FloatField(blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']


class ExportTask(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        STARTED = 'STARTED', _('Started')
        SUCCESS = 'SUCCESS', _('Success')
        FAILURE = 'FAILURE', _('Failure')

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    image = models.ForeignKey(ImageData, blank=True, null=True, on_delete=models.CASCADE)
    celery_task_id = models.CharField(max_length=255, blank=True)
    image_name = models.CharField(max_length=500)
    timestamp = models.CharField(max_length=80)
    coordinates = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']

class Image_Tile(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    link = models.CharField(max_length=1000)
    main_image = models.CharField(max_length=1000)

class Image_scale(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    image = models.ForeignKey(ImageData, blank=True, null=True, on_delete=models.CASCADE)
    scale = models.FloatField()
    scale_x = models.FloatField(default=1)
    scale_y = models.FloatField(default=1)
    detection_scale_x = models.FloatField(default=1)
    detection_scale_y = models.FloatField(default=1)
    
class Image_Metadata(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    X_Origin = models.FloatField()
    Y_Origin = models.FloatField()
    Pixel_SizeX = models.FloatField()
    Pixel_SizeY = models.FloatField()
