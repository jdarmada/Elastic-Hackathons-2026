#!/usr/bin/env python3
"""
⚽ World Cup 2026 Hack Night - one-shot setup

Does everything in one run:

  1. Fetches live 2026 World Cup data from openfootball/worldcup.json
  2. Ingests it into the `wc2026_matches` index (same schema as the notebook)
  3. Generates a natural-language story/description for every match and
     ingests them into `wc2026_match_stories` - a semantic_text index that
     is embedded automatically by the Elastic Inference Service (EIS)
  4. Creates four Agent Builder tools via the Kibana API:
       - get_team_form
       - get_team_stats_2026
       - get_upcoming_fixtures
       - search_match_stories   <- hybrid search (lexical + semantic, RRF)
  5. Creates the `wc2026_predictor` agent wired to all four tools

Usage:
    export ELASTIC_ENDPOINT="https://your-project.es.region.aws.elastic.cloud"
    export ELASTIC_API_KEY="your-api-key"
    # optional - derived from ELASTIC_ENDPOINT (.es. -> .kb.) if not set:
    export KIBANA_ENDPOINT="https://your-project.kb.region.aws.elastic.cloud"

    python setup_hacknight.py              # everything
    python setup_hacknight.py --data-only  # only ingest the two indices
    python setup_hacknight.py --agent-only # only create tools + agent

Credentials: Elastic Cloud Console -> Your Project -> Connection Details.
The same API key works for both Elasticsearch and Kibana.
"""

import argparse
import os
import sys

import requests
from elasticsearch import Elasticsearch, helpers

DATA_URL = 'https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json'
MATCHES_INDEX = 'wc2026_matches'
STORIES_INDEX = 'wc2026_match_stories'
AGENT_ID = 'wc2026_predictor'


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_config():
    endpoint = os.environ.get('ELASTIC_ENDPOINT', '').strip()
    api_key = os.environ.get('ELASTIC_API_KEY', '').strip()

    if not endpoint:
        endpoint = input('Elasticsearch endpoint (https://...es...elastic.cloud): ').strip()
    if not api_key:
        api_key = input('Elastic API key: ').strip()

    kibana = os.environ.get('KIBANA_ENDPOINT', '').strip()
    if not kibana and '.es.' in endpoint:
        kibana = endpoint.replace('.es.', '.kb.')
        print(f'ℹ️  KIBANA_ENDPOINT not set - derived {kibana}')
    if not kibana:
        kibana = input('Kibana endpoint (https://...kb...elastic.cloud): ').strip()

    return endpoint.rstrip('/'), kibana.rstrip('/'), api_key


def connect_es(endpoint, api_key):
    es = Elasticsearch(endpoint, api_key=api_key, request_timeout=120)
    info = es.info()
    print(f'✅ Connected to Elasticsearch {info["version"]["number"]}')
    return es


# ---------------------------------------------------------------------------
# Step 1 - fetch live 2026 data
# ---------------------------------------------------------------------------

def fetch_matches():
    print(f'\n📡 Fetching live 2026 data from openfootball ...')
    resp = requests.get(DATA_URL, timeout=30)
    resp.raise_for_status()
    all_matches = resp.json()['matches']
    played = sum(1 for m in all_matches if 'score' in m)
    print(f'✅ Fetched {len(all_matches)} matches ({played} played, {len(all_matches) - played} upcoming)')
    return all_matches


# ---------------------------------------------------------------------------
# Step 2 - matches index (same schema as the notebook)
# ---------------------------------------------------------------------------

MATCHES_MAPPING = {
    'mappings': {
        'properties': {
            'date':        {'type': 'date'},
            'round':       {'type': 'keyword'},
            'group':       {'type': 'keyword'},
            'stadium':     {'type': 'keyword'},
            'stage':       {'type': 'keyword'},
            'status':      {'type': 'keyword'},
            'team1':       {'type': 'keyword'},
            'team2':       {'type': 'keyword'},
            'score_ft1':   {'type': 'integer'},
            'score_ft2':   {'type': 'integer'},
            'score_ht1':   {'type': 'integer'},
            'score_ht2':   {'type': 'integer'},
            'total_goals': {'type': 'integer'},
            'winner':      {'type': 'keyword'},
            'team1_win':   {'type': 'boolean'},
            'team2_win':   {'type': 'boolean'},
            'goals': {
                'type': 'nested',
                'properties': {
                    'scorer': {'type': 'keyword'},
                    'minute': {'type': 'keyword'},
                    'team':   {'type': 'keyword'},
                    'type':   {'type': 'keyword'},
                },
            },
        }
    }
}

