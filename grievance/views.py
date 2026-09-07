import json

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .ai_engine import analyze_complaint
from .forms import (AdminSignUpForm, ComplaintForm, ParentSignUpForm, StatusUpdateForm,
                     StudentSignUpForm, WardenSignUpForm)
from .models import Complaint, ComplaintUpdate, StudentProfile, User


def signup_hub_view(request):
    """Landing page listing all four dedicated 'create account' pages."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'registration/signup_hub.html')


def _generic_signup(request, form_class, template_name, welcome_prefix='Welcome to Hostel AI'):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'{welcome_prefix}, {user.first_name or user.username}!')
            return redirect('dashboard')
    else:
        form = form_class()
    return render(request, template_name, {'form': form})


def student_signup_view(request):
    """Dedicated Student account creation — own username & password."""
    return _generic_signup(request, StudentSignUpForm, 'registration/signup_student.html')


def parent_signup_view(request):
    """Dedicated Parent account creation — own username & password, plus their child's."""
    return _generic_signup(request, ParentSignUpForm, 'registration/signup_parent.html')


def warden_signup_view(request):
    """Dedicated Warden account creation — own username & password, staff-code gated."""
    return _generic_signup(request, WardenSignUpForm, 'registration/signup_warden.html',
                            welcome_prefix='Staff account created. Welcome')


def admin_signup_view(request):
    """Dedicated Admin account creation — own username & password, staff-code gated."""
    return _generic_signup(request, AdminSignUpForm, 'registration/signup_admin.html',
                            welcome_prefix='Staff account created. Welcome')



@login_required
def dashboard_router(request):
    user = request.user
    if user.is_admin_role():
        return redirect('dashboard_admin')
    if user.is_warden():
        return redirect('dashboard_warden')
    if user.is_parent():
        return redirect('dashboard_parent')
    return redirect('dashboard_student')


def _category_counts(qs):
    return dict(qs.values('category').annotate(c=Count('id')).values_list('category', 'c'))


def _severity_counts(qs):
    return dict(qs.values('severity').annotate(c=Count('id')).values_list('severity', 'c'))


def _status_counts(qs):
    return dict(qs.values('status').annotate(c=Count('id')).values_list('status', 'c'))


@login_required
def student_dashboard(request):
    if not request.user.is_student():
        raise PermissionDenied
    complaints = Complaint.objects.filter(student=request.user)
    stats = {
        'total': complaints.count(),
        'pending': complaints.filter(status=Complaint.Status.PENDING).count(),
        'in_progress': complaints.filter(status__in=[Complaint.Status.ASSIGNED, Complaint.Status.IN_PROGRESS]).count(),
        'resolved': complaints.filter(status=Complaint.Status.RESOLVED).count(),
    }
    context = {
        'complaints': complaints[:25],
        'stats': stats,
        'category_data': json.dumps(_category_counts(complaints)),
        'severity_data': json.dumps(_severity_counts(complaints)),
    }
    return render(request, 'dashboard_student.html', context)


@login_required
def complaint_create(request):
    if not request.user.is_student():
        raise PermissionDenied
    if request.method == 'POST':
        form = ComplaintForm(request.POST, request.FILES)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.student = request.user
            complaint.save()  # need created_at for allocation calc

            analysis = analyze_complaint(complaint.description, complaint.category, complaint.title)
            complaint.severity = analysis['severity']
            complaint.severity_score = analysis['score']
            complaint.ai_explanation = analysis['explanation']
            complaint.ai_engine_used = analysis['engine']
            complaint.apply_allocation()
            complaint.save()

            ComplaintUpdate.objects.create(
                complaint=complaint, actor=request.user,
                note=f"Complaint submitted. AI classified severity as {complaint.severity} "
                     f"({complaint.severity_score}/100) via {complaint.ai_engine_used} engine.",
                new_status=complaint.status,
            )
            messages.success(request, f'Complaint submitted! AI predicted severity: {complaint.get_severity_display()}.')
            return redirect('complaint_detail', pk=complaint.pk)
    else:
        form = ComplaintForm()
    return render(request, 'complaint_form.html', {'form': form})


@login_required
def complaint_detail(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk)
    user = request.user

    allowed = (
        user.is_admin_role()
        or (user.is_student() and complaint.student_id == user.id)
        or (user.is_warden())
        or (user.is_parent() and StudentProfile.objects.filter(user=complaint.student, parent=user).exists())
    )
    if not allowed:
        raise PermissionDenied

    status_form = None
    can_manage = user.is_warden() or user.is_admin_role()

    if can_manage and request.method == 'POST':
        status_form = StatusUpdateForm(request.POST)
        if status_form.is_valid():
            new_status = status_form.cleaned_data['status']
            note = status_form.cleaned_data['note']
            complaint.status = new_status
            if new_status == Complaint.Status.RESOLVED:
                complaint.resolved_at = timezone.now()
            if user.is_warden() and not complaint.assigned_warden_id:
                complaint.assigned_warden = user
            complaint.save()
            ComplaintUpdate.objects.create(
                complaint=complaint, actor=user,
                note=note or f'Status changed to {complaint.get_status_display()}',
                new_status=new_status,
            )
            messages.success(request, 'Complaint updated.')
            return redirect('complaint_detail', pk=complaint.pk)
    elif can_manage:
        status_form = StatusUpdateForm(initial={'status': complaint.status})

    context = {
        'complaint': complaint,
        'status_form': status_form,
        'can_manage': can_manage,
        'updates': complaint.updates.all(),
    }
    return render(request, 'complaint_detail.html', context)


