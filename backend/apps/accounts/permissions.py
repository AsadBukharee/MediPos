"""Role → permission codes. The server is the only place these are enforced."""

OWNER = "owner"
BRANCH_ADMIN = "branch_admin"
PHARMACIST = "pharmacist"
CASHIER = "cashier"
INVENTORY_MANAGER = "inventory_manager"
PURCHASE_OFFICER = "purchase_officer"
ACCOUNTANT = "accountant"
AUDITOR = "auditor"

ROLE_CHOICES = [
    (OWNER, "Owner / Super Admin"),
    (BRANCH_ADMIN, "Branch Admin / Manager"),
    (PHARMACIST, "Pharmacist"),
    (CASHIER, "Cashier"),
    (INVENTORY_MANAGER, "Inventory Manager"),
    (PURCHASE_OFFICER, "Purchase Officer"),
    (ACCOUNTANT, "Accountant"),
    (AUDITOR, "Auditor"),
]

ALL_PERMISSIONS = {
    "system.manage": "Business profile, branches and configuration",
    "users.manage": "Create and edit users",
    "catalog.view": "View medicines",
    "catalog.manage": "Create and edit medicines, units and barcodes",
    "inventory.view": "View stock, batches and the stock ledger",
    "inventory.adjust": "Request stock adjustments and block batches",
    "inventory.adjust.approve": "Approve stock adjustments",
    "suppliers.view": "View suppliers",
    "suppliers.manage": "Create and edit suppliers",
    "suppliers.pay": "Record supplier payments",
    "customers.view": "View customers",
    "customers.manage": "Create and edit customers, receive customer payments",
    "purchases.view": "View purchase documents",
    "purchases.manage": "Create purchase orders and supplier returns",
    "purchases.approve": "Approve requisitions and purchase orders",
    "purchases.receive": "Create and confirm goods received notes",
    "requisitions.manage": "Edit the order list / purchase requisitions",
    "alerts.act": "Receive stock alerts and add to order list / skip",
    "sales.view": "View invoices",
    "sales.create": "Sell at the POS",
    "sales.return": "Process sales returns and refunds",
    "sales.cancel": "Cancel completed invoices",
    "accounting.view": "View ledgers and financial statements",
    "accounting.manage": "Post journal entries and expenses",
    "reports.view": "View reports and dashboards",
    "audit.view": "View audit logs",
}

VIEW_ONLY = {code for code in ALL_PERMISSIONS if code.endswith(".view")}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    OWNER: set(ALL_PERMISSIONS),
    BRANCH_ADMIN: set(ALL_PERMISSIONS) - {"system.manage"},
    PHARMACIST: {
        "catalog.view", "inventory.view", "customers.view", "customers.manage",
        "sales.view", "sales.create", "sales.return", "alerts.act", "requisitions.manage",
    },
    CASHIER: {"catalog.view", "inventory.view", "customers.view", "sales.view", "sales.create"},
    INVENTORY_MANAGER: {
        "catalog.view", "catalog.manage", "inventory.view", "inventory.adjust", "suppliers.view",
        "purchases.view", "purchases.receive", "alerts.act", "requisitions.manage", "reports.view",
    },
    PURCHASE_OFFICER: {
        "catalog.view", "inventory.view", "suppliers.view", "suppliers.manage", "purchases.view",
        "purchases.manage", "purchases.receive", "alerts.act", "requisitions.manage", "reports.view",
    },
    ACCOUNTANT: VIEW_ONLY | {"accounting.manage", "suppliers.pay", "customers.manage"},
    AUDITOR: set(VIEW_ONLY),
}
