package bench;

import com.starcode.config.ConfigLoader;
import java.nio.file.*;
import java.time.Instant;

/** Reuses the frozen production Team gate against current committed sources. */
public final class GateCurrent {
 public static void main(String[] args) throws Exception {
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();
  String commit=Common.git(Common.root.getParent(),"rev-parse","HEAD");
  if(!Common.git(Common.root.getParent(),"diff","HEAD","--","src/main").isBlank())
   throw new IllegalStateException("Commit production changes before measuring");
  Path run=Common.root.resolve("results/raw/multi-agent-current/"+Instant.now().toString().replace(':','-'));
  Files.createDirectories(run);
  var app=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));
  var provider=app.providers().getFirst();
  Common.write(run.resolve("environment.json"),Common.record("multi-agent-current",run.getFileName().toString(),provider)
    .put("implementation_commit",commit).put("fixture","multi-agent/fixture")
    .put("harness_behavior","observation and verification only; no task decomposition or merge"));
  Files.copy(Common.root.resolve(".work/build-manifest.json"),run.resolve("build-manifest.json"));
  Common.text(Common.root.resolve("results/multi-agent-current-latest.txt"),Common.root.relativize(run).toString());
  System.out.println("RAW_RESULTS="+run);
  GateBench.run(run,app,provider);
 }
}
