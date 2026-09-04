package com.starcode.skill;

import java.nio.file.Path;

public record Skill(SkillMeta meta, String promptBody, Path sourceDir, SkillSource source, boolean bodyLoaded) {
    public Skill withBody(String body) { return new Skill(meta, body, sourceDir, source, true); }
}
