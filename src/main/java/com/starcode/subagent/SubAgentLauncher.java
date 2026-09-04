package com.starcode.subagent;

import com.starcode.llm.ChatMessage;
import com.starcode.tool.ToolContext;
import java.util.List;

/** Narrow host port used by the Agent tool; implemented by the application layer. */
@FunctionalInterface
public interface SubAgentLauncher {
    SubAgentSession create(SubAgentDefinition definition, boolean background, String modelOverride,
                           List<ChatMessage> parentHistory) throws Exception;

    default SubAgentSession create(SubAgentDefinition definition, boolean background, String modelOverride,
                                   List<ChatMessage> parentHistory, ToolContext executionContext) throws Exception {
        return create(definition, background, modelOverride, parentHistory);
    }
}
