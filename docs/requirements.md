# Pharmacy Management ERP — Requirements

## 1. Product Overview
Build a production-ready Pharmacy / Medical Store ERP.

**Technology**
- Backend: Django + Django REST Framework
- Web frontend: Next.js + TypeScript
- Mobile: React Native + Expo
- Database: PostgreSQL
- Background jobs: Celery + Redis
- Push notifications: Firebase Cloud Messaging
- Deployment: Docker + Coolify

API-first architecture. All business rules must live in Django.

Support single and multiple branches.

## 2. Authentication & Permissions
- Owner / Super Admin
- Branch Admin / Manager
- Pharmacist
- Cashier
- Inventory Manager
- Purchase Officer
- Accountant
- Auditor
- Role-based and branch-based permissions.
- Restrict discounts, refunds, adjustments and approvals.
- Maintain user activity logs.
- Secure authentication, password reset and token management.

## 3. Medicine Catalog
- Medicine name, generic name, brand and manufacturer.
- Strength, dosage form and category.
- SKU, barcode and alternate barcodes.
- Prescription requirement.
- Product image and description.
- Purchase price, retail price and wholesale price.
- Tax and discount configuration.
- Minimum stock, reorder level and maximum stock.
- Preferred supplier.
- Product import/export through Excel/CSV.
- Duplicate product detection.

## 4. Units & Packaging
Support configurable conversions:

- Carton → Box
- Box → Strip
- Strip → Tablet
- Bottle → ml
- Other configurable units.

- Purchase and sale units may differ.
- Automatically calculate stock using base units.
- Prevent invalid fractional quantities.
- Maintain unit conversion history.

## 5. Batch & Inventory Management
- Batch-wise inventory.
- Batch number and expiry date.
- Manufacturing date.
- Purchase cost and selling price per batch.
- Supplier and purchase reference.
- Branch-wise stock.
- FEFO stock deduction.
- FIFO option.
- Prevent expired or blocked medicine sales.
- Near-expiry alerts: 30/60/90 days.
- Low-stock and out-of-stock tracking.
- Stock ledger and movement history.
- Damaged, lost and expired stock handling.
- Stock adjustments with approval.
- Physical stock counting.
- Stock transfers between branches.
- Prevent negative inventory.
- Maintain complete stock audit history.

## 6. Barcode Management
- USB barcode scanner support.
- Mobile camera barcode scanning.
- EAN-13, UPC and GTIN support.
- Custom barcode generation.
- Barcode label printing.
- Multiple barcodes per medicine.
- Barcode-based product lookup.
- Barcode scanning during sales, purchases and stock counting.
- Fast keyboard-driven POS.

## 7. Point of Sale (POS)
- Fast medicine search and barcode scanning.
- Add/remove products and edit quantities.
- Batch selection using FEFO.
- Box, strip and tablet sales.
- Customer selection.
- Prescription attachment where required.
- Item-level and invoice-level discounts.
- Tax calculation.
- Cash, card, bank and mobile wallet payments.
- Split payments.
- Customer credit sales.
- Hold and resume invoices.
- Sales cancellation with permissions.
- Full and partial returns.
- Thermal receipt printing (80mm).
- A4 invoice printing.
- Invoice reprinting.
- Cashier shift management.
- Cash opening and closing.

## 8. Purchasing & Suppliers
- Supplier profiles and contact information.
- Supplier opening balances.
- Supplier ledger.
- Purchase requisitions.
- Purchase orders.
- Purchase approval workflow.
- Supplier-wise product pricing.
- Expected delivery dates.
- Partial and complete receiving.
- Goods Received Notes (GRN).
- Batch and expiry entry during receiving.
- Handle damaged and short deliveries.
- Update stock only after confirmed receiving.
- Purchase invoices.
- Partial and full supplier payments.
- Supplier returns.
- Debit and credit notes.
- Outstanding supplier balances.
- Purchase history and price comparison.
- Purchase order PDF printing.

## 9. Smart Stock Alerts & Reordering
- Configurable minimum and reorder stock levels.
- Trigger alert when stock reaches or falls below threshold.
- Avoid duplicate alerts for the same low-stock condition.
- Notify authorized mobile users through FCM.
- Notification actions:
  - Add to Order List
  - Skip
