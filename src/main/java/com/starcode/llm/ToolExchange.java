package com.starcode.llm;

import com.starcode.tool.ToolResult;
import java.util.List;

public record ToolExchange(Completion assistant, List<ToolResult> results) {
    public ToolExchange { results = List.copyOf(results); }
}
