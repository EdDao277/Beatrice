import java.io.*;
import java.util.*;
import com.beatrice.backend.recommendation.RecommendationEngine;
import com.beatrice.backend.recommendation.WeightedRecommendations;
import static com.beatrice.backend.recommendation.RecommendationEngine.*;

/** Offline TSV harness: invokes unchanged Java production classes, with no server or DB. */
public class ReadinessScorer {
    static Set<String> tokens(String value) {
        return value.isEmpty() ? Set.of() : new HashSet<>(Arrays.asList(value.split(",")));
    }
    public static void main(String[] args) throws Exception {
        var input = new BufferedReader(new InputStreamReader(System.in));
        String id="", role="TOP", line;
        Set<String> desired=Set.of(), covered=Set.of(), unavailable=Set.of();
        var pool=new ArrayList<Champion>(); var known=new HashSet<String>();
        while ((line=input.readLine()) != null) {
            String[] p=line.split("\t", -1);
            switch(p[0]) {
                case "S" -> { id=p[1]; role=p[2]; desired=tokens(p[3]); covered=tokens(p[4]);
                              unavailable=tokens(p[5]); pool.clear(); known.clear(); }
                case "P" -> { pool.add(new Champion(p[1],Integer.parseInt(p[2]),tokens(p[3])));
                              if(p[4].equals("1")) known.add(p[1]); }
                case "END" -> {
                    var context=new Context(role,pool,unavailable,Set.of(),desired,covered,Map.of(),Map.of(),List.of());
                    var legal=new RecommendationEngine().scorePicks(context);
                    var scores=new ArrayList<WeightedRecommendations.Pick>();
                    // Singleton scoring removes only the public top-three presentation limit.
                    // Candidate eligibility comes from Java's full-pool generator above.
                    for(var candidate:legal) {
                        var champion=pool.stream().filter(c->c.id().equals(candidate.championId())).findFirst().orElseThrow();
                        var one=new Context(role,List.of(champion),unavailable,Set.of(),desired,covered,Map.of(),Map.of(),List.of());
                        scores.addAll(new WeightedRecommendations().score(one,known));
                    }
                    scores.sort(Comparator.comparingDouble(WeightedRecommendations.Pick::score).reversed()
                                          .thenComparing(WeightedRecommendations.Pick::championId));
                    // Fail if singleton scoring ever stops matching the actual public scorer.
                    if(!scores.stream().limit(3).toList().equals(new WeightedRecommendations().score(context,known)))
                        throw new IllegalStateException("Full ranking differs from Java top three");
                    for(var score:scores) System.out.println("R\t"+id+"\t"+score.championId()+"\t"+score.score());
                    System.out.println("DONE\t"+id);
                }
                default -> throw new IllegalArgumentException("Unknown harness record");
            }
        }
    }
}
