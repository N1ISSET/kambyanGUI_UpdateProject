from django.urls import path
from .views import *

urlpatterns = [
    path('signup/', SignupView.as_view()),
    path('login/', LoginView.as_view()),
    path('forgot-password/', ForgotPasswordView.as_view()),
    path('me/', MeView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('admin/users/', AdminUserListView.as_view()),
    path('admin/users/<int:user_id>/', AdminUserDetailView.as_view()),
    path('admin/images/', AdminImageListView.as_view()),
    path('admin/images/<int:image_id>/', AdminImageDetailView.as_view()),
    path('resizeIMG/', ResizeImageView.as_view()),
    path('upload-status/', UploadStatusView.as_view()),
    path('home/', ImageView.as_view()),
    path('processimg/', ProcessIMG.as_view()),
    path('processing/', ProcessIMG.as_view()),
    path('assignID/', PlottingView.as_view()),
    path('test/', PlotCoordinateView.as_view()),
    path('test2/', AnnotateDataView.as_view()),
    path('tempdata/', TempView.as_view()),
    path('scaledata/', ScaleView.as_view()),
    path('reviewdata/', ReviewView.as_view()),
    path('imgmetadata/', ImageMetadataView.as_view()),
    path('metatxt/', MetatxtView.as_view()),
    #path('imagetile/', ImageTileView.as_view()),
]
