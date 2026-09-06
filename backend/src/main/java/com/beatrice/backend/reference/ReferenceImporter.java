package com.beatrice.backend.reference;

import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.GZIPInputStream;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;
import com.beatrice.backend.champion.ChampionCatalog;

@Service
public class ReferenceImporter {
    public record Report(long id, Map<String,Integer> imported, Map<String,Integer> rejected) {}
    private static final Set<String> TABLES=Set.of("champion_metadata","champion_role_stats","champion_synergy_stats","champion_matchup_stats","team_comp_signature_stats");
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final ChampionCatalog catalog;
    public ReferenceImporter(JdbcTemplate jdbc, ObjectMapper mapper, ChampionCatalog catalog) {this.jdbc=jdbc;this.mapper=mapper;this.catalog=catalog;}

    @Transactional(rollbackFor=Exception.class)
    public Report importFile(Path path) throws Exception {
        var digest=MessageDigest.getInstance("SHA-256");
        try(var input=new DigestInputStream(Files.newInputStream(path),digest)) {input.transferTo(OutputStream.nullOutputStream());}
        String sha=HexFormat.of().formatHex(digest.digest());
        // Serialize imports so identical concurrent attempts cannot create partial duplicate batches.
        jdbc.execute("select pg_advisory_xact_lock(70420260905)");
        var existing=jdbc.queryForList("select report::text from reference_imports where sha256=?",String.class,sha);
        if(!existing.isEmpty()) return mapper.readValue(existing.getFirst(),Report.class);
        long id=jdbc.queryForObject("insert into reference_imports(sha256,filename) values (?,?) returning id",Long.class,sha,path.getFileName().toString());
        var aliases=new HashMap<String,String>();
        for(var c:catalog.catalog().champions()) {aliases.put(key(c.id()),c.id());aliases.put(key(c.name()),c.id());}
        var imported=new TreeMap<String,Integer>(); var rejected=new TreeMap<String,Integer>();
        var batch=new ArrayList<Object[]>();
        try(var reader=new InputStreamReader(new GZIPInputStream(Files.newInputStream(path)),java.nio.charset.StandardCharsets.UTF_8)) {
            CopyDumpReader.read(reader,TABLES,(table,row) -> {
                try {
                    if(table.equals("champion_metadata")) {
                        String champion=canonical(row.get("champion_id"),aliases);
                        String rawRoles=row.get("roles");
                        List<String> roles=rawRoles==null || rawRoles.equals("{}") ? List.of() : Arrays.stream(rawRoles.replace("{","").replace("}","").replace("\"","").split(",")).map(ReferenceImporter::role).distinct().toList();
                        jdbc.update("insert into reference_champion_metadata(import_id,champion_id,roles,raw_metadata) values (?,?,?::jsonb,?::jsonb)",id,champion,mapper.writeValueAsString(roles),mapper.writeValueAsString(row));
                    } else {
                        boolean composition=table.equals("team_comp_signature_stats");
                        String kind=composition ? "COMPOSITION" : table.equals("champion_role_stats") ? "ROLE" : table.equals("champion_synergy_stats") ? "SYNERGY" : "MATCHUP";
                        int games=Integer.parseInt(row.get("games")), wins=Integer.parseInt(row.get("wins"));
                        if(games<=0 || wins<0 || wins>games) throw new IllegalArgumentException("invalid counts");
                        String patch=required(row,"patch"); if(!patch.matches("[0-9]{1,3}\\.[0-9]{1,3}")) throw new IllegalArgumentException("invalid patch");
                        String champion=composition?null:canonical(row.get("champion_id"),aliases);
                        String championRole=composition?null:role(row.get("role"));
                        String partner=null, partnerRole=null;
                        if(kind.equals("SYNERGY") || kind.equals("MATCHUP")) {
                            String prefix=kind.equals("SYNERGY")?"ally":"enemy";
                            partner=canonical(row.get(prefix+"_champion_id"),aliases); partnerRole=role(row.get(prefix+"_role"));
                        }
                        Double delta=number(row.get(kind.equals("SYNERGY")?"delta_vs_average":"delta_vs_baseline"));
                        Double score=number(row.get("confidence"));
                        batch.add(new Object[]{id,kind,patch,required(row,"region"),Integer.parseInt(required(row,"queue_id")),required(row,"source_type"),champion,championRole,partner,partnerRole,games,wins,delta,score,mapper.writeValueAsString(row)});
                        if(batch.size()>=500) flush(batch);
                    }
                    imported.merge(table,1,Integer::sum);
                } catch(IllegalArgumentException error) { rejected.merge(table+": "+error.getMessage(),1,Integer::sum); }
            });
        }
        flush(batch);
        if(!imported.containsKey("champion_metadata") || !imported.containsKey("champion_role_stats") || !imported.containsKey("champion_synergy_stats"))
            throw new IOException("Backup must contain valid champion metadata, role and synergy data. Import rolled back.");
        var report=new Report(id,imported,rejected);
        jdbc.update("update reference_imports set report=?::jsonb where id=?",mapper.writeValueAsString(report),id);
        return report;
    }
    private void flush(List<Object[]> rows) {
        if(rows.isEmpty())return;
        jdbc.batchUpdate("""
            insert into reference_stats(import_id,kind,patch,region,queue_id,source_type,champion_id,role,partner_id,partner_role,games,wins,delta,original_sample_score,raw_stat)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?::jsonb)
            """,rows);
        rows.clear();
    }
    static String role(String value) {
        if(value==null) throw new IllegalArgumentException("missing role");
        return switch(value.trim().toUpperCase(Locale.ROOT)) {case "TOP" -> "TOP";case "JUNGLE" -> "JUNGLE";case "MID","MIDDLE" -> "MID";case "ADC","BOTTOM","BOT" -> "BOT";case "UTILITY","SUPPORT" -> "SUPPORT";default -> throw new IllegalArgumentException("unknown role");};
    }
    private static String key(String value) {return value.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]","");}
    private static String canonical(String value,Map<String,String> aliases) {
        String id=value==null?null:aliases.get(key(value));
        if(id==null)throw new IllegalArgumentException("unknown champion");
        return id;
    }
    private static String required(Map<String,String> row,String column) {
        String value=row.get(column);if(value==null||value.isBlank())throw new IllegalArgumentException("missing "+column);return value;
    }
    private static Double number(String value) {
        if(value==null)return null;
        double n=Double.parseDouble(value);if(!Double.isFinite(n))throw new IllegalArgumentException("nonfinite statistic");return n;
    }
}
