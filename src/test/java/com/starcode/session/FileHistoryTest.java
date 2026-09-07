package com.starcode.session;

import com.starcode.llm.ChatMessage;
import com.starcode.tool.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class FileHistoryTest {
    @TempDir Path root;
    @Test void actualFileToolsRestorePreviousContentAndRemoveNewFileAfterReload() throws Exception {
        var session=SessionContext.create(root); var journal=new FileHistory(root,session.sessionDir());
        var context=new ToolContext(root,true,false); context.fileHistory(journal);
        Files.writeString(root.resolve("existing.txt"),"old");
        var history=List.of(new ChatMessage(ChatMessage.Role.USER,"original task"));
        int id=journal.begin("first change",history);
        var json=new ObjectMapper(); var tools=ToolRegistry.standard();
        assertTrue(tools.execute(new ToolCall("edit","edit_file",json.createObjectNode()
                .put("path","existing.txt").put("old_text","old").put("new_text","new")),context).success());
        assertTrue(tools.execute(new ToolCall("write","write_file",json.createObjectNode()
                .put("path","created.txt").put("content","created")),context).success());
        var resumed=new FileHistory(root,session.sessionDir());
        var restored=resumed.rewind(id,true);
        assertEquals(history,restored.messages()); assertEquals(2,restored.paths().size());
        assertEquals("old",Files.readString(root.resolve("existing.txt")));
        assertFalse(Files.exists(root.resolve("created.txt")));
        assertEquals(history,new FileHistory(root,session.sessionDir()).rewind(id,false).messages());
        assertTrue(new FileHistory(root,session.sessionDir()).begin("next",history)>id);
    }
    @Test void externalEditsRejectEntireRewindBeforeAnyFileChanges() throws Exception {
        var session=SessionContext.create(root); var journal=new FileHistory(root,session.sessionDir());
        int id=journal.begin("changes",List.of());
        journal.write(root.resolve("a"),"a1".getBytes()); journal.write(root.resolve("b"),"b1".getBytes());
        Files.writeString(root.resolve("a"),"manual edit");
        assertThrows(java.io.IOException.class,()->journal.rewind(id,true));
        assertEquals("manual edit",Files.readString(root.resolve("a")));
        assertEquals("b1",Files.readString(root.resolve("b")));
    }
    @Test void multipleCheckpointsAndConversationOnlyDoNotLoseFileHistory() throws Exception {
        var session=SessionContext.create(root); var journal=new FileHistory(root,session.sessionDir());
        Files.writeString(root.resolve("a"),"zero");
        int first=journal.begin("one",List.of()); journal.write(root.resolve("a"),"one".getBytes());
        int second=journal.begin("two",List.of(new ChatMessage(ChatMessage.Role.USER,"one")));
        journal.write(root.resolve("a"),"two".getBytes());
        journal.rewind(first,false); assertEquals("two",Files.readString(root.resolve("a")));
        journal.rewind(second,true); assertEquals("one",Files.readString(root.resolve("a")));
        journal.rewind(first,true); assertEquals("zero",Files.readString(root.resolve("a")));
    }
    @Test void worktreeContextsShareJournalAndMetadataCannotBeRewritten() throws Exception {
        var session=SessionContext.create(root); var journal=new FileHistory(root,session.sessionDir());
        var context=new ToolContext(root,true,false); context.fileHistory(journal);
        Path tree=Files.createDirectories(root.resolve(".mewcode/worktrees/team-example"));
        int id=journal.begin("child",List.of()); context.withCwd(tree).writeFile(tree.resolve("new"),"child");
        journal.rewind(id,true); assertFalse(Files.exists(tree.resolve("new")));
        assertThrows(java.io.IOException.class,()->journal.write(root.resolve(".git/config"),new byte[0]));
        assertThrows(java.io.IOException.class,()->journal.write(tree.resolve(".git"),new byte[0]));
        assertThrows(java.io.IOException.class,()->journal.write(tree.resolve(".mewcode/config"),new byte[0]));
        assertThrows(java.io.IOException.class,()->journal.write(session.sessionDir().resolve("file-history.json"),new byte[0]));
    }
}
