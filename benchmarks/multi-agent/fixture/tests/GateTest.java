import checkout.shipping.ShippingQuote;
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
