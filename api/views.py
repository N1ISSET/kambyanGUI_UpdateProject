import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse
from django.conf import settings
from django.utils import timezone
from django.db.models.query import QuerySet
from django.http.response import HttpResponse, JsonResponse
from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework import generics, serializers
from api.models import *
from api.serializers import *
from rest_framework.decorators import APIView
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .mediaFileHandler import FileHandler
from PIL import Image
Image.MAX_IMAGE_PIXELS = 933120000
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
import json
import os
import subprocess
import threading
from io import BytesIO
from datetime import timedelta



# Create your views here.
def get_workspace(request):
    return get_user_workspace(request.user)


def get_workspace_paths(request):
    workspace = get_workspace(request)
    return {
        'workspace': workspace,
        'media': workspace.absolute_path,
        'temp': os.path.join(workspace.absolute_path, 'tempIMG'),
        'gdal': os.path.join(workspace.absolute_path, 'gdalIMG'),
        'media_tiles': os.path.join(workspace.absolute_path, 'media'),
        'zip': os.path.join(workspace.absolute_path, 'zip'),
    }


def is_admin_user(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser or getattr(getattr(user, 'workspace', None), 'role', None) == UserWorkspace.Role.ADMIN


class IsAdminUserWorkspace(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin_user(request.user))


def user_payload(user):
    workspace = get_user_workspace(user)
    return {
        'id': user.id,
        'name': user.first_name or user.username,
        'email': user.email,
        'role': workspace.role,
        'folder': workspace.folder_name,
        'is_active': user.is_active,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'image_count': ImageData.objects.filter(owner=user).count(),
    }


def image_file_payload(image):
    return {
        'id': image.id,
        'owner_id': image.owner_id,
        'owner_name': image.owner.first_name or image.owner.username if image.owner else '',
        'owner_email': image.owner.email if image.owner else '',
        'uploaded_on': image.uploaded_on,
        'image_file': image.image_file.url if image.image_file else '',
        'original_file': image.original_file.url if image.original_file else '',
        'preview_file': image.preview_file.url if image.preview_file else '',
        'detection_file': image.detection_file.url if image.detection_file else '',
        'image_name': file_name_from_url(image.original_file.name if image.original_file else image.image_file.name if image.image_file else ''),
    }


def delete_image_files(image):
    for field_name in ['image_file', 'original_file', 'preview_file', 'detection_file']:
        field = getattr(image, field_name, None)
        if field and field.name:
            try:
                field.delete(save=False)
            except Exception as error:
                print('Failed to delete {} for image {}: {}'.format(field_name, image.id, error))


def delete_client_workspace(user):
    try:
        workspace = get_user_workspace(user)
    except Exception:
        workspace = None
    if workspace and workspace.absolute_path and os.path.isdir(workspace.absolute_path):
        media_root = os.path.abspath(settings.MEDIA_ROOT)
        workspace_path = os.path.abspath(workspace.absolute_path)
        if workspace_path.startswith(media_root) and workspace_path != media_root:
            shutil.rmtree(workspace_path, ignore_errors=True)


def owned_queryset(model, request):
    queryset = model.objects.all()
    if is_admin_user(request.user):
        return queryset
    return queryset.filter(owner=request.user)


def clear_owned_data(request, *models):
    for model in models:
        owned_queryset(model, request).delete()


def save_owned_serializer(serializer, request):
    if serializer.is_valid():
        serializer.save(owner=request.user)
        return True
    return False


def get_owned_image(request, image_id=None, image_file=None):
    queryset = owned_queryset(ImageData, request)
    if image_id:
        return queryset.filter(id=image_id).first()

    if image_file:
        file_name = file_name_from_url(image_file)
        return queryset.filter(image_file__endswith=file_name).order_by('-uploaded_on').first()

    return None


def existing_image_queryset(request):
    queryset = owned_queryset(ImageData, request)
    missing_ids = []
    pending_upload_image_ids = set(owned_queryset(UploadTask, request).filter(
        status__in=[UploadTask.Status.PENDING, UploadTask.Status.STARTED],
    ).values_list('image_id', flat=True))

    for image in queryset:
        if image.id in pending_upload_image_ids:
            continue
        if not image.image_file or not image.image_file.storage.exists(image.image_file.name):
            missing_ids.append(image.id)

    if missing_ids:
        queryset.filter(id__in=missing_ids).delete()

    return queryset.exclude(id__in=missing_ids)


def file_name_from_url(value):
    return os.path.basename(unquote(urlparse(str(value)).path))


def clean_files(folder, extensions):
    os.makedirs(folder, exist_ok=True)
    for file_name in os.listdir(folder):
        path = os.path.join(folder, file_name)
        if os.path.isfile(path) and file_name.endswith(extensions):
            os.remove(path)


def save_uploaded_file(folder, uploaded_file):
    os.makedirs(folder, exist_ok=True)
    file_name = file_name_from_url(uploaded_file)
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)
    storage = FileSystemStorage(location=folder)
    saved_name = storage.save(file_name, uploaded_file)
    return os.path.join(folder, saved_name)


