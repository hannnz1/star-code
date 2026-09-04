package com.starcode.memory;

public enum NoteType {
    USER_PREFERENCE("user_preference"), CORRECTION_FEEDBACK("correction_feedback"),
    PROJECT_KNOWLEDGE("project_knowledge"), REFERENCE_MATERIAL("reference_material");
    private final String wire;
    NoteType(String wire) { this.wire = wire; }
    public String wire() { return wire; }
    public static NoteType fromWire(String value) {
        for (NoteType type : values()) if (type.wire.equals(value)) return type;
        throw new IllegalArgumentException("Unknown memory type: " + value);
    }
}
