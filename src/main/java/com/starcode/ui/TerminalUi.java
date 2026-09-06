package com.starcode.ui;

import com.starcode.config.ProviderConfig;
import com.starcode.tool.*;
import com.starcode.agent.AgentMode;
import com.starcode.agent.CancellationToken;
import com.starcode.llm.TokenUsage;
import com.starcode.permission.*;
import org.jline.keymap.KeyMap;
import org.jline.reader.*;
import org.jline.reader.impl.DefaultParser;
import org.jline.terminal.Terminal;
import org.jline.terminal.TerminalBuilder;
import org.jline.terminal.Attributes;
import org.jline.utils.InfoCmp;
import org.jline.utils.NonBlockingReader;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import com.starcode.session.SessionInfo;
import java.util.concurrent.*;
import com.starcode.command.CommandRegistry;
import com.starcode.command.CommandSpec;
import com.starcode.command.CommandCompletion;

public final class TerminalUi implements AutoCloseable, PermissionApprover {
    private static final String RESET = "\u001b[0m";
    private static final String BOLD = "\u001b[1m";
    private static final String CYAN = "\u001b[36m";
    private static final String RED = "\u001b[31m";
    private static final String DIM = "\u001b[2m";
    private static final String INPUT_PROMPT = "❯";
    private final Terminal terminal;
    private final Attributes initialAttributes;
    private final LineReader reader;
    private volatile ApprovalPending pendingApproval;
    private volatile PermissionManager permissions;
    private volatile CommandRegistry commands;
    private volatile String commandPrefix;
    private volatile int commandSelection;

    public TerminalUi() throws IOException {
        terminal = TerminalBuilder.builder().system(true).build();
        initialAttributes = new Attributes(terminal.getAttributes());
        DefaultParser parser = new DefaultParser().escapeChars(new char[0]);
        reader = LineReaderBuilder.builder().terminal(terminal).parser(parser)
                .completer(this::completeCommands).build();
        reader.setOpt(LineReader.Option.DISABLE_EVENT_EXPANSION);
        reader.setOpt(LineReader.Option.BRACKETED_PASTE);
        reader.setOpt(LineReader.Option.ERASE_LINE_ON_FINISH);
        reader.setOpt(LineReader.Option.AUTO_LIST);
        reader.setOpt(LineReader.Option.AUTO_MENU_LIST);
        reader.setOpt(LineReader.Option.CASE_INSENSITIVE);
        reader.setVariable(LineReader.MENU_LIST_MAX, 8);
        reader.setVariable(LineReader.SECONDARY_PROMPT_PATTERN, "  ");
        installMultilineWidget();
        installPermissionModeWidget();
        installCommandCompletionWidgets();
    }

    public ProviderConfig select(List<ProviderConfig> providers) {
        if (providers.size() == 1) return providers.getFirst();
        int selected = 0;
        var previous = terminal.getAttributes();
        try {
            terminal.enterRawMode();
            terminal.puts(InfoCmp.Capability.cursor_invisible);
            drawProviders(providers, selected, false);
            NonBlockingReader input = terminal.reader();
            while (true) {
                int key = input.read();
                if (key == 3 || key == 4) return null;
                if (key == 13 || key == 10) {
                    drawProviders(providers, selected, true);
                    return providers.get(selected);
                }
                if (key == 27) {
                    int next = input.read(80);
                    if (next < 0) return null;
                    if (next == '[' || next == 'O') {
                        int arrow = input.read(80);
                        if (arrow == 'A') selected = (selected - 1 + providers.size()) % providers.size();
                        if (arrow == 'B') selected = (selected + 1) % providers.size();
                        drawProviders(providers, selected, false);
                    }
                }
            }
        } catch (IOException e) {
            error("Cannot read provider selection: " + e.getMessage());
            return null;
        } finally {
            terminal.setAttributes(previous);
            terminal.puts(InfoCmp.Capability.cursor_visible);
            terminal.flush();
        }
    }

