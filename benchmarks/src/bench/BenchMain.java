package bench;
import com.starcode.config.*;import com.starcode.llm.*;import com.starcode.mcp.*;import com.starcode.tool.*;import com.starcode.agent.*;
import java.nio.file.*;import java.time.*;import java.util.*;
public final class BenchMain{
 public static void main(String[] args)throws Exception{
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();
  String actual=Common.git(Common.root.getParent(),"rev-parse","benchmark-baseline-v1^{commit}");
  if(!actual.equals(Common.BASELINE))throw new IllegalStateException("Baseline tag mismatch");
  String diff=Common.git(Common.root.getParent(),"diff",Common.BASELINE,"--","src/main","build.gradle.kts","settings.gradle.kts");
  if(!diff.isBlank())throw new IllegalStateException("Production differs from baseline");
  String run=Instant.now().toString().replace(':','-')+"-"+UUID.randomUUID().toString().substring(0,8);
  String resume=System.getProperty("bench.resume.batch","");
  Path dir=resume.isBlank()?Common.root.resolve("results/raw/"+args[0]+"/"+run):Common.root.resolve(resume);
  if(!resume.isBlank()){run=dir.getFileName().toString();if(!args[0].equals("context-retention"))throw new IllegalArgumentException("Resume is limited to context-retention");}
  Files.createDirectories(dir);
  var app=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));var p=app.providers().getFirst();
  var metadata=Common.record(args[0],run,p).put("source_sha256",Common.hash(Files.readAllBytes(Common.root.resolve("src/bench/BenchMain.java"))));
  metadata.put("request_timeout_seconds",app.requestTimeout().toSeconds()).put("enable_subagent_background",app.enableSubAgentBackground()).put("upstream_base_url_sha256",Common.hash(p.baseUrl().getBytes(java.nio.charset.StandardCharsets.UTF_8)));
  metadata.set("features",Common.JSON.valueToTree(app.features()));
  Common.write(dir.resolve("environment.json"),metadata);
  Files.copy(Common.root.resolve(".work/build-manifest.json"),dir.resolve("build-manifest.json"),StandardCopyOption.REPLACE_EXISTING);
  try(var paths=Files.walk(Common.root.resolve("src"))){for(Path f:paths.filter(Files::isRegularFile).toList()){Path dest=dir.resolve("harness-source-latest").resolve(Common.root.resolve("src").relativize(f));Files.createDirectories(dest.getParent());Files.copy(f,dest,StandardCopyOption.REPLACE_EXISTING);}}
  Common.text(Common.root.resolve("results/"+args[0]+"-latest.txt"),Common.root.relativize(dir).toString());
  if(args[0].equals("mcp-loading"))mcp(dir,app,p);
  else if(args[0].equals("context-retention"))ContextBench.run(dir,app,p);
  else if(args[0].equals("multi-agent"))GateBench.run(dir,app,p);
  else throw new IllegalArgumentException("Unknown benchmark");
  System.out.println("RAW_RESULTS="+dir);System.exit(0);
 }
 static void mcp(Path dir,AppConfig app,ProviderConfig p)throws Exception{
  if(!p.protocol().equals("openai-responses"))throw new IllegalStateException("Local recording sink currently implements Responses protocol only");
  var real=ToolRegistry.standard().definitions();Common.write(Common.root.resolve("mcp-loading/reference-definitions.json"),real);
  var indices=new ArrayList<Integer>();for(int i=0;i<100;i++)indices.add(i%real.size());Collections.shuffle(indices,new Random(Common.SEED));
  for(int count:new int[]{10,25,50,100}){
   var fixture=Common.JSON.createArrayNode();for(int i=0;i<count;i++){
    var t=real.get(indices.get(i));var f=fixture.addObject().put("name",t.name()+"_"+String.format("%03d",i)).put("description",t.description());f.set("inputSchema",t.inputSchema());f.putObject("annotations").put("readOnlyHint",true);
   }
   Path fixturePath=Common.root.resolve("mcp-loading/tools-"+count+".json");Common.write(fixturePath,fixture);
   var registry=ToolRegistry.standard();String java=Path.of(System.getProperty("java.home"),"bin","java.exe").toString();
   var config=new McpServerConfig("fixture",McpServerConfig.Type.STDIO,java,List.of("-cp",System.getProperty("java.class.path"),"bench.McpFixture",fixturePath.toString()),Map.of(),null,Map.of());
   try(var mcp=McpManager.connect(List.of(config),registry)){
    Common.write(dir.resolve("tools-"+count+"-discovered.json"),registry.definitions());
    for(int repeat=1;repeat<=5;repeat++){
     String id="tools-"+count+"-repeat-"+repeat;Path run=dir.resolve(id);Files.createDirectories(run);
     var r=Common.record("mcp-loading",id,p).put("tool_count",count).put("builtin_tool_count",real.size()).put("fixture_sha256",Common.hash(Files.readAllBytes(fixturePath))).put("lazy_status","NOT_IMPLEMENTED").put("usage_source","unavailable: deterministic local SSE sink");
     long start=System.nanoTime();try(var wire=new WireRecorder(run.resolve("wire"),p,app,true);var client=LlmClients.create(wire.localProvider(),Common.clean(app,wire.localProvider()))){
      r.put("discovered_registry_tool_count",registry.count());
      if(registry.count()!=count+real.size())throw new IllegalStateException("MCP discovery count mismatch: "+registry.count());
      Path agentWorkspace=Path.of(System.getProperty("bench.agent.workspace",Common.root.toString())).toAbsolutePath();Files.createDirectories(agentWorkspace);
      var context=new ToolContext(agentWorkspace,false,false);var agent=new AgentLoop(client,registry,context);
      var outcome=agent.run(List.of(),"Report that the tool catalog is available. Do not call tools.",AgentMode.DEFAULT,new CancellationToken(),ignored->{});
      if(outcome.status()!=AgentOutcome.Status.COMPLETED)throw new IllegalStateException("Agent ended "+outcome.status());
      r.put("status","SUCCESS");
     }catch(Exception e){r.put("status","FAILURE").put("exception",e.toString());}
     r.put("wall_clock_seconds",(System.nanoTime()-start)/1e9);Common.write(run.resolve("run.json"),r);System.out.println(id+" "+r.path("status").asText());
    }
   }
  }
 }
}