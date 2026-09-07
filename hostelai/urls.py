from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from grievance.forms import StaffLoginForm, StudentParentLoginForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='dashboard', permanent=False)),

    # Main portal — Students & Parents
    path('login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        authentication_form=StudentParentLoginForm,
    ), name='login'),

    # Staff portal — Wardens & Admins
    path('staff-login/', auth_views.LoginView.as_view(
        template_name='registration/staff_login.html',
        authentication_form=StaffLoginForm,
    ), name='staff_login'),

    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('grievance.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
