from django.urls import path

from . import views

app_name = "converter"

urlpatterns = [
    path("", views.index, name="index"),
    path("convert/start/", views.convert_file, name="convert"),
    path("convert/status/<str:job_id>/", views.conversion_status, name="status"),
    path(
        "convert/download/<str:job_id>/<str:file_name>/",
        views.download_single,
        name="download_single",
    ),
    path("convert/download-zip/<str:job_id>/", views.download_zip, name="download_zip"),
]
