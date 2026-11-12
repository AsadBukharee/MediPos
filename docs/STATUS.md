# Build status against the requirements

Last updated with the first commit. Section numbers refer to [`requirements.md`](requirements.md).

## Verified

- Backend: 106 automated tests pass on PostgreSQL 16 (66 of them are one smoke check per read endpoint and report), including 25 concurrent sales against 10 units of
  stock (exactly 10 succeed), expired-batch refusal, GRN confirmed twice (stock once), returns and
  cancellations preserving history, branch isolation, role restrictions, alert de-duplication, and
  stock valuation = stock ledger = Inventory GL account, and gross profit agreeing across the sales report, the
  per-medicine report and the profit & loss statement.
- Sales trends: the chart was driven in a browser against 218 seeded sales — five medicines
  picked through the search-and-tick dropdown render five distinct lines, the crosshair reads out
  every series at once, keyboard arrows move it, removing a medicine leaves the others' colours
  untouched, and the table view lists every value. Its palette is validated for colour-vision
  deficiency on this surface.
- Web app: lint, type-check and both production builds pass — the Vercel-style build (every route
  prerendered as static content, nothing fetched at build time) and the Docker standalone build. Login, dashboard, a POS sale with receipt, and
  every page were opened in a real browser against the running API with no console or API errors.
- Phone app: lint, type-check, `expo-doctor` (20/20) and an Android bundle export pass.
- Backup and restore scripts were run against a real database.

## Not verified here

- **The phone app has not been run on a device or emulator.** Screens, camera scanning and push are
  written against the installed SDK 58 type definitions but untested at runtime.
- **Push notifications** need a Firebase project. The Android payload follows what `expo-notifications`
  reads (data-only message with `title`, `message`, `body`, `categoryId`, `channelId`), unverified
  end to end. iOS push will not work as is: the app registers the native device token, which FCM
  only accepts for Android.
- **Docker images were not built** in the environment this was written in (no Docker daemon). The
  `docker` CI job builds them and waits for the health checks.

## Built

| # | Area | Notes |
| --- | --- | --- |
| 2 | Authentication & permissions | JWT with rotation and blacklist, 8 roles, branch membership, discount limits per user and per medicine, password change/reset, rate-limited auth, activity log |
| 3 | Medicine catalog | All listed fields, CSV import/export, duplicate detection, multiple barcodes |
| 4 | Units & packaging | Per-medicine packs with base-unit factors, whole numbers only, conversion changes audited |
| 5 | Batch inventory | Batches, FEFO/FIFO, expiry and block rules, ledger, adjustments with approval, low/out/near-expiry |
| 6 | Barcodes | EAN/UPC/GTIN validation, in-store EAN-13 generation, USB scanner in POS, camera scan on phone |
| 7 | POS | Search/scan, box/strip/tablet, discounts, tax, split payments, credit sales, hold/resume, cancel, returns, 80mm and A4 printing, reprint, shifts |
| 8 | Purchasing | Requisitions, POs with approval, partial receiving, GRN with batch/expiry, supplier ledger, payments, supplier returns, supplier prices |
| 9 | Smart alerts & reordering | Threshold alerts without duplicates, Add to Order List / Skip, suggested quantity (target − free − on order), reset on recovery, group by supplier, convert to POs, status tracking |
| 10 | Mobile app | Login, branch selection, role-based tabs, alerts with actions, order list, search, stock/batch/expiry, scanner, adjustment requests, manager dashboard, notification history, deep links, offline read-only cache |
| 11 | Customers | Profiles, price tiers, credit limits, balances, payments |
| 12 | Accounting | Chart of accounts, automatic postings for sales, returns, GRNs, payments, adjustments; expenses; general ledger, trial balance, P&L, balance sheet; period lock; reversals |
| 15 | Reports | Dashboard; **sales trends — up to eight medicines as coloured lines over time, by hour/day/week/month, units or revenue, with each medicine's peak marked**; sales by day/medicine/category/cashier/customer/payment method; purchases by supplier/medicine; valuation, low/out, expiry, fast/slow/dead stock; CSV export and print |
| 16 | Notifications | In-app centre, read/unread, preferences, FCM sender with retry, low/out-of-stock, near-expiry/expired, approval requests, goods received |
| 18–19 | Security & architecture | Server-side enforcement, service layer, selectors, constraints, atomic transactions, idempotency, versioned API, OpenAPI, structured logs, health checks, CI |

## Not built yet

- **Inter-branch stock transfers** and **physical stock counting** (web and phone), and the phone's
  transfer confirmation and stock count screens that depend on them.
- **Loyalty points** (the field exists; nothing earns or redeems points).
- **PDF and XLSX exports** (reports export CSV and print from the browser; no PDF purchase order
  file), **XLSX import** (CSV only), **barcode label printing**.
- **Settings screens** on the web: business profile, tax, receipt template, invoice numbering and
  approval workflow configuration. The profile has an API; numbering prefixes and period closing are
  edited in the Django admin (`/admin/`).
- **Customer statement / ledger screen**, **cash-flow report**, standalone debit/credit notes (a
  supplier return acts as the debit note).
- **Notifications:** supplier-payment-due and purchase-order-status alerts.
- **Phase 4:** offline POS, demand forecasting, external integrations.
- **Automated tests for the web and phone apps** (only lint, types and builds are checked).

## Known limitations

- The web app keeps its tokens in `localStorage`. Moving to httpOnly cookies behind a small
  server-side proxy would reduce what an XSS bug could steal.
- Journal amounts are rounded to 2 decimals per document while batch cost keeps 6, so the Inventory
  account and the stock valuation can drift by fractions of a rupee over many sales of odd-cost items.
- A sales return marked "damaged" refunds the customer but does not put stock back; it is not moved
  to a separate quarantine location.
- No security review or load test has been done.
