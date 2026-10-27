from django.urls import path

from . import views


app_name = "scheduling"
urlpatterns = [
    path("commitments/", views.CommitmentListView.as_view(), name="commitment_list"),
    path("sources/new/", views.SourceCreateView.as_view(), name="source_create"),
    path("commitments/new/", views.CommitmentCreateView.as_view(), name="commitment_create"),
    path("commitments/<int:pk>/edit/", views.CommitmentUpdateView.as_view(), name="commitment_update"),
    path("commitments/<int:pk>/delete/", views.CommitmentDeleteView.as_view(), name="commitment_delete"),
]
