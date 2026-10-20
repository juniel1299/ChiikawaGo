from django.urls import path

from . import views

urlpatterns = [
    path("capabilities", views.CapabilitiesView.as_view()),
    path("jobs", views.JobsView.as_view()),
    path("jobs/<uuid:pk>", views.JobView.as_view()),
    path("jobs/<uuid:pk>/runs", views.RunView.as_view()),
    path("sources", views.SourcesView.as_view()),
    path("schedules", views.SchedulesView.as_view()),
    path("schedules/<uuid:pk>", views.ScheduleView.as_view()),
    path("executions", views.ExecutionsView.as_view()),
    path("executions/<uuid:pk>", views.ExecutionView.as_view()),
    path("executions/<uuid:pk>/retry", views.RetryView.as_view()),
    path("executions/<uuid:pk>/confirm-failure", views.ConfirmFailureView.as_view()),
]
