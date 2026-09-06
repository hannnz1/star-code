package bench;
import com.starcode.agent.*;
import com.starcode.config.*;
import com.starcode.llm.*;
import com.starcode.mcp.*;
import com.starcode.tool.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;

/** Schema measurement uses a local sink; selection uses real model calls. Both use production MCP/client paths. */
public final class McpLazyBench {
 public static void main(String[] args)throws Exception {
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();
  boolean real=args.length>0&&args[0].equals("selection");
  String kind=real?"mcp-selection-v1":"mcp-schema-v1";
  Path batch=Common.root.resolve("results/raw/"+kind+"/"+Instant.now().toString().replace(':','-'));
  Files.createDirectories(batch);
  var app=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));var p=app.providers().getFirst();
  String commit=Common.git(Common.root.getParent(),"rev-parse","HEAD");
  if(!Common.git(Common.root.getParent(),"diff","HEAD","--","src/main").isBlank())throw new IllegalStateException("Commit production before benchmarking");
  Common.write(batch.resolve("environment.json"),Common.record(kind,batch.getFileName().toString(),p)
    .put("implementation_commit",commit).put("real_model",real));
  Files.copy(Common.root.resolve(".work/build-manifest.json"),batch.resolve("build-manifest.json"));
  if(real){
   var tasks=Common.JSON.readTree(Common.root.resolve("mcp-lazy-v1/selection-fixture.json").toFile()).path("tasks");
   int i=0;var random=new Random(Common.SEED);
   for(var task:tasks){
    var modes=new ArrayList<>(List.of(false,true));if(random.nextBoolean())Collections.reverse(modes);
    for(boolean lazy:modes)run(batch,app,p,commit,100,++i,lazy,task);
   }
  }else for(int count:new int[]{10,25,50,100})for(int repeat=1;repeat<=5;repeat++)
   for(boolean lazy:new boolean[]{false,true})run(batch,app,p,commit,count,repeat,lazy,null);
  Common.text(Common.root.resolve("results/"+kind+"-latest.txt"),Common.root.relativize(batch).toString());
  System.out.println("RAW_RESULTS="+batch);
 }
 static void run(Path batch,AppConfig app,ProviderConfig p,String commit,int count,int repeat,boolean lazy,com.fasterxml.jackson.databind.JsonNode task)throws Exception {
  boolean real=task!=null;String id=(real?task.path("id").asText():"tools-"+count+"-repeat-"+repeat)+"-"+(lazy?"lazy":"full");
  Path run=batch.resolve(id);Files.createDirectories(run);
  Path fixture=Common.root.resolve(real?"mcp-lazy-v1/selection-fixture.json":"mcp-loading/tools-"+count+".json");
  var registry=ToolRegistry.standard().lazyMcpLoading(lazy);
  String java=Path.of(System.getProperty("java.home"),"bin/java.exe").toString();
  var argv=new ArrayList<>(List.of("-cp",System.getProperty("java.class.path"),real?"bench.McpSelectionFixture":"bench.McpFixture",fixture.toString()));
  if(real)argv.add(run.resolve("mcp-calls.jsonl").toString());
  var server=new McpServerConfig("fixture",McpServerConfig.Type.STDIO,java,argv,Map.of(),null,Map.of());
  var record=Common.record(real?"mcp-selection-v1":"mcp-schema-v1",id,p).put("implementation_commit",commit)
    .put("loading_mode",lazy?"LAZY":"FULL").put("tool_count",count).put("fixture_sha256",Common.hash(Files.readAllBytes(fixture)))
    .put("real_model",real).put("retry_count",0).put("task_success",false);
  Common.write(run.resolve("run.json"),record.put("status","STARTED"));
  long start=System.nanoTime();
  try(var mcp=McpManager.connect(List.of(server),registry)) {
   if(registry.count()!=count+6)throw new IllegalStateException("Discovery count mismatch");
   record.put("discovery_seconds",(System.nanoTime()-start)/1e9);
   var context=new ToolContext(run,false,false);
   try(var wire=new WireRecorder(run.resolve("wire"),p,app,!real);var client=LlmClients.create(wire.localProvider(),Common.clean(app,wire.localProvider()))) {
    String prompt=real?task.path("prompt").asText():"Report that the tool catalog is available. Do not call tools.";
    Common.text(run.resolve("prompt.txt"),prompt);
    long agentStart=System.nanoTime();
    var outcome=new AgentLoop(client,registry,context).run(List.of(),prompt,AgentMode.DEFAULT,new CancellationToken(),e->{});
    record.put("agent_wall_clock_seconds",(System.nanoTime()-agentStart)/1e9).put("agent_status",outcome.status().name());
    Common.write(run.resolve("outcome.json"),outcome);
    if(outcome.status()!=AgentOutcome.Status.COMPLETED)throw new IllegalStateException("Agent ended "+outcome.status());
    if(real){
     String expected=task.path("tool").asText();String entity=task.path("entity_id").asText();
     boolean selected=false;int unexpected=0;
     if(Files.exists(run.resolve("mcp-calls.jsonl")))for(String line:Files.readAllLines(run.resolve("mcp-calls.jsonl"))){
      var call=Common.JSON.readTree(line);
      if(call.path("name").asText().equals(expected)&&call.path("arguments").path("entity_id").asText().equals(entity)&&call.path("success").asBoolean())selected=true;
      else unexpected++;
     }
     boolean correct=selected&&unexpected==0&&outcome.text().contains(task.path("expected_result").asText());
     record.put("task_success",correct).put("selection_correct",selected&&unexpected==0).put("unexpected_remote_calls",unexpected);
     Common.usage(record,outcome.usage(),p.protocol());
    }else record.putNull("task_success");
    record.put("status","SUCCESS");
   }
  }catch(Exception e){record.put("status","FAILURE").put("exception",e.toString());}
  record.put("wall_clock_seconds",(System.nanoTime()-start)/1e9);Common.write(run.resolve("run.json"),record);
  System.out.println(id+" "+record.path("status").asText()+" task_success="+record.path("task_success"));
  // Stop on infrastructure errors; preserve failed records, never silently replace them.
  if(record.path("status").asText().equals("FAILURE"))throw new IllegalStateException("Benchmark failure; inspect "+run);
 }
}
