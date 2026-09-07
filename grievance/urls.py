from django.urls import path

from . import views

urlpatterns = [
    path('signup/', views.signup_hub_view, name='signup'),
    path('signup/student/', views.student_signup_view, name='signup_student'),
    path('signup/parent/', views.parent_signup_view, name='signup_parent'),
    path('signup/warden/', views.warden_signup_view, name='signup_warden'),
    path('signup/admin/', views.admin_signup_view, name='signup_admin'),
    path('dashboard/', views.dashboard_router, name='dashboard'),
    path('dashboard/student/', views.student_dashboard, name='dashboard_student'),
    path('dashboard/parent/', views.parent_dashboard, name='dashboard_parent'),
    path('dashboard/warden/', views.warden_dashboard, name='dashboard_warden'),
    path('dashboard/admin/', views.admin_dashboard, name='dashboard_admin'),
    path('complaints/new/', views.complaint_create, name='complaint_create'),
    path('complaints/<uuid:pk>/', views.complaint_detail, name='complaint_detail'),
    path('complaints/<uuid:pk>/assign-me/', views.assign_to_me, name='assign_to_me'),
]