@login_required
def assign_to_me(request, pk):
    if not request.user.is_warden():
        raise PermissionDenied
    complaint = get_object_or_404(Complaint, pk=pk)
    complaint.assigned_warden = request.user
    if complaint.status == Complaint.Status.PENDING:
        complaint.status = Complaint.Status.ASSIGNED
    complaint.save()
    ComplaintUpdate.objects.create(
        complaint=complaint, actor=request.user,
        note=f'Assigned to warden {request.user.get_full_name() or request.user.username}',
        new_status=complaint.status,
    )
    messages.success(request, 'Complaint assigned to you.')
    return redirect('complaint_detail', pk=pk)


@login_required
def parent_dashboard(request):
    if not request.user.is_parent():
        raise PermissionDenied
    children = User.objects.filter(role=User.Role.STUDENT, student_profile__parent=request.user)
    complaints = Complaint.objects.filter(student__in=children)
    stats = {
        'children_count': children.count(),
        'total': complaints.count(),
        'pending': complaints.exclude(status__in=[Complaint.Status.RESOLVED, Complaint.Status.REJECTED]).count(),
        'resolved': complaints.filter(status=Complaint.Status.RESOLVED).count(),
        'critical': complaints.filter(severity=Complaint.Severity.CRITICAL).count(),
    }
    context = {
        'children': children,
        'complaints': complaints[:25],
        'stats': stats,
        'category_data': json.dumps(_category_counts(complaints)),
        'severity_data': json.dumps(_severity_counts(complaints)),
    }
    return render(request, 'dashboard_parent.html', context)


@login_required
def warden_dashboard(request):
    if not request.user.is_warden():
        raise PermissionDenied
    active = Complaint.objects.exclude(status__in=[Complaint.Status.RESOLVED, Complaint.Status.REJECTED])
    # Priority queue: severity rank desc, then nearest deadline first
    active_list = sorted(active, key=lambda c: (-c.severity_rank, c.deadline or timezone.now()))
    for c in active_list:
        remaining = c.time_remaining
        if c.is_overdue:
            c.deadline_state = 'overdue'
        elif remaining is not None and remaining.total_seconds() <= 4 * 3600:
            c.deadline_state = 'soon'
        else:
            c.deadline_state = 'ok'
        if remaining is not None:
            hrs = remaining.total_seconds() / 3600
            c.hours_left_display = f'{abs(round(hrs, 1))}h {"overdue" if hrs < 0 else "left"}'
        else:
            c.hours_left_display = '—'

    mine = active.filter(assigned_warden=request.user)
    unassigned = active.filter(assigned_warden__isnull=True)
    overdue = [c for c in active_list if c.is_overdue]

    all_complaints = Complaint.objects.all()
    resolved = all_complaints.filter(status=Complaint.Status.RESOLVED, resolved_at__isnull=False)
    avg_resolution = None
    if resolved.exists():
        total_seconds = sum((c.resolved_at - c.created_at).total_seconds() for c in resolved)
        avg_resolution = round(total_seconds / resolved.count() / 3600, 1)  # hours

    stats = {
        'active': active.count(),
        'mine': mine.count(),
        'unassigned': unassigned.count(),
        'overdue': len(overdue),
        'resolved_total': resolved.count(),
        'avg_resolution_hours': avg_resolution,
    }
    context = {
        'active_list': active_list[:30],
        'stats': stats,
        'category_data': json.dumps(_category_counts(all_complaints)),
        'severity_data': json.dumps(_severity_counts(all_complaints)),
        'status_data': json.dumps(_status_counts(all_complaints)),
    }
    return render(request, 'dashboard_warden.html', context)


@login_required
def admin_dashboard(request):
    if not request.user.is_admin_role():
        raise PermissionDenied
    complaints = Complaint.objects.all()
    users = User.objects.all()

    stats = {
        'total_complaints': complaints.count(),
        'total_users': users.count(),
        'students': users.filter(role=User.Role.STUDENT).count(),
        'parents': users.filter(role=User.Role.PARENT).count(),
        'wardens': users.filter(role=User.Role.WARDEN).count(),
        'resolved': complaints.filter(status=Complaint.Status.RESOLVED).count(),
        'critical_open': complaints.filter(severity=Complaint.Severity.CRITICAL)
                                   .exclude(status__in=[Complaint.Status.RESOLVED, Complaint.Status.REJECTED]).count(),
        'overdue': len([c for c in complaints if c.is_overdue]),
    }

    warden_load = (
        Complaint.objects.filter(assigned_warden__isnull=False)
        .values('assigned_warden__first_name', 'assigned_warden__last_name', 'assigned_warden__username')
        .annotate(total=Count('id'),
                  resolved=Count('id', filter=Q(status=Complaint.Status.RESOLVED)))
    )

    context = {
        'stats': stats,
        'recent_complaints': complaints[:15],
        'warden_load': warden_load,
        'category_data': json.dumps(_category_counts(complaints)),
        'severity_data': json.dumps(_severity_counts(complaints)),
        'status_data': json.dumps(_status_counts(complaints)),
    }
    return render(request, 'dashboard_admin.html', context)