    public SessionInfo selectSession(List<SessionInfo> sessions) {
        if (sessions.isEmpty()) { system("No resumable sessions found."); return null; }
        int selected = 0; StringBuilder query = new StringBuilder();
        List<SessionInfo> filtered = new ArrayList<>(sessions); var previous = terminal.getAttributes();
        try {
            terminal.enterRawMode(); terminal.puts(InfoCmp.Capability.cursor_invisible);
            drawSessions(filtered, selected, query.toString());
            NonBlockingReader input = terminal.reader();
            while (true) {
                int key = input.read();
                if (key == 3) return null;
                if ((key == 13 || key == 10) && !filtered.isEmpty()) return filtered.get(selected);
                if (key == 27) {
                    int next = input.read(80);
                    if (next < 0) return null;
                    if (next == '[' || next == 'O') {
                        int arrow = input.read(80);
                        if (!filtered.isEmpty() && arrow == 'A') selected = (selected - 1 + filtered.size()) % filtered.size();
                        if (!filtered.isEmpty() && arrow == 'B') selected = (selected + 1) % filtered.size();
                        drawSessions(filtered, selected, query.toString());
                    }
                    continue;
                }
                if (key == 127 || key == 8) {
                    if (!query.isEmpty()) query.deleteCharAt(query.length() - 1);
                } else if (key >= 32 && Character.isValidCodePoint(key)) query.appendCodePoint(key);
                else continue;
                String needle = query.toString().toLowerCase(java.util.Locale.ROOT);
                filtered = sessions.stream()
                        .filter(value -> value.title().toLowerCase(java.util.Locale.ROOT).contains(needle)).toList();
                selected = 0; drawSessions(filtered, selected, query.toString());
            }
        } catch (IOException error) { this.error("Cannot select session: " + error.getMessage()); return null; }
        finally { terminal.setAttributes(previous); terminal.puts(InfoCmp.Capability.cursor_visible); terminal.flush(); }
    }

    private synchronized void drawSessions(List<SessionInfo> sessions, int selected, String query) {
        terminal.writer().print("\u001b[H\u001b[2J");
        println(CYAN + "Resume a session" + RESET + DIM + "  (type to filter, Up/Down, Enter, Esc)" + RESET);
        if (!query.isEmpty()) println(DIM + "Filter: " + query + RESET);
        if (sessions.isEmpty()) println(DIM + "  No matching sessions" + RESET);
        for (int i = 0; i < sessions.size(); i++) {
            SessionInfo info = sessions.get(i); String marker = i == selected ? CYAN + "  > " : "    ";
            println(marker + info.title() + RESET + DIM + "  · " + relative(info.modifiedAt()) + " · "
                    + info.model() + " · " + info.size() + " bytes" + RESET);
        }
    }
    private static String relative(java.time.Instant instant) {
        long seconds = Math.max(0, java.time.Duration.between(instant, java.time.Instant.now()).toSeconds());
        if (seconds < 60) return seconds + "s ago"; if (seconds < 3600) return seconds / 60 + "m ago";
        if (seconds < 86400) return seconds / 3600 + "h ago"; return seconds / 86400 + "d ago";
    }

    private void drawProviders(List<ProviderConfig> providers, int selected, boolean accepted) {
        if (!accepted) terminal.writer().print("\u001b[H\u001b[2J");
        println(CYAN + "Select a provider" + RESET + DIM + "  (↑/↓ choose, Enter confirm, Esc cancel)" + RESET);
        for (int i = 0; i < providers.size(); i++) {
            ProviderConfig p = providers.get(i);
            String marker = i == selected ? CYAN + "❯ " + RESET : "  ";
            String style = i == selected ? BOLD : "";
            println(marker + style + p.name() + RESET + "  " + DIM + p.protocol() + " / " + p.model() + RESET);
        }
        if (accepted) println("");
    }

    public void banner(ProviderConfig provider, Path cwd) {
        println(" /\\_/\\    " + CYAN + "Star Code v0.1.0" + RESET);
        println("( o.o )   " + provider.name() + " / " + provider.model());
        println(" > ^ <    " + cwd.toAbsolutePath().normalize());
        println(DIM + "Ready — workspace tools are protected by the permission pipeline. Type /help for commands." + RESET);
        println(DIM + "Enter sends · Ctrl+J inserts a newline · Shift+Tab changes permission mode." + RESET);
        println("");
    }

