from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parent/'multi-agent'/'fixture'
files={
'.gitignore':'.mewcode/\n.starcode/\nbuild/\n',
'README.md':'''# Checkout validation gate
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
''',
'src/checkout/shipping/ShippingQuote.java':'''package checkout.shipping;
public final class ShippingQuote {
    public static int quoteCents(int weightGrams, String postalCode) {
        throw new UnsupportedOperationException("Not implemented");
    }
}
''',
'src/checkout/pricing/DiscountPolicy.java':'''package checkout.pricing;
public final class DiscountPolicy {
    public static int totalCents(int unitCents, int quantity, boolean member) {
        throw new UnsupportedOperationException("Not implemented");
    }
}
''',
'verify.ps1':'''$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'build') | Out-Null
$sources=@(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'src') -Recurse -Filter '*.java' | ForEach-Object {$_.FullName})
& javac -d (Join-Path $PSScriptRoot 'build') @sources (Join-Path $PSScriptRoot 'tests\\GateTest.java')
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& java -cp (Join-Path $PSScriptRoot 'build') GateTest
exit $LASTEXITCODE
''',
'tests/GateTest.java':'''import checkout.shipping.ShippingQuote;
import checkout.pricing.DiscountPolicy;
public final class GateTest {
 static int checks;
 static void eq(int a,int b){checks++;if(a!=b)throw new AssertionError("expected "+b+" got "+a);}
 static void bad(Runnable r){checks++;try{r.run();}catch(IllegalArgumentException e){return;}throw new AssertionError("Expected IllegalArgumentException");}
 public static void main(String[] args){
  eq(ShippingQuote.quoteCents(1,"AU2000"),570);eq(ShippingQuote.quoteCents(500," au2000 "),570);
  eq(ShippingQuote.quoteCents(501,"AU2000"),690);eq(ShippingQuote.quoteCents(1500,"NZ6011"),1480);
  eq(ShippingQuote.quoteCents(501,"intl-90210"),2700);
  bad(()->ShippingQuote.quoteCents(0,"AU"));bad(()->ShippingQuote.quoteCents(-1,"AU"));
  bad(()->ShippingQuote.quoteCents(1,null));bad(()->ShippingQuote.quoteCents(1," "));bad(()->ShippingQuote.quoteCents(1,"US"));
  eq(DiscountPolicy.totalCents(1000,1,false),1000);eq(DiscountPolicy.totalCents(1000,1,true),930);
  eq(DiscountPolicy.totalCents(1000,12,false),11400);eq(DiscountPolicy.totalCents(1000,12,true),10560);
  eq(DiscountPolicy.totalCents(50,1,true),46);eq(DiscountPolicy.totalCents(150,1,true),140);
  eq(DiscountPolicy.totalCents(100,0,true),0);eq(DiscountPolicy.totalCents(0,40,true),0);
  bad(()->DiscountPolicy.totalCents(-1,1,false));bad(()->DiscountPolicy.totalCents(1,-1,false));
  bad(()->DiscountPolicy.totalCents(Integer.MAX_VALUE,2,false));
  System.out.println("PASS "+checks+" contract checks");
 }
}
'''
}
for name,text in files.items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
(root.parent/'fixture-manifest.json').write_text(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files},indent=2),encoding='utf-8')