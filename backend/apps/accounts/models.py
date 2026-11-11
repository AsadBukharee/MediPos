from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from . import permissions as perms


class User(AbstractUser):
    role = models.CharField(max_length=24, choices=perms.ROLE_CHOICES, default=perms.CASHIER)
    branches = models.ManyToManyField("branches.Branch", blank=True, related_name="users")
    phone = models.CharField(max_length=40, blank=True)
    max_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Largest total discount this user may give on an invoice.",
    )

    @property
    def effective_role(self) -> str:
        return perms.OWNER if self.is_superuser else self.role

    @property
    def is_owner(self) -> bool:
        return self.effective_role == perms.OWNER

    @property
    def permission_codes(self) -> set[str]:
        return perms.ROLE_PERMISSIONS.get(self.effective_role, set())

    def has_perm_code(self, code: str) -> bool:
        return self.is_active and code in self.permission_codes

    def accessible_branches(self):
        from apps.branches.models import Branch

        if self.is_owner:
            return Branch.objects.filter(is_active=True)
        return self.branches.filter(is_active=True)

    def can_access_branch(self, branch) -> bool:
        return self.accessible_branches().filter(pk=branch.pk).exists()