STAGE_BY_ROUND = {
    'Round of 32':           'round_of_32',
    'Round of 16':           'round_of_16',
    'Quarter-finals':        'quarter',
    'Semi-finals':           'semi',
    'Match for third place': 'third_place',
    'Final':                 'final',
}


def round_to_stage(round_name):
    return STAGE_BY_ROUND.get(round_name, 'group')


def enrich(m):
    doc = {
        'date':    m['date'],
        'round':   m['round'],
        'group':   m.get('group', 'Knockout'),
        'stadium': m.get('ground', ''),
        'stage':   round_to_stage(m['round']),
        'team1':   m['team1'],
        'team2':   m['team2'],
    }

    if 'score' in m:
        ft1, ft2 = m['score']['ft']
        ht = m['score'].get('ht', [None, None])

        if ft1 > ft2:
            winner = m['team1']
        elif ft2 > ft1:
            winner = m['team2']
        else:
            winner = 'draw'

        doc.update({
            'status':      'played',
            'score_ft1':   ft1,
            'score_ft2':   ft2,
            'score_ht1':   ht[0],
            'score_ht2':   ht[1],
            'total_goals': ft1 + ft2,
            'winner':      winner,
            'team1_win':   winner == m['team1'],
            'team2_win':   winner == m['team2'],
        })

        goals = []
        for g in m.get('goals1', []):
            goals.append({
                'scorer': g['name'],
                'minute': g.get('minute', ''),
                'team':   m['team1'],
                'type':   'own_goal' if g.get('owngoal') else ('penalty' if g.get('penalty') else 'goal'),
            })
        for g in m.get('goals2', []):
            goals.append({
                'scorer': g['name'],
                'minute': g.get('minute', ''),
                'team':   m['team2'],
                'type':   'own_goal' if g.get('owngoal') else ('penalty' if g.get('penalty') else 'goal'),
            })
        doc['goals'] = goals
    else:
        doc['status'] = 'upcoming'

    return doc


def ingest_matches(es, all_matches):
    print(f'\n📦 Ingesting {MATCHES_INDEX} ...')
    if es.indices.exists(index=MATCHES_INDEX):
        es.indices.delete(index=MATCHES_INDEX)
        print(f'🗑️  Deleted existing index: {MATCHES_INDEX}')
    es.indices.create(index=MATCHES_INDEX, **MATCHES_MAPPING)

    docs = [enrich(m) for m in all_matches]
    actions = [{'_index': MATCHES_INDEX, '_source': d} for d in docs]
    success, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=MATCHES_INDEX)
    print(f'✅ Indexed {success} matches into {MATCHES_INDEX}')
    return docs


# ---------------------------------------------------------------------------
# Step 3 - match stories index (semantic_text + text, for hybrid search)
# ---------------------------------------------------------------------------

STORIES_MAPPING = {
    'mappings': {
        'properties': {
            'match_id': {'type': 'keyword'},
            'date':     {'type': 'date'},
            'team1':    {'type': 'keyword'},
            'team2':    {'type': 'keyword'},
            'teams':    {'type': 'keyword'},
            'group':    {'type': 'keyword'},
            'stage':    {'type': 'keyword'},
            'status':   {'type': 'keyword'},
            'stadium':  {'type': 'keyword'},
            # Same text in both fields: `story` powers lexical (BM25) search,
            # `story_semantic` is embedded automatically by EIS for semantic
            # search. Querying both and fusing with RRF = hybrid search.
            'story':          {'type': 'text'},
            'story_semantic': {'type': 'semantic_text'},
        }
    }
}

STAGE_LABEL = {
    'group':        'group-stage',
    'round_of_32':  'Round of 32',
    'round_of_16':  'Round of 16',
    'quarter':      'quarter-final',
    'semi':         'semi-final',
    'third_place':  'third-place playoff',
    'final':        'World Cup final',
}