- Capture requested quantity.
- Suggest reorder quantity using target stock minus available and on-order stock.
- Allow quantity editing.
- Record skipped notifications.
- Reset alert when stock recovers above threshold.
- Consolidate requested medicines into purchase requisitions.
- Admin can review and edit order lists.
- Group items by supplier.
- Convert approved requests into purchase orders.
- Track pending, approved, ordered, partially received and fulfilled status.

## 10. React Native Mobile Application
- Secure login.
- Branch selection.
- Role-based screens.
- Push notifications.
- Low-stock notifications.
- Add to Order List / Skip actions.
- Edit requested quantities.
- Product search.
- Stock and batch information.
- Expiry information.
- Camera barcode scanner.
- Purchase request management.
- Stock count.
- Adjustment requests.
- Transfer confirmation.
- Manager dashboard.
- Notification history.
- Deep links from notifications.
- Secure API integration.
- Offline read-only cache where appropriate.

## 11. Customer Management
- Customer profiles.
- Contact information.
- Purchase history.
- Sales returns.
- Customer credit limits.
- Outstanding balances.
- Customer ledger.
- Payment history.
- Loyalty points (optional).
- Customer groups and price tiers.

## 12. Accounting & Finance
- Double-entry accounting.
- Chart of accounts.
- Cash and bank accounts.
- Sales and purchase accounting.
- Supplier payables.
- Customer receivables.
- Expenses and expense categories.
- Payment tracking.
- Cash register reconciliation.
- Journal entries.
- General ledger.
- Trial balance.
- Profit & Loss.
- Balance sheet.
- Gross and net profit.
- Tax reports.
- Financial period closing.
- Reversal entries instead of deleting posted transactions.

## 13. Returns & Stock Adjustments
- Customer sales returns.
- Supplier purchase returns.
- Partial and full returns.
- Original invoice reference.
- Batch-wise return tracking.
- Return reasons.
- Damaged goods quarantine.
- Expired stock write-offs.
- Stock adjustment approvals.
- Complete audit trail.
- Reversal transactions.

## 14. Multi-Branch Management
- Multiple branches.
- Multiple warehouses.
- Branch-specific inventory.
- Branch-specific prices.
- Branch-level users and permissions.
- Inter-branch stock transfers.
- Dispatch and receiving confirmation.
- Centralized product catalog.
- Centralized or branch-level purchasing.
- Consolidated business reports.
- Strict branch data isolation.

## 15. Reports & Analytics

All reports should support date filters, branch filters and relevant product/supplier/user filters.

### Sales Reports
- Daily, weekly and monthly sales.
- Product-wise sales.
- Category-wise sales.
- Cashier-wise sales.
- Customer-wise sales.
- Sales returns.
- Discount reports.
- Payment method reports.

### Purchase Reports
- Supplier-wise purchases.
- Product-wise purchases.
- Purchase history.
- Outstanding purchase invoices.
- Supplier payment reports.

### Inventory Reports
- Current stock.
- Stock valuation.
- Stock ledger.
- Low-stock medicines.
- Out-of-stock medicines.
- Near-expiry medicines.
- Expired medicines.
- Dead stock.
- Fast-moving products.
- Slow-moving products.
- Stock turnover.
- Batch-wise inventory.

### Financial Reports
- Gross profit.
- Net profit.
- Product-wise profit.
- Category-wise profit.
- Expense reports.
- Cash flow.
- Supplier balances.
- Customer balances.
- General ledger.
- Trial balance.
- Profit & Loss.
- Balance sheet.

### Dashboard
- Today's sales.
- Monthly revenue.
- Gross profit.
- Total purchases.
- Current stock value.
- Low-stock count.
- Near-expiry count.
- Outstanding supplier payments.
- Customer receivables.
- Top-selling medicines.
- Sales and profit charts.

### Export
- PDF
- Excel/XLSX
- CSV
- Printable reports.

## 16. Notifications
- Low-stock alerts.
- Out-of-stock alerts.
- Near-expiry alerts.
- Expired stock alerts.
- Purchase approval requests.
- Purchase order status.
- Goods receiving notifications.
- Supplier payment due alerts.
- Stock transfer notifications.
- In-app notification center.
- Push notifications.
- Read/unread status.
- Notification preferences.
- Retry failed notifications.

