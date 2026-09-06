import text.Slug; import text.Header; import java.util.*;
public class GateTest {
 static int n; static void eq(Object a,Object b){n++;if(!Objects.equals(a,b))throw new AssertionError("expected "+b+" got "+a);}
 static void bad(Runnable r){n++;try{r.run();}catch(IllegalArgumentException e){return;}throw new AssertionError("expected rejection");}
 public static void main(String[]args){
 eq(Slug.of(" Hello, WORLD! "),"hello-world");eq(Slug.of("caf\u00e9 d\u00e9j\u00e0"),"cafe-deja");
 eq(Slug.of("A___B  12"),"a-b-12");eq(Slug.of(""),"");eq(Slug.of("---"),"");bad(()->Slug.of(null));
 Locale old=Locale.getDefault();try{Locale.setDefault(Locale.forLanguageTag("tr-TR"));eq(Slug.of("I"),"i");eq(Header.parse("X-ID: I"),Map.of("x-id","I"));}finally{Locale.setDefault(old);}
 eq(Header.parse(" Content-Type : Text/Plain "),Map.of("content-type","Text/Plain"));
 eq(Header.parse("Url: https://example.test:443"),Map.of("url","https://example.test:443"));eq(Header.parse("X-Empty: "),Map.of("x-empty",""));
 bad(()->Header.parse(null));bad(()->Header.parse("missing"));bad(()->Header.parse(":v"));bad(()->Header.parse("1X:v"));bad(()->Header.parse("a b:v"));
 bad(()->Header.parse("x:v\r\ny:z"));bad(()->Header.parse("x:v\n"));
 System.out.println("PASS "+n+" contract checks");}}
