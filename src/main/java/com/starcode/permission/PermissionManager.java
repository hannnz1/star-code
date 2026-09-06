package com.starcode.permission;

import com.starcode.agent.CancellationToken;
import com.starcode.tool.*;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.function.Predicate;
import java.util.function.BiConsumer;

public final class PermissionManager {
    private final ToolContext context;
    private final PermissionRuleSet userRules, projectRules;
    private PermissionRuleSet localRules;
    private final Path localConfig;
    private final PermissionApprover approver;
    private final Predicate<String> readOnlyTool;
    private volatile BiConsumer<PermissionRequest, CancellationToken> approvalObserver = (request, cancellation) -> {};
    private volatile PermissionMode mode;

    public PermissionManager(ToolContext context, PermissionRuleSet userRules, PermissionRuleSet projectRules,
                             PermissionRuleSet localRules, Path localConfig, PermissionApprover approver) {
        this(context, userRules, projectRules, localRules, localConfig, approver, ignored -> false);
    }
    public PermissionManager(ToolContext context, PermissionRuleSet userRules, PermissionRuleSet projectRules,
                             PermissionRuleSet localRules, Path localConfig, PermissionApprover approver,
                             Predicate<String> readOnlyTool) {
        this.context = context; this.userRules = userRules; this.projectRules = projectRules;
        this.localRules = localRules; this.localConfig = localConfig; this.approver = approver;
        this.readOnlyTool = readOnlyTool; this.mode = firstMode(localRules, projectRules, userRules);
    }

    public static PermissionManager load(ToolContext context, PermissionApprover approver) {
        return load(context, approver, ignored -> false);
    }
    public static PermissionManager load(ToolContext context, PermissionApprover approver, Predicate<String> readOnlyTool) {
        Path workspace = context.workspace();
        Path user = Path.of(System.getProperty("user.home"), ".starcode", "permissions.yaml");
        Path project = workspace.resolve(".starcode").resolve("permissions.yaml");
        Path local = workspace.resolve(".starcode").resolve("permissions.local.yaml");
        return new PermissionManager(context, PermissionConfigLoader.load(user), PermissionConfigLoader.load(project),
                PermissionConfigLoader.load(local), local, approver, readOnlyTool);
    }
    public static PermissionManager trustedForTests(ToolContext context) {
        PermissionManager manager = new PermissionManager(context, PermissionRuleSet.empty(), PermissionRuleSet.empty(),
                PermissionRuleSet.empty(), context.workspace().resolve(".starcode-test-permissions.yaml"), null);
        manager.mode(PermissionMode.BYPASS_PERMISSIONS);
        return manager;
    }

    public PermissionMode mode() { return mode; }
    public void mode(PermissionMode value) { mode = Objects.requireNonNull(value); }
    public PermissionMode cycleMode() { mode = mode.next(); return mode; }
    public void approvalObserver(BiConsumer<PermissionRequest, CancellationToken> observer) {
        approvalObserver = observer == null ? (request, cancellation) -> {} : observer;
    }

    public PermissionOutcome authorize(ToolCall call, CancellationToken cancellation) throws InterruptedException {
        return authorize(call, cancellation, null, false, "");
    }

    public PermissionOutcome authorize(ToolCall call, CancellationToken cancellation,
                                       PermissionMode modeOverride, boolean dontAsk, String actor)
            throws InterruptedException {
        return authorize(call, cancellation, modeOverride, dontAsk, actor, context);
    }

    public PermissionOutcome authorize(ToolCall call, CancellationToken cancellation,
                                       PermissionMode modeOverride, boolean dontAsk, String actor,
                                       ToolContext executionContext) throws InterruptedException {
        Descriptor descriptor = describe(call);
        if (descriptor.category == ToolCategory.COMMAND && DangerousCommandPolicy.blocked(descriptor.target))
            return PermissionOutcome.deny("blacklist", "Dangerous command blocked by immutable blacklist");
        if (descriptor.pathTarget) {
            String error = sandboxError(descriptor.target, descriptor.mustExist, executionContext);
            if (error != null) return PermissionOutcome.deny("sandbox", error);
        }
        for (Layer layer : List.of(new Layer("local rule", localRules), new Layer("project rule", projectRules), new Layer("user rule", userRules))) {
            PermissionDecision decision = layer.rules.match(descriptor.friendlyName, descriptor.target, descriptor.pathTarget);
            if (decision == PermissionDecision.ALLOW) return PermissionOutcome.allow(layer.name);
            if (decision == PermissionDecision.DENY) return PermissionOutcome.deny(layer.name, "Denied by " + layer.name);
        }
        PermissionMode effectiveMode = modeOverride == null ? mode : modeOverride;
        PermissionDecision fallback = fallback(descriptor.category, effectiveMode);
        if (fallback == PermissionDecision.ALLOW) return PermissionOutcome.allow("mode " + effectiveMode.configName());
        if (dontAsk) return PermissionOutcome.allow("subagent dontAsk");
        if (approver == null) return PermissionOutcome.deny("approval", "Permission requires interactive approval");
        String prefix = actor == null || actor.isBlank() ? "" : "[SubAgent " + actor + "] ";
        PermissionRequest request = new PermissionRequest(call, prefix + descriptor.friendlyName,
                descriptor.target, prefix + "Mode " + effectiveMode.configName() + " requires confirmation");
        approvalObserver.accept(request, cancellation);
        ApprovalChoice choice = approver.approve(request, cancellation);
        if (choice == ApprovalChoice.DENY || cancellation.isCancelled())
            return PermissionOutcome.deny("user", cancellation.isCancelled() ? "Permission prompt cancelled" : "User denied this action");
        if (choice == ApprovalChoice.ALLOW_ALWAYS) persist(descriptor);
        return PermissionOutcome.allow(choice == ApprovalChoice.ALLOW_ALWAYS ? "permanent local rule" : "user once");
    }

