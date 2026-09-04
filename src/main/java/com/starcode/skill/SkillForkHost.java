package com.starcode.skill;

import com.starcode.llm.ChatMessage;
import java.util.List;

public interface SkillForkHost extends SkillHost {
    SkillRunResult runSubAgent(String body, List<ChatMessage> seed, SkillMeta meta) throws Exception;
    List<ChatMessage> snapshotParentMessages();
}
