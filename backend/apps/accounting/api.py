from django.utils.dateparse import parse_date
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.response import Response

from apps.common.schema import documented
from apps.common.api import BranchAPIView, BranchMixin, BranchReadOnlyViewSet, MasterDataViewSet

from . import services
from .models import Account, Expense, JournalEntry, JournalLine


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "code", "name", "type", "is_system", "is_active"]
        read_only_fields = ["is_system"]


class AccountViewSet(MasterDataViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    read_perm = "accounting.view"
    write_perm = "accounting.manage"
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        services.ensure_default_accounts()
        return super().list(request, *args, **kwargs)


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = JournalLine
        fields = ["id", "account", "account_code", "account_name", "debit", "credit", "description"]


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ["id", "date", "memo", "source_type", "source_id", "source_number", "reversal_of", "posted_by",
                  "created_at", "lines"]


class JournalEntryViewSet(BranchReadOnlyViewSet):
    """General ledger entries. Read-only: postings come from business documents."""

    queryset = JournalEntry.objects.prefetch_related("lines__account")
    serializer_class = JournalEntrySerializer
    read_perm = "accounting.view"
    filterset_fields = {"source_type": ["exact"], "date": ["gte", "lte"], "lines__account": ["exact"]}


class ExpenseSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = Expense
        fields = ["id", "account", "account_name", "amount", "paid_from", "description", "date", "created_by", "created_at"]
        read_only_fields = ["created_by"]


class ExpenseViewSet(BranchMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Expense.objects.select_related("account")
    serializer_class = ExpenseSerializer
    read_perm = "accounting.view"
    write_perm = "accounting.manage"
    filterset_fields = {"account": ["exact"], "date": ["gte", "lte"]}

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        expense = services.record_expense(
            branch=request.branch, user=request.user, account_obj=d["account"], amount=d["amount"],
            paid_from=d.get("paid_from", "cash"), description=d["description"], date=d.get("date"))
        return Response(self.get_serializer(expense).data, status=status.HTTP_201_CREATED)


class StatementView(BranchAPIView):
    """?statement=trial_balance|profit_and_loss|balance_sheet&date_from=&date_to=&consolidated=1"""

    read_perm = "accounting.view"

    @documented("Trial balance, profit & loss or balance sheet", params=("statement", "date_from", "date_to", "consolidated"))
    def get(self, request):
        q = request.query_params
        branches = [request.branch]
        if q.get("consolidated") in {"1", "true"}:
            branches = list(request.user.accessible_branches())
        date_from, date_to = parse_date(q.get("date_from", "") or ""), parse_date(q.get("date_to", "") or "")
        statement = q.get("statement", "trial_balance")
        if statement == "profit_and_loss":
            data = services.profit_and_loss(branches=branches, date_from=date_from, date_to=date_to)
        elif statement == "balance_sheet":
            data = services.balance_sheet(branches=branches, date_to=date_to)
        else:
            rows = services.trial_balance(branches=branches, date_from=date_from, date_to=date_to)
            data = {"rows": rows, "total_debit": sum(r["debit"] for r in rows), "total_credit": sum(r["credit"] for r in rows)}
        return Response(data)
