import com.starcode.config.*;
import java.nio.file.*;import java.net.*;import java.net.http.*;import java.time.*;
/** Read-only HEAD request to the already configured provider; no model call/key sent. */
public class ConnectionProbe {
 public static void main(String[] args)throws Exception{
  var app=ConfigLoader.load(Path.of(args[0]));var p=app.providers().getFirst();
  var builder=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(20));
  if(app.proxy().enabled())builder.proxy(ProxySelector.of(new InetSocketAddress(app.proxy().host(),app.proxy().port())));
  try(var http=builder.build()){
   try{var r=http.send(HttpRequest.newBuilder(URI.create(p.baseUrl())).timeout(Duration.ofSeconds(30)).method("HEAD",HttpRequest.BodyPublishers.noBody()).build(),HttpResponse.BodyHandlers.discarding());System.out.println("TLS_AND_HTTP_REACHABLE status="+r.statusCode()+" proxy="+app.proxy().enabled());}
   catch(Exception e){System.out.println("CONNECTIVITY_FAILURE="+e.getClass().getSimpleName()+" proxy="+app.proxy().enabled());System.exit(2);}
  }
 }
}
