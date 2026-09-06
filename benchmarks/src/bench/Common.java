package bench;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.starcode.config.*;
import com.starcode.llm.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import java.security.MessageDigest;

public final class Common {
    public static final ObjectMapper JSON = new ObjectMapper().findAndRegisterModules();
    public static final long SEED = 20260905L;
    public static final String BASELINE = "014808a0b0942f25bc4f1c3f415fa63262f98176";
    public static Path root;
    public static void write(Path path, Object value) throws Exception {
        Files.createDirectories(path.getParent());
        JSON.writerWithDefaultPrettyPrinter().writeValue(path.toFile(), value);
    }
    public static void text(Path path, String value) throws Exception {
        Files.createDirectories(path.getParent()); Files.writeString(path, value, StandardCharsets.UTF_8);
    }
    public static ObjectNode record(String name, String run, ProviderConfig p) {
        ObjectNode r=JSON.createObjectNode().put("benchmark",name).put("run_id",run)
            .put("timestamp",Instant.now().toString()).put("baseline_commit",BASELINE)
            .put("seed",SEED).put("harness_build_manifest_sha256",System.getProperty("bench.harness.sha","unavailable")).put("java",System.getProperty("java.runtime.version"))
            .put("os",System.getProperty("os.name")).put("os_version",System.getProperty("os.version"))
            .put("architecture",System.getProperty("os.arch")).put("logical_processors",Runtime.getRuntime().availableProcessors())
            .put("model",p.model()).put("protocol",p.protocol()).put("thinking",p.thinking())
            .put("context_window",p.contextWindow()).put("temperature","provider default; production does not set it");
        r.putNull("input_tokens").putNull("output_tokens").putNull("total_tokens");
        return r;
    }
    public static String hash(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
    public static AppConfig clean(AppConfig source, ProviderConfig provider) {
        return new AppConfig(source.systemPrompt(),source.requestTimeout(),ProxyConfig.disabled(),List.of(provider),
            new com.starcode.prompt.PromptContext(),source.enableSubAgentBackground(),source.features());
    }
    public static String process(Path cwd, String... argv) throws Exception {
        Process p=new ProcessBuilder(argv).directory(cwd.toFile()).redirectErrorStream(true).start();
        String out=new String(p.getInputStream().readAllBytes(),StandardCharsets.UTF_8);
        int code=p.waitFor(); if(code!=0) throw new IllegalStateException("Process exit "+code+": "+String.join(" ",argv)+"\n"+out);
        return out.strip();
    }
    public static String git(Path cwd,String... args) throws Exception {
        List<String> cmd=new ArrayList<>(List.of("git","-c","safe.directory="+cwd.toAbsolutePath().toString().replace('\\','/')));
        cmd.addAll(List.of(args)); return process(cwd,cmd.toArray(String[]::new));
    }
    public static void usage(ObjectNode r, TokenUsage u, String protocol) {
        long input=u.inputTokens();
        if("anthropic".equals(protocol)) input+=u.cacheReadTokens()+u.cacheWriteTokens();
        r.put("input_tokens",input).put("output_tokens",u.outputTokens()).put("total_tokens",input+u.outputTokens());
        r.put("cache_read_tokens",u.cacheReadTokens()).put("cache_write_tokens",u.cacheWriteTokens());
    }
}
