import stats.Mean; import retry.Delay;
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