    public void bindPermissions(PermissionManager value) {
        permissions = value;
        mode(value.mode());
    }

    public void bindCommands(CommandRegistry value) { commands = value; }

    private void completeCommands(LineReader ignored, ParsedLine line, List<Candidate> candidates) {
        CommandRegistry registry = commands;
        String input = line.line();
        if (registry == null || input.indexOf('\n') >= 0 || !input.startsWith("/")) return;
        for (CommandSpec command : registry.complete(input)) {
            candidates.add(new Candidate(command.name(), command.name(), null, command.description(),
                    null, command.name(), true));
        }
    }

    public String readMessage() {
        return readMessage(null);
    }

    public String readMessage(String initial) {
        try {
            String first = initial == null ? reader.readLine(INPUT_PROMPT) : reader.readLine(INPUT_PROMPT, null, initial);
            if ("/".equals(first) && commands != null) {
                SlashSelection selection = selectSlashCommand();
                if (selection.continueEditing()) return reader.readLine(INPUT_PROMPT, null, selection.text());
                return selection.text();
            }
            if (!"/multi".equals(first.strip())) return first;
            return readMultiline();
        }
        catch (UserInterruptException e) {
            // Ctrl+C cancels the current edit. It must not terminate the whole
            // application, especially when the key that cancelled an agent run
            // is still observed by JLine after raw mode is restored.
            system("Input cancelled. Use /exit to quit.");
            return "";
        }
        catch (EndOfFileException e) { return null; }
    }

    private String readMultiline() {
        println(DIM + "Multiline mode — enter /send on its own line to submit, /cancel to discard." + RESET);
        StringBuilder message = new StringBuilder();
        while (true) {
            String line = reader.readLine(DIM + "│ " + RESET);
            if ("/cancel".equals(line.strip())) {
                println(DIM + "Multiline input cancelled." + RESET);
                return "";
            }
            if ("/send".equals(line.strip())) return message.toString().stripTrailing();
            if (!message.isEmpty()) message.append('\n');
            message.append(line);
        }
    }

