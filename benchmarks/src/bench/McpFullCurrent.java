package bench;
import com.starcode.config.ConfigLoader;
import java.nio.file.*;
import java.time.Instant;
/** Current committed production baseline, separate from immutable original BenchMain guard. */
public final class McpFullCurrent {
 public static void main(String[] args)throws Exception {
  Common.root=Path.of(System.getProperty("bench.root")).toAbsolutePath();
  String commit=Common.git(Common.root.getParent(),"rev-parse","HEAD");
  if(!Common.git(Common.root.getParent(),"diff","HEAD","--","src/main").isBlank())
   throw new IllegalStateException("Commit production before measuring baseline");
  Path dir=Common.root.resolve("results/raw/mcp-full-current/"+Instant.now().toString().replace(':','-'));
  Files.createDirectories(dir);
  var app=ConfigLoader.load(Common.root.getParent().resolve("config.yaml"));var provider=app.providers().getFirst();
  Common.write(dir.resolve("environment.json"),Common.record("mcp-full-current",dir.getFileName().toString(),provider)
   .put("implementation_commit",commit).put("model_behavior","local deterministic sink; no real selection model"));
  Files.copy(Common.root.resolve(".work/build-manifest.json"),dir.resolve("build-manifest.json"));
  for(int count:new int[]{10,25,50,100})for(int repeat=1;repeat<=5;repeat++)
   McpLazyBench.run(dir,app,provider,commit,count,repeat,false,null);
  Common.text(Common.root.resolve("results/mcp-full-current-latest.txt"),Common.root.relativize(dir).toString());
  System.out.println("RAW_RESULTS="+dir);
 }
}
