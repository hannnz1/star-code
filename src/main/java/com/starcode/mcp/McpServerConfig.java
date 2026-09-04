package com.starcode.mcp;

import java.util.List;
import java.util.Map;

public record McpServerConfig(String name, Type type, String command, List<String> args,
                              Map<String, String> env, String url, Map<String, String> headers) {
    public enum Type { STDIO, HTTP }
}
