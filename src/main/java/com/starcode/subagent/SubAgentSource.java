package com.starcode.subagent;

/** Source tier for a sub-agent definition. Higher-priority tiers are loaded later. */
public enum SubAgentSource {
    BUILTIN,
    USER,
    PROJECT,
    PLUGIN
}
