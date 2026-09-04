package com.starcode.config;

public record ProxyConfig(boolean enabled, String host, int port) {
    public static ProxyConfig disabled() { return new ProxyConfig(false, "", 0); }
}

