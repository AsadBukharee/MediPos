"""Shared DRF building blocks: permission codes, branch scoping and audited writes."""
from rest_framework import exceptions, permissions, viewsets
from rest_framework.views import APIView

from apps.audit.services import diff_instance, log_action
from apps.branches.models import Branch


class HasPermCode(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        code = view.get_required_perm() if hasattr(view, "get_required_perm") else None
        return code is None or user.has_perm_code(code)


class PermMixin:
    """`perms` maps a viewset action (or lowercase HTTP method) to a permission code."""

    permission_classes = [permissions.IsAuthenticated, HasPermCode]
    perms: dict[str, str] = {}
    read_perm: str | None = None
    write_perm: str | None = None

    def get_required_perm(self):
        action = getattr(self, "action", None) or self.request.method.lower()
        if action in self.perms:
            return self.perms[action]
        if self.request.method in permissions.SAFE_METHODS:
            return self.read_perm
        return self.write_perm or self.read_perm


def resolve_branch(request) -> Branch:
    user = request.user
    raw = request.headers.get("X-Branch-Id") or request.query_params.get("branch")
    accessible = user.accessible_branches()
    if raw in (None, ""):
        branches = list(accessible[:2])
        if len(branches) == 1:
            return branches[0]
        raise exceptions.ValidationError({"branch": "Send the X-Branch-Id header to choose a branch."})
    try:
        return accessible.get(pk=int(raw))
    except (ValueError, Branch.DoesNotExist):
        # Same answer whether the branch is missing or simply not yours: no data leaks across branches.
        raise exceptions.PermissionDenied("You do not have access to this branch.")


class BranchMixin(PermMixin):
    """Resolves request.branch after authentication and scopes querysets to it."""

    branch_field = "branch"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        request.branch = resolve_branch(request)

    def get_queryset(self):
        return super().get_queryset().filter(**{self.branch_field: self.request.branch})


class AuditedMixin:
    """Records create/update/delete of master data in the audit log."""

    def perform_create(self, serializer):
        instance = serializer.save(**self.get_save_kwargs())
        log_action(user=self.request.user, action="create", obj=instance, request=self.request, summary=str(instance))

    def perform_update(self, serializer):
        simple = {k: v for k, v in serializer.validated_data.items() if not isinstance(v, (list, dict))}
        changes = diff_instance(serializer.instance, simple)
        instance = serializer.save()
        log_action(
            user=self.request.user, action="update", obj=instance, request=self.request,
            summary=str(instance), changes=changes,
        )

    def perform_destroy(self, instance):
        log_action(user=self.request.user, action="delete", obj=instance, request=self.request, summary=str(instance))
        instance.delete()

    def get_save_kwargs(self) -> dict:
        return {}


class MasterDataViewSet(AuditedMixin, PermMixin, viewsets.ModelViewSet):
    """Business-wide master data (catalog, suppliers...)."""


class BranchModelViewSet(AuditedMixin, BranchMixin, viewsets.ModelViewSet):
    """Master data that belongs to one branch."""

    def get_save_kwargs(self):
        return {self.branch_field: self.request.branch}


class BranchReadOnlyViewSet(BranchMixin, viewsets.ReadOnlyModelViewSet):
    pass


class BranchAPIView(BranchMixin, APIView):
    def get_queryset(self):  # APIView subclasses query explicitly
        raise NotImplementedError
