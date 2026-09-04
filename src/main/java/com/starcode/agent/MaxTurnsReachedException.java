package com.starcode.agent;

/** Raised when a non-interactive child reaches its configured ReAct turn limit. */
public final class MaxTurnsReachedException extends Exception {
    private final String partialResult;

    public MaxTurnsReachedException(int turns, String partialResult) {
        super("SubAgent reached its maximum of " + turns + " turns");
        this.partialResult = partialResult == null ? "" : partialResult;
    }

    public String partialResult() { return partialResult; }
}
