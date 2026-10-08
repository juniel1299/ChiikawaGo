from rest_framework.exceptions import PermissionDenied


def require_operator(user, *permissions):
    if not user.is_active or not user.is_staff or not user.has_perms(permissions):
        raise PermissionDenied()
