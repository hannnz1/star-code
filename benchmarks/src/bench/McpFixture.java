package bench;
import java.io.*;import java.nio.file.*;import java.nio.charset.StandardCharsets;
public final class McpFixture{
 public static void main(String[] args)throws Exception{
  var tools=Common.JSON.readTree(Path.of(args[0]).toFile());
  try(var input=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8))){String line;while((line=input.readLine())!=null){
   var req=Common.JSON.readTree(line);if(!req.has("id"))continue;
   var res=Common.JSON.createObjectNode().put("jsonrpc","2.0");res.set("id",req.get("id"));var result=res.putObject("result");
   switch(req.path("method").asText()){
    case "initialize" -> {result.put("protocolVersion",req.path("params").path("protocolVersion").asText("2025-03-26"));result.putObject("capabilities").putObject("tools");result.putObject("serverInfo").put("name","frozen-schema-fixture").put("version","1");}
    case "tools/list" -> result.set("tools",tools);
    case "tools/call" -> result.putArray("content").addObject().put("type","text").put("text","Fixture has no side effects.");
    case "ping" -> {}
    default -> {res.remove("result");res.putObject("error").put("code",-32601).put("message","Method not found");}
   }
   System.out.println(Common.JSON.writeValueAsString(res));System.out.flush();
  }}
 }
}