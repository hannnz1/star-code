package com.starcode.permission;

import com.starcode.tool.ToolCall;

public record PermissionRequest(ToolCall call, String friendlyName, String target, String reason) {}
