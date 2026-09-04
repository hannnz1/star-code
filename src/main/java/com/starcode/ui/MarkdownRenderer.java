package com.starcode.ui;

public final class MarkdownRenderer {
    private static final String RESET = "\u001b[0m";
    private static final String BOLD = "\u001b[1m";
    private static final String CYAN = "\u001b[36m";
    private static final String DIM = "\u001b[2m";
    private MarkdownRenderer() {}

    public static String render(String markdown) {
        StringBuilder out = new StringBuilder();
        boolean code = false;
        for (String line : markdown.split("\\R", -1)) {
            if (line.stripLeading().startsWith("```")) {
                code = !code;
                String language = line.stripLeading().substring(3).strip();
                if (code && !language.isEmpty()) out.append(DIM).append("┌─ ").append(language).append(RESET).append('\n');
                else if (!code) out.append(DIM).append("└─").append(RESET).append('\n');
                continue;
            }
            if (code) {
                out.append(DIM).append("│ ").append(RESET).append(line).append('\n');
                continue;
            }
            String rendered = line;
            if (rendered.startsWith("### ")) rendered = BOLD + rendered.substring(4) + RESET;
            else if (rendered.startsWith("## ")) rendered = BOLD + CYAN + rendered.substring(3) + RESET;
            else if (rendered.startsWith("# ")) rendered = BOLD + CYAN + rendered.substring(2) + RESET;
            else if (rendered.matches("^\\s*[-*+]\\s+.*")) rendered = rendered.replaceFirst("^(\\s*)[-*+]\\s+", "$1• ");
            rendered = rendered.replaceAll("\\*\\*([^*]+)\\*\\*", BOLD + "$1" + RESET);
            rendered = rendered.replaceAll("`([^`]+)`", CYAN + "$1" + RESET);
            out.append(rendered).append('\n');
        }
        return out.toString().stripTrailing();
    }
}