## 17. System Configuration
- Business profile.
- Branch configuration.
- Currency and timezone.
- Tax settings.
- Invoice numbering.
- Receipt templates.
- Payment methods.
- Units and conversions.
- Reorder policies.
- Expiry warning policies.
- Discount limits.
- Approval workflows.
- Language settings.
- User permissions.
- Data import/export.
- Backup configuration.

## 18. Security & Audit
- Server-side permission enforcement.
- Branch-level access restrictions.
- Secure password hashing.
- Token rotation and expiration.
- HTTPS.
- API rate limiting.
- Secure file uploads.
- Activity and audit logs.
- Track stock, price, payment and refund changes.
- Database backups.
- Backup restoration testing.
- Error monitoring.
- Structured application logs.
- No destructive deletion of posted transactions.
- Idempotent critical operations.
- Database transaction integrity.

## 19. Technical Architecture

### Django Backend
Separate domain modules:
- accounts
- branches
- catalog
- inventory
- sales
- purchases
- suppliers
- customers
- accounting
- reports
- notifications
- audit

Use:
- DRF serializers and ViewSets/APIViews.
- Service layer for business operations.
- Selectors/query services for complex reads.
- PostgreSQL constraints and indexes.
- Atomic database transactions.
- Versioned REST APIs.
- OpenAPI documentation.
- Celery for background jobs.
- Redis for caching and task broker.

### Next.js Frontend
- App Router.
- TypeScript.
- Responsive dashboard.
- POS interface.
- Inventory management.
- Purchase management.
- Supplier management.
- Accounting.
- Reporting.
- Role-based navigation.
- Typed API client.
- Reusable components.

### React Native
- Expo.
- TypeScript.
- Shared API contracts.
- Camera barcode scanning.
- Push notifications.
- Secure token storage.
- Offline-safe read-only caching.

### DevOps
- Docker and Docker Compose.
- Environment-based configuration.
- CI/CD.
- Automated migrations.
- Health checks.
- Centralized logs.
- Production backups.
- Coolify deployment support.

## 20. Critical Business Rules
- Only posted inventory transactions change stock.
- Sales must atomically validate and deduct stock.
- Purchase orders do not increase stock.
- Confirmed GRN increases stock.
- Draft/cancelled documents do not affect stock or accounts.
- Expired and blocked batches cannot be sold.
- Returns must reference original transactions where possible.
- Stock history must never be silently overwritten.
- Profit must use actual batch cost and defined costing policy.
- Reorder quantity must consider on-hand, reserved and on-order stock.
- Monetary calculations must use Decimal, never float.
- Every transaction records branch, user, timestamp and source document.
- Critical operations must be safe against duplicate requests and concurrent execution.

## 21. Development Priorities

### Phase 1 — Core ERP
- Authentication and permissions.
- Product catalog.
- Units and packaging.
- Batch inventory.
- Barcode support.
- FEFO.
- POS and sales.
- Purchases and GRN.
- Suppliers.
- Returns.
- Stock ledger.
- Core reports.
- Audit logs.

### Phase 2 — Smart Inventory
- Reorder thresholds.
- Smart purchase suggestions.
- Purchase requisitions.
- Approval workflow.
- Notification infrastructure.
- React Native application.
- FCM integration.
- Add to Order List / Skip workflow.

### Phase 3 — Advanced ERP
- Full accounting.
- Multi-branch operations.
- Stock transfers.
- Advanced analytics.
- Customer credit and loyalty.
- Advanced financial statements.

### Phase 4 — Optimization
- Offline POS.
- Demand forecasting.
- Advanced integrations.
- Performance optimization.
- Security review.

## 22. Definition of Done
- All critical workflows have automated tests.
- Concurrent sales cannot oversell stock.
- Expired batches cannot be sold.
- Receiving updates stock exactly once.
- Returns and reversals preserve history.
- Branch permissions are tested.
- Reports reconcile with inventory and accounting ledgers.
- Backup restoration is verified.
- API documentation is complete.
- Docker deployment works.
- No critical security or data-integrity issues remain.