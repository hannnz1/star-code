package com.starcode.context;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;

/** Offline validation only: never regenerates or alters a recorded model answer. */
public final class SummaryMarkerReplay {
    public static void main(String[] args) throws Exception {
        var json = new ObjectMapper();
        var report = json.createObjectNode().put("type", "offline_parser_replay")
                .put("original_batch", args[0]).put("end_to_end_benchmark", false);
        var rows = report.putArray("responses");
        try (var files = Files.walk(Path.of(args[0]))) {
            for (var file : files.filter(p -> p.getParent().getFileName().toString().equals("calls")
                    && p.toString().endsWith(".json")).sorted().toList()) {
                var call = json.readTree(file.toFile());
                var row = rows.addObject().put("file", Path.of(args[0]).relativize(file).toString());
                if (!call.hasNonNull("response_text")) { row.put("status", "NO_RESPONSE"); continue; }
                try {
                    String body = SummaryValidator.parse(call.path("response_text").asText());
                    row.put("status", "VALID").put("body_characters", body.length());
                } catch (Exception error) { row.put("status", "INVALID").put("exception", error.toString()); }
            }
        }
        json.writerWithDefaultPrettyPrinter().writeValue(Path.of(args[1]).toFile(), report);
    }
}
