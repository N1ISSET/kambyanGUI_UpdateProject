import threading
import time
import json
import math
import os
import subprocess
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import close_old_connections
from PIL import Image
Image.MAX_IMAGE_PIXELS = 933120000

from api.mediaFileHandler import FileHandler
from api.models import (
    Annotate_Data,
    DetectionTask,
    ExportTask,
    Image_scale,
    ImageData,
    Image_Metadata,
    Plot_Coordinate,
    Temp_Data,
    UploadTask,
    get_user_workspace,
)
from api.serializers import AnnotateSerializer, PlotSerializer, TempSerializer
from Detection.kambyan_main import get_rows, image_tiling, main
import numpy as np

try:
    from celery import shared_task
except ImportError:
    shared_task = None


PREVIEW_MAX_DIMENSION = 8000
# Keep TensorFlow inference at the legacy model scale unless explicitly overridden.
DETECTION_MAX_DIMENSION = int(os.environ.get('KAMBYAN_DETECTION_MAX_DIMENSION', '7707'))


def _workspace_media_path(user):
    return get_user_workspace(user).absolute_path


def _save_job(job, status=None, progress=None, message=None, error=None):
    update_fields = ['updated_on']
    if status is not None:
        job.status = status
        update_fields.append('status')
    if progress is not None:
        job.progress = max(0, min(100, int(progress)))
        update_fields.append('progress')
    if message is not None:
        job.message = message
        update_fields.append('message')
    if error is not None:
        job.error = error
        update_fields.append('error')
    job.save(update_fields=update_fields)


def _safe_rmtree_children(folder):
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
        elif os.path.isfile(path):
            os.remove(path)


def _file_name_from_url(value):
    from urllib.parse import unquote, urlparse
    return os.path.basename(unquote(urlparse(str(value)).path))


def _read_gdalinfo(file_path, as_json=False):
    args = ['gdalinfo', file_path]
    if as_json:
        args.append('-json')
    try:
        return subprocess.check_output(args, universal_newlines=True, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return '{}'.format('{}' if as_json else '')


def _default_image_metadata():
    return {
        'X_Origin': float(0),
        'Y_Origin': float(0),
        'Pixel_SizeX': float(0),
        'Pixel_SizeY': float(0),
    }


def _metadata_from_gdal_file(gdal_file):
    metadata_text = _read_gdalinfo(gdal_file, as_json=True)
    metatxt = str(_read_gdalinfo(gdal_file))
    try:
        metadata = json.loads(metadata_text)
    except json.JSONDecodeError:
        metadata = {}

    if 'geoTransform' not in metadata:
        return _default_image_metadata(), metatxt

    return {
        'X_Origin': float(metadata['geoTransform'][0]),
        'Y_Origin': float(metadata['geoTransform'][3]),
        'Pixel_SizeX': float(metadata['geoTransform'][1]),
        'Pixel_SizeY': float(metadata['geoTransform'][5]),
    }, metatxt


def _default_metadata_text(file_name):
    return (
        'Files: {}\n'
        'No GeoTIFF metadata found. Default coordinates were used.\n'
        'X_Origin: 0\n'
        'Y_Origin: 0\n'
        'Pixel_SizeX: 0\n'
        'Pixel_SizeY: 0\n'
    ).format(file_name)


def _is_tiff_file(file_name):
    return str(file_name).lower().endswith(('.tif', '.tiff'))


def _preview_scale_for_image(width, height):
    longest_edge = max(width, height)
    if longest_edge > PREVIEW_MAX_DIMENSION:
        return PREVIEW_MAX_DIMENSION / float(longest_edge)
    return 1


def _detection_scale_for_image(width, height):
    if DETECTION_MAX_DIMENSION <= 0:
        return 1
    longest_edge = max(width, height)
    if longest_edge > DETECTION_MAX_DIMENSION:
        return DETECTION_MAX_DIMENSION / float(longest_edge)
    return 1


def _image_to_content_file(image, file_name):
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), name=file_name)


def _csv_value(row, key, index, default=None):
    if isinstance(row, dict):
        normalized_key = key.strip().lower().replace('_', ' ')
        for row_key, value in row.items():
            if row_key is None:
                continue
            if str(row_key).strip().lower().replace('_', ' ') == normalized_key:
                return value
        return default

    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]

    return default


def _default_review_scale(width, height):
    if (width * height) > 200000000:
        return round(15000 / max(width, height), 1)
    return 1


