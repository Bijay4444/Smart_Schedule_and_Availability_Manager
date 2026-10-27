from django.contrib import admin

from .models import Commitment, CommitmentSource


class OwnedReadOnlyAdmin(admin.ModelAdmin):
    """Inspect records here; editing uses the user-facing validation/warning flow."""

    owner_lookup = "owner"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(**{self.owner_lookup: request.user})

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommitmentSource)
class CommitmentSourceAdmin(OwnedReadOnlyAdmin):
    list_display = ["name", "owner", "color", "archived_at"]
    list_select_related = ["owner"]


@admin.register(Commitment)
class CommitmentAdmin(OwnedReadOnlyAdmin):
    owner_lookup = "source__owner"
    list_display = ["title", "source", "starts_at", "ends_at"]
    list_select_related = ["source"]
