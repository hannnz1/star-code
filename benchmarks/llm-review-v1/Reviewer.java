import com.starcode.config.*;
import com.fasterxml.jackson.databind.*;import com.fasterxml.jackson.databind.node.*;
import java.nio.file.*;import java.nio.charset.StandardCharsets;import java.net.*;import java.net.http.*;import java.time.*;import java.util.*;import java.io.*;import java.util.concurrent.*;import java.util.concurrent.atomic.*;
/** Reads blind inputs/config only. External requests carry no conversation history/tools. */
public class Reviewer {
 static final ObjectMapper J=new ObjectMapper();
 static void save(Path p,JsonNode n)throws Exception {Files.createDirectories(p.getParent());Path t=p.resolveSibling(p.getFileName()+".tmp");J.writerWithDefaultPrettyPrinter().writeValue(t.toFile(),n);Files.move(t,p,StandardCopyOption.REPLACE_EXISTING);}
 static String hash(Path p)throws Exception{return HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p)));}
 static boolean rateLimitedWithoutOutput(Path call)throws Exception {
  if(!Files.exists(call.resolve("response.sse")))return false;
  boolean limited=false;
  for(String line:Files.readAllLines(call.resolve("response.sse"))){
   if(!line.startsWith("data:"))continue;String data=line.substring(5).strip();if(data.equals("[DONE]"))continue;
   JsonNode event=J.readTree(data);
   if(event.path("type").asText().equals("response.output_text.delta"))return false;
   if(event.path("type").asText().equals("error")&&event.path("error").path("code").asText().equals("rate_limit_exceeded"))limited=true;
  }
  return limited;
 }
 public static void main(String[] args)throws Exception {
  Path root=Path.of(args[0]),here=root.resolve("llm-review-v1"),raw=root.resolve("results/raw/llm-blind-review-v1");var freeze=J.readTree(here.resolve("freeze.json").toFile());
  for(var pair:Map.of("blind_csv_sha256",root.resolve("results/manual-review-blind.csv"),"samples_sha256",here.resolve("blind-samples.json"),"rubric_sha256",here.resolve("rubric.txt")).entrySet())if(!hash(pair.getValue()).equals(freeze.path(pair.getKey()).asText()))throw new IllegalStateException("Frozen input changed");
  var app=ConfigLoader.load(root.getParent().resolve("config.yaml"));var p=app.providers().getFirst();if(!p.protocol().equals("openai-responses"))throw new IllegalStateException("Responses protocol required");String secret=System.getenv(p.apiKeyEnv());String rubric=Files.readString(here.resolve("rubric.txt"));
  var meta=J.createObjectNode().put("model",p.model()).put("provider",p.name()).put("protocol",p.protocol()).put("temperature",0).put("max_output_tokens",2048).put("stateless",true).put("source_sha256",hash(here.resolve("Reviewer.java"))).put("java",System.getProperty("java.version"));
  Path config=here.resolve("reviewer-config.json");if(Files.exists(config)&&!J.readTree(config.toFile()).equals(meta))throw new IllegalStateException("Reviewer configuration changed");save(config,meta);
  var hb=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30));if(app.proxy().enabled())hb.proxy(ProxySelector.of(new InetSocketAddress(app.proxy().host(),app.proxy().port())));
  try(var http=hb.build()){
   var probe=http.send(HttpRequest.newBuilder(URI.create(p.baseUrl())).timeout(Duration.ofSeconds(30)).method("HEAD",HttpRequest.BodyPublishers.noBody()).build(),HttpResponse.BodyHandlers.discarding());System.out.println("CONNECTIVITY_HTTP="+probe.statusCode());if(args.length>1&&args[1].equals("preflight"))return;
   int done=0;for(var sample:J.readTree(here.resolve("blind-samples.json").toFile())){
    String id=sample.path("review_id").asText();if(!id.matches("R\\d{4}"))throw new IllegalStateException("Unsafe ID");Path dir=raw.resolve(id),label=dir.resolve("review.json");Files.createDirectories(dir);if(Files.exists(label)){done++;continue;}boolean accepted=false;
    boolean formatRetry=false;
    for(int attempt=1;attempt<=2;attempt++){
     Path call=dir.resolve("attempt-"+attempt);
     if(Files.exists(call)){
      if(rateLimitedWithoutOutput(call)){System.out.println("PRESERVED_RATE_LIMIT_ATTEMPT "+id+" "+attempt);continue;}
      throw new IllegalStateException("Existing unfinished attempt: "+id);
     }
     var body=J.createObjectNode().put("model",p.model()).put("temperature",0).put("max_output_tokens",2048).put("stream",true).put("store",false).put("instructions",rubric+(!formatRetry?"":"\nReturn only the required JSON object. Prior response was not parseable; apply the same rubric independently."));body.putArray("input").addObject().put("role","user").put("content",sample.toString());
     // Conservative character estimate for pacing only, never reported as billed usage.
     long pacingMs=Math.max(1000,Math.round((body.toString().length()/3.5+2048)*60000/150000));
     Thread.sleep(pacingMs);Files.createDirectories(call);save(call.resolve("request.json"),body);
     var record=J.createObjectNode().put("review_id",id).put("attempt",attempt).put("started_at",Instant.now().toString()).put("status","STARTED").put("pre_request_pacing_ms",pacingMs);save(call.resolve("call.json"),record);long start=System.nanoTime();StringBuilder text=new StringBuilder(),wire=new StringBuilder();JsonNode usage=null;boolean completed=false;
     var timer=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r);t.setDaemon(true);return t;});var stream=new AtomicReference<InputStream>();Thread current=Thread.currentThread();var deadline=timer.schedule(()->{try{if(stream.get()!=null)stream.get().close();}catch(Exception ignored){}current.interrupt();},300,TimeUnit.SECONDS);
     try{
      var response=http.send(HttpRequest.newBuilder(URI.create(p.baseUrl()+"/responses")).timeout(Duration.ofSeconds(120)).header("Authorization","Bearer "+secret).header("Content-Type","application/json").header("Accept","text/event-stream").POST(HttpRequest.BodyPublishers.ofString(body.toString())).build(),HttpResponse.BodyHandlers.ofInputStream());stream.set(response.body());record.put("http_status",response.statusCode());if(response.statusCode()!=200)throw new IOException("Non200 status="+response.statusCode());
      try(var reader=new BufferedReader(new InputStreamReader(response.body(),StandardCharsets.UTF_8))){String line;while((line=reader.readLine())!=null){wire.append(line).append('\n');if(!line.startsWith("data:"))continue;String data=line.substring(5).strip();if(data.equals("[DONE]"))continue;var e=J.readTree(data);String type=e.path("type").asText();if(type.equals("response.output_text.delta"))text.append(e.path("delta").asText());if(type.equals("response.completed")){completed=true;usage=e.path("response").get("usage");record.put("returned_model",e.path("response").path("model").asText());}if(type.equals("response.failed")||type.equals("error"))throw new IOException("Reviewer failure event");}}
      Files.writeString(call.resolve("response.txt"),text.toString());if(!completed)throw new IOException("No response.completed; no label fabricated");String value=text.toString().strip();if(value.startsWith("```")){int nl=value.indexOf('\n');if(nl>=0)value=value.substring(nl+1);if(value.strip().endsWith("```"))value=value.strip().substring(0,value.strip().length()-3).strip();}
      JsonNode result=null;try{result=J.readTree(value);}catch(Exception ignored){}
      if(result!=null&&result.isObject()&&result.size()==3&&Set.of("PASS","PARTIAL","FAIL","UNCERTAIN").contains(result.path("reviewer_label").asText())&&Set.of("HIGH","MEDIUM","LOW").contains(result.path("reviewer_confidence").asText())&&!result.path("reviewer_notes").asText().isBlank()){
       save(label,((ObjectNode)result).deepCopy().put("review_id",id).put("attempt",attempt).put("model",p.model()));accepted=true;record.put("status","VALID_REVIEW");
      }else {record.put("status","INVALID_REVIEW_SCHEMA");formatRetry=true;}
     }catch(Exception error){record.put("status","INFRASTRUCTURE_FAILURE").put("exception_type",error.getClass().getSimpleName());throw error;}
     finally{deadline.cancel(false);timer.shutdownNow();Files.writeString(call.resolve("response.sse"),wire.toString().replace(secret,"[REDACTED]"));record.put("wall_clock_seconds",(System.nanoTime()-start)/1e9).put("ended_at",Instant.now().toString());if(usage!=null)record.set("usage",usage);save(call.resolve("call.json"),record);}
     if(accepted)break;
    }
    if(!accepted)throw new IllegalStateException("Two invalid outputs: "+id);System.out.println("REVIEW_SAVED "+(++done)+"/160 "+id);
   }
  }
 }
}
