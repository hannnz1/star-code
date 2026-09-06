package com.starcode.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.agent.*;
import com.starcode.llm.*;
import com.starcode.tool.*;
import com.starcode.permission.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import static org.junit.jupiter.api.Assertions.*;

class McpLazyLoadingTest {
    static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path dir;
    Tool remote(String name, boolean readOnly, AtomicInteger calls) {
        return new Tool() {
            public ToolDefinition definition() { return new ToolDefinition(name,"Lookup shipment tracking number",
                    JSON.createObjectNode().put("type","object")); }
            public boolean deferred() { return true; }
            public boolean readOnly() { return readOnly; }
            public ToolResult execute(ToolCall call,ToolContext context) { calls.incrementAndGet(); return ToolResult.success(call,"delivered",false); }
        };
    }
    ToolCall search(String query) { return new ToolCall("search1",ModelToolCatalog.SEARCH,JSON.createObjectNode().put("query",query).put("limit",1)); }
    @Test void catalogIsLazyAndPerAgentAndFullModeIsAvailable() {
        var registry=new ToolRegistry().register(remote("mcp__carrier__track",true,new AtomicInteger()));
        var first=new ModelToolCatalog(registry,registry.definitions(),new HashSet<>());
        var second=new ModelToolCatalog(registry,registry.definitions(),new HashSet<>());
        assertEquals(List.of(ModelToolCatalog.SEARCH),first.definitions().stream().map(ToolDefinition::name).toList());
        assertTrue(first.discover(search("shipment tracking")).success());
        assertEquals(2,first.definitions().size());assertEquals(1,second.definitions().size());
        registry.lazyMcpLoading(false);
        assertEquals(registry.definitions(),new ModelToolCatalog(registry,registry.definitions(),new HashSet<>()).definitions());
    }
    @Test void hiddenToolsCannotBeDiscoveredOrExecutedAndInvalidSearchDoesNotLoad() {
        var registry=new ToolRegistry().register(remote("mcp__secret__write",false,new AtomicInteger()));
        var catalog=new ModelToolCatalog(registry,List.of(),new HashSet<>());
        assertFalse(catalog.isSearch(ModelToolCatalog.SEARCH));assertFalse(catalog.canExecute("mcp__secret__write"));
        var visible=new ModelToolCatalog(registry,registry.definitions(),new HashSet<>());
        assertFalse(visible.discover(search("")).success());
        assertTrue(visible.discover(search("nonexistent")).success());assertEquals(1,visible.definitions().size());
        assertFalse(visible.discover(new ToolCall("bad",ModelToolCatalog.SEARCH,JSON.createObjectNode().put("query","write").put("limit",6))).success());
    }
    static final class Scripted implements LlmClient {
        final List<List<ToolDefinition>> requests=new ArrayList<>();final List<Completion> script;int pos;
        final List<ToolResult> results=new ArrayList<>();
        Scripted(Completion... script) {this.script=List.of(script);}
        public Completion stream(List<ChatMessage> h,String u,List<ToolDefinition> t,Consumer<StreamEvent> e) {
            requests.add(List.copyOf(t));return script.get(pos++);
        }
        public Completion continueWithTools(List<ChatMessage> h,String u,List<ToolExchange> x,List<ToolDefinition> t,Consumer<StreamEvent> e) {
            results.addAll(x.getLast().results());return stream(h,u,t,e);
        }
    }
    @Test void agentRefreshesSchemasExecutesRemoteAndKeepsActivationOnNextTurn() throws Exception {
        AtomicInteger calls=new AtomicInteger();var registry=new ToolRegistry().register(remote("mcp__carrier__track",true,calls));
        var client=new Scripted(new Completion("",List.of(search("mcp__carrier__track")),null),
                new Completion("",List.of(new ToolCall("remote1","mcp__carrier__track",JSON.createObjectNode())),null),
                new Completion("delivered"),new Completion("still available"));
        var agent=new AgentLoop(client,registry,new ToolContext(dir,false,false));
        assertEquals(AgentOutcome.Status.COMPLETED,agent.run(List.of(),"track",AgentMode.DEFAULT,new CancellationToken(),e->{}).status());
        assertEquals(1,calls.get());assertEquals(1,client.requests.getFirst().size());assertEquals(2,client.requests.get(1).size());
        agent.run(List.of(),"again",AgentMode.DEFAULT,new CancellationToken(),e->{});
        assertEquals(2,client.requests.getLast().size());
    }
    @Test void discoveryDoesNotAuthorizeRemoteSideEffects() throws Exception {
        AtomicInteger calls=new AtomicInteger();var registry=new ToolRegistry().register(remote("mcp__carrier__track",false,calls));
        var client=new Scripted(new Completion("",List.of(search("track")),null),
                new Completion("",List.of(new ToolCall("remote1","mcp__carrier__track",JSON.createObjectNode())),null),new Completion("denied"));
        var context=new ToolContext(dir,false,false);
        var permissions=new PermissionManager(context,PermissionRuleSet.empty(),PermissionRuleSet.empty(),PermissionRuleSet.empty(),dir.resolve("permissions.yaml"),null,registry::isReadOnly);
        new AgentLoop(client,registry,context,permissions).run(List.of(),"track",AgentMode.DEFAULT,new CancellationToken(),e->{});
        assertEquals(0,calls.get());assertTrue(client.results.getFirst().success());
        assertTrue(client.results.getLast().errorCode().startsWith("PERMISSION_DENIED"));
    }
    @Test void planCannotInvokeAnUnadvertisedMutatingMcpTool() throws Exception {
        AtomicInteger calls=new AtomicInteger();var registry=new ToolRegistry().register(remote("mcp__carrier__track",false,calls));
        var client=new Scripted(new Completion("",List.of(new ToolCall("remote1","mcp__carrier__track",JSON.createObjectNode())),null),new Completion("denied"));
        new AgentLoop(client,registry,new ToolContext(dir,false,false)).run(List.of(),"plan",AgentMode.PLAN,new CancellationToken(),e->{});
        assertEquals(0,calls.get());assertFalse(client.results.getFirst().success());
    }
}