def save_pending_upload_image(request, uploaded_file):
    file_name = file_name_from_url(uploaded_file)
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)
    image = ImageData(owner=request.user)
    image.original_file.save(file_name, uploaded_file, save=False)
    image.save()
    return image


def read_gdalinfo(file_path, as_json=False):
    args = ['gdalinfo', file_path]
    if as_json:
        args.append('-json')
    try:
        return subprocess.check_output(args, universal_newlines=True, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return '{}'.format('{}' if as_json else '')


def default_image_metadata():
    return {
        'X_Origin': float(0),
        'Y_Origin': float(0),
        'Pixel_SizeX': float(0),
        'Pixel_SizeY': float(0),
    }


def metadata_from_gdal_file(gdal_file):
    metadata_text = read_gdalinfo(gdal_file, as_json=True)
    metatxt = str(read_gdalinfo(gdal_file))
    try:
        metadata = json.loads(metadata_text)
    except json.JSONDecodeError:
        metadata = {}

    if 'geoTransform' not in metadata:
        print('No geoTransform found this image')
        return default_image_metadata(), metatxt

    print(metadata['geoTransform'])
    print('X_Origin:', float(metadata['geoTransform'][0]))
    print('Y_Origin:', float(metadata['geoTransform'][3]))
    print('Pixel_SizeX:', float(metadata['geoTransform'][1]))
    print('Pixel_SizeY:', float(metadata['geoTransform'][5]))
    return {
        'X_Origin': float(metadata['geoTransform'][0]),
        'Y_Origin': float(metadata['geoTransform'][3]),
        'Pixel_SizeX': float(metadata['geoTransform'][1]),
        'Pixel_SizeY': float(metadata['geoTransform'][5]),
    }, metatxt


def default_metadata_text(file_name):
    return (
        'Files: {}\n'
        'No GeoTIFF metadata found. Default coordinates were used.\n'
        'X_Origin: 0\n'
        'Y_Origin: 0\n'
        'Pixel_SizeX: 0\n'
        'Pixel_SizeY: 0\n'
    ).format(file_name)


def safe_rmtree_children(folder):
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.isfile(path):
            os.remove(path)


def is_tiff_file(uploaded_file):
    return str(uploaded_file).lower().endswith((".tif", ".tiff"))


def is_csv_file(uploaded_file):
    return str(uploaded_file).lower().endswith(".csv")


def validate_tiff_upload(uploaded_file):
    if not is_tiff_file(uploaded_file):
        raise ValidationError("Image uploads only allow .tif or .tiff files.")


def validate_csv_upload(uploaded_file):
    if not is_csv_file(uploaded_file):
        raise ValidationError("Plot data imports only allow .csv files.")


def validate_kambyan_password(password, user=None):
    validate_password(password, user)
    if re.search(r"\s", password):
        raise ValidationError("Password cannot contain spaces.")
    if "_" not in password:
        raise ValidationError("Password must include an underscore (_).")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must include an uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must include a lowercase letter.")
    if not re.search(r"\d", password):
        raise ValidationError("Password must include a number.")


def csv_value(row, key, index, default=None):
    if isinstance(row, dict):
        normalized_key = key.strip().lower().replace("_", " ")
        for row_key, value in row.items():
            if row_key is None:
                continue
            if str(row_key).strip().lower().replace("_", " ") == normalized_key:
                return value
        return default

    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]

    return default


def default_review_scale(width, height):
    if (width * height) > 200000000:
        return round(15000 / max(width, height), 1)
    return 1


PREVIEW_MAX_DIMENSION = 8000
# The detector was trained/tuned around the legacy resized image scale.
# Full-resolution orthomosaics make leaf overlaps look like separate trees.
DETECTION_MAX_DIMENSION = int(os.environ.get('KAMBYAN_DETECTION_MAX_DIMENSION', '7707'))


