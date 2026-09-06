package com.beatrice.backend.reference;

import java.io.StringReader;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CopyDumpReaderTest {
    @Test void readsOnlyAllowlistedCopyDataWithoutExecutingSql() throws Exception {
        var rows = new ArrayList<Map<String,String>>();
        CopyDumpReader.read(new StringReader("""
            DROP TABLE teams;
            COPY auth.users (secret) FROM stdin;
            private
            \\.
            COPY public.champion_metadata (champion_id, notes, roles) FROM stdin;
            Swain\tline\\nnext\\tcolumn\\\\slash\t\\N
            \\.
            """), Set.of("champion_metadata"), (table, row) -> rows.add(row));
        assertEquals(1, rows.size());
        assertEquals("line\nnext\tcolumn\\slash", rows.getFirst().get("notes"));
        assertNull(rows.getFirst().get("roles"));
    }
    @Test void rejectsTruncatedCopyBlocks() {
        assertThrows(java.io.IOException.class, () -> CopyDumpReader.read(new StringReader(
            "COPY public.champion_metadata (champion_id) FROM stdin;\nSwain\n"), Set.of("champion_metadata"), (t,r) -> {}));
    }
}