    public synchronized void user(String text) { println(CYAN + "You" + RESET + "  " + text); }
    public synchronized void assistantStart() { print("\n" + CYAN + "Star" + RESET + " "); }
    public synchronized void delta(String text) { print(text); }
    public synchronized void assistantDone(String raw, double seconds) {
        // A scrolling terminal cannot reliably erase wrapped/scrollback lines after a
        // long stream. Keep the streamed answer as the canonical display to avoid
        // duplicating it; full in-place Markdown replacement requires a frame-based TUI.
        println(RESET + "\n" + DIM + "Completed in %.1fs".formatted(seconds) + RESET);
        println("");
    }
    public synchronized void waiting(long seconds) {
        terminal.writer().print("\r" + DIM + "Imagining… (" + seconds + "s)" + RESET);
        terminal.flush();
    }
    public synchronized void clearWaiting() { terminal.writer().print("\r\u001b[2K"); terminal.flush(); }
    public synchronized void error(String message) { println(RED + "✖ " + message + RESET); }
    public synchronized void system(String message) { println(DIM + message + RESET); }
    /** Print an asynchronous notification without corrupting the active JLine input buffer. */
    public synchronized void notification(String message) {
        reader.printAbove(DIM + message + RESET);
    }
    public synchronized void clearScreen() {
        terminal.writer().print("\u001b[H\u001b[2J"); terminal.flush();
    }
    public synchronized void iteration(int number) { println(DIM + "Iteration " + number + RESET); }
    public synchronized void usage(TokenUsage usage) {
        String cache = usage.cacheWriteTokens() == 0 && usage.cacheReadTokens() == 0 ? ""
                : " / cache " + usage.cacheWriteTokens() + " write, " + usage.cacheReadTokens() + " read";
        println(DIM + "Tokens: " + usage.inputTokens() + " in / " + usage.outputTokens() + " out" + cache + RESET);
    }
    public synchronized void mode(AgentMode mode) {
        println(CYAN + "Mode: " + mode.name().toLowerCase() + RESET);
    }
    public synchronized void mode(PermissionMode mode) {
        println(CYAN + "Permission mode: " + mode.configName() + RESET);
    }
    public AutoCloseable onInterrupt(Runnable callback) {
        var previous = terminal.handle(Terminal.Signal.INT, signal -> callback.run());
        return () -> terminal.handle(Terminal.Signal.INT, previous);
    }
    public <T> T awaitAgent(CompletableFuture<T> future, CancellationToken cancellation)
            throws InterruptedException, ExecutionException {
        var previous = terminal.getAttributes();
        try {
            terminal.enterRawMode();
            NonBlockingReader input = terminal.reader();
            while (!future.isDone()) {
                int key;
                try { key = input.read(100); }
                catch (IOException e) { key = -1; }
                ApprovalPending approval = pendingApproval;
                if (approval != null) handleApprovalKey(approval, key, input, cancellation);
                else if (key == 3 || key == 27) {
                    cancellation.cancel();
                    println(DIM + "Cancelling agent…" + RESET);
                }
            }
            return future.get();
        } finally {
            terminal.setAttributes(previous); terminal.flush();
        }
    }
    @Override
    public ApprovalChoice approve(PermissionRequest request, CancellationToken cancellation) throws InterruptedException {
        ApprovalPending pending = new ApprovalPending(request);
        if (pendingApproval != null) return ApprovalChoice.DENY;
        pendingApproval = pending;
        drawApproval(pending);
        try { return pending.result.get(); }
        catch (ExecutionException e) { return ApprovalChoice.DENY; }
        finally { pendingApproval = null; }
    }
    public synchronized void toolCall(ToolCall call) {
        String key = switch (call.name()) {
            case "read_file", "write_file", "edit_file" -> call.arguments().path("path").asText();
            case "bash" -> call.arguments().path("command").asText();
            case "glob" -> call.arguments().path("pattern").asText();
            case "search_text" -> call.arguments().path("query").asText();
            default -> call.arguments().toString();
        };
        if (key.length() > 100) key = key.substring(0, 100) + "…";
        println(CYAN + "● " + displayName(call.name()) + RESET + "(" + key + ")");
    }
    public synchronized void toolResult(ToolResult result) {
        String summary = result.success() ? result.output() : result.errorCode() + ": " + result.errorMessage();
        summary = summary == null ? "" : summary.replace('\n', ' ');
        if (summary.length() > 180) summary = summary.substring(0, 180) + "…";
        println((result.success() ? DIM : RED) + "  " + (result.success() ? "✓ " : "✖ ") + summary + RESET);
    }
    public synchronized void println(String value) { terminal.writer().println(value); terminal.flush(); }
    public synchronized void print(String value) { terminal.writer().print(value); terminal.flush(); }

    private void installMultilineWidget() {
        reader.getWidgets().put("star-newline", () -> {
            return insertNewline();
        });
        reader.getWidgets().put("star-submit-or-paste-newline", () -> {
            try {
                NonBlockingReader input = terminal.reader();
                int queued = input.peek(60);
                if (queued >= 0) {
                    // Windows terminals may paste CRLF without bracketed-paste markers.
                    // A physical Enter can also arrive as CRLF, so CRLF alone must
                    // submit. Treat it as pasted multiline input only when another
                    // character is already queued after the LF.
                    if (queued == '\n') {
                        input.read();
                        if (input.peek(10) < 32) {
                            acceptInputLine();
                            return true;
                        }
                        return insertNewline();
                    }
                    if (queued >= 32) return insertNewline();
                    acceptInputLine();
                    return true;
                }
            } catch (IOException ignored) {
                // Fall through to normal submission if look-ahead is unavailable.
            }
            acceptInputLine();
            return true;
        });
        KeyMap<Binding> keys = reader.getKeyMaps().get(LineReader.MAIN);
        Reference newline = new Reference("star-newline");
        keys.bind(new Reference("star-submit-or-paste-newline"), "\r");
        keys.bind(newline, "\n", "\033\r", "\033\n");
    }

