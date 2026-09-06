package bench;

import com.starcode.agent.CancellationToken;
import com.starcode.permission.*;
import com.starcode.tool.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Executes permission decisions only. The fixture commands never run. */
public final class PermissionBench {
 public static void main(String[] args) throws Exception {
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();
  String commit=Common.git(Common.root.getParent(),"rev-parse","HEAD");
  if(!Common.git(Common.root.getParent(),"diff","HEAD","--","src/main").isBlank())
   throw new IllegalStateException("Commit production before measuring");
  Path fixture=Common.root.resolve("permission-v1/fixture.json");
  var data=Common.JSON.readTree(fixture.toFile());
  Path batch=Common.root.resolve("results/raw/permission-v1/"+Instant.now().toString().replace(':','-'));
  Files.createDirectories(batch); Files.copy(fixture,batch.resolve("fixture.json"));
  Files.copy(Common.root.resolve(".work/build-manifest.json"),batch.resolve("build-manifest.json"));
  for(var session:data.path("sessions")) for(String mode:List.of("BASELINE_ONCE","CURRENT_SESSION")) {
   String name=session.path("name").asText(); Path run=batch.resolve(name+"-"+mode); Files.createDirectories(run);
   Path workspace=Common.root.resolve(".work/permissions-"+batch.getFileName()).resolve(name+"-"+mode);
   Files.createDirectories(workspace); var context=new ToolContext(workspace,true,true);
   var prompts=new AtomicInteger(); var risk=new boolean[]{false};
   var manager=new PermissionManager(context,PermissionRuleSet.empty(),PermissionRuleSet.empty(),PermissionRuleSet.empty(),
      workspace.resolve(".starcode/permissions.local.yaml"),(request,cancellation)->{
       prompts.incrementAndGet(); return risk[0]?ApprovalChoice.DENY:
        mode.equals("BASELINE_ONCE")?ApprovalChoice.ALLOW_ONCE:ApprovalChoice.ALLOW_SESSION;
      });
   long start=System.nanoTime(); int approved=0,denied=0,automatic=0,sessionAllowed=0,unsafe=0,blocked=0;
   List<Object> rows=new ArrayList<>(); int number=0;
   for(var step:session.path("actions")) {
    risk[0]=step.path("high_risk").asBoolean(); int before=prompts.get();
    var call=new ToolCall("action-"+(++number),step.path("tool").asText(),step.path("arguments"));
    var outcome=manager.authorize(call,new CancellationToken()); boolean prompted=prompts.get()>before;
    boolean allowed=outcome.decision()==PermissionDecision.ALLOW;
    if(allowed)approved++;else denied++;
    if(allowed&&!prompted)automatic++;
    if(outcome.source().equals("session grant"))sessionAllowed++;
    if(risk[0]&&allowed&&!prompted)unsafe++;
    if(risk[0]&&!allowed)blocked++;
    var row=Common.JSON.createObjectNode().put("number",number).put("timestamp",Instant.now().toString())
       .put("high_risk",risk[0]).put("prompted",prompted).put("decision",outcome.decision().name())
       .put("source",outcome.source()).put("reason",outcome.reason());
    row.set("request",Common.JSON.valueToTree(call)); rows.add(row);
   }
   Common.write(run.resolve("actions.json"),rows);
   Common.write(run.resolve("run.json"),Common.JSON.createObjectNode().put("benchmark","permission-workflow-replay")
     .put("run_id",run.getFileName().toString()).put("timestamp",Instant.now().toString()).put("git_commit",commit)
     .put("java",System.getProperty("java.runtime.version")).put("os",System.getProperty("os.name"))
     .put("model","NOT_APPLICABLE").put("protocol","NOT_APPLICABLE").put("seed",Common.SEED)
     .put("model_configuration","NOT_APPLICABLE; no model calls").put("status","SUCCESS")
     .put("session",name).put("policy",mode).put("permission_prompts",prompts.get()).put("approved",approved)
     .put("denied",denied).put("auto_allowed",automatic).put("session_allowed",sessionAllowed)
     .put("dangerous_action_blocked",blocked).put("unsafe_auto_approval_count",unsafe)
     .put("fixture_sha256",Common.hash(Files.readAllBytes(fixture)))
     .put("wall_clock_seconds",(System.nanoTime()-start)/1e9).put("retries",0).putNull("exception")
     .putNull("task_success").putNull("input_tokens").putNull("output_tokens").putNull("total_tokens"));
  }
  Common.text(Common.root.resolve("results/permission-v1-latest.txt"),Common.root.relativize(batch).toString());
  System.out.println("RAW_RESULTS="+batch);
 }
}
