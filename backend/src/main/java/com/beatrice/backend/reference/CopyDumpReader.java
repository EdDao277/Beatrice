package com.beatrice.backend.reference;

import java.io.*;
import java.util.*;
import java.util.function.BiConsumer;
import java.util.regex.Pattern;

/** A data reader, not a SQL interpreter. All DDL, functions and unrelated tables are ignored. */
public final class CopyDumpReader {
    private static final Pattern HEADER = Pattern.compile("^COPY ([a-zA-Z0-9_.]+) \\(([^)]+)\\) FROM stdin;$");
    private CopyDumpReader() {}
    public static void read(Reader source, Set<String> allowed, BiConsumer<String,Map<String,String>> consumer) throws IOException {
        var reader = new BufferedReader(source);
        String table=null; String[] columns=null; boolean selected=false;
        String line;
        while ((line=reader.readLine()) != null) {
            if (table == null) {
                var matcher=HEADER.matcher(line);
                if (!matcher.matches()) continue;
                table=matcher.group(1); columns=matcher.group(2).split(", ");
                selected=table.startsWith("public.") && allowed.contains(table.substring(7));
            } else if (line.equals("\\.")) { table=null; selected=false; }
            else if (selected) {
                String[] values=line.split("\t", -1);
                if (values.length != columns.length) throw new IOException("Invalid COPY column count in " + table);
                var row=new LinkedHashMap<String,String>();
                for (int n=0;n<columns.length;n++) row.put(columns[n], decode(values[n]));
                consumer.accept(table.substring(7), row);
            }
        }
        if (table != null) throw new IOException("Truncated COPY block");
    }
    static String decode(String value) throws IOException {
        if (value.equals("\\N")) return null;
        var out=new StringBuilder();
        for(int i=0;i<value.length();i++) {
            char c=value.charAt(i);
            if(c != '\\') { out.append(c); continue; }
            if(++i >= value.length()) throw new IOException("Truncated COPY escape");
            c=value.charAt(i);
            if(c >= '0' && c <= '7') {
                int code=c-'0'; int count=1;
                while(count<3 && i+1<value.length() && value.charAt(i+1)>='0' && value.charAt(i+1)<='7') {code=code*8+value.charAt(++i)-'0';count++;}
                out.append((char)code);
            } else out.append(switch(c) {case 'n' -> '\n'; case 't' -> '\t'; case 'r' -> '\r'; case 'b' -> '\b'; case 'f' -> '\f'; case 'v' -> '\u000b'; default -> c;});
        }
        return out.toString();
    }
}
