package bench;
import com.starcode.ChatApplication;import com.starcode.config.*;import com.starcode.llm.*;import com.starcode.tool.*;import com.starcode.session.*;import com.starcode.memory.*;import com.starcode.skill.*;import com.starcode.hook.*;import com.starcode.subagent.*;import com.starcode.task.*;import com.starcode.team.*;import com.starcode.team.registry.*;import com.starcode.team.tools.*;import com.starcode.worktree.*;import com.starcode.ui.TerminalUi;
import java.nio.file.*;import java.time.*;import java.util.*;import java.util.concurrent.*;
public final class GateSuiteBench{
 static List<Object> taskSnapshots(SubAgentTaskManager tasks){
  List<Object> out=new ArrayList<>();for(var t:tasks.list()){
   var r=Common.JSON.createObjectNode().put("id",t.id()).put("name",t.name()).put("status",t.status().name()).put("start_time",t.startTime().toString()).put("result",t.result()).put("initial_task",t.initialTask()).put("tool_count",t.toolCount());
   if(t.endTime()!=null)r.put("end_time",t.endTime().toString());if(t.error()!=null)r.put("exception",t.error().toString());Common.usage(r,t.usage(),"openai-responses");out.add(r);
  }return out;
 }
 public static void run(Path run,AppConfig original,ProviderConfig p,Path fixture)throws Exception{
  var record=Common.record("multi-agent",run.getFileName().toString(),p).put("status","BLOCKED").put("speedup_status","NOT_MEASURED");long start=System.nanoTime();
  Path repo=Common.root.resolve(".work/gate-"+run.getFileName());Files.createDirectories(repo);record.put("repository",repo.toString());
  String previousHome=System.getProperty("user.home");
  try{
   try(var paths=Files.walk(fixture)){for(Path f:paths.toList()){Path d=repo.resolve(fixture.relativize(f));if(Files.isDirectory(f))Files.createDirectories(d);else Files.copy(f,d);}}
   Common.git(repo,"init");Common.git(repo,"config","user.name","Benchmark Fixture");Common.git(repo,"config","user.email","fixture@localhost");Common.git(repo,"add",".");Common.git(repo,"commit","-m","Frozen feasibility fixture");String base=Common.git(repo,"rev-parse","HEAD");record.put("fixture_commit",base);
   Common.text(run.resolve("initial-git-status.txt"),Common.git(repo,"status","--short"));
   Common.text(repo.resolve(".starcode/permissions.yaml"),"allow:\n  - Read\n  - Write\n  - Edit\n  - Glob\n  - Grep\n  - Bash\n  - Agent\n  - TeamCreate\n  - TaskCreate\n  - TaskGet\n  - TaskList\n  - TaskUpdate\n  - SendMessage\n  - TaskStop\n");
   Path isolatedHome=run.resolve("isolated-home");Files.createDirectories(isolatedHome);System.setProperty("user.home",isolatedHome.toString());
   try(var wire=new WireRecorder(run.resolve("wire"),p,original,false)){
    var local=wire.localProvider();var app=Common.clean(original,local);app.promptContext().instructions("Benchmark workspace: "+repo+". Operate only on this synthetic checkout and its managed Worktrees. Use the existing Team tools to coordinate. All agents use the inherited model. Do not modify verification files, access credentials or read other projects.");
    try(var client=new RecordingClient(LlmClients.create(local,app),run.resolve("calls"),p);var ui=new TerminalUi();var hooks=HookEngine.empty();var tasks=new SubAgentTaskManager()){
     client.phase="multi-agent";var tc=new ToolContext(repo,true,true);var wt=new WorktreeManager(repo);var teams=new TeamManager(isolatedHome,repo,wt,tasks,new AgentNameRegistry());var registry=ToolRegistry.standard();
     registry.register(new TaskListTool(tasks,teams)).register(new TaskGetTool(tasks,teams)).register(new TaskStopTool(tasks)).register(new SendMessageTool(tasks,teams)).register(new TeamCreateTool(teams)).register(new TeamDeleteTool(teams)).register(new TaskCreateTool(teams)).register(new TaskUpdateTool(teams));
     var session=SessionContext.create(repo);var writer=SessionWriter.create(session,p.model());var conv=Conversation.fromMessages(List.of(),m->{try{writer.append(m);}catch(Exception e){throw new RuntimeException(e);}},m->{try{writer.replace(m);}catch(Exception e){throw new RuntimeException(e);}});
     var memory=new MemoryManager(repo,client,app.promptContext());var skills=new SkillCatalog();
     try(var application=new ChatApplication(client,conv,ui,registry,tc,local,session,writer,memory,skills,new ActiveSkills(),app.promptContext(),app,new SkillRefresh(),hooks,SubAgentCatalog.load(repo),tasks,wt,teams)){
      String prompt="Complete the coding contract in README.md in the benchmark workspace. First read it and choose your own decomposition. Use a Team and at least two concurrent general-purpose Sub-Agents in independent Worktrees. You, the Main Agent, must collect their results, integrate the code into the main checkout using your existing tools, and run powershell.exe -NoProfile -File ./verify.ps1. Do not modify README.md, verify.ps1, contract.json or tests/GateTest.java. Do not stop at worker DONE messages: finish with an integrated checkout passing the unified verifier. Do not ask the harness to merge or decompose work. Existing production iteration limits apply.";
      Common.text(run.resolve("main-prompt.txt"),prompt);
      var executor=Executors.newSingleThreadExecutor();var future=executor.submit(()->application.sendPrompt(prompt));
      Map<String,com.fasterxml.jackson.databind.node.ObjectNode> observedTrees=new LinkedHashMap<>();List<Object> lifecycle=new ArrayList<>();long deadline=System.nanoTime()+Duration.ofMinutes(12).toNanos();
      while(!future.isDone()&&System.nanoTime()<deadline){
       lifecycle.add(Map.of("timestamp",Instant.now().toString(),"tasks",taskSnapshots(tasks),"worktrees",wt.list().stream().map(w->Map.of("name",w.name(),"path",w.path().toString(),"branch",w.branch())).toList()));
       for(var w:wt.list()){try{var snapshot=Common.JSON.createObjectNode().put("name",w.name()).put("path",w.path().toString()).put("branch",w.branch()).put("last_observed_at",Instant.now().toString()).put("diff",Common.git(w.path(),"diff",base));observedTrees.put(w.path().toString(),snapshot);}catch(Exception observationError){Common.text(run.resolve("observation-error.txt"),observationError.toString());}}
       Common.write(run.resolve("lifecycle.json"),lifecycle);Common.write(run.resolve("observed-worktrees.json"),observedTrees.values());Thread.sleep(1000);
      }
      if(!future.isDone()){future.cancel(true);record.put("failure_reason","Gate exceeded 12-minute wall-clock limit");}else future.get();executor.shutdownNow();
      Common.write(run.resolve("tasks.json"),taskSnapshots(tasks));Common.write(run.resolve("parent-conversation.json"),application.snapshotParentMessages());
      Common.text(run.resolve("git-diff.patch"),Common.git(repo,"diff",base));Common.text(run.resolve("git-log.txt"),Common.git(repo,"log","--oneline","--all"));Common.text(run.resolve("git-status.txt"),Common.git(repo,"status","--short"));
      var trees=Common.JSON.createArrayNode();for(var w:wt.list()){
       var row=trees.addObject().put("name",w.name()).put("path",w.path().toString()).put("branch",w.branch());row.put("diff",Common.git(w.path(),"diff",base));row.put("status",Common.git(w.path(),"status","--short"));
      }Common.write(run.resolve("worktrees.json"),trees);
      for(var tree:trees)observedTrees.put(tree.path("path").asText(),(com.fasterxml.jackson.databind.node.ObjectNode)tree);
      Common.write(run.resolve("observed-worktrees.json"),observedTrees.values());
      boolean intact=true;for(String f:List.of("README.md","verify.ps1","tests/GateTest.java","contract.json"))intact&=Arrays.equals(Files.readAllBytes(repo.resolve(f)),Files.readAllBytes(fixture.resolve(f)));
      record.put("verifier_unchanged",intact);boolean tested=false;
      if(intact){try{Common.text(run.resolve("unified-test.txt"),Common.process(repo,"powershell.exe","-NoProfile","-File","./verify.ps1"));tested=true;}catch(Exception e){Common.text(run.resolve("unified-test.txt"),e.toString());}}
      double overlap=0;var list=tasks.list();for(int i=0;i<list.size();i++)for(int j=i+1;j<list.size();j++){
       var a=list.get(i);var b=list.get(j);Instant lo=a.startTime().isAfter(b.startTime())?a.startTime():b.startTime();Instant ae=a.endTime()==null?Instant.now():a.endTime(),be=b.endTime()==null?Instant.now():b.endTime();Instant hi=ae.isBefore(be)?ae:be;overlap=Math.max(overlap,Math.max(0,Duration.between(lo,hi).toMillis()/1000.0));
      }
      record.put("subagent_count",list.size()).put("maximum_pair_overlap_seconds",overlap).put("unified_test_passed",tested).put("independent_worktree_count",observedTrees.size());
      int changedTrees=0; for(var tree:observedTrees.values()){ if(!tree.path("diff").asText().isBlank()) changedTrees++; }
      boolean integrated=true;
      for(var component:Common.JSON.readTree(fixture.resolve("contract.json").toFile()).path("components"))
       integrated &= !Common.git(repo,"diff",base,"--",component.asText()).isBlank();
      var parent=application.snapshotParentMessages();
      String terminal=parent.isEmpty()?"":parent.getLast().content();
      boolean mainCompleted=terminal!=null&&!terminal.isBlank()&&!terminal.startsWith("[Agent run ended with ");
      int lastMutation=-1,lastVerify=-1;Map<String,ToolCall> callMap=new HashMap<>();
      Set<String> collected=new HashSet<>();
      for(int mi=0;mi<parent.size();mi++){
       var message=parent.get(mi);
       for(var call:message.toolCalls()){
        callMap.put(call.id(),call);
        if(call.name().equals("write_file")||call.name().equals("edit_file")||
           call.name().equals("bash")&&call.arguments().path("command").asText().matches("(?is).*(copy-item|set-content|git (apply|merge|cherry-pick)).*"))lastMutation=mi;
       }
       for(var result:message.toolResults()){
        var call=callMap.get(result.callId());
        if(call==null||!result.success())continue;
        if(call.name().equals("bash")&&call.arguments().path("command").asText().contains("verify.ps1")&&result.output().contains("PASS "))lastVerify=mi;
        if(call.name().equals("TaskGet"))try{var value=Common.JSON.readTree(result.output());if(value.path("status").asText().equals("completed"))collected.add(value.path("id").asText());}catch(Exception ignored){}
       }
      }
      boolean mainVerified=lastVerify>=0&&lastVerify>lastMutation;
      record.put("main_completed",mainCompleted).put("main_terminal_message",terminal)
       .put("main_verified_after_changes",mainVerified).put("explicitly_collected_results",collected.size());
      record.put("worktrees_with_modifications",changedTrees).put("both_components_integrated",integrated);
      boolean passed=mainCompleted&&mainVerified&&collected.size()>=2&&tested&&intact&&integrated&&changedTrees>=2&&list.size()>=2&&observedTrees.size()>=2&&overlap>0&&list.stream().allMatch(t->t.status()==TaskStatus.COMPLETED);
      record.put("status",passed?"PASS":"BLOCKED");if(!passed&&!record.has("failure_reason"))record.put("failure_reason","Strict gate conditions not all met (including normal Main completion, explicit result retrieval and final Main verification); inspect task status, Worktree changes, parent transcript and unified-test.txt. No harness merge performed.");
     }
    }
   }
  }catch(Exception e){record.put("status","BLOCKED").put("failure_reason",e.toString());}
  finally{System.setProperty("user.home",previousHome);record.put("wall_clock_seconds",(System.nanoTime()-start)/1e9);Common.write(run.resolve("run.json"),record);System.out.println("multi-agent "+record.path("status").asText());}
 }
}