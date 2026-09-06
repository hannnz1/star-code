package bench;
import com.starcode.llm.*;import com.starcode.tool.*;import com.starcode.config.ProviderConfig;
import java.util.*;import java.util.concurrent.atomic.AtomicInteger;import java.nio.file.*;import java.util.function.Consumer;import java.time.Instant;
public final class RecordingClient implements LlmClient{
 final LlmClient delegate;final Path dir;final ProviderConfig provider;final AtomicInteger calls=new AtomicInteger();public volatile String phase="compact";
 public RecordingClient(LlmClient d,Path dir,ProviderConfig p){delegate=d;this.dir=dir;provider=p;}
 interface Call{Completion run()throws LlmException,InterruptedException;}
 Completion record(List<ChatMessage> h,String u,List<ToolDefinition> t,TurnContext ctx,Call call)throws LlmException,InterruptedException{
  String id=String.format("%04d",calls.incrementAndGet());var r=Common.record("model-call",id,provider).put("phase",phase).put("thread_id",Thread.currentThread().threadId());
  r.put("agent_kind",t.stream().anyMatch(v->v.name().equals("Agent"))?"main":t.isEmpty()?phase:"subagent");r.set("history",Common.JSON.valueToTree(h));r.put("user_text",u);r.set("tools",Common.JSON.valueToTree(t));r.set("turn_context",Common.JSON.valueToTree(ctx));long start=System.nanoTime();
  try{r.put("status","STARTED");Common.write(dir.resolve(id+".json"),r);}catch(Exception e){throw new IllegalStateException("Cannot persist call input",e);}
  try{Completion c=call.run();r.put("status","SUCCESS").put("response_text",c.text());r.set("tool_calls",Common.JSON.valueToTree(c.toolCalls()));Common.usage(r,c.usage(),provider.protocol());r.put("usage_source","production Completion; ZERO fallback possible, verify wire response.completed.usage");return c;}
  catch(LlmException|InterruptedException e){r.put("status","FAILURE").put("exception",e.toString());throw e;}
  finally{r.put("end_time",Instant.now().toString()).put("wall_clock_seconds",(System.nanoTime()-start)/1e9);try{Common.write(dir.resolve(id+".json"),r);}catch(Exception e){throw new IllegalStateException("Cannot persist model call",e);}}
 }
 public Completion stream(List<ChatMessage> h,String u,List<ToolDefinition> t,Consumer<StreamEvent> e)throws LlmException,InterruptedException{return stream(h,u,t,TurnContext.NONE,e);}
 public Completion stream(List<ChatMessage> h,String u,List<ToolDefinition> t,TurnContext c,Consumer<StreamEvent> e)throws LlmException,InterruptedException{return record(h,u,t,c,()->delegate.stream(h,u,t,c,e));}
 public Completion continueWithTools(List<ChatMessage> h,String u,List<ToolExchange>x,List<ToolDefinition> t,Consumer<StreamEvent> e)throws LlmException,InterruptedException{return continueWithTools(h,u,x,t,TurnContext.NONE,e);}
 public Completion continueWithTools(List<ChatMessage>h,String u,List<ToolExchange>x,List<ToolDefinition>t,TurnContext c,Consumer<StreamEvent>e)throws LlmException,InterruptedException{List<ChatMessage>full=new ArrayList<>(h);for(var v:x){full.add(ChatMessage.assistant(v.assistant()));full.add(ChatMessage.tool(v.results()));}return record(full,u,t,c,()->delegate.continueWithTools(h,u,x,t,c,e));}
 public void close(){try{delegate.close();}catch(Exception ignored){}}
}