def preview_scale_for_image(width, height):
    longest_edge = max(width, height)
    if longest_edge > PREVIEW_MAX_DIMENSION:
        return PREVIEW_MAX_DIMENSION / float(longest_edge)
    return 1


def detection_scale_for_image(width, height):
    if DETECTION_MAX_DIMENSION <= 0:
        return 1
    longest_edge = max(width, height)
    if longest_edge > DETECTION_MAX_DIMENSION:
        return DETECTION_MAX_DIMENSION / float(longest_edge)
    return 1


def image_to_content_file(image, file_name):
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), name=file_name)


def create_image_record(request, uploaded_file, img_metadata, preview_scale=None, temp_data=None):
    file_name = file_name_from_url(uploaded_file)
    stem = os.path.splitext(file_name)[0]
    image = Image.open(uploaded_file)
    image.load()
    source_width, source_height = image.size
    source_rgb = image.convert('RGB')
    detection_scale = detection_scale_for_image(source_width, source_height)
    detection_width = max(1, int(round(source_width * detection_scale)))
    detection_height = max(1, int(round(source_height * detection_scale)))
    detection_image = source_rgb.resize((detection_width, detection_height)) if detection_scale != 1 else source_rgb.copy()
    detection_width, detection_height = detection_image.size
    preview_scale = preview_scale if preview_scale is not None else preview_scale_for_image(source_width, source_height)
    preview_width = max(1, int(round(source_width * preview_scale)))
    preview_height = max(1, int(round(source_height * preview_scale)))
    preview_image = source_rgb.resize((preview_width, preview_height)) if preview_scale != 1 else source_rgb.copy()

    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)

    uploaded_image = ImageData(
        owner=request.user,
        source_width=source_width,
        source_height=source_height,
        detection_width=detection_width,
        detection_height=detection_height,
        preview_scale_x=preview_width / float(detection_width or 1),
        preview_scale_y=preview_height / float(detection_height or 1),
        detection_scale_x=detection_width / float(source_width or 1),
        detection_scale_y=detection_height / float(source_height or 1),
    )
    uploaded_image.original_file.save(file_name, uploaded_file, save=False)
    uploaded_image.detection_file.save("{}_detection.png".format(stem), image_to_content_file(detection_image, "{}_detection.png".format(stem)), save=False)
    uploaded_image.image_file.save("{}_preview.png".format(stem), image_to_content_file(preview_image, "{}_preview.png".format(stem)), save=False)
    uploaded_image.preview_file.name = uploaded_image.image_file.name
    uploaded_image.save()

    serializer = ImageMetadataSerializer(data=img_metadata)
    save_owned_serializer(serializer, request)

    scale_data = {
        "image": uploaded_image.id,
        "scale": uploaded_image.preview_scale_x,
        "scale_x": uploaded_image.preview_scale_x,
        "scale_y": uploaded_image.preview_scale_y,
        "detection_scale_x": uploaded_image.detection_scale_x,
        "detection_scale_y": uploaded_image.detection_scale_y,
    }
    serializer = ScaleSerializer(data=scale_data)
    save_owned_serializer(serializer, request)

    if temp_data:
        for row in temp_data:
            serializer = TempSerializer(data=row)
            if serializer.is_valid():
                serializer.save(owner=request.user, image=uploaded_image)

    return uploaded_image


