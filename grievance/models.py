import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


class HostelUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Anyone created with `manage.py createsuperuser` is an Admin with full access.
        extra_fields.setdefault('role', 'ADMIN')
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = 'STUDENT', 'Student'
        PARENT = 'PARENT', 'Parent'
        WARDEN = 'WARDEN', 'Warden'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True)

    objects = HostelUserManager()

    def is_student(self):
        return self.role == self.Role.STUDENT

    def is_parent(self):
        return self.role == self.Role.PARENT

    def is_warden(self):
        return self.role == self.Role.WARDEN

    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'


class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='student_profile',
                                 limit_choices_to={'role': User.Role.STUDENT})
    hostel_room = models.CharField(max_length=20, blank=True)
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='children',
                                limit_choices_to={'role': User.Role.PARENT})

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} - Room {self.hostel_room}'


class Complaint(models.Model):
    class Category(models.TextChoices):
        FOOD = 'FOOD', 'Food'
        ROOM = 'ROOM', 'Room'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
        RAGGING = 'RAGGING', 'Ragging / Safety'
        OTHER = 'OTHER', 'Other'

    class Severity(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ASSIGNED = 'ASSIGNED', 'Assigned'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        RESOLVED = 'RESOLVED', 'Resolved'
        REJECTED = 'REJECTED', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='complaints',
                                 limit_choices_to={'role': User.Role.STUDENT})
    title = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.TextField()
    image = models.ImageField(upload_to='complaints/%Y/%m/', blank=True, null=True)

    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.LOW)
    severity_score = models.FloatField(default=0)  # 0-100, higher = more severe
    ai_explanation = models.TextField(blank=True)
    ai_engine_used = models.CharField(max_length=20, default='rule-based')

    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    assigned_warden = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='assigned_complaints',
                                         limit_choices_to={'role': User.Role.WARDEN})

    allocation_hours = models.FloatField(default=72)
    deadline = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} [{self.severity}]'

    @property
    def severity_rank(self):
        order = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        return order.get(self.severity, 0)

    @property
    def is_overdue(self):
        return bool(self.deadline) and self.status not in (self.Status.RESOLVED, self.Status.REJECTED) \
            and timezone.now() > self.deadline

    @property
    def time_remaining(self):
        if not self.deadline:
            return None
        return self.deadline - timezone.now()

    def apply_allocation(self):
        """Set allocation_hours & deadline based on current severity."""
        hours = settings.SEVERITY_ALLOCATION_HOURS.get(self.severity, 72)
        self.allocation_hours = hours
        base = self.created_at or timezone.now()
        self.deadline = base + timedelta(hours=hours)


class ComplaintUpdate(models.Model):
    """Audit trail / status-change log + comments on a complaint."""
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='updates')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    note = models.CharField(max_length=255)
    new_status = models.CharField(max_length=15, choices=Complaint.Status.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.complaint_id} - {self.note}'
