"""Freeze three independent E2E contracts; never implement or integrate Agent work."""
from pathlib import Path
import json, hashlib, shutil

here=Path(__file__).resolve().parent
root=here.parent
target=here/'fixtures'
if target.exists(): raise SystemExit('Fixtures already frozen; refusing to overwrite')
target.mkdir()
shutil.copytree(root/'multi-agent/fixture', target/'checkout')
contracts={'checkout':['src/checkout/shipping/ShippingQuote.java','src/checkout/pricing/DiscountPolicy.java']}

def write(case, file, value):
    p=target/case/file;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(value,encoding='utf-8',newline='')

write('text','README.md','''# Text utilities contract
Implement two existing independent interfaces, preserving signatures and verification files.
text.Slug.of(String): reject null with IllegalArgumentException. Normalize NFKD, discard Unicode combining marks,
lowercase with Locale.ROOT, replace each run outside ASCII a-z/0-9 with one hyphen, strip edge hyphens.
An empty or punctuation-only input returns the empty string.
text.Header.parse(String): reject null, CR/LF anywhere, no colon, or an invalid header name with IllegalArgumentException.
Split at the FIRST colon. Trim both parts; lowercase name with Locale.ROOT. Name must match [a-z][a-z0-9-]*.
Return a one-entry Map<String,String>; value can be empty and can contain additional colons. Preserve value case.
Read tests/GateTest.java for boundary checks. Run powershell.exe -NoProfile -File ./verify.ps1 after integrating both components.
''')
write('text','src/text/Slug.java','package text; public final class Slug { public static String of(String text) { throw new UnsupportedOperationException("Not implemented"); } }\n')
write('text','src/text/Header.java','package text; public final class Header { public static java.util.Map<String,String> parse(String line) { throw new UnsupportedOperationException("Not implemented"); } }\n')
write('text','tests/GateTest.java','''import text.Slug; import text.Header; import java.util.*;
public class GateTest {
 static int n; static void eq(Object a,Object b){n++;if(!Objects.equals(a,b))throw new AssertionError("expected "+b+" got "+a);}
 static void bad(Runnable r){n++;try{r.run();}catch(IllegalArgumentException e){return;}throw new AssertionError("expected rejection");}
 public static void main(String[]args){
 eq(Slug.of(" Hello, WORLD! "),"hello-world");eq(Slug.of("caf\\u00e9 d\\u00e9j\\u00e0"),"cafe-deja");
 eq(Slug.of("A___B  12"),"a-b-12");eq(Slug.of(""),"");eq(Slug.of("---"),"");bad(()->Slug.of(null));
 Locale old=Locale.getDefault();try{Locale.setDefault(Locale.forLanguageTag("tr-TR"));eq(Slug.of("I"),"i");eq(Header.parse("X-ID: I"),Map.of("x-id","I"));}finally{Locale.setDefault(old);}
 eq(Header.parse(" Content-Type : Text/Plain "),Map.of("content-type","Text/Plain"));
 eq(Header.parse("Url: https://example.test:443"),Map.of("url","https://example.test:443"));eq(Header.parse("X-Empty: "),Map.of("x-empty",""));
 bad(()->Header.parse(null));bad(()->Header.parse("missing"));bad(()->Header.parse(":v"));bad(()->Header.parse("1X:v"));bad(()->Header.parse("a b:v"));
 bad(()->Header.parse("x:v\\r\\ny:z"));bad(()->Header.parse("x:v\\n"));
 System.out.println("PASS "+n+" contract checks");}}
''')
contracts['text']=['src/text/Slug.java','src/text/Header.java']
write('numeric','README.md','''# Numeric utilities contract
Implement two independent interfaces; invalid inputs must throw IllegalArgumentException.
stats.Mean.rounded(long[]): reject null/empty. Compute the arithmetic mean rounded to the nearest long with HALF_EVEN.
Intermediate sum must not overflow even for Long.MAX_VALUE and Long.MIN_VALUE arrays. Do not mutate the input.
retry.Delay.millis(long base, int attempt, long cap): require base>=1, attempt>=0, cap>=base.
Return min(cap, base * 2^attempt), avoiding overflow and avoiding work proportional to very large attempt values.
Read tests/GateTest.java. Preserve signatures, README.md, verifier and tests. Integrate both modules and run
powershell.exe -NoProfile -File ./verify.ps1 in the main checkout.
''')
write('numeric','src/stats/Mean.java','package stats; public final class Mean { public static long rounded(long[] values) { throw new UnsupportedOperationException("Not implemented"); } }\n')
write('numeric','src/retry/Delay.java','package retry; public final class Delay { public static long millis(long base,int attempt,long cap) { throw new UnsupportedOperationException("Not implemented"); } }\n')
write('numeric','tests/GateTest.java','''import stats.Mean; import retry.Delay;
public class GateTest {
 static int n;static void eq(long a,long b){n++;if(a!=b)throw new AssertionError("expected "+b+" got "+a);}
 static void bad(Runnable r){n++;try{r.run();}catch(IllegalArgumentException e){return;}throw new AssertionError("expected rejection");}
 public static void main(String[]args){
 eq(Mean.rounded(new long[]{1,2}),2);eq(Mean.rounded(new long[]{2,3}),2);eq(Mean.rounded(new long[]{-1,-2}),-2);
 eq(Mean.rounded(new long[]{-2,-3}),-2);eq(Mean.rounded(new long[]{Long.MAX_VALUE,Long.MAX_VALUE}),Long.MAX_VALUE);
 eq(Mean.rounded(new long[]{Long.MIN_VALUE,Long.MIN_VALUE}),Long.MIN_VALUE);eq(Mean.rounded(new long[]{Long.MIN_VALUE,Long.MAX_VALUE}),0);
 long[] a={9,1,5};eq(Mean.rounded(a),5);eq(a[0],9);bad(()->Mean.rounded(null));bad(()->Mean.rounded(new long[]{}));
 eq(Delay.millis(10,0,100),10);eq(Delay.millis(10,3,100),80);eq(Delay.millis(10,4,100),100);
 eq(Delay.millis(1,Integer.MAX_VALUE,Long.MAX_VALUE),Long.MAX_VALUE);eq(Delay.millis(Long.MAX_VALUE,1,Long.MAX_VALUE),Long.MAX_VALUE);
 eq(Delay.millis(3,61,Long.MAX_VALUE),6917529027641081856L);bad(()->Delay.millis(0,0,1));bad(()->Delay.millis(1,-1,3));bad(()->Delay.millis(5,1,4));
 System.out.println("PASS "+n+" contract checks");}}
''')
contracts['numeric']=['src/stats/Mean.java','src/retry/Delay.java']
for case,paths in contracts.items():
    if case!='checkout': shutil.copyfile(root/'multi-agent/fixture/verify.ps1',target/case/'verify.ps1')
    write(case,'contract.json',json.dumps({'components':paths},indent=2)+'\n')
manifest={p.relative_to(here).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(here/'fixtures.sha256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='')
print(json.dumps({'contracts':list(contracts),'files':len(manifest)}))
