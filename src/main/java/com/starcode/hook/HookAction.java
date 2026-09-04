package com.starcode.hook;

import java.net.URI;
import java.util.Map;
import java.util.Objects;

public sealed interface HookAction
        permits HookAction.Shell, HookAction.Prompt, HookAction.Http, HookAction.Subagent {
    String type();

    record Shell(String command) implements HookAction {
        public Shell {
            command = Objects.requireNonNullElse(command, "");
        }

        @Override public String type() { return "shell"; }
    }

    record Prompt(String text) implements HookAction {
        public Prompt {
            text = Objects.requireNonNullElse(text, "");
        }

        @Override public String type() { return "prompt"; }
    }

    record Http(URI url, String method, Map<String, String> headers, String body) implements HookAction {
        public Http {
            Objects.requireNonNull(url, "url");
            method = Objects.requireNonNullElse(method, "POST").toUpperCase(java.util.Locale.ROOT);
            headers = Map.copyOf(headers);
        }

        @Override public String type() { return "http"; }
    }

    record Subagent(String agentName, String prompt) implements HookAction {
        public Subagent {
            agentName = Objects.requireNonNullElse(agentName, "");
            prompt = Objects.requireNonNullElse(prompt, "");
        }

        @Override public String type() { return "subagent"; }
    }
}