def _first_present_value(row, keys, default=None):
    for key, index in keys:
        value = _csv_value(row, key, index, None)
        if value not in (None, ''):
            return value
    return default


def _parse_review_coordinate_rows(csv_data, fallback_scale=None):
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
            scale = _first_present_value(row, [('Scale', 3)], fallback_scale)
            x_pixel = _first_present_value(row, [
                ('X Pixel', 4),
                ('Pixel X', 1),
                ('X Coordinate', 1),
            ])
            y_pixel = _first_present_value(row, [
                ('Y Pixel', 5),
                ('Pixel Y', 2),
                ('Y Coordinate', 2),
            ])

        if scale in (None, '') or x_pixel in (None, '') or y_pixel in (None, ''):
            continue

        try:
            coordinate_rows.append({
                'scale': float(scale),
                'x_pixel': float(x_pixel),
                'y_pixel': float(y_pixel),
            })
        except (TypeError, ValueError):
            continue

    return coordinate_rows


def _prepare_upload_assets(image, img_metadata, preview_scale=None, temp_data=None):
    source_field = image.original_file or image.image_file
    if not source_field or not source_field.storage.exists(source_field.name):
        raise ValueError('Uploaded image file is missing')

    file_name = _file_name_from_url(source_field.name)
    stem = os.path.splitext(file_name)[0]
    source_image = Image.open(source_field.path)
    source_image.load()
    source_width, source_height = source_image.size
    source_rgb = source_image.convert('RGB')
    detection_scale = _detection_scale_for_image(source_width, source_height)
    detection_width = max(1, int(round(source_width * detection_scale)))
    detection_height = max(1, int(round(source_height * detection_scale)))
    detection_image = source_rgb.resize((detection_width, detection_height)) if detection_scale != 1 else source_rgb.copy()
    detection_width, detection_height = detection_image.size
    preview_scale = preview_scale if preview_scale is not None else _preview_scale_for_image(source_width, source_height)
    preview_width = max(1, int(round(source_width * preview_scale)))
    preview_height = max(1, int(round(source_height * preview_scale)))
    preview_image = source_rgb.resize((preview_width, preview_height)) if preview_scale != 1 else source_rgb.copy()

    image.source_width = source_width
    image.source_height = source_height
    image.detection_width = detection_width
    image.detection_height = detection_height
    image.preview_scale_x = preview_width / float(detection_width or 1)
    image.preview_scale_y = preview_height / float(detection_height or 1)
    image.detection_scale_x = detection_width / float(source_width or 1)
    image.detection_scale_y = detection_height / float(source_height or 1)
    image.detection_file.save(
        '{}_detection.png'.format(stem),
        _image_to_content_file(detection_image, '{}_detection.png'.format(stem)),
        save=False,
    )
    image.image_file.save(
        '{}_preview.png'.format(stem),
        _image_to_content_file(preview_image, '{}_preview.png'.format(stem)),
        save=False,
    )
    image.preview_file.name = image.image_file.name
    image.save()

    Image_Metadata.objects.create(owner=image.owner, **img_metadata)
    Image_scale.objects.create(
        owner=image.owner,
        image=image,
        scale=image.preview_scale_x,
        scale_x=image.preview_scale_x,
        scale_y=image.preview_scale_y,
        detection_scale_x=image.detection_scale_x,
        detection_scale_y=image.detection_scale_y,
    )

    if temp_data:
        Temp_Data.objects.bulk_create([
            Temp_Data(owner=image.owner, image=image, lat=row['lat'], lng=row['lng'])
            for row in temp_data
        ])

    return image


def _save_upload_job(job, status=None, progress=None, message=None, error=None):
    update_fields = ['updated_on']
    if status is not None:
        job.status = status
        update_fields.append('status')
    if progress is not None:
        job.progress = max(0, min(100, int(progress)))
        update_fields.append('progress')
    if message is not None:
        job.message = message
        update_fields.append('message')
    if error is not None:
        job.error = error
        update_fields.append('error')
    job.save(update_fields=update_fields)


