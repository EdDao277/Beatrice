"""Research-only team-wide baseline. Preference scores are NOT win probabilities."""
from collections import Counter, defaultdict
from itertools import combinations

VARIANTS = ('pool', 'pool_rules', 'pool_rules_stats')
WEIGHTS = {'comfort': 35, 'composition': 20, 'synergy': 15, 'matchup': 10,
           'meta': 8, 'teamHistory': 7, 'draftValue': 5}


def posterior(games, wins):
    """Beta(25,25) prior: fifty neutral pseudo-games, not fifty real matches."""
    if not 0 <= wins <= games:
        raise ValueError('Invalid games/wins')
    return (wins + 25) / (games + 50)


class History:
    def __init__(self):
        self.players = defaultdict(Counter)
        self.champions = defaultdict(lambda: [0, 0])
        self.pairs = defaultdict(lambda: [0, 0])
        self.game_ids = set()
        self.latest_date = None
        self.patches = Counter()

    def observe(self, game):
        if game['gameId'] in self.game_ids:
            raise ValueError('Duplicate history game')
        self.game_ids.add(game['gameId'])
        self.latest_date = max(self.latest_date or game['date'], game['date'])
        self.patches[game['patch']] += 1
        for team in game['teams']:
            champions = []
            for player in team['players']:
                champion = player['championId']
                champions.append(champion)
                # Blank IDs cannot form a shared anonymous mega-player.
                if player['playerId']:
                    self.players[player['playerId']][champion] += 1
                row = self.champions[champion]
                row[0] += 1
                row[1] += team['result']
            for pair in combinations(sorted(champions), 2):
                row = self.pairs[pair]
                row[0] += 1
                row[1] += team['result']

    def pools(self, player_ids):
        return [dict(self.players.get(player, {})) for player in player_ids]


def placements(required, pools, blocked, candidate):
    """Return one complete five-player witness per feasible candidate player.

    Match mandatory picks first (at most 5! choices), then use augmenting paths
    for the remaining players. This avoids enumerating every future champion combo.
    Player assignment is hypothetical; lane assignments remain unknown.
    """
    if len(pools) != 5 or len(set(required)) != len(required) or len(required) > 5:
        return {}
    if set(required) & blocked or candidate not in required:
        return {}
    domains = [set(pool) - blocked for pool in pools]
    if any(not domain for domain in domains):
        return {}
    if all(domain == domains[0] for domain in domains):
        # Inferred capability is deliberately unknown for every player. Identical domains
        # need no combinatorial search: a distinct five-champion set is sufficient.
        if len(domains[0]) < 5 or not set(required) <= domains[0]:
            return {}
        others = sorted(set(required) - {candidate})
        others += sorted(domains[0] - set(required))[:5 - len(required)]
        return {owner: {owner: candidate, **dict(zip((p for p in range(5) if p != owner), others))}
                for owner in range(5)}
    result = {}

    def finish(assigned):
        owners = {champ: player for player, champ in assigned.items()}
        fixed = set(owners)

        def augment(player, visited):
            for champ in sorted(domains[player] - fixed):
                if champ in visited:
                    continue
                visited.add(champ)
                if champ not in owners or augment(owners[champ], visited):
                    owners[champ] = player
                    return True
            return False

        for player in range(5):
            if player not in assigned and not augment(player, set()):
                return None
        return {player: champ for champ, player in owners.items()}

    # Candidate first allows pruning after the first witness for each player.
    remaining = [candidate] + sorted(set(required) - {candidate},
                                    key=lambda c: (sum(c in d for d in domains), c))

    def search(index, assigned):
        if index == len(remaining):
            witness = finish(assigned)
            if witness is not None:
                owner = next(p for p, c in assigned.items() if c == candidate)
                result[owner] = witness
            return
        if assigned:
            owner = next(p for p, c in assigned.items() if c == candidate)
            if owner in result:
                return
        champ = remaining[index]
        for player, domain in enumerate(domains):
            if player not in assigned and champ in domain:
                search(index + 1, {**assigned, player: champ})

    search(0, {})
    return result


