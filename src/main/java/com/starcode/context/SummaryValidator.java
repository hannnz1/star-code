package com.starcode.context;

import com.starcode.llm.LlmException;
import java.util.*;
import java.util.regex.*;

/** Checks structure, not factual truth. Unterminated summaries are never committed. */
final class SummaryValidator {
    static final int MAX_CHARACTERS = 28_000;
    static final List<String> SECTIONS = List.of("Primary Requests and Intent", "Key Technical Concepts",
            "Files and Code Sections", "Errors and Fixes", "Problem Solving", "All User Messages",
            "Pending Tasks", "Current Work", "Possible Next Step");
    private static final Pattern OPEN = Pattern.compile("<\\s*summary\\s*>", Pattern.CASE_INSENSITIVE);
    private static final Pattern CLOSE = Pattern.compile("<\\s*/\\s*summary\\s*>", Pattern.CASE_INSENSITIVE);

    static String parse(String text) throws LlmException {
        if (text == null || text.isBlank()) throw invalid("EMPTY_RESPONSE");
        // Inline code may quote the summary protocol itself; it is content, not a delimiter.
        String markers = maskInlineCode(text);
        Matcher open = OPEN.matcher(markers), close = CLOSE.matcher(markers);
        if (!open.find()) throw invalid("MISSING_OPEN_MARKER");
        int start = open.end();
        if (!close.find(start)) throw invalid("MISSING_CLOSE_MARKER_POSSIBLY_TRUNCATED");
        int end = close.start();
        if (open.find() || close.find()) throw invalid("MULTIPLE_SUMMARY_BLOCKS");
        String body = text.substring(start, end).strip();
        if (body.startsWith("```")) {
            int newline = body.indexOf('\n');
            if (newline < 0) throw invalid("EMPTY_SUMMARY");
            body = body.substring(newline + 1).strip();
            if (body.endsWith("```")) body = body.substring(0, body.length() - 3).strip();
        }
        if (body.isBlank()) throw invalid("EMPTY_SUMMARY");
        if (body.length() > MAX_CHARACTERS) throw invalid("SUMMARY_TOO_LARGE");
        int previousEnd = -1;
        List<Integer> starts = new ArrayList<>(), ends = new ArrayList<>();
        for (int i = 0; i < SECTIONS.size(); i++) {
            String title = String.join("\\h+", Arrays.stream(SECTIONS.get(i).split(" ")).map(Pattern::quote).toList());
            Pattern heading = Pattern.compile("(?im)^\\h*(?:#{1,6}\\h*)?(?:\\*\\*)?(?:" + (i + 1)
                    + "[.)]\\h*)?" + title + "(?:\\*\\*)?\\h*(?:\\([^\\r\\n]*\\))?\\h*:?(?:\\*\\*)?\\h*$");
            Matcher match = heading.matcher(body);
            if (!match.find()) throw invalid("MISSING_SECTION_" + (i + 1));
            if (match.start() <= previousEnd) throw invalid("SECTION_ORDER");
            starts.add(match.start()); ends.add(match.end()); previousEnd = match.end();
            if (match.find()) throw invalid("DUPLICATE_SECTION_" + (i + 1));
        }
        for (int i = 0; i < ends.size(); i++) {
            int stop = i + 1 < starts.size() ? starts.get(i + 1) : body.length();
            String content = body.substring(ends.get(i), stop).strip();
            if (content.isBlank() || content.matches("[\\s`*#:_-]+")) throw invalid("EMPTY_SECTION_" + (i + 1));
        }
        return body;
    }

    private static String maskInlineCode(String text) {
        char[] masked = text.toCharArray();
        for (int start = 0; start < text.length();) {
            if (text.charAt(start) != '`') { start++; continue; }
            int end = start;
            while (end < text.length() && text.charAt(end) == '`') end++;
            int width = end - start;
            int cursor = end;
            boolean matched = false;
            while (cursor < text.length() && text.charAt(cursor) != '\n' && text.charAt(cursor) != '\r') {
                if (text.charAt(cursor) != '`') { cursor++; continue; }
                int next = cursor;
                while (next < text.length() && text.charAt(next) == '`') next++;
                if (next - cursor == width) {
                    Arrays.fill(masked, start, next, ' ');
                    start = next;
                    matched = true;
                    break;
                }
                cursor = next;
            }
            if (!matched) start = end;
        }
        return new String(masked);
    }

    private static LlmException invalid(String code) {
        return new LlmException(LlmException.Kind.PROTOCOL, "Invalid compression summary: " + code);
    }
}
