from django.urls import path

from . import availability_views, recurring_views, shift_views, views, working_views


app_name = "scheduling"
urlpatterns = [
    path("check-shift/", shift_views.ProposedShiftView.as_view(), name="shift_check"),
    path("availability/", availability_views.WeeklyAvailabilityView.as_view(), name="availability"),
    path("working-windows/", working_views.WorkingWindowsView.as_view(), name="working_windows"),
    path("working-windows/edit/", working_views.WorkingRowsView.as_view(), name="working_schedule_edit"),
    path("working-windows/dates/new/", working_views.WorkingOverrideView.as_view(), name="working_override_create"),
    path("working-windows/dates/<int:pk>/edit/", working_views.WorkingOverrideView.as_view(), name="working_override_edit"),
    path("working-windows/dates/<int:pk>/remove/", working_views.WorkingOverrideRemoveView.as_view(), name="working_override_remove"),
    path("week/", views.WeeklyCalendarView.as_view(), name="week"),
    path("commitments/", views.CommitmentListView.as_view(), name="commitment_list"),
    path("sources/new/", views.SourceCreateView.as_view(), name="source_create"),
    path("commitments/new/", views.CommitmentCreateView.as_view(), name="commitment_create"),
    path("commitments/<int:pk>/edit/", views.CommitmentUpdateView.as_view(), name="commitment_update"),
    path("commitments/<int:pk>/delete/", views.CommitmentDeleteView.as_view(), name="commitment_delete"),
    path("recurring/", recurring_views.SeriesListView.as_view(), name="series_list"),
    path("recurring/new/", recurring_views.SeriesCreateView.as_view(), name="series_create"),
    path("recurring/<int:pk>/edit/", recurring_views.SeriesReviseView.as_view(), name="series_revise"),
    path("recurring/<int:pk>/end/", recurring_views.SeriesEndView.as_view(), name="series_end"),
    path("recurring/<int:pk>/<str:original_date>/change/", recurring_views.OccurrenceChangeView.as_view(), name="occurrence_change"),
    path("recurring/<int:pk>/<str:original_date>/cancel/", recurring_views.OccurrenceCancelView.as_view(), name="occurrence_cancel"),
]
