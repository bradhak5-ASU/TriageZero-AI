"""Scenario templates for the synthetic historical corpus.

Compact templates plus a seeded generator, rather than hundreds of committed
JSON files. Each template is one *family*: variants of a family are
near-duplicates of each other, which is exactly why splitting must be grouped
by family (see ``datasets.py``) — a random row split would put near-identical
cases on both sides and inflate every metric.

The expected outcome of each family lives in ``EXPECTED_BY_FAILURE`` — the
private oracle. It is deliberately kept out of the generated failure packages
and is loaded only after a prediction has been made.
"""

from dataclasses import dataclass, field

REPOSITORIES = ("novacart-target", "novacart-web", "novacart-api", "novacart-playwright")
BROWSERS = ("chromium", "firefox", "webkit")
ENVIRONMENTS = ("local", "staging", "production")


@dataclass(frozen=True)
class ScenarioTemplate:
    """One failure family and the ground truth it should produce."""

    family: str
    expected_classification: str
    expected_severity: str
    expected_release_risk: str
    test_names: tuple[str, ...]
    test_files: tuple[str, ...]
    messages: tuple[str, ...]
    endpoints: tuple[str, ...] = ()
    methods: tuple[str, ...] = ("POST", "GET", "PATCH")
    statuses: tuple[int, ...] = ()
    console_lines: tuple[str, ...] = ()
    expected_values: tuple[str, ...] = ("",)
    actual_values: tuple[str, ...] = ("",)
    stack_components: tuple[str, ...] = ("spec.ts",)
    resolutions: tuple[str, ...] = ("Fixed by the owning team.",)
    root_causes: tuple[str, ...] = ("Root cause recorded during review.",)
    noise_console: tuple[str, ...] = field(default=("Download the React DevTools",))


