package com.starcode.config;

/** Opt-in experimental features. Every flag defaults to false. */
public record FeaturesConfig(boolean coordinatorMode, boolean forkTeammate) {
    public static FeaturesConfig disabled() { return new FeaturesConfig(false, false); }
}
