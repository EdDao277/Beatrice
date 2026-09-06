package com.beatrice.backend.reference;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

@Service
@Transactional(readOnly=true, isolation=org.springframework.transaction.annotation.Isolation.REPEATABLE_READ)
public class ReferenceService {
    public record Slice(String patch,int queueId,String region,String source) {}
    public record Options(Long importId,List<Slice> slices) {}
    public record Stat(String role,String partnerId,String partnerRole,int games,int wins,double winRate,Double delta,String tier) {}
    public record Evidence(List<String> roles,List<Stat> roleStats,List<Stat> synergies) {}
    private final JdbcTemplate jdbc; private final ObjectMapper mapper;
    public ReferenceService(JdbcTemplate jdbc,ObjectMapper mapper) {this.jdbc=jdbc;this.mapper=mapper;}
    private Long latest() {return jdbc.queryForObject("select max(id) from reference_imports",Long.class);}
    public Options options() {
        Long id=latest();if(id==null)return new Options(null,List.of());
        var slices=jdbc.query("""
            select distinct patch,queue_id,region,source_type from reference_stats where import_id=?
            order by patch,queue_id,region,source_type
            """,(rs,n)->new Slice(rs.getString(1),rs.getInt(2),rs.getString(3),rs.getString(4)),id);
        // Numeric sorting keeps 16.15 ahead of 16.9; patch strings are validated on import.
        slices.sort(Comparator.<Slice>comparingInt(s->Integer.parseInt(s.patch().split("\\.")[0]))
            .thenComparingInt(s->Integer.parseInt(s.patch().split("\\.")[1])).reversed().thenComparingInt(Slice::queueId));
        return new Options(id,slices);
    }
    public Evidence evidence(String champion,String patch,int queue,String region,String source,String role) {
        Long id=latest();if(id==null)return new Evidence(List.of(),List.of(),List.of());
        var metadata=jdbc.queryForList("select roles::text from reference_champion_metadata where import_id=? and champion_id=?",String.class,id,champion);
        List<String> roles=metadata.isEmpty()?List.of():Arrays.asList(mapper.readValue(metadata.getFirst(),String[].class));
        return new Evidence(roles,stats(id,"ROLE",champion,patch,queue,region,source,role),stats(id,"SYNERGY",champion,patch,queue,region,source,role));
    }
    private List<Stat> stats(long id,String kind,String champion,String patch,int queue,String region,String source,String role) {
        // Directional query: never sum A→B with B→A, which are the same observed games.
        return jdbc.query("""
            select role,partner_id,partner_role,games,wins,delta,raw_stat->>'tier' as tier
            from reference_stats where import_id=? and kind=? and champion_id=? and patch=?
            and queue_id=? and region=? and source_type=? and role=?
            order by games desc, partner_id, partner_role limit 40
            """,(rs,n)->new Stat(rs.getString(1),rs.getString(2),rs.getString(3),rs.getInt(4),rs.getInt(5),
                (double)rs.getInt(5)/rs.getInt(4),(Double)rs.getObject(6),rs.getString(7)),id,kind,champion,patch,queue,region,source,role);
    }
}
