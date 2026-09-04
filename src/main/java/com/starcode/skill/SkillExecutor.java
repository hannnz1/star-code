package com.starcode.skill;

import com.starcode.llm.ChatMessage;
import java.util.List;

public final class SkillExecutor {
    public String executeInline(Skill skill, String arguments, SkillHost host) {
        String rendered = substituteArguments(skill.promptBody(), arguments);
        host.activateSkill(skill.meta().name(), rendered);
        host.recordSkillInvocation(skill.meta().name(), rendered);
        return rendered;
    }

    public SkillRunResult executeFork(Skill skill, String arguments, SkillForkHost host) throws Exception {
        String rendered = substituteArguments(skill.promptBody(), arguments);
        host.recordSkillInvocation(skill.meta().name(), rendered);
        return host.runSubAgent(rendered,
                buildForkSeed(skill.meta().forkContext(), host.snapshotParentMessages()), skill.meta());
    }

    public static String substituteArguments(String body, String arguments) {
        String args = arguments == null ? "" : arguments.strip();
        if (args.isEmpty()) return body;
        if (body.contains("$ARGUMENTS")) return body.replace("$ARGUMENTS", args);
        return body.stripTrailing() + "\n\n## User Request\n\n" + args;
    }

    public static List<ChatMessage> buildForkSeed(String mode, List<ChatMessage> parent) {
        List<ChatMessage> source = parent == null ? List.of() : parent;
        return switch (mode == null ? "none" : mode.toLowerCase()) {
            case "full" -> List.copyOf(source);
            case "recent" -> recentSeed(source);
            default -> List.of();
        };
    }

    private static List<ChatMessage> recentSeed(List<ChatMessage> source) {
        int start = Math.max(0, source.size() - 5);
        if (start < source.size() && source.get(start).role() == ChatMessage.Role.TOOL) {
            while (start > 0) {
                start--;
                ChatMessage candidate = source.get(start);
                if (candidate.role() == ChatMessage.Role.ASSISTANT && !candidate.toolCalls().isEmpty()) break;
            }
        }
        return List.copyOf(source.subList(start, source.size()));
    }
}
