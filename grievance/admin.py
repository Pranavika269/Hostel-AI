from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Complaint, ComplaintUpdate, StudentProfile, User

# Rebrand the built-in admin so it reads "Hostel AI" instead of
# "Django administration" everywhere (browser tab, header, index page).
admin.site.site_header = 'Hostel AI · Control Panel'
admin.site.site_title = 'Hostel AI Admin'
admin.site.index_title = 'Manage students, parents, wardens, and complaints'


@admin.register(User)
class HostelUserAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'role', 'email', 'is_active')
    list_filter = ('role', 'is_active', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Hostel AI', {'fields': ('role', 'phone')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Hostel AI', {'fields': ('role', 'phone', 'email')}),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'hostel_room', 'parent')
    search_fields = ('user__username', 'hostel_room')
    list_filter = ('hostel_room',)


class ComplaintUpdateInline(admin.TabularInline):
    model = ComplaintUpdate
    extra = 0
    readonly_fields = ('actor', 'note', 'new_status', 'created_at')


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'category', 'severity', 'status',
                     'assigned_warden', 'deadline', 'created_at')
    list_filter = ('category', 'severity', 'status')
    search_fields = ('title', 'description', 'student__username')
    inlines = [ComplaintUpdateInline]
    readonly_fields = ('id', 'created_at', 'updated_at', 'severity_score', 'ai_explanation', 'ai_engine_used')


@admin.register(ComplaintUpdate)
class ComplaintUpdateAdmin(admin.ModelAdmin):
    list_display = ('complaint', 'actor', 'new_status', 'created_at')