    private void installPermissionModeWidget() {
        reader.getWidgets().put("star-cycle-permission", () -> {
            PermissionManager manager = permissions;
            if (manager == null) return true;
            PermissionMode value = manager.cycleMode();
            terminal.writer().println(); mode(value);
            reader.callWidget(LineReader.REDRAW_LINE); reader.callWidget(LineReader.REDISPLAY);
            return true;
        });
        reader.getKeyMaps().get(LineReader.MAIN).bind(new Reference("star-cycle-permission"), "\033[Z");
    }

    private void installCommandCompletionWidgets() {
        KeyMap<Binding> keys = reader.getKeyMaps().get(LineReader.MAIN);
        // Space must use the same refresh path as command-name characters so
        // zero-argument commands visibly transition to the no-match state.
        String characters = "/abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ";
        for (int i = 0; i < characters.length(); i++) {
            char value = characters.charAt(i); String widget = "star-command-char-" + (int) value;
            reader.getWidgets().put(widget, () -> {
                reader.getBuffer().write(value);
                refreshCommandChoices();
                return true;
            });
            keys.bind(new Reference(widget), String.valueOf(value));
        }
        reader.getWidgets().put("star-command-backspace", () -> {
            reader.callWidget(LineReader.BACKWARD_DELETE_CHAR); refreshCommandChoices(); return true;
        });
        keys.bind(new Reference("star-command-backspace"), "\177", "\b");
        reader.getWidgets().put("star-command-down", () -> commandMenuMove(false));
        reader.getWidgets().put("star-command-up", () -> commandMenuMove(true));
        keys.bind(new Reference("star-command-down"), "\033[B", "\033OB");
        keys.bind(new Reference("star-command-up"), "\033[A", "\033OA");
        reader.getWidgets().put("star-command-tab", () -> {
            if (!commandInput()) { reader.callWidget(LineReader.COMPLETE_WORD); return true; }
            if (!selectCommandCandidate()) {
                reader.callWidget(LineReader.REDISPLAY); return true;
            }
            acceptInputLine();
            return true;
        });
        keys.bind(new Reference("star-command-tab"), "\t");
        reader.getWidgets().put("star-command-escape", () -> {
            commandPrefix = null; commandSelection = 0;
            reader.callWidget(LineReader.REDRAW_LINE); reader.callWidget(LineReader.REDISPLAY); return true;
        });
        keys.bind(new Reference("star-command-escape"), "\033");
        reader.getWidgets().put("star-command-open", () -> {
            if (reader.getBuffer().length() == 0) {
                reader.getBuffer().write('/'); reader.callWidget(LineReader.ACCEPT_LINE); return true;
            }
            reader.getBuffer().write('/'); return true;
        });
        keys.bind(new Reference("star-command-open"), "/");
    }

