package bench;
import com.sun.net.httpserver.*;
import com.starcode.config.*;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
/** Actual HTTP bodies, never request headers or credentials. */
public final class QualityWireRecorder implements AutoCloseable {
 final HttpServer server; final ExecutorService executor=Executors.newVirtualThreadPerTaskExecutor();
 final ScheduledExecutorService watchdog=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r,"benchmark-watchdog");t.setDaemon(true);return t;}); volatile boolean timedOut;
 final AtomicInteger sequence=new AtomicInteger(); final Path dir; final ProviderConfig upstream; final AppConfig app; final boolean mock; final HttpClient http;
 public QualityWireRecorder(Path dir,ProviderConfig upstream,AppConfig app,boolean mock)throws Exception{
  this.dir=dir;this.upstream=upstream;this.app=app;this.mock=mock;Files.createDirectories(dir);
  var hb=HttpClient.newBuilder().connectTimeout(app.requestTimeout());
  if(app.proxy().enabled())hb.proxy(ProxySelector.of(new InetSocketAddress(app.proxy().host(),app.proxy().port())));
  http=hb.build();server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);server.setExecutor(executor);server.createContext("/",this::handle);server.start();
 }
 public ProviderConfig localProvider(){return new ProviderConfig(upstream.name(),upstream.protocol(),"http://127.0.0.1:"+server.getAddress().getPort(),upstream.apiKeyEnv(),upstream.model(),upstream.thinking(),upstream.contextWindow());}
 String redact(String s){String key=System.getenv(upstream.apiKeyEnv());return key==null||key.isBlank()?s:s.replace(key,"[REDACTED]");}
 void handle(HttpExchange x)throws IOException{
  String id=String.format("%04d",sequence.incrementAndGet());long start=System.nanoTime();long lastSave=start;var m=Common.record("http-wire",id,upstream).put("mock_response",mock).put("path",x.getRequestURI().getPath());var captured=new ByteArrayOutputStream();
  AtomicReference<InputStream> upstreamBody=new AtomicReference<>(); Thread handler=Thread.currentThread();
  ScheduledFuture<?> deadline=mock?null:watchdog.schedule(()->{timedOut=true;try{InputStream in=upstreamBody.get();if(in!=null)in.close();}catch(IOException ignored){}x.close();handler.interrupt();},900,TimeUnit.SECONDS);
  try{
   byte[] body=x.getRequestBody().readAllBytes();Common.text(dir.resolve(id+"-request.json"),redact(new String(body,StandardCharsets.UTF_8)));m.put("request_sha256",Common.hash(body)).put("status","REQUEST_SAVED").put("harness_request_deadline_seconds",900);Common.write(dir.resolve(id+"-meta.json"),m);
   if(mock){
    String s="event: response.output_text.delta\ndata: {\"type\":\"response.output_text.delta\",\"delta\":\"Recorded full-loading request.\"}\n\nevent: response.completed\ndata: {\"type\":\"response.completed\",\"response\":{\"output\":[]}}\n\n";
    byte[] data=s.getBytes(StandardCharsets.UTF_8);captured.write(data);x.getResponseHeaders().set("Content-Type","text/event-stream");x.sendResponseHeaders(200,data.length);x.getResponseBody().write(data);m.put("http_status",200);
   }else{
    var b=HttpRequest.newBuilder(URI.create(upstream.baseUrl()+x.getRequestURI().toString())).timeout(app.requestTimeout()).POST(HttpRequest.BodyPublishers.ofByteArray(body));
    for(String name:new String[]{"Authorization","x-api-key","anthropic-version","anthropic-beta","Content-Type","Accept"}){String value=x.getRequestHeaders().getFirst(name);if(value!=null)b.header(name,value);}
    var response=http.send(b.build(),HttpResponse.BodyHandlers.ofInputStream());upstreamBody.set(response.body());m.put("http_status",response.statusCode()).put("status","STREAMING");Common.write(dir.resolve(id+"-meta.json"),m);x.getResponseHeaders().set("Content-Type",response.headers().firstValue("Content-Type").orElse("text/event-stream"));x.sendResponseHeaders(response.statusCode(),0);
    try(InputStream in=response.body();OutputStream out=x.getResponseBody()){byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){captured.write(buf,0,n);out.write(buf,0,n);out.flush();if(System.nanoTime()-lastSave>1_000_000_000L){Common.text(dir.resolve(id+"-response.sse"),redact(captured.toString(StandardCharsets.UTF_8)));lastSave=System.nanoTime();}}}
   }m.put("status","RECORDED");
  }catch(Exception e){m.put("status","ERROR").put("exception",redact(e.toString()));try{byte[] b="{\"error\":{\"message\":\"Benchmark forwarding failed; see wire metadata\"}}".getBytes(StandardCharsets.UTF_8);x.sendResponseHeaders(502,b.length);x.getResponseBody().write(b);}catch(Exception ignored){}}
  finally{if(deadline!=null)deadline.cancel(false);m.put("harness_timeout",timedOut);m.put("end_time",Instant.now().toString()).put("wall_clock_seconds",(System.nanoTime()-start)/1e9);try{Common.text(dir.resolve(id+"-response.sse"),redact(captured.toString(StandardCharsets.UTF_8)));Common.write(dir.resolve(id+"-meta.json"),m);}catch(Exception e){System.err.println("Wire persistence failed: "+e.getClass().getSimpleName());}x.close();}
 }
 public void close(){server.stop(1);executor.shutdownNow();watchdog.shutdownNow();}
}