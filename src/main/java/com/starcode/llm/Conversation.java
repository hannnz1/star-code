package com.starcode.llm;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public final class Conversation {
    private final List<ChatMessage> committed = new ArrayList<>();
    private final Consumer<ChatMessage> onAppend;
    private final Consumer<List<ChatMessage>> onReplace;
    public Conversation() { this(null, null); }
    public Conversation(Consumer<ChatMessage> onAppend, Consumer<List<ChatMessage>> onReplace) {
        this.onAppend = onAppend; this.onReplace = onReplace;
    }
    public static Conversation fromMessages(List<ChatMessage> messages, Consumer<ChatMessage> onAppend,
                                            Consumer<List<ChatMessage>> onReplace) {
        Conversation value = new Conversation(onAppend, onReplace);
        synchronized (value) { value.committed.addAll(messages); }
        return value;
    }
    public synchronized List<ChatMessage> snapshot() { return List.copyOf(committed); }
    public void commit(String user, String assistant) {
        commit(user, List.of(), assistant);
    }
    public void commit(String user, List<ToolExchange> exchanges, String assistant) {
        List<ChatMessage> batch = new ArrayList<>();
        batch.add(new ChatMessage(ChatMessage.Role.USER, user));
        for (ToolExchange exchange : exchanges == null ? List.<ToolExchange>of() : exchanges) {
            batch.add(ChatMessage.assistant(exchange.assistant()));
            batch.add(ChatMessage.tool(exchange.results()));
        }
        if (!assistant.isBlank() || batch.size() == 1)
            batch.add(new ChatMessage(ChatMessage.Role.ASSISTANT, assistant));
        synchronized (this) { committed.addAll(batch); }
        if (onAppend != null) batch.forEach(onAppend);
    }
    public synchronized int size() { return committed.size(); }
    public void append(ChatMessage message) {
        synchronized (this) { committed.add(message); }
        if (onAppend != null) onAppend.accept(message);
    }
    public void replace(List<ChatMessage> messages) {
        List<ChatMessage> copy = List.copyOf(messages);
        synchronized (this) { committed.clear(); committed.addAll(copy); }
        if (onReplace != null) onReplace.accept(copy);
    }
}