def result_phrase(doc):
    """Pick a result verb from the scoreline so stories vary naturally."""
    ft1, ft2 = doc['score_ft1'], doc['score_ft2']
    margin = abs(ft1 - ft2)
    total = doc['total_goals']

    if doc['winner'] == 'draw':
        if total == 0:
            return f"{doc['team1']} and {doc['team2']} played out a goalless draw"
        if total >= 4:
            return f"{doc['team1']} and {doc['team2']} shared the points in a wild {ft1}-{ft2} high-scoring draw"
        return f"{doc['team1']} and {doc['team2']} drew {ft1}-{ft2} in an evenly matched contest"

    winner = doc['winner']
    loser = doc['team2'] if winner == doc['team1'] else doc['team1']
    w_goals, l_goals = max(ft1, ft2), min(ft1, ft2)
    score = f'{w_goals}-{l_goals}'

    if margin >= 3:
        return f'{winner} thrashed {loser} {score} in a dominant, one-sided display'
    if margin == 2:
        return f'{winner} beat {loser} {score} with a comfortable, controlled win'
    if total >= 4:
        return f'{winner} edged {loser} {score} in an end-to-end thriller'
    return f'{winner} edged {loser} {score} in a tight, hard-fought contest'


def comeback_phrase(doc):
    """Note a half-time comeback if the eventual winner trailed at the break."""
    ht1, ht2 = doc.get('score_ht1'), doc.get('score_ht2')
    if ht1 is None or ht2 is None or doc['winner'] == 'draw':
        return ''
    if doc['winner'] == doc['team1'] and ht1 < ht2:
        return f" {doc['team1']} came from behind after trailing {ht1}-{ht2} at half-time."
    if doc['winner'] == doc['team2'] and ht2 < ht1:
        return f" {doc['team2']} came from behind after trailing {ht2}-{ht1} at half-time."
    return ''


def scorers_phrase(doc):
    goals = doc.get('goals', [])
    if not goals:
        return ''
    parts = []
    for g in goals[:6]:
        minute = f" ({g['minute']}')" if g.get('minute') else ''
        note = ''
        if g['type'] == 'penalty':
            note = ' from the penalty spot'
        elif g['type'] == 'own_goal':
            note = ' with an own goal'
        parts.append(f"{g['scorer']}{minute}{note} for {g['team']}")
    extra = f' and {len(goals) - 6} more' if len(goals) > 6 else ''
    joined = '; '.join(parts)
    return f' Goals came from {joined}{extra}.'


def build_story(doc):
    """Turn an enriched match doc into a natural-language description."""
    stage = STAGE_LABEL.get(doc['stage'], 'group-stage')
    where = f" at {doc['stadium']}" if doc['stadium'] else ''
    group = f" in {doc['group']}" if doc['stage'] == 'group' else ''

    if doc['status'] == 'upcoming':
        return (
            f"Upcoming fixture: {doc['team1']} face {doc['team2']} in a {stage} match{group}"
            f"{where} on {doc['date']} at the 2026 FIFA World Cup. "
            f"A preview of the {doc['team1']} vs {doc['team2']} matchup."
        )

    return (
        f"{result_phrase(doc)} in their {stage} match{group}{where} "
        f"on {doc['date']} at the 2026 FIFA World Cup."
        f"{comeback_phrase(doc)}"
        f"{scorers_phrase(doc)}"
    )


def ingest_stories(es, match_docs):
    print(f'\n📦 Ingesting {STORIES_INDEX} (semantic_text - EIS embeds each doc at index time) ...')
    if es.indices.exists(index=STORIES_INDEX):
        es.indices.delete(index=STORIES_INDEX)
        print(f'🗑️  Deleted existing index: {STORIES_INDEX}')
    es.indices.create(index=STORIES_INDEX, **STORIES_MAPPING)

    actions = []
    for d in match_docs:
        story = build_story(d)
        actions.append({
            '_index': STORIES_INDEX,
            '_id': f"{d['date']}-{d['team1']}-{d['team2']}".replace(' ', '_').lower(),
            '_source': {
                'match_id': f"{d['date']}-{d['team1']}-{d['team2']}".replace(' ', '_').lower(),
                'date':     d['date'],
                'team1':    d['team1'],
                'team2':    d['team2'],
                'teams':    [d['team1'], d['team2']],
                'group':    d['group'],
                'stage':    d['stage'],
                'status':   d['status'],
                'stadium':  d['stadium'],
                'story':          story,
                'story_semantic': story,
            },
        })

    # Smaller chunks + generous timeout: EIS generates embeddings during indexing
    success, _ = helpers.bulk(es, actions, chunk_size=50, request_timeout=300)
    es.indices.refresh(index=STORIES_INDEX)
    print(f'✅ Indexed {success} match stories into {STORIES_INDEX}')

    sample = es.search(index=STORIES_INDEX, size=2, query={'term': {'status': 'played'}})
    for h in sample['hits']['hits']:
        print(f"   e.g. \"{h['_source']['story'][:110]}...\"")