def _run_upload_job(job_id, celery_task=None):
    close_old_connections()
    job = UploadTask.objects.select_related('owner', 'image').get(id=job_id)
    celery_task_id = None
    if celery_task is not None:
        celery_task_id = getattr(getattr(celery_task, 'request', None), 'id', None)

    def update(status=None, progress=None, message=None, error=None):
        _save_upload_job(job, status=status, progress=progress, message=message, error=error)
        if celery_task is not None and celery_task_id:
            celery_task.update_state(
                task_id=celery_task_id,
                state=job.status,
                meta={
                    'progress': job.progress,
                    'message': job.message,
                    'error': job.error,
                },
            )

    try:
        update(status=UploadTask.Status.STARTED, progress=5, message='Preparing upload')
        image = job.image
        if not image or not image.original_file:
            raise ValueError('Uploaded image is missing')

        workspace = get_user_workspace(job.owner)
        gdal_folder = os.path.join(workspace.absolute_path, 'gdalIMG')
        temp_folder = os.path.join(workspace.absolute_path, 'tempIMG')
        if job.kind == UploadTask.Kind.REVIEW:
            _safe_rmtree_children(temp_folder)
            Plot_Coordinate.objects.filter(owner=job.owner).delete()
            Annotate_Data.objects.filter(owner=job.owner).delete()

        Image_scale.objects.filter(owner=job.owner, image=image).delete()
        Temp_Data.objects.filter(owner=job.owner, image=image).delete()

        source_path = image.original_file.path
        source_name = _file_name_from_url(image.original_file.name)
        update(status=UploadTask.Status.STARTED, progress=20, message='Reading image metadata')
        if _is_tiff_file(source_name):
            img_metadata, metatxt = _metadata_from_gdal_file(source_path)
        else:
            img_metadata = _default_image_metadata()
            metatxt = _default_metadata_text(source_name)

        os.makedirs(gdal_folder, exist_ok=True)
        with open(os.path.join(gdal_folder, 'metaimg.txt'), 'w') as meta_file:
            meta_file.write(metatxt)

        update(status=UploadTask.Status.STARTED, progress=45, message='Creating preview assets')
        preview_scale = job.preview_scale
        temp_data = None
        if job.kind == UploadTask.Kind.REVIEW:
            source_image = Image.open(source_path)
            source_image.load()
            width, height = source_image.size
            coordinate_rows = _parse_review_coordinate_rows(job.csv_data or [], _default_review_scale(width, height))
            if not coordinate_rows:
                raise ValueError('No valid coordinate rows found in CSV.')
            preview_scale = coordinate_rows[0]['scale']
            temp_data = [
                {
                    'lat': round(-coord['y_pixel'] + int(height), 2),
                    'lng': round(coord['x_pixel'], 2),
                }
                for coord in coordinate_rows
            ]

        update(status=UploadTask.Status.STARTED, progress=75, message='Saving upload results')
        _prepare_upload_assets(image, img_metadata, preview_scale, temp_data)
        update(status=UploadTask.Status.SUCCESS, progress=100, message='Upload processed', error='')
        return {'progress': 100, 'message': job.message, 'image_id': image.id}
    except Exception as error:
        update(
            status=UploadTask.Status.FAILURE,
            progress=job.progress,
            message='Upload processing failed',
            error=str(error),
        )
        raise
    finally:
        close_old_connections()


def _update_job_debug(job, debug_metadata):
    job.debug_metadata = debug_metadata or {}
    job.save(update_fields=['debug_metadata', 'updated_on'])


def _run_detection_job(job_id, celery_task=None):
    close_old_connections()
    job = DetectionTask.objects.select_related('owner', 'image').get(id=job_id)
    celery_task_id = None
    if celery_task is not None:
        celery_task_id = getattr(getattr(celery_task, 'request', None), 'id', None)

    def update(status=None, progress=None, message=None, error=None):
        _save_job(job, status=status, progress=progress, message=message, error=error)
        if celery_task is not None and celery_task_id:
            celery_task.update_state(
                task_id=celery_task_id,
                state=job.status,
                meta={
                    'progress': job.progress,
                    'message': job.message,
                    'error': job.error,
                },
            )

    stop_estimate = threading.Event()

    def estimate_progress():
        estimated_progress = 20
        while not stop_estimate.wait(3):
            if job.progress >= 85:
                continue
            estimated_progress = min(85, estimated_progress + 3)
            update(
                status=DetectionTask.Status.STARTED,
                progress=estimated_progress,
                message='Detecting trees',
            )

    try:
        update(
            status=DetectionTask.Status.STARTED,
            progress=10,
            message='Preparing image',
        )
        Temp_Data.objects.filter(owner=job.owner, image=job.image).delete()

        progress_thread = threading.Thread(target=estimate_progress, daemon=True)
        progress_thread.start()
        detection_path = job.image.detection_file.path if job.image and job.image.detection_file else None
        object_list, debug_metadata = main(
            detection_path or job.image_name,
            job.timestamp,
            job.model_backend,
            _workspace_media_path(job.owner),
            return_debug=True,
        )
        _update_job_debug(job, debug_metadata)
        stop_estimate.set()
        progress_thread.join(timeout=1)

        update(
            status=DetectionTask.Status.STARTED,
            progress=92,
            message='Saving detection results',
        )
        for row in object_list:
            serializer = TempSerializer(data=row)
            if serializer.is_valid():
                serializer.save(owner=job.owner, image=job.image)

        update(
            status=DetectionTask.Status.SUCCESS,
            progress=100,
            message='Detection finished',
            error='',
        )
        return {'progress': 100, 'message': job.message}
    except Exception as error:
        stop_estimate.set()
        update(
            status=DetectionTask.Status.FAILURE,
            progress=job.progress,
            message='Detection failed',
            error=str(error),
        )
        raise
    finally:
        close_old_connections()


