package com.starcode.skill;

public interface SkillHost {
    void activateSkill(String name, String body);
    void recordSkillInvocation(String name, String body);
}
