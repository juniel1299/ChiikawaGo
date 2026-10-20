from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User


class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "display_name")


class AdminUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    ordering = ("email",)
    list_display = ("email", "display_name", "is_active", "is_staff")
    search_fields = ("email", "display_name")
    fieldsets = (
        (None, {"fields": ("email", "password", "display_name")}),
        (
            "권한",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("기록", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "display_name", "password1", "password2")}),)
