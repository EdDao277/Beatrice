import java.io.*;
import java.util.*;
import com.beatrice.backend.recommendation.TeamPickFeasibility;
import com.beatrice.backend.recommendation.WeightedRecommendations;
import static com.beatrice.backend.recommendation.RecommendationEngine.*;

/** Offline saved-pool probe. Actual Java matching and scoring, neutral unavailable metadata. */
public class FreshnessScorer {
    static List<String> tokens(String s) {return s.isEmpty()?List.of():Arrays.asList(s.split(","));}
    public static void main(String[] args) throws Exception {
        var reader=new BufferedReader(new InputStreamReader(System.in));
        String line,id=""; List<String> allies=List.of(); Set<String> unavailable=Set.of();
        var pools=new TreeMap<String,Map<String,Integer>>();
        while((line=reader.readLine())!=null) {
            var p=line.split("\t",-1);
            switch(p[0]) {
                case "S" -> {id=p[1];allies=tokens(p[2]);unavailable=new HashSet<>(tokens(p[3]));pools.clear();}
                case "P" -> pools.computeIfAbsent(p[1],k->new TreeMap<>()).put(p[2],Integer.parseInt(p[3]));
                case "END" -> {
                    var membership=new TreeMap<String,Set<String>>();pools.forEach((r,v)->membership.put(r,v.keySet()));
                    var feasible=TeamPickFeasibility.candidates(membership,allies,unavailable);
                    var scores=new HashMap<String,Double>();
                    for(var c:feasible.entrySet()) for(var role:c.getValue()) {
                        var champion=new Champion(c.getKey(),pools.get(role).get(c.getKey()),Set.of());
                        var context=new Context(role,List.of(champion),unavailable,Set.of(),Set.of(),Set.of(),Map.of(),Map.of(),List.of());
                        double score=new WeightedRecommendations().score(context,Set.of()).getFirst().score();
                        scores.merge(c.getKey(),score,Math::max);
                    }
                    var order=new ArrayList<>(scores.keySet());
                    order.sort(Comparator.<String>comparingDouble(scores::get).reversed().thenComparing(s->s));
                    for(var c:order) System.out.println("R\t"+id+"\t"+c+"\t"+scores.get(c));
                    System.out.println("DONE\t"+id);
                }
                default -> throw new IllegalArgumentException("Unknown record");
            }
        }
    }
}
