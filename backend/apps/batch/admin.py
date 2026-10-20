from django.contrib import admin

from .models import BatchExecution, BatchJob, BatchSchedule


class BatchReadOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_active
            and request.user.is_staff
            and request.user.has_perm("batch.view_batch")
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(BatchJob, BatchReadOnlyAdmin)
admin.site.register(BatchSchedule, BatchReadOnlyAdmin)
admin.site.register(BatchExecution, BatchReadOnlyAdmin)