TEMPLATES: tuple[ScenarioTemplate, ...] = (
    ScenarioTemplate(
        family="backend_5xx_checkout",
        expected_classification="backend_application_defect",
        expected_severity="critical",
        expected_release_risk="block_release",
        test_names=(
            "successful checkout shows confirmation page",
            "order submission returns confirmation",
            "checkout completes for signed-in user",
        ),
        test_files=("playwright-tests/tests/checkout.spec.ts",
                    "playwright-tests/tests/novacart-baseline.spec.ts"),
        messages=(
            "Expected HTTP 201 but received HTTP {status}",
            "Order creation failed with HTTP {status}",
            "expect(response.status()).toBe(201) — received {status}",
        ),
        endpoints=("/api/v1/orders", "/api/v1/orders/submit", "/api/v1/checkout"),
        methods=("POST",),
        statuses=(500, 502, 503),
        expected_values=("201",),
        actual_values=("500", "502", "503"),
        stack_components=("checkout.page.ts", "orders.spec.ts"),
        resolutions=("Null-check added in the orders service; hotfix released.",
                     "Unhandled exception in order creation fixed."),
        root_causes=("The order-creation endpoint raised before persisting the order.",
                     "Order submission returned a server error instead of 201."),
    ),
    ScenarioTemplate(
        family="backend_5xx_inventory",
        expected_classification="backend_application_defect",
        expected_severity="critical",
        expected_release_risk="block_release",
        test_names=("inventory endpoint returns stock levels",
                    "product availability loads on PDP"),
        test_files=("playwright-tests/tests/inventory.spec.ts",),
        messages=("Expected HTTP 200 but received HTTP {status}",
                  "Inventory read failed with HTTP {status}"),
        endpoints=("/api/v1/inventory", "/api/v1/inventory/LAMP-042"),
        methods=("GET",),
        statuses=(500, 503),
        expected_values=("200",),
        actual_values=("500", "503"),
        stack_components=("inventory.spec.ts",),
        resolutions=("Inventory query fixed after schema change.",),
        root_causes=("The inventory service errored on a renamed column.",),
    ),
    ScenarioTemplate(
        family="frontend_type_error",
        expected_classification="frontend_application_defect",
        expected_severity="high",
        expected_release_risk="high",
        test_names=("mini-cart badge shows item count",
                    "wishlist icon reflects saved items",
                    "header renders account menu"),
        test_files=("playwright-tests/tests/cart.spec.ts",
                    "playwright-tests/tests/header.spec.ts"),
        messages=("expect(locator).toHaveText — badge not found",
                  "expect(locator).toBeVisible — element missing from DOM"),
        endpoints=("/api/v1/cart", "/api/v1/wishlist"),
        methods=("GET",),
        statuses=(200,),
        console_lines=(
            "TypeError: undefined is not an object (evaluating 'items.reduce') — cart-store.ts:41",
            "TypeError: Cannot read properties of undefined (reading 'length') — header.tsx:88",
            "ReferenceError: formatCurrency is not defined — price.tsx:12",
        ),
        stack_components=("cart.spec.ts", "header.spec.ts"),
        resolutions=("Guarded the empty-state hydration path.",),
        root_causes=("A client-side error prevented the component from rendering.",),
    ),
    ScenarioTemplate(
        family="selector_drift",
        expected_classification="test_automation_defect",
        expected_severity="medium",
        expected_release_risk="low",
        test_names=("product search returns results",
                    "category filter narrows results",
                    "promo banner is visible"),
        test_files=("playwright-tests/tests/search.spec.ts",
                    "playwright-tests/tests/home.spec.ts"),
        messages=(
            'Timeout 15000ms waiting for locator("[data-test=result-card]")',
            'Timeout 30000ms exceeded waiting for locator("[data-test=banner]")',
            'locator.waitFor: Timeout 20000ms waiting for selector ".legacy-class"',
        ),
        endpoints=(),
        statuses=(),
        expected_values=("at least 1 result card",),
        actual_values=("locator matched 0 elements",),
        stack_components=("search.spec.ts", "home.spec.ts"),
        resolutions=("Selectors migrated to getByRole.",),
        root_causes=("The selector no longer matched after a UI refactor.",),
    ),
    ScenarioTemplate(
        family="environment_dns",
        expected_classification="environment_failure",
        expected_severity="low",
        expected_release_risk="none",
        test_names=("login succeeds with valid credentials",
                    "home page loads",
                    "api reachable from suite"),
        test_files=("playwright-tests/tests/auth.spec.ts",
                    "playwright-tests/tests/smoke.spec.ts"),
        messages=(
            "page.goto: net::ERR_NAME_NOT_RESOLVED at staging.novacart.internal",
            "connect ECONNREFUSED 127.0.0.1:8000",
            "page.goto: net::ERR_CONNECTION_REFUSED",
        ),
        endpoints=("/", "/api/v1/auth/login"),
        methods=("GET", "POST"),
        statuses=(0,),
        stack_components=("auth.spec.ts", "smoke.spec.ts"),
        resolutions=("Suite re-run green after the environment recovered.",),
        root_causes=("The target environment was unreachable for the whole run.",),
    ),
    ScenarioTemplate(
        family="data_integrity_totals",
        expected_classification="data_integrity_defect",
        expected_severity="high",
        expected_release_risk="high",
        test_names=("inventory decrements after order",
                    "cart total matches line items",
                    "account balance updates after refund"),
        test_files=("playwright-tests/tests/inventory.spec.ts",
                    "playwright-tests/tests/cart.spec.ts"),
        messages=("expect(stock).toBe({expected}) — received {actual}",
                  "expect(total).toBe({expected}) — received {actual}",
                  "expect(balance).toBe({expected}) — received {actual}"),
        endpoints=("/api/v1/inventory/LAMP-042", "/api/v1/cart"),
        methods=("GET",),
        statuses=(200,),
        expected_values=("4", "124.50", "80.00"),
        actual_values=("5", "0.00", "100.00"),
        stack_components=("inventory.spec.ts", "cart.spec.ts"),
        resolutions=("Audit-log insert decoupled from the inventory transaction.",),
        root_causes=("Stored business data diverged from the operation performed.",),
    ),
    ScenarioTemplate(
        family="performance_budget",
        expected_classification="performance_timing_defect",
        expected_severity="medium",
        expected_release_risk="moderate",
        test_names=("checkout completes within 5 seconds",
                    "search responds within budget",
                    "PDP renders within budget"),
        test_files=("playwright-tests/tests/perf.spec.ts",),
        messages=("expect(duration).toBeLessThan(5000) — received {actual}",
                  "flow took {actual}ms, exceeding the 3000ms budget"),
        endpoints=("/api/v1/tax/quote", "/api/v1/search"),
        methods=("POST", "GET"),
        statuses=(200,),
        expected_values=("under 5000ms",),
        actual_values=("6480", "7220", "5310"),
        stack_components=("perf.spec.ts",),
        resolutions=("Slow endpoint cached per request hash.",),
        root_causes=("A new call added latency beyond the configured budget.",),
    ),
    ScenarioTemplate(
        family="dependency_provider",
        expected_classification="dependency_failure",
        expected_severity="high",
        expected_release_risk="moderate",
        test_names=("payment provider sandbox responds",
                    "address autocomplete suggests entries",
                    "shipping rates load"),
        test_files=("playwright-tests/tests/payment.spec.ts",
                    "playwright-tests/tests/checkout.spec.ts"),
        messages=("Expected 200 but received {status} from provider sandbox",
                  "Third-party request failed with HTTP {status}"),
        endpoints=("https://pay.sandbox.example-psp.com/tokenize",
                   "https://geo.example-maps.com/v2/suggest",
                   "https://rates.example-ship.com/v1/quote"),
        methods=("POST", "GET"),
        statuses=(500, 503),
        expected_values=("200",),
        actual_values=("503", "500"),
        stack_components=("payment.spec.ts",),
        resolutions=("Waited out the provider incident; CI mock added.",),
        root_causes=("An external provider returned server errors.",),
    ),
    ScenarioTemplate(
        family="unknown_sparse",
        expected_classification="unknown",
        expected_severity="medium",
        expected_release_risk="moderate",
        test_names=("assertion mismatch in flow",
                    "unexpected state after navigation",
                    "intermittent assertion failure"),
        test_files=("playwright-tests/tests/misc.spec.ts",),
        messages=("assertion mismatch", "unexpected state", "expectation not met"),
        endpoints=(),
        statuses=(),
        stack_components=("misc.spec.ts",),
        resolutions=("Closed after manual review; insufficient evidence captured.",),
        root_causes=("Evidence was insufficient to determine a cause.",),
    ),
)

TEMPLATES_BY_FAMILY = {template.family: template for template in TEMPLATES}