# ---------------------------------------------------------------------------
# Step 4 + 5 - Agent Builder tools and agent (Kibana API)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        'id': 'get_team_form',
        'type': 'esql',
        'description': (
            "Returns a team's 2026 World Cup results so far - wins, losses, draws, goals scored and "
            "conceded, and each match result with opponent, date, and stage. Use this when the user asks "
            "about a team's current form, recent results, or how they have performed in the tournament."
        ),
        'configuration': {
            'query': (
                'FROM wc2026_matches | WHERE status == "played" AND (team1 == ?team_name OR team2 == ?team_name) '
                '| EVAL goals_scored = CASE(team1 == ?team_name, score_ft1, score_ft2), '
                'goals_conceded = CASE(team1 == ?team_name, score_ft2, score_ft1), '
                'result = CASE(winner == ?team_name, "win", winner == "draw", "draw", "loss") '
                '| KEEP date, team1, team2, score_ft1, score_ft2, group, stage, result, goals_scored, goals_conceded, winner, stadium '
                '| SORT date ASC'
            ),
            'params': {
                'team_name': {
                    'type': 'string',
                    'description': 'The team name exactly as it appears in the data, e.g. France',
                }
            },
        },
    },
    {
        'id': 'get_team_stats_2026',
        'type': 'esql',
        'description': (
            'Returns aggregated 2026 tournament statistics for a team: total matches played, wins, draws, '
            'losses, goals scored, and goals conceded. Use this when comparing two teams statistically or '
            'assessing overall tournament performance.'
        ),
        'configuration': {
            'query': (
                'FROM wc2026_matches | WHERE status == "played" AND (team1 == ?team_name OR team2 == ?team_name) '
                '| EVAL goals_scored = CASE(team1 == ?team_name, score_ft1, score_ft2), '
                'goals_conceded = CASE(team1 == ?team_name, score_ft2, score_ft1), '
                'is_win = CASE(winner == ?team_name, 1, 0), '
                'is_draw = CASE(winner == "draw", 1, 0), '
                'is_loss = CASE(winner != ?team_name AND winner != "draw", 1, 0) '
                '| STATS matches_played = COUNT(*), wins = SUM(is_win), draws = SUM(is_draw), losses = SUM(is_loss), '
                'total_scored = SUM(goals_scored), total_conceded = SUM(goals_conceded)'
            ),
            'params': {
                'team_name': {
                    'type': 'string',
                    'description': 'The team name, e.g. Germany',
                }
            },
        },
    },
    {
        'id': 'get_upcoming_fixtures',
        'type': 'esql',
        'description': (
            'Returns upcoming scheduled matches for a team that have not yet been played. Use this when the '
            'user asks when a team plays next, who their next opponent is, or to identify a real upcoming '
            'matchup to predict.'
        ),
        'configuration': {
            'query': (
                'FROM wc2026_matches | WHERE status == "upcoming" AND (team1 == ?team_name OR team2 == ?team_name) '
                '| KEEP date, round, group, team1, team2, stadium | SORT date ASC'
            ),
            'params': {
                'team_name': {
                    'type': 'string',
                    'description': 'The team name, e.g. England',
                }
            },
        },
    },
    {
        # Hybrid search: lexical BM25 on `story` + semantic on `story_semantic`,
        # fused with reciprocal rank fusion (FORK ... | FUSE).
        'id': 'search_match_stories',
        'type': 'esql',
        'description': (
            'Hybrid search (lexical + semantic vector search fused with RRF) over natural-language stories '
            'of every 2026 World Cup match. Use this for descriptive or fuzzy questions where exact team '
            'names or stats are not enough - e.g. "dramatic comebacks", "close low-scoring knockout games", '
            '"biggest thrashings of the group stage", "matches decided by penalties or own goals", or to '
            'find matches similar to a described scenario.'
        ),
        'configuration': {
            'query': (
                'FROM wc2026_match_stories METADATA _id, _index, _score '
                '| FORK (WHERE MATCH(story, ?query) | SORT _score DESC | LIMIT 20) '
                '(WHERE MATCH(story_semantic, ?query) | SORT _score DESC | LIMIT 20) '
                '| FUSE '
                '| SORT _score DESC '
                '| KEEP date, team1, team2, group, stage, status, stadium, story, _score '
                '| LIMIT 8'
            ),
            'params': {
                'query': {
                    'type': 'string',
                    'description': (
                        'Natural-language search query describing the kind of match to find, '
                        'e.g. "dramatic late comeback in the knockout rounds"'
                    ),
                }
            },
        },
    },
]