    public static PermissionDecision fallback(ToolCategory category, PermissionMode mode) {
        if (category == ToolCategory.READ_ONLY) return PermissionDecision.ALLOW;
        if (mode == PermissionMode.BYPASS_PERMISSIONS) return PermissionDecision.ALLOW;
        if (mode == PermissionMode.ACCEPT_EDITS && category == ToolCategory.FILE_WRITE) return PermissionDecision.ALLOW;
        return PermissionDecision.ASK;
    }

    private Descriptor describe(ToolCall call) {
        return switch (call.name()) {
            case ModelToolCatalog.SEARCH -> new Descriptor(ModelToolCatalog.SEARCH, "", ToolCategory.READ_ONLY, false, false);
            case "read_file" -> new Descriptor("Read", call.arguments().path("path").asText(""), ToolCategory.READ_ONLY, true, true);
            case "write_file" -> new Descriptor("Write", call.arguments().path("path").asText(""), ToolCategory.FILE_WRITE, true, false);
            case "edit_file" -> new Descriptor("Edit", call.arguments().path("path").asText(""), ToolCategory.FILE_WRITE, true, true);
            case "glob" -> new Descriptor("Glob", globRoot(call.arguments().path("pattern").asText("")), ToolCategory.READ_ONLY, true, false);
            case "search_text" -> new Descriptor("Grep", call.arguments().path("path").asText(""), ToolCategory.READ_ONLY, true, false);
            case "bash" -> new Descriptor("Bash", call.arguments().path("command").asText(""), ToolCategory.COMMAND, false, false);
            default -> new Descriptor(call.name(), "", readOnlyTool.test(call.name()) ? ToolCategory.READ_ONLY : ToolCategory.COMMAND, false, false);
        };
    }

    private String sandboxError(String value, boolean mustExist, ToolContext executionContext) {
        try {
            String path = value == null || value.isBlank() ? "." : value;
            // Permission checks answer only "is this path inside the sandbox?".
            // Existence belongs to the tool itself: a missing read should become
            // NOT_FOUND, not a misleading PERMISSION_DENIED_SANDBOX result.
            executionContext.resolve(path, false);
            return null;
        } catch (Exception e) { return "Path sandbox denied access: " + safe(e.getMessage()); }
    }

    private synchronized void persist(Descriptor descriptor) {
        PermissionRule rule = new PermissionRule(PermissionDecision.ALLOW, descriptor.friendlyName, descriptor.target);
        List<PermissionRule> updated = new ArrayList<>(localRules.rules()); updated.add(rule);
        localRules = new PermissionRuleSet(List.copyOf(updated), localRules.defaultMode());
        try {
            Files.createDirectories(localConfig.getParent());
            StringBuilder yaml = new StringBuilder("# Local permissions generated by Star Code\nallow:\n");
            for (PermissionRule current : updated) if (current.decision() == PermissionDecision.ALLOW)
                yaml.append("  - ").append(quote(current.expression())).append('\n');
            List<PermissionRule> denied = updated.stream().filter(r -> r.decision() == PermissionDecision.DENY).toList();
            if (!denied.isEmpty()) {
                yaml.append("deny:\n");
                for (PermissionRule current : denied) yaml.append("  - ").append(quote(current.expression())).append('\n');
            }
            if (localRules.defaultMode() != null) yaml.append("defaultMode: ").append(localRules.defaultMode().configName()).append('\n');
            Files.writeString(localConfig, yaml.toString(), StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        } catch (IOException ignored) {}
    }

    private static PermissionMode firstMode(PermissionRuleSet... layers) {
        for (PermissionRuleSet layer : layers) if (layer.defaultMode() != null) return layer.defaultMode();
        return PermissionMode.DEFAULT;
    }
    private static String globRoot(String pattern) {
        if (pattern == null || pattern.isBlank()) return ".";
        int wildcard = pattern.indexOf('*'); int question = pattern.indexOf('?');
        int cut = wildcard < 0 ? question : question < 0 ? wildcard : Math.min(wildcard, question);
        String prefix = cut < 0 ? pattern : pattern.substring(0, cut);
        int slash = Math.max(prefix.lastIndexOf('/'), prefix.lastIndexOf('\\'));
        return slash < 0 ? "." : prefix.substring(0, slash);
    }
    private static String quote(String value) { return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""; }
    private static String safe(String message) { return message == null ? "invalid path" : message; }
    private record Descriptor(String friendlyName, String target, ToolCategory category, boolean pathTarget, boolean mustExist) {}
    private record Layer(String name, PermissionRuleSet rules) {}
}
