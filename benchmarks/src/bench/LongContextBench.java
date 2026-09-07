package bench;

import com.starcode.config.*;import com.starcode.context.ContextManager;import com.starcode.llm.*;
import com.starcode.session.*;import com.starcode.tool.*;import com.starcode.memory.MemoryManager;
import com.starcode.instructions.InstructionLoader;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;import java.time.Instant;import java.util.*;

/** Scripted production-component pilot, not an autonomous long coding session. */
public final class LongContextBench {
 static List<ChatMessage> history; static SessionWriter writer;static long suppliedChars;static int compactCount;
 static void append(ChatMessage message) throws Exception {
  history.add(message);writer.append(message);suppliedChars+=message.modelText().length();
 }
 static void query(Path out,String view,List<ChatMessage> messages,ObjectNode expected,
                   LlmClient client) throws Exception {
  var keys=new ArrayList<String>();expected.fieldNames().forEachRemaining(keys::add);
  String prompt="Recover the project state from the provided context. Return ONLY one JSON object with these keys: "
       +keys+". Preserve value types: limits and timeout_ms are integers; allow_network and preserve_public_api are booleans; "
       +"other fields are strings. Use the latest current-state values, not outdated memory. "
       +"If a value is not recoverable use null; do not guess. No tool calls.";
  Common.text(out.resolve(view+"-question.txt"),prompt);
  long start=System.nanoTime();var record=Common.JSON.createObjectNode().put("view",view).put("status","FAILURE");
  try {
   var response=client.stream(messages,prompt,List.of(),ignored->{});
   Common.text(out.resolve(view+"-answer.txt"),response.text());
   Common.write(out.resolve(view+"-completion.json"),response);
   var actual=Common.JSON.readTree(response.text().strip());
   var scores=record.putArray("fields");int passed=0;
   for(String key:keys){boolean ok=actual!=null&&actual.isObject()&&expected.path(key).equals(actual.path(key));
    if(ok)passed++;var row=scores.addObject().put("key",key).put("pass",ok);row.set("expected",expected.path(key));
    row.set("actual",actual==null?Common.JSON.nullNode():actual.path(key));}
   record.put("status","SCORED").put("passed",passed).put("total",keys.size());
  }catch(Exception error){record.put("exception",error.toString()).put("passed",0).put("total",keys.size());}
  record.put("wall_clock_seconds",(System.nanoTime()-start)/1e9);Common.write(out.resolve(view+"-score.json"),record);
 }
 public static void main(String[] args)throws Exception {
  if(args.length!=0&&args.length!=2)throw new IllegalArgumentException("Optional arguments: firstRepeat lastRepeat (1..3)");
  int firstRepeat=args.length==0?1:Integer.parseInt(args[0]),lastRepeat=args.length==0?3:Integer.parseInt(args[1]);
  if(firstRepeat<1||lastRepeat>3||firstRepeat>lastRepeat)throw new IllegalArgumentException("Repeat range must be within1..3");
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();String commit=Common.git(Common.root.getParent(),"rev-parse","HEAD");
  if(!Common.git(Common.root.getParent(),"diff","HEAD","--","src/main").isBlank())throw new IllegalStateException("Commit production first");
  Path fixture=Common.root.resolve("long-context-v1/fixture.json");
  if(!Common.hash(Files.readAllBytes(fixture)).equals(Files.readString(Common.root.resolve("long-context-v1/fixture.sha256")).strip()))throw new IllegalStateException("Fixture hash mismatch");
  var data=Common.JSON.readTree(fixture.toFile());var original=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));var provider=original.providers().getFirst();
  if(provider.contextWindow()!=128000)throw new IllegalStateException("Preregistered pilot requires configured128000 context; do not lower it");
  Path batch=Common.root.resolve("results/raw/long-context-v1/"+Instant.now().toString().replace(':','-'));Files.createDirectories(batch);
  Common.write(batch.resolve("environment.json"),Common.record("long-context-component-pilot",batch.getFileName().toString(),provider)
      .put("implementation_commit",commit).put("fixture_sha256",Common.hash(Files.readAllBytes(fixture)))
      .put("estimate_method","production chars/3.5; cumulative new-history load, not provider tokens")
      .put("autonomous_coding_session",false).put("model_seed","UNSET")
      .put("first_repeat",firstRepeat).put("last_repeat",lastRepeat));
  Files.copy(Common.root.resolve(".work/build-manifest.json"),batch.resolve("build-manifest.json"));
  Common.text(Common.root.resolve("results/long-context-v1-latest.txt"),Common.root.relativize(batch).toString());
  for(int repeat=firstRepeat;repeat<=lastRepeat;repeat++){
   Path run=batch.resolve("run-"+repeat);Files.createDirectories(run);Path workspace=run.resolve("workspace");Files.createDirectories(workspace);
   String previousHome=System.getProperty("user.home");Path isolatedHome=run.resolve("isolated-home");Files.createDirectories(isolatedHome);
   var record=Common.record("long-context-component-pilot","run-"+repeat,provider).put("implementation_commit",commit).put("status","FAILURE");
   long start=System.nanoTime(); suppliedChars=0;compactCount=0;history=new ArrayList<>();
   try {
    System.setProperty("user.home",isolatedHome.toString());
    Common.text(workspace.resolve("MEWCODE.md"),data.path("instructions").asText());
    Common.text(workspace.resolve(".mewcode/memory/MEMORY.md"),data.path("stale_memory").asText());
    var session=SessionContext.create(workspace);var context=new ContextManager(session,provider);var registry=ToolRegistry.standard();var tc=new ToolContext(workspace,true,true);
    try(var wire=new WireRecorder(run.resolve("wire"),provider,original,false)){
     var local=wire.localProvider();var app=Common.clean(original,local);
     app.promptContext().instructions(new InstructionLoader(workspace).load());
     try(var client=new RecordingClient(LlmClients.create(local,app),run.resolve("calls"),provider);
         var memory=new MemoryManager(workspace,client,app.promptContext())){
      Common.text(run.resolve("loaded-instructions.txt"),app.promptContext().instructions());Common.text(run.resolve("loaded-memory.txt"),app.promptContext().memory());
      writer=SessionWriter.create(session,provider.model());
      try {
       // Real UTF-8 read: below file-size cap, above byte-based offload threshold.
       Common.text(workspace.resolve("unicode.log"),"示例诊断数据".repeat(4000));
       var bigCall=new ToolCall("unicode-read","read_file",Common.JSON.createObjectNode().put("path","unicode.log"));
       var bigRaw=registry.execute(bigCall,tc);if(!bigRaw.success())throw new IllegalStateException(bigRaw.modelText());
       var bigOffload=context.offloadAndSnip(List.of(bigRaw)).getFirst();
       Common.write(run.resolve("offload-original.json"),bigRaw);Common.write(run.resolve("offload-replacement.json"),bigOffload);
       if(bigRaw.output().equals(bigOffload.output()))throw new IllegalStateException("Real read did not exercise offload");
       append(ChatMessage.assistant(new Completion("Read diagnostic attachment",List.of(bigCall),null,TokenUsage.ZERO)));append(ChatMessage.tool(List.of(bigOffload)));
       ObjectNode expected=Common.JSON.createObjectNode();String lastSummary="";
       for(var stage:data.path("stages")){
        int phase=stage.path("phase").asInt();Path stageDir=run.resolve("stage-"+phase);Files.createDirectories(stageDir);
        expected.setAll((ObjectNode)stage.path("facts"));expected.setAll((ObjectNode)stage.path("current_state"));
        append(new ChatMessage(ChatMessage.Role.USER,"Project facts to preserve from phase "+phase+": "+stage.path("facts")
            +"\nThe latest active task state replaces older defaults, including old memory: "+stage.path("current_state")));
        Common.write(stageDir.resolve("expected.json"),expected);
        int chunk=0;long target=phase*100000L;int beforeCompactions=compactCount;
        for(var log:stage.path("logs")){
         String path="logs/phase"+phase+"-"+(chunk++)+".txt";Common.text(workspace.resolve(path),log.asText());
         var call=new ToolCall("phase"+phase+"-read"+chunk,"read_file",Common.JSON.createObjectNode().put("path",path));
         var raw=registry.execute(call,tc);if(!raw.success())throw new IllegalStateException(raw.modelText());
         context.trackSuccessfulRead(call,raw,tc);var processed=context.offloadAndSnip(List.of(raw));
         append(ChatMessage.assistant(new Completion("Inspect build diagnostics",List.of(call),null,TokenUsage.ZERO)));append(ChatMessage.tool(processed));
         if(context.shouldAutoCompact(history)){
          Path compactDir=stageDir.resolve("compact-"+(++compactCount));Common.write(compactDir.resolve("input.json"),history);
          Common.write(compactDir.resolve("trigger.json"),Common.JSON.createObjectNode().put("should_auto_compact",true)
              .put("active_tokens_estimated",context.estimate(history)).put("cumulative_new_tokens_estimated",Math.round(suppliedChars/3.5)));
          client.phase="compact";
          var compacting=context;
          try {
           var compacted=context.compact(history,registry.definitions(),client,ContextManager.Reason.AUTO,ignored->{});
           Common.write(compactDir.resolve("output.json"),compacted.messages());
           String body=compacted.messages().get(1).content();int recovery=body.indexOf("<context-recovery>");
           lastSummary=recovery<0?body:body.substring(0,recovery);
           Common.text(compactDir.resolve("summary.txt"),lastSummary);
           Common.text(compactDir.resolve("recovery.txt"),recovery<0?"":body.substring(recovery));
           Common.write(compactDir.resolve("retained-recent.json"),compacted.messages().subList(2,compacted.messages().size()));
           writer.replace(compacted.messages());writer.close();
           var opened=SessionContext.open(workspace,session.sessionId());var loaded=SessionLoader.load(opened);
           if(loaded.badLines()!=0||!loaded.messages().equals(compacted.messages()))throw new IllegalStateException("Persist/resume mismatch");
           history=new ArrayList<>(loaded.messages());writer=SessionWriter.open(opened,provider.model());context=new ContextManager(opened,provider);
           if(!context.offloadAndSnip(List.of(bigRaw)).getFirst().output().equals(bigOffload.output()))throw new IllegalStateException("Offload ledger mismatch after resume");
           Common.write(compactDir.resolve("resumed.json"),history);
          }finally{
           Common.write(compactDir.resolve("diagnostics.json"),compacting.lastCompression());
          }
         }
         if(Math.round(suppliedChars/3.5)>=target)break;
        }
        if(Math.round(suppliedChars/3.5)<target||compactCount==beforeCompactions)throw new IllegalStateException("Fixture did not cross target/production compaction threshold");
        Common.write(stageDir.resolve("stage.json"),Common.JSON.createObjectNode().put("phase",phase)
            .put("cumulative_new_tokens_estimated",Math.round(suppliedChars/3.5)).put("active_tokens_estimated",context.estimate(history))
            .put("compactions_in_stage",compactCount-beforeCompactions).put("session_reload_equal",true).put("offload_replay_equal",true));
        Common.write(stageDir.resolve("complete-context.json"),history);
        client.phase="complete-state-probe";query(stageDir,"complete",history,expected,client);
        String savedMemory=app.promptContext().memory(),savedInstructions=app.promptContext().instructions();
        try{app.promptContext().memory("");app.promptContext().instructions("");client.phase="summary-state-probe";
         query(stageDir,"summary",List.of(new ChatMessage(ChatMessage.Role.ASSISTANT,lastSummary)),expected,client);
        }finally{app.promptContext().memory(savedMemory);app.promptContext().instructions(savedInstructions);}
        System.out.println("long-context run"+repeat+" stage"+phase+" saved; compactions="+compactCount);
       }
       record.put("status","COMPLETED_COMPONENT_WORKFLOW").put("state_retrieval_status","SEE_PER_FIELD_SCORES");
      }finally{writer.close();}
     }
    }
   }catch(Exception error){record.put("exception",error.toString());}
   finally{System.setProperty("user.home",previousHome);record.put("compactions",compactCount)
       .put("cumulative_new_tokens_estimated",Math.round(suppliedChars/3.5)).put("wall_clock_seconds",(System.nanoTime()-start)/1e9);
    Common.write(run.resolve("run.json"),record);System.out.println("long-context run"+repeat+" "+record.path("status").asText());}
  }
 }
}
