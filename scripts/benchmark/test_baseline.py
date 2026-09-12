import unittest

from baseline import History, recommend, placements, posterior
from test_protocol import game


def context():
    return {'playerIds': ['P0', 'P1', 'P2', 'P3', 'P4'],
            'allyPicks': [], 'enemyPicks': [], 'bans': []}


class BaselineTests(unittest.TestCase):
    def test_equal_unknown_domains_keep_all_player_options_with_valid_witnesses(self):
        pools = [set('ABCDEFG') for _ in range(5)]
        options = placements(['A', 'B'], pools, {'G'}, 'B')
        self.assertEqual(set(options), {0, 1, 2, 3, 4})
        for owner, witness in options.items():
            self.assertEqual(witness[owner], 'B')
            self.assertEqual(set(witness.values()), set('ABCDE'))
        self.assertEqual(placements(['A', 'B'], pools, {'D', 'E', 'F', 'G'}, 'B'), {})
    def test_inferred_pool_keeps_unknown_players_and_excludes_future_champions(self):
        history = History()
        history.observe(game())
        state = context()
        state['playerIds'][0] = 'new_player'
        result = recommend(state, history, 'pool_rules_stats', pool_policy='inferred')
        self.assertIsNone(result['abstention'])
        self.assertEqual(len(result['candidates']), 10)
        self.assertNotIn('FutureChampion', [r['championId'] for r in result['candidates']])
        row = next(r for r in result['candidates'] if r['championId'] == 'C9')
        self.assertEqual(row['factors']['comfort'], 50)
        self.assertEqual(row['observedPlayers'], [])
        self.assertIn('unobserved_player_champion_not_prohibited', row['warnings'])
        self.assertNotIn('C9', result['poolCandidates'])

    def test_saved_pool_is_authoritative_even_when_history_contains_more_champions(self):
        history = History()
        history.observe(game())
        state = context()
        state['savedPools'] = {f'P{i}': {f'C{i}': 8} for i in range(5)}
        result = recommend(state, history, 'pool', pool_policy='saved')
        self.assertEqual({r['championId'] for r in result['candidates']}, {'C0', 'C1', 'C2', 'C3', 'C4'})
        self.assertTrue(all(r['score'] == 60.5 for r in result['candidates']))
        state['savedPools']['P0'] = {}
        self.assertEqual(recommend(state, history, 'pool', pool_policy='saved')['candidates'], [])

    def test_unknown_pool_policy_and_invalid_saved_rating_rejected(self):
        with self.assertRaises(ValueError):
            recommend(context(), History(), 'pool', pool_policy='oops')
        state = context()
        state['savedPools'] = {f'P{i}': {f'C{i}': 11} for i in range(5)}
        with self.assertRaises(ValueError):
            recommend(state, History(), 'pool', pool_policy='saved')

    def test_sparse_wins_shrink_and_missing_is_neutral(self):
        self.assertEqual(posterior(0, 0), 0.5)
        self.assertAlmostEqual(posterior(1, 1), 26 / 51)
        self.assertEqual(posterior(100, 75), 2 / 3)
        with self.assertRaises(ValueError):
            posterior(2, 3)

    def test_flex_assignment_leaves_each_player_a_playable_champion(self):
        pools = [{'A': 1, 'B': 1}, {'A': 1}, {'C': 1}, {'D': 1}, {'E': 1}]
        witnesses = placements(['A', 'B'], pools, set(), 'B')
        self.assertEqual(witnesses, {0: {0: 'B', 1: 'A', 2: 'C', 3: 'D', 4: 'E'}})
        self.assertEqual(placements(['A', 'B'], pools, {'E'}, 'B'), {})

    def test_blind_picks_use_all_five_pools_and_exclude_unavailable(self):
        history = History()
        history.observe(game(date='2024-01-01 00:00:00'))
        result = recommend(context(), history, 'pool')
        self.assertEqual({c['championId'] for c in result['candidates']}, {'C0', 'C1', 'C2', 'C3', 'C4'})
        self.assertTrue(all(c['score'] == 67.5 for c in result['candidates']))
        changed = context()
        changed['bans'] = ['C0']
        # With this tiny historical pool, banning the only TOP option blocks a full roster.
        self.assertEqual(recommend(changed, history, 'pool')['candidates'], [])

    def test_never_assigns_two_picks_to_one_player(self):
        history = History()
        history.observe(game(date='2024-01-01 00:00:00'))
        alternate = game('alt', '2024-01-02 00:00:00')
        alternate['teams'][0]['players'][0]['championId'] = 'OtherTop'
        history.observe(alternate)
        state = context()
        state['allyPicks'] = ['C0']
        candidates = recommend(state, history, 'pool')['candidates']
        self.assertNotIn('OtherTop', [c['championId'] for c in candidates])
        self.assertNotIn('C0', [c['championId'] for c in candidates])

    def test_unknown_player_abstains_instead_of_using_final_pick(self):
        history = History()
        history.observe(game())
        state = context()
        state['playerIds'][0] = 'unknown'
        self.assertEqual(recommend(state, history, 'pool')['abstention'], 'missing_player_history')
        self.assertIn('C1', recommend(state, history, 'pool')['poolCandidates'])

    def test_stats_use_earlier_pairs_not_invented_roles(self):
        history = History()
        history.observe(game())
        state = context()
        state['allyPicks'] = ['C0']
        result = recommend(state, history, 'pool_rules_stats')
        row = result['candidates'][0]
        self.assertEqual(row['factors']['matchup'], 50)
        self.assertEqual(row['factors']['composition'], 50)
        self.assertEqual(row['evidence']['meta'], {'games': 1, 'wins': 1})
        self.assertEqual(row['evidence']['allyPairs'][0]['games'], 1)
        self.assertIn('small_sample', row['warnings'])
        self.assertGreater(row['score'], 67.5)


if __name__ == '__main__':
    unittest.main()
