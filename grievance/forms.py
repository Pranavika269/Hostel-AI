from django import forms
from django.conf import settings as dj_settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Complaint, StudentProfile, User


# ---------------------------------------------------------------------------
# Login forms
# ---------------------------------------------------------------------------

class StudentParentLoginForm(AuthenticationForm):
    """Login form for the main portal — Students and Parents only."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role not in (User.Role.STUDENT, User.Role.PARENT):
            raise ValidationError(
                'This login is for Students and Parents. '
                'Wardens and Admins should use the Staff Login page.',
                code='wrong_portal',
            )


class StaffLoginForm(AuthenticationForm):
    """Login form for the Staff Portal — Wardens and Admins only."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role not in (User.Role.WARDEN, User.Role.ADMIN) and not user.is_superuser:
            raise ValidationError(
                'This login is for Wardens and Admins only. '
                'Students and Parents should use the main Sign In page.',
                code='wrong_portal',
            )


# ---------------------------------------------------------------------------
# Shared plumbing for the four dedicated signup forms
# ---------------------------------------------------------------------------

class _BaseAccountForm(UserCreationForm):
    """
    Common fields every account type needs: name, email, phone, username
    (their OWN), and password (their OWN). Each subclass below is a
    completely separate, dedicated form — there is no shared role picker.
    """
    first_name = forms.CharField(max_length=30, required=True, label='First name')
    last_name = forms.CharField(max_length=30, required=False, label='Last name')
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phone',
                  'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Username'
        self.fields['password1'].label = 'Password'
        self.fields['password2'].label = 'Confirm password'
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()


class _StaffAccountForm(_BaseAccountForm):
    """Shared plumbing for Warden/Admin forms: adds the staff signup code gate."""
    staff_code = forms.CharField(
        max_length=100, label='Staff signup code', widget=forms.PasswordInput,
        help_text='Provided by hostel administration.')

    role = None  # set by subclass

    def clean_staff_code(self):
        code = self.cleaned_data.get('staff_code', '')
        if code != dj_settings.STAFF_SIGNUP_CODE:
            raise ValidationError('Incorrect staff signup code. Ask your hostel administrator for it.')
        return code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.role
        user.email = self.cleaned_data['email']
        user.is_staff = True
        if self.role == User.Role.ADMIN:
            user.is_superuser = True
        if commit:
            user.save()
        return user


# ---------------------------------------------------------------------------
# 1. Student — creates their OWN username & password
# ---------------------------------------------------------------------------

class StudentSignUpForm(_BaseAccountForm):
    hostel_room = forms.CharField(max_length=20, required=True, help_text='e.g. B-204')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.STUDENT
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            StudentProfile.objects.create(user=user, hostel_room=self.cleaned_data['hostel_room'])
        return user


# ---------------------------------------------------------------------------
# 2. Parent — creates their OWN username & password, AND their child's
# ---------------------------------------------------------------------------

class ParentSignUpForm(_BaseAccountForm):
    child_first_name = forms.CharField(max_length=30, required=True, label="Child's first name")
    child_last_name = forms.CharField(max_length=30, required=False, label="Child's last name")
    child_username = forms.CharField(max_length=150, required=True, label="Child's username")
    child_hostel_room = forms.CharField(max_length=20, required=True, label="Child's hostel room")
    child_password1 = forms.CharField(
        required=True, widget=forms.PasswordInput, label="Child's password")
    child_password2 = forms.CharField(
        required=True, widget=forms.PasswordInput, label="Confirm child's password")

    def clean(self):
        cleaned = super().clean()
        child_username = cleaned.get('child_username')
        if child_username:
            if child_username == cleaned.get('username'):
                self.add_error('child_username', "Child's username must be different from your own.")
            elif User.objects.filter(username=child_username).exists():
                self.add_error('child_username', 'That username is already taken.')

        pw1, pw2 = cleaned.get('child_password1'), cleaned.get('child_password2')
        if pw1 and pw2 and pw1 != pw2:
            self.add_error('child_password2', "Child's passwords do not match.")
        elif pw1:
            try:
                validate_password(pw1)
            except ValidationError as exc:
                self.add_error('child_password1', exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PARENT
        user.email = self.cleaned_data['email']
        if not commit:
            return user
        user.save()

        child = User.objects.create_user(
            username=self.cleaned_data['child_username'],
            email='',
            password=self.cleaned_data['child_password1'],
            first_name=self.cleaned_data.get('child_first_name', ''),
            last_name=self.cleaned_data.get('child_last_name', ''),
            role=User.Role.STUDENT,
        )
        StudentProfile.objects.create(
            user=child, hostel_room=self.cleaned_data['child_hostel_room'], parent=user)
        return user


# ---------------------------------------------------------------------------
# 3. Warden — creates their OWN username & password (staff-code gated)
# ---------------------------------------------------------------------------

class WardenSignUpForm(_StaffAccountForm):
    role = User.Role.WARDEN

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Warden username'


# ---------------------------------------------------------------------------
# 4. Admin — creates their OWN username & password (staff-code gated)
# ---------------------------------------------------------------------------

class AdminSignUpForm(_StaffAccountForm):
    role = User.Role.ADMIN

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Admin username'


# ---------------------------------------------------------------------------
# Complaint / status forms (unchanged)
# ---------------------------------------------------------------------------

class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ['title', 'category', 'description', 'image']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Short summary of the issue'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5,
                                                   'placeholder': 'Describe the issue in detail...'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class StatusUpdateForm(forms.Form):
    status = forms.ChoiceField(choices=Complaint.Status.choices,
                                widget=forms.Select(attrs={'class': 'form-select'}))
    note = forms.CharField(required=False, widget=forms.Textarea(
        attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Add a note (optional)'}))
