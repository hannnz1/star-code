package com.starcode.permission;

public enum PermissionMode {
    DEFAULT("default"), ACCEPT_EDITS("acceptEdits"), PLAN("plan"), BYPASS_PERMISSIONS("bypassPermissions");
    private final String configName;
    PermissionMode(String configName) { this.configName = configName; }
    public String configName() { return configName; }
    public PermissionMode next() {
        PermissionMode[] values = values();
        return values[(ordinal() + 1) % values.length];
    }
    public static PermissionMode parse(String value) {
        if (value != null) for (PermissionMode mode : values()) if (mode.configName.equalsIgnoreCase(value)) return mode;
        return DEFAULT;
    }
}
