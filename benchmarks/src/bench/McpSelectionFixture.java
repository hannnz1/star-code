package bench;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

/** Deterministic synthetic service with argument validation and an append-only call log. */
public final class McpSelectionFixture {
 public static void main(String[] args)throws Exception {
  var fixture=Common.JSON.readTree(Path.of(args[0]).toFile());
  try(var input=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8))){String line;
   while((line=input.readLine())!=null){
    var request=Common.JSON.readTree(line);if(!request.has("id"))continue;
    var response=Common.JSON.createObjectNode().put("jsonrpc","2.0");response.set("id",request.get("id"));var result=response.putObject("result");
    switch(request.path("method").asText()){
     case "initialize" -> {result.put("protocolVersion",request.path("params").path("protocolVersion").asText());result.putObject("capabilities").putObject("tools");result.putObject("serverInfo").put("name","synthetic-service-selection").put("version","1");}
     case "tools/list" -> result.set("tools",fixture.path("tools"));
     case "tools/call" -> {
      var params=request.path("params");String name=params.path("name").asText();String entity=params.path("arguments").path("entity_id").asText();
      String answer=null;
      for(var task:fixture.path("tasks"))if(task.path("tool").asText().equals(name)&&task.path("entity_id").asText().equals(entity))answer=task.path("expected_result").asText();
      var log=Common.JSON.createObjectNode().put("name",name).put("success",answer!=null);log.set("arguments",params.path("arguments"));
      Files.writeString(Path.of(args[1]),log+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
      result.put("isError",answer==null).putArray("content").addObject().put("type","text").put("text",answer==null?"Unknown synthetic entity or incorrect tool":answer);
     }
     case "ping" -> {}
     default -> {response.remove("result");response.putObject("error").put("code",-32601).put("message","Unknown method");}
    }
    System.out.println(response);System.out.flush();
   }
  }
 }
}