    private SlashSelection selectSlashCommand() {
        StringBuilder prefix = new StringBuilder("/");
        CommandCompletion completion = new CommandCompletion();
        var previous = terminal.getAttributes();
        try {
            terminal.enterRawMode(); terminal.puts(InfoCmp.Capability.cursor_invisible);
            NonBlockingReader input = terminal.reader();
            int opening = input.peek(20);
            while (opening == '\r' || opening == '\n') {
                input.read(); opening = input.peek(5);
            }
            while (true) {
                completion.update(prefix.toString(), commands);
                List<CommandSpec> matches = completion.items();
                drawCommandMenu(prefix.toString(), matches, completion.cursor());
                int key = input.read();
                if (key == 3) return new SlashSelection("/exit", false);
                if (key == 13 || key == 10) return new SlashSelection(
                        completion.selected() == null ? prefix.toString() : completion.selected().name(), false);
                if (key == 9) return new SlashSelection(
                        completion.selected() == null ? "" : completion.selected().name(), false);
                if (key == 27) {
                    int next = input.read(80);
                    if (next < 0) return new SlashSelection(prefix.toString(), true);
                    if (next == '[' || next == 'O') {
                        int arrow = input.read(80);
                        if (arrow == 'A') completion.moveUp();
                        if (arrow == 'B') completion.moveDown();
                        if (arrow == '3') {
                            // Windows terminals encode Delete as ESC [ 3 ~. In
                            // this end-positioned selector it behaves like
                            // Backspace, which is what users expect when
                            // removing a trailing space or argument character.
                            if (input.peek(20) == '~') input.read();
                            if (prefix.length() > 1) prefix.deleteCharAt(prefix.length() - 1);
                        }
                    } else return new SlashSelection(prefix.toString(), true);
                    continue;
                }
                if (key == 127 || key == 8) {
                    if (prefix.length() > 1) prefix.deleteCharAt(prefix.length() - 1);
                    else return new SlashSelection("", true);
                } else if (key >= 32 && key < 127) {
                    prefix.append((char) key);
                }
            }
        } catch (IOException error) {
            this.error("Command menu failed: " + error.getMessage()); return new SlashSelection(prefix.toString(), true);
        } finally {
            terminal.setAttributes(previous); terminal.puts(InfoCmp.Capability.cursor_visible); terminal.flush();
        }
    }

    private synchronized void drawCommandMenu(String prefix, List<CommandSpec> matches, int selected) {
        terminal.writer().print("\u001b[H\u001b[2J");
        println(CYAN + "Slash commands" + RESET + DIM + "  (type to filter, Up/Down, Tab/Enter, Esc)" + RESET);
        println(DIM + "Input: " + prefix + RESET);
        if (matches.isEmpty()) { println(DIM + "  No matching commands" + RESET); return; }
        int max = 8, start = Math.max(0, Math.min(selected - max + 1, Math.max(0, matches.size() - max)));
        int width = matches.stream().mapToInt(command -> command.name().length()).max().orElse(0);
        for (int i = start; i < Math.min(matches.size(), start + max); i++) {
            CommandSpec command = matches.get(i); String marker = i == selected ? CYAN + "  > " : "    ";
            println(marker + String.format("%-" + width + "s", command.name()) + RESET + DIM
                    + "  " + command.description() + RESET);
        }
    }

    private record SlashSelection(String text, boolean continueEditing) {}

    private boolean commandMenuMove(boolean reverse) {
        if (!commandInput()) {
            reader.callWidget(reverse ? LineReader.UP_LINE_OR_HISTORY : LineReader.DOWN_LINE_OR_HISTORY); return true;
        }
        CommandRegistry registry = commands;
        String prefix = commandPrefix == null ? reader.getBuffer().toString() : commandPrefix;
        List<CommandSpec> matches = registry == null ? List.of() : registry.complete(prefix);
        if (matches.isEmpty()) return true;
        commandSelection = Math.floorMod(commandSelection + (reverse ? -1 : 1), matches.size());
        reader.getBuffer().clear(); reader.getBuffer().write(matches.get(commandSelection).name());
        reader.callWidget(LineReader.REDISPLAY); return true;
    }

    private void refreshCommandChoices() {
        if (commandInput()) {
            commandPrefix = reader.getBuffer().toString(); commandSelection = 0;
            reader.callWidget(LineReader.COMPLETE_WORD);
        } else {
            commandPrefix = null; commandSelection = 0; reader.callWidget(LineReader.REDISPLAY);
        }
    }

    private boolean selectCommandCandidate() {
        CommandRegistry registry = commands;
        String current = reader.getBuffer().toString();
        if (registry == null) return false;
        if (registry.resolve(current).isPresent()) return true;
        String prefix = commandPrefix == null ? current : commandPrefix;
        List<CommandSpec> matches = registry.complete(prefix);
        if (matches.isEmpty()) return false;
        CommandSpec selected = matches.get(Math.min(commandSelection, matches.size() - 1));
        reader.getBuffer().clear(); reader.getBuffer().write(selected.name()); return true;
    }

    private boolean commandInput() {
        String value = reader.getBuffer().toString();
        return value.startsWith("/") && value.indexOf('\n') < 0;
    }

