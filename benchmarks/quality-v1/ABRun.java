package bench;
import com.starcode.config.*;import com.starcode.llm.*;import com.starcode.context.ContextManager;import com.starcode.session.SessionContext;import com.starcode.tool.ToolRegistry;
import java.nio.file.*;import java.util.*;
/** Same harness compiled against each complete frozen production checkout. */
public final class ABRun {
 public static void main(String[] args)throws Exception {
  Common.root=Path.of(System.getProperty("bench.root"));Path run=Path.of(args[0]);String arm=args[1],commit=args[2];
  var app=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));var p=app.providers().getFirst();
  if(!p.model().equals("gpt-5.4-mini")||!p.protocol().equals("openai-responses")||p.thinking()||p.contextWindow()!=128000)throw new IllegalStateException("Frozen provider configuration mismatch");
  var config=Common.record("quality-preflight","preflight",p).put("provider",p.name()).put("endpoint_sha256",Common.hash(p.baseUrl().getBytes(java.nio.charset.StandardCharsets.UTF_8))).put("max_output_tokens","UNSET; provider default, identical production client").put("sampling_seed","UNSET").put("system_prompt_sha256",Common.hash(app.systemPrompt().getBytes(java.nio.charset.StandardCharsets.UTF_8))).put("request_timeout_seconds",app.requestTimeout().toSeconds());
  if(arm.equals("preflight")){Common.write(run,config);System.out.println("PREFLIGHT_PASS");return;}
  if(Files.exists(run.resolve("run.json")))throw new IllegalStateException("Refusing to overwrite attempt");Files.createDirectories(run);
  List<ChatMessage> history=new ArrayList<>();for(var m:Common.JSON.readTree(Common.root.resolve("context-retention/conversation.json").toFile()))history.add(new ChatMessage(ChatMessage.Role.valueOf(m.path("role").asText()),m.path("content").asText()));
  var r=Common.record("context-quality-ab",run.getFileName().toString(),p).put("arm",arm).put("git_commit",commit).put("status","RUNNING").put("operational_success",false).put("memory_isolated",true).put("evaluator","quality-v1 offline; no paid extraction calls");
  r.set("model_configuration",config);Common.write(run.resolve("compact-input.json"),history);Common.write(run.resolve("run.json"),r);long start=System.nanoTime();
  try(var wire=new QualityWireRecorder(run.resolve("wire"),p,app,false);var client=new RecordingClient(LlmClients.create(wire.localProvider(),Common.clean(app,wire.localProvider())),run.resolve("calls"),p)){
   Path session=run.resolve("session");Files.createDirectories(session.resolve("tool-results"));
   var manager=new ContextManager(new SessionContext("quality",session,session.resolve("tool-results"),session.resolve("conversation.jsonl")),p);
   r.put("estimated_input_tokens",manager.estimate(history)).put("threshold",95000).put("should_auto_compact",manager.shouldAutoCompact(history));
   if(!manager.shouldAutoCompact(history))throw new IllegalStateException("Production trigger did not fire");
   // Forensics only: retain the exact production-selected recent/recovery components,
   // even if compact fails. These are never installed in a real conversation.
   var recent=ContextManager.class.getDeclaredMethod("recent",List.class);recent.setAccessible(true);
   var recovery=ContextManager.class.getDeclaredMethod("recovery",List.class);recovery.setAccessible(true);
   Common.write(run.resolve("forensic-recent.json"),recent.invoke(manager,history));
   Common.text(run.resolve("forensic-recovery.txt"),(String)recovery.invoke(manager,ToolRegistry.standard().definitions()));
   try{
    var result=manager.compact(history,ToolRegistry.standard().definitions(),client,ContextManager.Reason.AUTO,s->{});
    Common.write(run.resolve("effective-context.json"),result.messages());
    String content=result.messages().get(1).content();int split=content.lastIndexOf("<context-recovery>");
    Common.text(run.resolve("summary.txt"),split<0?content:content.substring(0,split).strip());
    r.put("status","SUCCESS").put("operational_success",true).put("estimated_after_tokens",result.afterTokens());
   }catch(Exception e){r.put("status","FAILURE").put("failure_type",e.getClass().getSimpleName()).put("failure_reason",e.toString());}
   try{var method=ContextManager.class.getMethod("lastCompression");Common.write(run.resolve("diagnostics.json"),method.invoke(manager));}catch(NoSuchMethodException expected){}
  }catch(Exception e){r.put("status","FAILURE").put("failure_type",e.getClass().getSimpleName()).put("failure_reason",e.toString());}
  finally{r.put("wall_clock_seconds",(System.nanoTime()-start)/1e9).put("end_timestamp",java.time.Instant.now().toString());Common.write(run.resolve("run.json"),r);}
  System.out.println(run.getFileName()+" "+r.path("status").asText()+" "+r.path("wall_clock_seconds").asDouble()+"s");System.exit(0);
 }
}