def ensure_detection_assets(image):
    source_width = image.source_width or image.image_width or 0
    source_height = image.source_height or image.image_height or 0
    detection_scale = detection_scale_for_image(source_width, source_height)
    expected_detection_width = max(1, int(round(source_width * detection_scale))) if source_width else 0
    expected_detection_height = max(1, int(round(source_height * detection_scale))) if source_height else 0
    detection_matches_expected_size = (
        image.detection_width
        and image.detection_height
        and int(image.detection_width) == int(expected_detection_width)
        and int(image.detection_height) == int(expected_detection_height)
    )
    if (
        image.detection_file
        and image.detection_file.storage.exists(image.detection_file.name)
        and detection_matches_expected_size
    ):
        return image

    source_field = image.original_file if image.original_file else image.image_file
    if not source_field or not source_field.storage.exists(source_field.name):
        return None

    source_name = file_name_from_url(source_field.name)
    stem = os.path.splitext(source_name)[0]
    source_image = Image.open(source_field.path)
    source_image.load()
    source_width, source_height = source_image.size
    source_rgb = source_image.convert('RGB')
    detection_scale = detection_scale_for_image(source_width, source_height)
    detection_width = max(1, int(round(source_width * detection_scale)))
    detection_height = max(1, int(round(source_height * detection_scale)))
    detection_image = source_rgb.resize((detection_width, detection_height)) if detection_scale != 1 else source_rgb.copy()
    detection_width, detection_height = detection_image.size

    preview_width = image.image_width or detection_width
    preview_height = image.image_height or detection_height
    image.source_width = image.source_width or source_width
    image.source_height = image.source_height or source_height
    image.detection_width = detection_width
    image.detection_height = detection_height
    image.preview_scale_x = preview_width / float(detection_width or 1)
    image.preview_scale_y = preview_height / float(detection_height or 1)
    image.detection_scale_x = detection_width / float(image.source_width or detection_width or 1)
    image.detection_scale_y = detection_height / float(image.source_height or detection_height or 1)
    if not image.preview_file and image.image_file:
        image.preview_file.name = image.image_file.name
    image.detection_file.save(
        "{}_detection.png".format(stem),
        image_to_content_file(detection_image, "{}_detection.png".format(stem)),
        save=False,
    )
    image.save()

    Image_scale.objects.update_or_create(
        owner=image.owner,
        image=image,
        defaults={
            "scale": image.preview_scale_x,
            "scale_x": image.preview_scale_x,
            "scale_y": image.preview_scale_y,
            "detection_scale_x": image.detection_scale_x,
            "detection_scale_y": image.detection_scale_y,
        },
    )
    return image


def first_present_value(row, keys, default=None):
    for key, index in keys:
        value = csv_value(row, key, index, None)
        if value not in (None, ""):
            return value
    return default


def parse_review_coordinate_rows(csv_data, fallback_scale=None):
    coordinate_rows = []
    for row in csv_data:
        if isinstance(row, (list, tuple)):
            if len(row) >= 6:
                scale = row[3]
                x_pixel = row[4]
                y_pixel = row[5]
            elif len(row) == 5:
                scale = fallback_scale
                x_pixel = row[1]
                y_pixel = row[2]
            elif len(row) >= 4:
                scale = row[3]
                x_pixel = row[1]
                y_pixel = row[2]
            else:
                continue
        else:
            scale = first_present_value(row, [("Scale", 3)], fallback_scale)
            x_pixel = first_present_value(row, [
                ("X Pixel", 4),
                ("Pixel X", 1),
                ("X Coordinate", 1),
            ])
            y_pixel = first_present_value(row, [
                ("Y Pixel", 5),
                ("Pixel Y", 2),
                ("Y Coordinate", 2),
            ])

        if scale in (None, "") or x_pixel in (None, "") or y_pixel in (None, ""):
            continue

        try:
            coordinate_rows.append({
                "scale": float(scale),
                "x_pixel": float(x_pixel),
                "y_pixel": float(y_pixel),
            })
        except (TypeError, ValueError):
            continue

    return coordinate_rows


