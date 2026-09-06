# Checkout validation gate
Implement the existing production interfaces without modifying the verifier or changing signatures.
This is a small feasibility gate, not a speed benchmark.

ShippingQuote.quoteCents(weightGrams, postalCode): reject nonpositive grams and null/blank postal codes.
Trim and uppercase postal codes with Locale.ROOT. Domestic codes begin with AU, NZ, or INTL.
AU costs 450 cents plus 120 cents per started 500 grams. NZ costs 850 plus 210 per started 500 grams.
INTL costs 1800 plus 450 per started 500 grams. Reject any other prefix. Use long for intermediate arithmetic
and reject totals beyond Integer.MAX_VALUE.

DiscountPolicy.totalCents(unitCents, quantity, member): reject negative unit cents or quantity.
A zero quantity returns zero. Members get 7 percent discount; nonmembers get none.
Quantity at least 12 adds another 5 percentage points. Round the final total to the nearest cent with HALF_EVEN.
Use exact arithmetic and reject results beyond Integer.MAX_VALUE.

Run: powershell.exe -NoProfile -File ./verify.ps1
Both components must be integrated in the main checkout and all checks must pass.
