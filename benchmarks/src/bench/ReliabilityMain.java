package bench;
import com.starcode.config.*;
import java.nio.file.*;import java.time.*;import java.util.*;
public final class ReliabilityMain {
 public static void main(String[] args)throws Exception {
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();
  var manifest=Common.JSON.readTree(Common.root.resolve("reliability-v1/comparison-manifest.json").toFile());
  var iter=manifest.path("files").fields();while(iter.hasNext()){var e=iter.next();if(!Common.hash(Files.readAllBytes(Common.root.resolve(e.getKey()))).equals(e.getValue().asText()))throw new IllegalStateException("Frozen comparator/fixture changed: "+e.getKey());}
  String baseline=Common.git(Common.root.getParent(),"rev-parse","benchmark-baseline-v1^{commit}");if(!baseline.equals(Common.BASELINE))throw new IllegalStateException("Baseline mismatch");
  String changed=Common.git(Common.root.getParent(),"diff","--name-only",Common.BASELINE,"--","src/main","build.gradle.kts","settings.gradle.kts");
  for(String f:changed.lines().toList())if(!f.startsWith("src/main/java/com/starcode/context/"))throw new IllegalStateException("Out-of-scope production change: "+f);
  var app=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));var p=app.providers().getFirst();
  if(!p.model().equals(manifest.path("model").asText())||!p.protocol().equals(manifest.path("protocol").asText())||p.contextWindow()!=128000||p.thinking())throw new IllegalStateException("Provider configuration changed");
  String id=Instant.now().toString().replace(':','-')+"-"+UUID.randomUUID().toString().substring(0,8);
  Path batch=Common.root.resolve("results/raw/context-reliability/"+id);Files.createDirectories(batch);
  var env=Common.record("context-reliability",id,p).put("git_commit",Common.git(Common.root.getParent(),"rev-parse","HEAD")).put("production_worktree_dirty",true).put("planned_runs",10).put("judge","unchanged original extraction prompt and model; temperature provider default");
  Common.write(batch.resolve("environment.json"),env);Common.write(batch.resolve("comparison-manifest.json"),manifest);
  Common.text(batch.resolve("production-diff.patch"),Common.git(Common.root.getParent(),"diff",Common.BASELINE,"--","src/main"));
  for(Path dir:List.of(Common.root.resolve("src"),Common.root.getParent().resolve("src/main/java/com/starcode/context"))){try(var paths=Files.walk(dir)){for(Path f:paths.filter(Files::isRegularFile).toList()){Path dest=batch.resolve("source-snapshot").resolve(Common.root.getParent().relativize(f));Files.createDirectories(dest.getParent());Files.copy(f,dest);}}}
  Files.copy(Common.root.resolve(".work/build-manifest.json"),batch.resolve("build-manifest.json"));
  Common.text(Common.root.resolve("results/context-reliability-latest.txt"),Common.root.relativize(batch).toString());
  ReliabilityContextBench.run(batch,app,p);
  System.out.println("RAW_RESULTS="+batch);System.exit(0);
 }
}
