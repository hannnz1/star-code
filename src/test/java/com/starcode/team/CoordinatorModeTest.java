package com.starcode.team;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.config.AppConfig;
import com.starcode.config.FeaturesConfig;
import com.starcode.config.ProxyConfig;
import com.starcode.prompt.PromptContext;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class CoordinatorModeTest {
    @Test void requiresConfigAndEnvironmentSwitches() {
        AppConfig enabled = new AppConfig("system", Duration.ofSeconds(30), ProxyConfig.disabled(),
                List.of(), new PromptContext(), true, new FeaturesConfig(true, false));
        AppConfig disabled = new AppConfig("system", Duration.ofSeconds(30), ProxyConfig.disabled(),
                List.of(), new PromptContext(), true, FeaturesConfig.disabled());
        assertFalse(CoordinatorMode.enabled(enabled, Map.of()));
        assertFalse(CoordinatorMode.enabled(disabled, Map.of("STAR_CODE_COORDINATOR_MODE", "1")));
        assertTrue(CoordinatorMode.enabled(enabled, Map.of("STAR_CODE_COORDINATOR_MODE", "true")));
        assertTrue(CoordinatorMode.enabled(enabled, Map.of("MEWCODE_COORDINATOR_MODE", "yes")));
    }

    @Test void whitelistExcludesDirectFileWrites() {
        var allowed = CoordinatorMode.allowedTools(List.of("read_file", "write_file", "edit_file",
                "bash", "Agent", "TaskList"));
        assertTrue(allowed.containsAll(List.of("read_file", "bash", "Agent", "TaskList")));
        assertFalse(allowed.contains("write_file"));
        assertFalse(allowed.contains("edit_file"));
    }
}