AGENT = {
    'id': AGENT_ID,
    'name': 'World Cup 2026 Predictor',
    'description': (
        'Ask me anything about the 2026 World Cup - form, stats, upcoming matches, memorable games, '
        'and predictions based on real tournament data.'
    ),
    'labels': ['worldcup', 'hacknight'],
    'avatar_color': '#16C47F',
    'avatar_symbol': '⚽',
    'configuration': {
        'instructions': (
            'You are a football analyst specialising in the 2026 FIFA World Cup in the USA, Mexico, and Canada.\n\n'
            'You have access to live tournament data: completed results, upcoming fixtures, team form, and '
            'natural-language stories of every match searchable with hybrid (lexical + semantic) search.\n\n'
            'When a user asks you to predict a match:\n'
            '1. Call get_upcoming_fixtures for each team to confirm they are actually scheduled to play\n'
            '2. Call get_team_stats_2026 for both teams to get their tournament numbers\n'
            '3. Call get_team_form for both teams to see their actual match-by-match results\n'
            '4. Produce a prediction structured as:\n'
            '   - Current form summary for each team (results so far, goals scored/conceded)\n'
            '   - Statistical edge: which team has the data advantage and why\n'
            '   - Key factors: 2-3 things that will decide this match\n'
            '   - Predicted scoreline and winner\n'
            '   - Confidence level: Low / Medium / High with one sentence of reasoning\n\n'
            'When a user asks a descriptive or fuzzy question - "any dramatic comebacks?", "closest games so far", '
            '"find me matches like a tense defensive final" - use search_match_stories. It runs hybrid search '
            '(BM25 + semantic vector search fused with RRF) over match narratives, so it understands meaning, '
            'not just keywords. You can also use it to add colour to predictions (e.g. find both teams\' most '
            'dramatic moments).\n\n'
            'Always ground your answers in the 2026 data.\n\n'
            'Keep your tone punchy and engaging.\n\n'
            'Only answer questions about the 2026 World Cup. Politely decline anything off-topic.'
        ),
        'tools': [
            {
                'tool_ids': [
                    'get_team_form',
                    'get_team_stats_2026',
                    'get_upcoming_fixtures',
                    'search_match_stories',
                ]
            }
        ],
    },
}


def kibana_headers(api_key):
    return {
        'Authorization': f'ApiKey {api_key}',
        'Content-Type': 'application/json',
        'kbn-xsrf': 'true',
    }


def create_agent_builder(kibana, api_key):
    print('\n🤖 Creating Agent Builder tools and agent ...')
    headers = kibana_headers(api_key)

    for tool in TOOLS:
        # Delete-then-create keeps the script idempotent across re-runs
        requests.delete(f'{kibana}/api/agent_builder/tools/{tool["id"]}', headers=headers, timeout=30)
        r = requests.post(f'{kibana}/api/agent_builder/tools', headers=headers, json=tool, timeout=30)
        if r.status_code >= 300:
            print(f'❌ Failed to create tool {tool["id"]}: {r.status_code} {r.text[:300]}')
            sys.exit(1)
        print(f'   ✅ Tool created: {tool["id"]}')

    requests.delete(f'{kibana}/api/agent_builder/agents/{AGENT_ID}', headers=headers, timeout=30)
    r = requests.post(f'{kibana}/api/agent_builder/agents', headers=headers, json=AGENT, timeout=30)
    if r.status_code >= 300:
        print(f'❌ Failed to create agent {AGENT_ID}: {r.status_code} {r.text[:300]}')
        sys.exit(1)
    print(f'   ✅ Agent created: {AGENT_ID} ("{AGENT["name"]}")')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='World Cup 2026 hack night setup')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--data-only', action='store_true', help='only ingest the two indices')
    group.add_argument('--agent-only', action='store_true', help='only create Agent Builder tools + agent')
    args = parser.parse_args()

    endpoint, kibana, api_key = get_config()

    if not args.agent_only:
        es = connect_es(endpoint, api_key)
        all_matches = fetch_matches()
        match_docs = ingest_matches(es, all_matches)
        ingest_stories(es, match_docs)

    if not args.data_only:
        create_agent_builder(kibana, api_key)

    print('\n🎉 Done! Open Kibana → Agents and chat with the World Cup 2026 Predictor.')
    print('   Try: "Find the most dramatic comebacks of the tournament so far"')


if __name__ == '__main__':
    main()
