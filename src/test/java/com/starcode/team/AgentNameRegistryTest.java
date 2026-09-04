package com.starcode.team;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.team.registry.AgentNameRegistry;
import org.junit.jupiter.api.Test;

class AgentNameRegistryTest {
    @Test void maintainsBidirectionalMappingsAcrossReplacement() {
        AgentNameRegistry registry = new AgentNameRegistry();
        registry.register("alice", "agent-1");
        assertEquals("agent-1", registry.resolve("alice").orElseThrow());
        assertEquals("alice", registry.nameOf("agent-1").orElseThrow());
        registry.register("alice", "agent-2");
        assertTrue(registry.resolve("agent-1").isEmpty());
        registry.register("bob", "agent-2");
        assertTrue(registry.resolve("alice").isEmpty());
        assertEquals("bob", registry.nameOf("agent-2").orElseThrow());
    }
}
