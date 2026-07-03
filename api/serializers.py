from django.db import models
from rest_framework import serializers
from .models import *

class ImageSerializers(serializers.ModelSerializer):
    detection_scale = serializers.SerializerMethodField()
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    owner_name = serializers.SerializerMethodField()

    def get_detection_scale(self, obj):
        return {
            'x': obj.detection_scale_x,
            'y': obj.detection_scale_y,
        }

    def get_owner_name(self, obj):
        if not obj.owner:
            return ''
        return obj.owner.first_name or obj.owner.username

    class Meta:
        model = ImageData
        fields = (
            'id',
            'owner_id',
            'owner_email',
            'owner_name',
            'uploaded_on',
            'image_file',
            'original_file',
            'preview_file',
            'detection_file',
            'image_width',
            'image_height',
            'source_width',
            'source_height',
            'detection_width',
            'detection_height',
            'preview_scale_x',
            'preview_scale_y',
            'detection_scale_x',
            'detection_scale_y',
            'detection_scale',
        )

class PlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plot_Coordinate
        fields = ['ids', 'X_Coordinate', 'Y_Coordinate', 'Scale', 'X_Pixel', 'Y_Pixel']
        
class AnnotateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotate_Data
        fields = ['filename','width','height','classes','xmin','ymin','xmax','ymax']
        
        
class TempSerializer(serializers.ModelSerializer):
    class Meta:
        model = Temp_Data
        fields = ['lat', 'lng']
        
class ScaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image_scale
        fields = ['image', 'scale', 'scale_x', 'scale_y', 'detection_scale_x', 'detection_scale_y']

class ImageTileerializer(serializers.ModelSerializer):
    class Meta:
        model = Image_Tile
        fields = ['link']

class ImageMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image_Metadata
        fields = ['X_Origin', 'Y_Origin', 'Pixel_SizeX', 'Pixel_SizeY']
