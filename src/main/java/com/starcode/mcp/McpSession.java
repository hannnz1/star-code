package com.starcode.mcp;

import java.util.List;
import java.util.Map;

public interface McpSession extends AutoCloseable {
    List<McpRemoteTool> tools();
    McpCallResult call(String tool, Map<String, Object> arguments);
    @Override void close();
}
