package com.starcode.skill;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SkillInvocationAuditTest {
    @TempDir Path temp;

    @Test void appendsTraceableSessionScopedRecords() throws Exception {
        SkillInvocationAudit.append(temp, "session-1", "review", SkillSource.PROJECT);
        SkillInvocationAudit.append(temp, "session-1", "style", SkillSource.USER);

        String audit = Files.readString(temp.resolve("skill-invocations.jsonl"));
        assertEquals(2, audit.lines().count());
        assertTrue(audit.contains("\"name\":\"review\""));
        assertTrue(audit.contains("\"source\":\"project\""));
        assertTrue(audit.contains("\"sessionId\":\"session-1\""));
    }
}