def recommend(context, history, variant, pool_policy='observed'):
    if variant not in VARIANTS:
        raise ValueError('Unknown baseline variant')
    if pool_policy not in ('observed', 'inferred', 'saved'):
        raise ValueError('Unknown pool policy')
    ids = context['playerIds']
    if len(ids) != 5 or len(set(ids)) != 5 or not all(ids):
        return {'candidates': [], 'abstention': 'invalid_roster', 'poolCandidates': []}
    pools = history.pools(ids)
    if pool_policy == 'saved':
        saved = context.get('savedPools')
        if not isinstance(saved, dict) or set(saved) != set(ids):
            raise ValueError('Saved pools must explicitly cover all five players')
        pools = [dict(saved[player]) for player in ids]
        if any(not isinstance(champion, str) or not champion or type(rating) is not int or not 1 <= rating <= 10
               for pool in pools for champion, rating in pool.items()):
            raise ValueError('Saved comfort ratings must be integers from 1 to 10')
    allies = context['allyPicks']
    blocked = set(context['bans']) | set(context['enemyPicks'])
    observed_available = sorted(set().union(*pools) - blocked - set(allies))
    domains = pools
    if pool_policy == 'inferred':
        # The vocabulary is earlier observed champions, NOT the current catalog or held-out target.
        # Already visible ally picks can be assigned even if they were previously unobserved.
        domains = [set(history.champions) | set(allies) for _ in ids]
    elif any(not pool for pool in pools):
        return {'candidates': [], 'abstention': 'missing_player_history', 'poolCandidates': observed_available}
    available = sorted(set().union(*domains) - blocked - set(allies))
    candidates = []
    for champion in available:
        options = placements(allies + [champion], domains, blocked, champion)
        if not options:
            continue
        # Frequency proxy only, not an invented user comfort rating.
        def familiarity(p):
            count = pools[p].get(champion, 0)
            if pool_policy == 'inferred':
                return 50 + 50 * count / (count + 10)
            if pool_policy == 'saved':
                return count * 10
            return 100 * count / max(pools[p].values())

        player = min(options, key=lambda p: (-familiarity(p), ids[p]))
        observed_players = [p for p in options if pools[p].get(champion, 0) > 0]
        factors = dict.fromkeys(WEIGHTS, 50.0)
        factors['comfort'] = familiarity(player)
        coverage = 35 if observed_players else 0
        if variant != 'pool':
            # Unknown capability does not earn a five-player flexibility bonus.
            factors['draftValue'] = 50 + 12.5 * max(0, len(observed_players) - 1)
            coverage += 5
        evidence = {'meta': None, 'allyPairs': []}
        warnings = ['historical_frequency_not_comfort', 'roles_unknown',
                    'composition_matchup_team_history_unavailable']
        if pool_policy == 'saved':
            warnings.remove('historical_frequency_not_comfort')
        if pool_policy == 'inferred':
            warnings.append('unobserved_player_champion_not_prohibited')
        if variant == 'pool_rules_stats':
            games, wins = history.champions.get(champion, (0, 0))
            if games:
                factors['meta'] = 100 * posterior(games, wins)
                evidence['meta'] = {'games': games, 'wins': wins}
                coverage += 8
                if games < 30:
                    warnings.append('small_sample')
            deltas = []
            for ally in allies:
                pair_games, pair_wins = history.pairs.get(tuple(sorted((champion, ally))), (0, 0))
                ally_games, ally_wins = history.champions.get(ally, (0, 0))
                if not pair_games or not games or not ally_games:
                    continue
                baseline = (posterior(games, wins) + posterior(ally_games, ally_wins)) / 2
                delta = posterior(pair_games, pair_wins) - baseline
                deltas.append(delta)
                evidence['allyPairs'].append({'ally': ally, 'games': pair_games, 'wins': pair_wins,
                    'allyBaseline': {'games': ally_games, 'wins': ally_wins}, 'delta': delta})
                if min(pair_games, games, ally_games) < 30:
                    warnings.append('small_sample')
            if deltas:
                factors['synergy'] = max(0, min(100, 50 + 100 * sum(deltas) / len(deltas)))
                coverage += 15
            warnings.append('pooled_historical_patches_not_current_meta')
        score = sum(factors[key] * weight / 100 for key, weight in WEIGHTS.items())
        candidates.append({'championId': champion, 'score': round(score, 6),
            'factorCoverage': coverage, 'factors': factors, 'evidence': evidence,
            'feasiblePlayers': [ids[p] for p in sorted(options)],
            'observedPlayers': [ids[p] for p in sorted(observed_players)],
            'playerChampionEvidence': {ids[p]: pools[p].get(champion, 0) for p in range(5)},
            'poolPolicy': pool_policy,
            'completionWitness': {ids[p]: c for p, c in options[player].items()},
            'warnings': sorted(set(warnings))})
    candidates.sort(key=lambda row: (-row['score'], row['championId']))
    return {'candidates': candidates, 'poolCandidates': observed_available,
            'abstention': None if candidates else 'no_feasible_pool_completion'}