class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        name = request.data.get('name', '').strip()
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not name or not email or not password:
            return Response({'error': 'Name, email, and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=email).exists():
            return Response({'error': 'An account with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        password_user = User(username=email, email=email, first_name=name)
        try:
            validate_kambyan_password(password, password_user)
        except ValidationError as error:
            return Response({'error': ' '.join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
        workspace = get_user_workspace(user)
        login(request, user)
        # A newly created account should require a new login when the browser
        # is next opened, just like a normal login without "Remember me".
        request.session.set_expiry(0)
        return Response({
            'name': user.first_name or user.username,
            'email': user.email,
            'role': workspace.role,
            'folder': workspace.folder_name,
        }, status=status.HTTP_201_CREATED)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        confirm_password = request.data.get('confirm_password', '')

        if not email or not password or not confirm_password:
            return Response({'error': 'Email, new password, and confirmation are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_email(email)
        except ValidationError:
            return Response({'error': 'Enter a valid email address.'}, status=status.HTTP_400_BAD_REQUEST)

        if password != confirm_password:
            return Response({'error': 'Passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(username=email).first()
        if not user:
            return Response({'error': 'No account was found for this email.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            validate_kambyan_password(password, user)
        except ValidationError as error:
            return Response({'error': ' '.join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=['password'])
        return Response({'message': 'Password has been reset. Please login with your new password.'}, status=status.HTTP_200_OK)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response({'error': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        existing_user = User.objects.filter(username=email).first()
        if existing_user and not existing_user.is_active and existing_user.check_password(password):
            return Response({
                'error': 'Your account is inactive, please contact system admin for further assistance.'
            }, status=status.HTTP_403_FORBIDDEN)

        user = authenticate(request, username=email, password=password)
        if user is None:
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_400_BAD_REQUEST)

        workspace = get_user_workspace(user)
        login(request, user)
        # The default is a browser-only session.  A deliberate opt-in keeps
        # the session active for 14 days across browser restarts.
        if request.data.get('remember_me') is True:
            request.session.set_expiry(60 * 60 * 24 * 14)
        else:
            request.session.set_expiry(0)
        return Response({
            'name': user.first_name or user.username,
            'email': user.email,
            'role': workspace.role,
            'folder': workspace.folder_name,
        }, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user), status=status.HTTP_200_OK)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out'}, status=status.HTTP_200_OK)


class AdminUserListView(APIView):
    permission_classes = [IsAdminUserWorkspace]

    def get(self, request):
        users = User.objects.all().order_by('username')
        return Response([user_payload(user) for user in users], status=status.HTTP_200_OK)


class AdminUserDetailView(APIView):
    permission_classes = [IsAdminUserWorkspace]

    def patch(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'error': 'Account not found.'}, status=status.HTTP_404_NOT_FOUND)
        if is_admin_user(user):
            return Response({'error': 'Admin accounts cannot be edited here.'}, status=status.HTTP_403_FORBIDDEN)

        if 'is_active' not in request.data:
            return Response({'error': 'No account access change was provided.'}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = bool(request.data.get('is_active'))
        user.save(update_fields=['is_active'])
        return Response(user_payload(user), status=status.HTTP_200_OK)

    def delete(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'error': 'Account not found.'}, status=status.HTTP_404_NOT_FOUND)
        if is_admin_user(user):
            return Response({'error': 'Admin accounts cannot be deleted here.'}, status=status.HTTP_403_FORBIDDEN)

        delete_client_workspace(user)
        user.delete()
        return Response({'message': 'Client account and images deleted.'}, status=status.HTTP_200_OK)


class AdminImageListView(APIView):
    permission_classes = [IsAdminUserWorkspace]

    def get(self, request):
        user_id = request.query_params.get('user_id')
        images = existing_image_queryset(request).select_related('owner').order_by('-uploaded_on')
        if user_id:
            images = images.filter(owner_id=user_id)
        return Response([image_file_payload(image) for image in images], status=status.HTTP_200_OK)


class AdminImageDetailView(APIView):
    permission_classes = [IsAdminUserWorkspace]

    def delete(self, request, image_id):
        image = ImageData.objects.filter(id=image_id).select_related('owner').first()
        if not image:
            return Response({'error': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        if image.owner and is_admin_user(image.owner):
            return Response({'error': 'Admin account images cannot be removed here.'}, status=status.HTTP_403_FORBIDDEN)

        delete_image_files(image)
        image.delete()
        return Response({'message': 'Image removed from client account.'}, status=status.HTTP_200_OK)


class ResizeImageView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ImageSerializers

    def get_queryset(self):
        return owned_queryset(ImageData, self.request)

    def post(self, request, *args, **kwargs):
        image_files = request.FILES.getlist('image_file')
        if not image_files:
            image_file = request.data.get('image_file')
            image_files = [image_file] if image_file else []

        if not image_files:
            return Response({'error': 'Image is required'}, status=status.HTTP_400_BAD_REQUEST)

        jobs = []
        for image_file in image_files:
            try:
                validate_tiff_upload(image_file)
            except ValidationError as error:
                return Response({'error': ' '.join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)

            image = save_pending_upload_image(request, image_file)
            job = UploadTask.objects.create(
                owner=request.user,
                image=image,
                kind=UploadTask.Kind.IMAGE,
                status=UploadTask.Status.PENDING,
                progress=0,
                message='Queued for upload processing',
            )
            queue_upload_task(job)
            jobs.append(job)

        payload = {
            'id': jobs[0].id,
            'jobs': [upload_task_payload(job) for job in jobs],
            'count': len(jobs),
        }
        return Response(payload, status=status.HTTP_202_ACCEPTED)
    
class MetatxtView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        GDAL_IMG = get_workspace_paths(request)['gdal']
        meta_path = os.path.join(GDAL_IMG, 'metaimg.txt')
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                metatxt = f.read()
        else:
            metatxt = ''
        return Response({'message': metatxt})

class ImageView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ImageSerializers

    def get_queryset(self):
        return existing_image_queryset(self.request)

    def post(self, request, *args, **kwargs):
        image_scale = request.data['image_scale']
        scaling = float(request.data['scale'])

        clear_owned_data(request, Image_scale, Plot_Coordinate, Annotate_Data, Temp_Data)
        create_image_record(request, image_scale, default_image_metadata(), scaling)
        return HttpResponse({'message': 'Uploaded'}, status=200)
    
    
# To run the Tree detection
from Detection.kambyan_main import*
from api.tasks import _run_detection_job, _run_export_job, _run_upload_job, run_detection_task, run_export_task, run_upload_task

DETECTION_PENDING_STALE_AFTER = timedelta(minutes=2)
DETECTION_STARTED_STALE_AFTER = timedelta(minutes=10)


def detection_task_payload(job):
    image_display_name = job.image_name
    if job.image:
        image_source = job.image.original_file or job.image.image_file or job.image.detection_file
        if image_source:
            image_display_name = file_name_from_url(image_source.name)

    return {
        'id': job.id,
        'task_id': job.celery_task_id,
        'status': job.status,
        'progress': job.progress,
        'message': job.message,
        'error': job.error,
        'image_id': job.image_id,
        'image_name': job.image_name,
        'image_display_name': image_display_name,
        'model_backend': job.model_backend,
        'debug_metadata': job.debug_metadata,
        'created_on': job.created_on,
        'updated_on': job.updated_on,
    }


def export_task_payload(job):
    image_display_name = job.image_name
    if job.image:
        image_source = job.image.original_file or job.image.image_file or job.image.detection_file
        if image_source:
            image_display_name = file_name_from_url(image_source.name)

    zip_stem = os.path.splitext(job.image_name)[0]
    workspace = get_user_workspace(job.owner)
    zip_name = "{}.zip".format(zip_stem)
    zip_path = os.path.join(workspace.absolute_path, 'zip', zip_name)
    zip_url = "{}{}/zip/{}".format(settings.MEDIA_URL, workspace.relative_path.replace("\\", "/"), zip_name)
    artifact_exists = os.path.exists(zip_path)

    return {
        'id': job.id,
        'task_id': job.celery_task_id,
        'status': job.status,
        'progress': job.progress,
        'message': job.message,
        'error': job.error,
        'image_id': job.image_id,
        'image_name': job.image_name,
        'image_display_name': image_display_name,
        'zip_url': zip_url,
        'artifact_exists': artifact_exists,
        'created_on': job.created_on,
        'updated_on': job.updated_on,
    }


def upload_task_payload(job):
    image_file = ''
    preview_file = ''
    original_file = ''
    if job.image:
        image_file = job.image.image_file.url if job.image.image_file else ''
        preview_file = job.image.preview_file.url if job.image.preview_file else ''
        original_file = job.image.original_file.url if job.image.original_file else ''

    return {
        'id': job.id,
        'task_id': job.celery_task_id,
        'status': job.status,
        'progress': job.progress,
        'message': job.message,
        'error': job.error,
        'kind': job.kind,
        'image_id': job.image_id,
        'image_file': image_file,
        'preview_file': preview_file,
        'original_file': original_file,
        'created_on': job.created_on,
        'updated_on': job.updated_on,
    }


def queue_upload_task(job):
    try:
        celery_result = run_upload_task.delay(job.id)
        if celery_result is not None and getattr(celery_result, 'id', None):
            job.celery_task_id = celery_result.id
            job.save(update_fields=['celery_task_id', 'updated_on'])
    except Exception as error:
        print('Celery upload queue failed, running local background task: {}'.format(error))
        threading.Thread(target=_run_upload_job, args=(job.id,), daemon=True).start()


class UploadStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        job_id = request.query_params.get('job_id')
        jobs = owned_queryset(UploadTask, request)
        if job_id:
            job = jobs.filter(id=job_id).select_related('image').first()
        else:
            job = jobs.select_related('image').first()

        if not job:
            return Response({'message': 'No upload task found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(upload_task_payload(job))


def timestamp_from_datetime(value):
    date = value.split('T')[0]
    times = value.split('T')[1].split('.')[0].replace(":", "-")
    return date +"_"+ times


def fail_stale_detection_tasks(queryset):
    pending_stale_before = timezone.now() - DETECTION_PENDING_STALE_AFTER
    started_stale_before = timezone.now() - DETECTION_STARTED_STALE_AFTER
    queryset.filter(
        status=DetectionTask.Status.PENDING,
        updated_on__lt=pending_stale_before,
    ).update(
        status=DetectionTask.Status.FAILURE,
        message='Detection queue expired',
        error='The detection task was queued but the worker did not start it. Please start detection again.',
    )
    queryset.filter(
        status=DetectionTask.Status.STARTED,
        updated_on__lt=started_stale_before,
    ).update(
        status=DetectionTask.Status.FAILURE,
        message='Detection stopped before completion',
        error='The detection worker stopped before this job finished. Please start detection again.',
    )


class ProcessIMG(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        job_id = request.query_params.get('job_id')
        image_id = request.query_params.get('image_id')
        jobs = owned_queryset(DetectionTask, request)
        if job_id:
            job = jobs.filter(id=job_id).first()
        elif image_id:
            job = jobs.filter(image_id=image_id).first()
        else:
            job = jobs.first()

        if not job:
            return Response({'message': 'No detection task found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(detection_task_payload(job))

    def post(self, request):
        #print(request.data['path'])
        image = get_owned_image(request, request.data.get('image_id'), request.data.get('image'))
        if not image:
            return Response({'error': 'Image is required'}, status=status.HTTP_400_BAD_REQUEST)
        image = ensure_detection_assets(image)
        if not image or not image.detection_file:
            return Response({'error': 'Detection image is missing and could not be rebuilt for this upload'}, status=status.HTTP_400_BAD_REQUEST)

        fail_stale_detection_tasks(owned_queryset(DetectionTask, request))
        active_job = owned_queryset(DetectionTask, request).filter(
            image=image,
            status__in=[DetectionTask.Status.PENDING, DetectionTask.Status.STARTED],
        ).first()
        if active_job:
            return Response(detection_task_payload(active_job), status=status.HTTP_202_ACCEPTED)

        owned_queryset(Temp_Data, request).filter(image=image).delete()
        img_file = file_name_from_url(image.detection_file.name)
        Timestamp = timestamp_from_datetime(request.data['datetime'])
        print(img_file)
        job = DetectionTask.objects.create(
            owner=request.user,
            image=image,
            image_name=img_file,
            timestamp=Timestamp,
            model_backend=DetectionTask.DEFAULT_MODEL_BACKEND,
            status=DetectionTask.Status.PENDING,
            progress=0,
            message='Queued for detection',
        )
        try:
            celery_result = run_detection_task.delay(job.id)
            if celery_result is not None and getattr(celery_result, 'id', None):
                job.celery_task_id = celery_result.id
                job.save(update_fields=['celery_task_id', 'updated_on'])
        except Exception as error:
            print('Celery detection queue failed, running local background task: {}'.format(error))
            threading.Thread(target=_run_detection_job, args=(job.id,), daemon=True).start()

        return Response(detection_task_payload(job), status=status.HTTP_202_ACCEPTED)

import json
class PlottingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        job_id = request.query_params.get('job_id')
        image_id = request.query_params.get('image_id')
        jobs = owned_queryset(ExportTask, request)
        if job_id:
            job = jobs.filter(id=job_id).first()
        elif image_id:
            job = jobs.filter(image_id=image_id).first()
        else:
            job = jobs.first()

        if not job:
            return Response({'message': 'No export task found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(export_task_payload(job))

    def post(self, request):
        image = get_owned_image(request, request.data.get('image_id'), request.data.get('image_file'))
        if not image:
            return Response({'error': 'Image is required'}, status=status.HTTP_400_BAD_REQUEST)
        image = ensure_detection_assets(image)
        if not image or not image.detection_file:
            return Response({'error': 'Detection image is missing for this upload'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            coordinates = json.loads(request.data['coordinate'])
        except (KeyError, TypeError, json.JSONDecodeError):
            return Response({'error': 'Coordinates are required'}, status=status.HTTP_400_BAD_REQUEST)

        active_job = owned_queryset(ExportTask, request).filter(
            image=image,
            status__in=[ExportTask.Status.PENDING, ExportTask.Status.STARTED],
        ).first()
        if active_job:
            return Response(export_task_payload(active_job), status=status.HTTP_202_ACCEPTED)

        timestamp = timestamp_from_datetime(request.data['datetime'])
        img_file = file_name_from_url(image.image_file.name if image.image_file else request.data.get('image_file', 'image'))
        job = ExportTask.objects.create(
            owner=request.user,
            image=image,
            image_name=img_file,
            timestamp=timestamp,
            coordinates=coordinates,
            status=ExportTask.Status.PENDING,
            progress=0,
            message='Queued for export preparation',
        )
        try:
            celery_result = run_export_task.delay(job.id)
            if celery_result is not None and getattr(celery_result, 'id', None):
                job.celery_task_id = celery_result.id
                job.save(update_fields=['celery_task_id', 'updated_on'])
        except Exception as error:
            print('Celery export queue failed, running local background task: {}'.format(error))
            threading.Thread(target=_run_export_job, args=(job.id,), daemon=True).start()

        return Response(export_task_payload(job), status=status.HTTP_202_ACCEPTED)


class TempView (APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        image = get_owned_image(request, request.query_params.get('image_id'))
        if not image:
            return Response([])
        temp_data = owned_queryset(Temp_Data, request)
        temp_data = temp_data.filter(image=image)
        serializer = TempSerializer(temp_data, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Add a single new marker point."""
        image = get_owned_image(request, request.data.get('image_id'))
        if not image:
            return Response({'error': 'Image is required'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = TempSerializer(data={
            'lat': request.data.get('lat'),
            'lng': request.data.get('lng'),
        })
        if serializer.is_valid():
            serializer.save(owner=request.user, image=image)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        """Update a marker's position after drag. Expects old_lat, old_lng, lat, lng."""
        old_lat = request.data.get('old_lat')
        old_lng = request.data.get('old_lng')
        new_lat = request.data.get('lat')
        new_lng = request.data.get('lng')
        image = get_owned_image(request, request.data.get('image_id'))
        if not image:
            return Response({'error': 'Image is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            marker = owned_queryset(Temp_Data, request).filter(image=image, lat=old_lat, lng=old_lng).first()
            if marker is None:
                return Response({'error': 'Marker not found'}, status=status.HTTP_404_NOT_FOUND)
            marker.lat = new_lat
            marker.lng = new_lng
            marker.save()
            return Response({'lat': marker.lat, 'lng': marker.lng}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        """Remove a marker by lat/lng."""
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        image = get_owned_image(request, request.data.get('image_id'))
        if not image:
            return Response({'error': 'Image is required'}, status=status.HTTP_400_BAD_REQUEST)

        if lat is None and lng is None:
            owned_queryset(Temp_Data, request).filter(image=image).delete()
            return Response({'message': 'Deleted'}, status=status.HTTP_200_OK)

        deleted, _ = owned_queryset(Temp_Data, request).filter(image=image, lat=lat, lng=lng).delete()
        if deleted:
            return Response({'message': 'Deleted'}, status=status.HTTP_200_OK)
        return Response({'error': 'Marker not found'}, status=status.HTTP_404_NOT_FOUND)

class ScaleView (APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        image = get_owned_image(request, request.query_params.get('image_id'))
        scale_data = owned_queryset(Image_scale, request)
        if image:
            scale_data = scale_data.filter(image=image)
        serializer = ScaleSerializer(scale_data, many=True)
        return Response(serializer.data)

class PlotCoordinateView (APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plot_data = owned_queryset(Plot_Coordinate, request)
        serializer = PlotSerializer(plot_data, many=True)
        return Response(serializer.data)

class AnnotateDataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        annotate_data = owned_queryset(Annotate_Data, request)
        serializers = AnnotateSerializer(annotate_data, many=True)
        return Response(serializers.data)
    
class ImageMetadataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        img_meta = owned_queryset(Image_Metadata, request)
        serializers = ImageMetadataSerializer(img_meta, many=True)
        return Response(serializers.data)

class ReviewView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ImageSerializers

    def get_queryset(self):
        return owned_queryset(ImageData, self.request)

    def post(self, request, *args, **kwargs):
        image_file = request.data.get('image_file')
        csv_file = request.data.get('csv_data')
        csv_file_name = request.data.get('csv_file_name')
        if not image_file or csv_file is None or not csv_file_name:
            return Response({'error': 'Image and CSV data are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_tiff_upload(image_file)
            validate_csv_upload(csv_file_name)
        except ValidationError as error:
            return Response({'error': ' '.join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            csv_data = json.loads(csv_file)
        except (TypeError, json.JSONDecodeError):
            return Response({'error': 'CSV data is invalid.'}, status=status.HTTP_400_BAD_REQUEST)

        image = save_pending_upload_image(request, image_file)
        job = UploadTask.objects.create(
            owner=request.user,
            image=image,
            kind=UploadTask.Kind.REVIEW,
            status=UploadTask.Status.PENDING,
            progress=0,
            message='Queued for review upload processing',
            csv_data=csv_data,
        )
        queue_upload_task(job)
        return Response(upload_task_payload(job), status=status.HTTP_202_ACCEPTED)