    private void handleApprovalKey(ApprovalPending pending, int key, NonBlockingReader input,
                                   CancellationToken cancellation) {
        if (pending.result.isDone()) return;
        try {
            if (key == '1' || key == '2' || key == '3' || key == '4') {
                pending.selected = key - '1'; completeApproval(pending); return;
            }
            if (key == 13 || key == 10) { completeApproval(pending); return; }
            if (key == 3) { cancellation.cancel(); pending.result.complete(ApprovalChoice.DENY); return; }
            if (key == 27) {
                int next = input.read(80);
                if (next == '[' || next == 'O') {
                    int arrow = input.read(80);
                    if (arrow == 'A') pending.selected = (pending.selected + 3) % 4;
                    if (arrow == 'B') pending.selected = (pending.selected + 1) % 4;
                    drawApproval(pending);
                } else {
                    cancellation.cancel(); pending.result.complete(ApprovalChoice.DENY);
                }
            }
        } catch (IOException ignored) {}
    }

    private void completeApproval(ApprovalPending pending) {
        if (pending.result.isDone()) return;
        ApprovalChoice choice = switch (pending.selected) {
            case 1 -> ApprovalChoice.ALLOW_ALWAYS;
            case 2 -> ApprovalChoice.DENY;
            case 3 -> ApprovalChoice.ALLOW_SESSION;
            default -> ApprovalChoice.ALLOW_ONCE;
        };
        if (pending.result.complete(choice))
            println(DIM + "Permission: " + choice.name().toLowerCase().replace('_', ' ') + RESET);
    }

    private synchronized void drawApproval(ApprovalPending pending) {
        PermissionRequest request = pending.request;
        println(""); println(CYAN + "Permission required" + RESET);
        println("  Tool: " + request.friendlyName());
        println("  Target: " + request.target());
        println("  Reason: " + request.reason());
        String[] options = {"1. Allow once", "2. Always allow this rule", "3. Deny once",
                "4. Allow for this session (same tool/path, or exact command/arguments)"};
        for (int i = 0; i < options.length; i++) println((i == pending.selected ? CYAN + "  > " : "    ") + options[i] + RESET);
        println(DIM + "Use Up/Down and Enter, or press 1/2/3/4. Esc/Ctrl+C cancels." + RESET);
    }

    private static final class ApprovalPending {
        final PermissionRequest request;
        final CompletableFuture<ApprovalChoice> result = new CompletableFuture<>();
        volatile int selected;
        ApprovalPending(PermissionRequest request) { this.request = request; }
    }

    private boolean insertNewline() {
        // Some Windows terminal/JLine combinations encode both Enter and
        // Ctrl+J as LF. Slash commands are always single-line commands, so LF
        // must submit them; this keeps /exit, /resume, /plan, etc. usable while
        // Ctrl+J continues to insert newlines in ordinary prompts.
        if (reader.getBuffer().toString().stripLeading().startsWith("/")) {
            acceptInputLine();
            return true;
        }
        reader.getBuffer().write('\n');
        reader.callWidget(LineReader.REDRAW_LINE);
        reader.callWidget(LineReader.REDISPLAY);
        return true;
    }

    private void acceptInputLine() {
        if (commandInput()) selectCommandCandidate();
        commandPrefix = null; commandSelection = 0;
        reader.callWidget(LineReader.ACCEPT_LINE);
    }

    private static String displayName(String name) {
        return switch (name) {
            case "read_file" -> "Read"; case "write_file" -> "Write"; case "edit_file" -> "Edit";
            case "bash" -> "Bash"; case "glob" -> "Glob"; case "search_text" -> "Search"; default -> name;
        };
    }

    public synchronized void restoreTerminal() {
        try {
            terminal.setAttributes(initialAttributes);
            terminal.puts(InfoCmp.Capability.cursor_visible);
            terminal.writer().print(RESET);
            terminal.flush();
        } catch (Exception ignored) { }
    }

    @Override public void close() throws IOException {
        restoreTerminal();
        terminal.close();
    }
}
