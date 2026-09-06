package bench;

import com.starcode.config.ConfigLoader;
import java.nio.file.*;
import java.time.Instant;
import java.util.List;

/** Three frozen E2E tasks; this entry point never decomposes or integrates changes. */
public final class GateSuiteCurrent {
 public static void main(String[] args) throws Exception {
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();
  String commit=Common.git(Common.root.getParent(),"rev-parse","HEAD");
  if(!Common.git(Common.root.getParent(),"diff","HEAD","--","src/main").isBlank())
   throw new IllegalStateException("Commit production before measuring");
  var hashes=Common.JSON.readTree(Common.root.resolve("multi-agent-v2/fixtures.sha256.json").toFile());
  var names=hashes.fieldNames();
  while(names.hasNext()){
   String name=names.next();
   if(!Common.hash(Files.readAllBytes(Common.root.resolve("multi-agent-v2").resolve(name))).equals(hashes.path(name).asText()))
    throw new IllegalStateException("Frozen fixture changed: "+name);
  }
  String timestamp=Instant.now().toString().replace(':','-');
  Path batch=Common.root.resolve("results/raw/multi-agent-v2/"+timestamp);Files.createDirectories(batch);
  var app=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));var p=app.providers().getFirst();
  Common.write(batch.resolve("environment.json"),Common.record("multi-agent-v2",timestamp,p)
    .put("implementation_commit",commit).put("main_max_turns",app.agentLimits().maxTurns())
    .put("main_max_tool_calls",app.agentLimits().maxToolCalls()).put("speedup_status","NOT_MEASURED"));
  Files.copy(Common.root.resolve(".work/build-manifest.json"),batch.resolve("build-manifest.json"));
  Files.copy(Common.root.resolve("multi-agent-v2/fixtures.sha256.json"),batch.resolve("fixtures.sha256.json"));
  Common.text(Common.root.resolve("results/multi-agent-v2-latest.txt"),Common.root.relativize(batch).toString());
  for(String name:List.of("checkout","text","numeric")){
   Path run=batch.resolve(timestamp+"-"+name);Files.createDirectories(run);
   GateSuiteBench.run(run,app,p,Common.root.resolve("multi-agent-v2/fixtures/"+name));
   if(!Common.JSON.readTree(run.resolve("run.json").toFile()).path("status").asText().equals("PASS")){
    System.out.println("SUITE_BLOCKED: "+name+"; remaining cases not run; no speed experiment");return;
   }
  }
  System.out.println("SUITE_PASS: three distinct complete E2E contracts; no speed experiment");
 }
}
