package com.starcode.team.backend;

import com.starcode.team.BackendType;
import java.io.IOException;

public interface Backend {
    BackendType type();
    SpawnResult spawn(SpawnRequest request) throws IOException;
    void wake(String paneId, String agentId) throws IOException;
    void kill(String paneId, String agentId) throws IOException;
}