def _save_export_job(job, status=None, progress=None, message=None, error=None):
    _save_job(job, status=status, progress=progress, message=message, error=error)


def _run_export_job(job_id, celery_task=None):
    close_old_connections()
    job = ExportTask.objects.select_related('owner', 'image').get(id=job_id)
    celery_task_id = None
    if celery_task is not None:
        celery_task_id = getattr(getattr(celery_task, 'request', None), 'id', None)

    def update(status=None, progress=None, message=None, error=None):
        _save_export_job(job, status=status, progress=progress, message=message, error=error)
        if celery_task is not None and celery_task_id:
            celery_task.update_state(
                task_id=celery_task_id,
                state=job.status,
                meta={
                    'progress': job.progress,
                    'message': job.message,
                    'error': job.error,
                },
            )

    try:
        update(status=ExportTask.Status.STARTED, progress=5, message='Preparing export data')
        image = job.image
        if not image or not image.detection_file:
            raise ValueError('Detection image is missing for this upload')

        workspace_path = _workspace_media_path(job.owner)
        media_tiles_path = os.path.join(workspace_path, 'media')
        zip_path = os.path.join(workspace_path, 'zip')
        os.makedirs(media_tiles_path, exist_ok=True)
        os.makedirs(zip_path, exist_ok=True)

        metadata = Image_Metadata.objects.filter(owner=job.owner).first()
        if metadata:
            x_origin = metadata.X_Origin
            y_origin = metadata.Y_Origin
            pixel_size_x = metadata.Pixel_SizeX
            pixel_size_y = metadata.Pixel_SizeY
        else:
            x_origin = 0
            y_origin = 0
            pixel_size_x = 0
            pixel_size_y = 0

        img_file = _file_name_from_url(job.image_name)
        tile_stem = os.path.splitext(_file_name_from_url(image.detection_file.name))[0]
        img_height = int(image.detection_height or image.image_height or 0)
        img_width = int(image.detection_width or image.image_width or 0)
        preview_scale_x = float(getattr(image, 'preview_scale_x', 1) or 1)
        detection_scale_x = float(getattr(image, 'detection_scale_x', 1) or 1)
        detection_scale_y = float(getattr(image, 'detection_scale_y', 1) or 1)
        folder_tiling = os.path.join(media_tiles_path, "{}_{}".format(img_file, job.timestamp))
        if os.path.isdir(folder_tiling):
            import shutil
            shutil.rmtree(folder_tiling)
        zip_file_path = os.path.join(zip_path, "{}.zip".format(os.path.splitext(img_file)[0]))
        if os.path.isfile(zip_file_path):
            os.remove(zip_file_path)

        os.makedirs(folder_tiling, exist_ok=True)
        update(status=ExportTask.Status.STARTED, progress=20, message='Creating image tiles')
        img_tile, img_offset = image_tiling(image.detection_file.path, folder_tiling)
        if img_tile is None:
            raise ValueError('Image tiling failed')
        filelist = [file_name for file_name in os.listdir(folder_tiling)]

        receive_data = job.coordinates or []
        data = [[float(row['X_coord']), -float(row['Y_coord']) + img_height] for row in receive_data]
        sorted_data = sorted(data, key=lambda point: (float(point[1]), float(point[0])))
        row_amt = math.trunc(img_height / 58)
        db_data = []
        for row in get_rows(sorted_data, row_amt, img_height):
            db_data.extend(row)

        update(status=ExportTask.Status.STARTED, progress=45, message='Building coordinate tables')
        plot_list = []
        annotate_list = []
        for point in db_data:
            plot_list.append({
                "ids": int(len(plot_list)) + 1,
                "X_Pixel": round((float(point[0])) / detection_scale_x, 2),
                "Y_Pixel": round((float(point[1])) / detection_scale_y, 2),
                "Scale": preview_scale_x,
                "X_Coordinate": round(float(x_origin) + (((float(point[0])) / detection_scale_x) * float(pixel_size_x)), 2),
                "Y_Coordinate": round(float(y_origin) + (((float(point[1])) / detection_scale_y) * float(pixel_size_y)), 2),
            })

        tile_size = (480, 480)
        offset = img_offset
        img_list = []
        name = tile_stem
        for i in range(int(math.ceil(img_height / (offset[1] * 1.0)))):
            for j in range(int(math.ceil(img_width / (offset[0] * 1.0)))):
                y1 = offset[1] * i
                y2 = min(offset[1] * i + tile_size[1], img_height)
                x1 = offset[0] * j
                x2 = min(offset[0] * j + tile_size[0], img_width)
                y_range = range(y1, y2)
                x_range = range(x1, x2)

                for point in db_data:
                    if int(point[1]) in y_range and int(point[0]) in x_range:
                        x_small = int(point[0]) - j * offset[0]
                        y_small = int(point[1]) - i * offset[1]
                        other_x = x2 - x1
                        other_y = y2 - y1
                        xmin = 1 if (x_small - 20) < 0 else x_small - 20
                        ymin = 1 if (y_small - 20) < 0 else y_small - 20
                        xmax = other_x - 1 if (x_small + 20) > other_x else x_small + 20
                        ymax = other_y - 1 if (y_small + 20) > other_y else y_small + 20
                        filename = "{}_r{}_c{}.png".format(name, i, j)
                        img_list.append(filename)
                        annotate_list.append({
                            'filename': filename,
                            'width': int(x2 - x1),
                            'height': int(y2 - y1),
                            'classes': 'palm oil',
                            'xmin': int(xmin),
                            'ymin': int(ymin),
                            'xmax': int(xmax),
                            'ymax': int(ymax),
                        })

        update(status=ExportTask.Status.STARTED, progress=70, message='Saving export rows')
        img_list = np.unique(img_list, axis=0)
        for path in filelist:
            if path not in img_list:
                os.remove(os.path.join(folder_tiling, path))
        if not os.listdir(folder_tiling):
            raise ValueError('No cut images were created for the export zip')

        Plot_Coordinate.objects.filter(owner=job.owner).delete()
        Annotate_Data.objects.filter(owner=job.owner).delete()
        for row in plot_list:
            serializer = PlotSerializer(data=row)
            if serializer.is_valid():
                serializer.save(owner=job.owner)
        for row in annotate_list:
            serializer = AnnotateSerializer(data=row)
            if serializer.is_valid():
                serializer.save(owner=job.owner)

        update(status=ExportTask.Status.STARTED, progress=90, message='Packaging export files')
        FileHandler(folder_tiling, img_file, workspace_path)
        update(status=ExportTask.Status.SUCCESS, progress=100, message='Export files are ready', error='')
        return {'progress': 100, 'message': job.message}
    except Exception as error:
        update(
            status=ExportTask.Status.FAILURE,
            progress=job.progress,
            message='Export preparation failed',
            error=str(error),
        )
        raise
    finally:
        close_old_connections()


if shared_task is not None:
    @shared_task(bind=True)
    def run_upload_task(self, job_id):
        return _run_upload_job(job_id, self)

    @shared_task(bind=True)
    def run_detection_task(self, job_id):
        return _run_detection_job(job_id, self)

    @shared_task(bind=True)
    def run_export_task(self, job_id):
        return _run_export_job(job_id, self)
else:
    class LocalUploadTask:
        def delay(self, job_id):
            thread = threading.Thread(target=_run_upload_job, args=(job_id,), daemon=True)
            thread.start()
            return None

    run_upload_task = LocalUploadTask()

    class LocalDetectionTask:
        def delay(self, job_id):
            thread = threading.Thread(target=_run_detection_job, args=(job_id,), daemon=True)
            thread.start()
            return None

    run_detection_task = LocalDetectionTask()

    class LocalExportTask:
        def delay(self, job_id):
            thread = threading.Thread(target=_run_export_job, args=(job_id,), daemon=True)
            thread.start()
            return None

    run_export_task = LocalExportTask()
