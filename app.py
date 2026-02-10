from flask import Flask, render_template, request, jsonify, session
import requests
import json
import random
import os
from datetime import timedelta, datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

# Initialize cache
app.user_cache = {}
app.cache_timestamps = {}

ANILIST_API = 'https://graphql.anilist.co'
CACHE_EXPIRY_HOURS = 2

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent'

def cleanup_expired_cache():
    """Remove cache entries older than CACHE_EXPIRY_HOURS"""
    now = datetime.now()
    expired_keys = []
    
    for key, timestamp in app.cache_timestamps.items():
        if (now - timestamp).total_seconds() > CACHE_EXPIRY_HOURS * 3600:
            expired_keys.append(key)
    
    for key in expired_keys:
        if key in app.user_cache:
            del app.user_cache[key]
        if key in app.cache_timestamps:
            del app.cache_timestamps[key]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch_user', methods=['POST'])
def fetch_user():
    data = request.json
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    
    try:
        # Fetch user ID
        user_query = """
        query ($username: String) {
            User(name: $username) {
                id
                name
            }
        }
        """
        
        response = requests.post(
            ANILIST_API,
            json={'query': user_query, 'variables': {'username': username}},
            headers={'Content-Type': 'application/json'}
        )
        
        user_data = response.json()
        
        if 'errors' in user_data:
            return jsonify({'error': user_data['errors'][0]['message']}), 400
        
        user_id = user_data['data']['User']['id']
        
        # Fetch completed and planning lists
        lists_query = """
        query ($userId: Int) {
            completed: MediaListCollection(userId: $userId, type: ANIME, status: COMPLETED) {
                lists {
                    entries {
                        media {
                            id
                            title {
                                romaji
                                english
                            }
                            coverImage {
                                large
                                extraLarge
                            }
                            genres
                            tags {
                                name
                                rank
                            }
                            averageScore
                            studios {
                                nodes {
                                    name
                                }
                            }
                            description
                        }
                    }
                }
            }
            planning: MediaListCollection(userId: $userId, type: ANIME, status: PLANNING) {
                lists {
                    entries {
                        media {
                            id
                            title {
                                romaji
                                english
                            }
                            coverImage {
                                large
                                extraLarge
                            }
                            genres
                            tags {
                                name
                                rank
                            }
                            averageScore
                            studios {
                                nodes {
                                    name
                                }
                            }
                            description
                        }
                    }
                }
            }
        }
        """
        
        response = requests.post(
            ANILIST_API,
            json={'query': lists_query, 'variables': {'userId': user_id}},
            headers={'Content-Type': 'application/json'}
        )
        
        lists_data = response.json()
        
        if 'errors' in lists_data:
            return jsonify({'error': lists_data['errors'][0]['message']}), 400
        
        # Extract anime from lists - store full data temporarily
        completed = []
        for list_item in lists_data['data']['completed']['lists']:
            for entry in list_item['entries']:
                completed.append(entry['media'])
        
        planning = []
        for list_item in lists_data['data']['planning']['lists']:
            for entry in list_item['entries']:
                planning.append(entry['media'])
        
        if not completed:
            return jsonify({'error': 'No completed anime found in your list'}), 400
        
        if not planning:
            return jsonify({'error': 'No anime found in your planning list'}), 400
        
        # Sample 10 random completed anime
        sample_size = min(10, len(completed))
        sample = random.sample(completed, sample_size)
        
        # Store only IDs in session to avoid cookie size limits
        session['username'] = username
        session['user_id'] = user_id
        session['sample_ids'] = [anime['id'] for anime in sample]
        session['completed_ids'] = [anime['id'] for anime in completed]
        session['planning_ids'] = [anime['id'] for anime in planning]
        session['ratings'] = {}
        session['current_index'] = 0
        
        # Clean up expired cache entries
        cleanup_expired_cache()
        
        # Store the full data in server-side cache
        cache_key = f"{user_id}_{username}"
        app.user_cache[cache_key] = {
            'completed': completed,
            'planning': planning,
            'sample': sample
        }
        app.cache_timestamps[cache_key] = datetime.now()
        
        return jsonify({
            'success': True,
            'total_completed': len(completed),
            'total_planning': len(planning),
            'sample_size': sample_size
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch data: {str(e)}'}), 500

@app.route('/get_current_anime', methods=['GET'])
def get_current_anime():
    if 'sample_ids' not in session or 'user_id' not in session:
        return jsonify({'error': 'No session data found'}), 400
    
    # Get cached data
    cache_key = f"{session['user_id']}_{session['username']}"
    if cache_key not in app.user_cache:
        return jsonify({'error': 'Session expired. Please start over.'}), 400
    
    cached_data = app.user_cache[cache_key]
    sample = cached_data['sample']
    
    index = session.get('current_index', 0)
    
    if index >= len(sample):
        return jsonify({'done': True})
    
    anime = sample[index]
    title = anime['title']['english'] or anime['title']['romaji']
    
    # Get existing rating if any
    anime_id = str(anime['id'])
    existing_rating = session.get('ratings', {}).get(anime_id, {})
    
    return jsonify({
        'done': False,
        'index': index,
        'total': len(sample),
        'anime': {
            'id': anime['id'],
            'title': title,
            'coverImage': anime['coverImage']['extraLarge'] or anime['coverImage']['large'],
            'genres': anime['genres'],
        },
        'existingRating': existing_rating
    })

@app.route('/save_rating', methods=['POST'])
def save_rating():
    data = request.json
    anime_id = str(data.get('animeId'))
    score = data.get('score')
    reason = data.get('reason', '').strip()
    
    if not anime_id or score is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    if not reason:
        return jsonify({'error': 'Feedback is required'}), 400
    
    # Check word count
    words = reason.split()
    if len(words) > 10:
        return jsonify({'error': 'Feedback must be 10 words or less'}), 400
    
    # Save rating
    if 'ratings' not in session:
        session['ratings'] = {}
    
    ratings = session['ratings']
    ratings[anime_id] = {
        'score': score,
        'reason': reason
    }
    session['ratings'] = ratings
    session.modified = True
    
    return jsonify({'success': True})

@app.route('/navigate', methods=['POST'])
def navigate():
    data = request.json
    direction = data.get('direction', 'next')
    
    if 'sample_ids' not in session:
        return jsonify({'error': 'No session data found'}), 400
    
    # Get cached data
    cache_key = f"{session['user_id']}_{session['username']}"
    if cache_key not in app.user_cache:
        return jsonify({'error': 'Session expired. Please start over.'}), 400
    
    cached_data = app.user_cache[cache_key]
    sample = cached_data['sample']
    
    current_index = session.get('current_index', 0)
    
    if direction == 'next':
        current_index += 1
    elif direction == 'prev':
        current_index = max(0, current_index - 1)
    
    session['current_index'] = current_index
    session.modified = True
    
    return jsonify({'success': True, 'index': current_index})

@app.route('/generate_recommendations', methods=['POST'])
def generate_recommendations():
    try:
        if 'ratings' not in session or 'user_id' not in session:
            return jsonify({'error': 'No session data found'}), 400
        
        cache_key = f"{session['user_id']}_{session['username']}"
        cached_data = app.user_cache[cache_key]
        if not cached_data:
            return jsonify({'error': 'Session expired. Please start over.'}), 400
        
        sample = cached_data['sample']
        planning = cached_data['planning']
        planning_limited = sorted(planning, key=lambda x: x.get('averageScore') or 0, reverse=True)[:100]
        
        ratings = session.get('ratings', {})
        
        if not ratings:
            return jsonify({'error': 'No ratings found'}), 400
        
        # Prepare rated anime data
        rated_anime = []
        for anime in sample:
            anime_id = str(anime['id'])
            if anime_id in ratings:
                rated_anime.append({
                    'title': anime['title']['english'] or anime['title']['romaji'],
                    'genres': anime['genres'],
                    'tags': [tag['name'] for tag in anime['tags'] if tag['rank'] >= 60][:5],
                    'score': ratings[anime_id]['score'],
                    'reason': ratings[anime_id]['reason'],
                    'studio': [studio['name'] for studio in anime['studios']['nodes']][:2],
                    'description': (anime['description'] or '')[:200]
                })
        
        # Prepare planning anime data
        planning_anime = []
        for anime in planning_limited:
            planning_anime.append({
                'id': anime['id'],
                'title': anime['title']['english'] or anime['title']['romaji'],
                'genres': anime['genres'],
                'tags': [tag['name'] for tag in anime['tags'] if tag['rank'] >= 60][:5],
                'studio': [studio['name'] for studio in anime['studios']['nodes']][:2],
                'description': (anime['description'] or '')[:200],
                'averageScore': anime['averageScore'],
                'coverImage': anime['coverImage']['large']
            })
        
        # Create AI prompt
        prompt = f"""You are an expert anime recommendation system. Analyze the user's ratings and preferences to recommend anime from their planning list that they would likely rate 8 or above.

User's Rated Anime (with their scores and reasons):
{json.dumps(rated_anime, indent=2)}

Planning List (choose from these ONLY):
{json.dumps(planning_anime, indent=2)}

Task: Based on the user's ratings, reasons, and preferences, recommend the TOP 5 anime from the planning list that the user would most likely rate 8 or above.

Consider:
- Which genres and tags appear in their highly-rated anime
- The reasons they gave for their ratings
- Studio preferences
- Themes and story elements from descriptions
- Their rating patterns

For each recommendation, provide:
1. The anime title (MUST match exactly from planning list)
2. Predicted score (8.0-10.0 scale)
3. Detailed reasoning (explain why this matches their preferences)
4. Key matching elements

Respond ONLY with valid JSON in this exact format (no markdown, no code blocks):
[
  {{
    "title": "exact title from planning list",
    "predictedScore": 8.5,
    "reasoning": "Based on your love of X and Y, this anime features...",
    "matchingElements": ["element1", "element2", "element3"]
  }}
]"""

        # Check if API key is configured
        if not GEMINI_API_KEY:
            return jsonify({'error': 'Gemini API key not configured. Please set the GEMINI_API_KEY environment variable. Get your free key at: https://aistudio.google.com/app/apikey'}), 500
        
        # Call Google Gemini API
        api_url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
        
        api_response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            json={
                'contents': [{
                    'parts': [{
                        'text': prompt
                    }]
                }],
                'generationConfig': {
                    'temperature': 0.7,
                    'response_mime_type': 'application/json'
                }
            },
            timeout=30
        )
        
        if api_response.status_code != 200:
            error_detail = api_response.json() if api_response.text else {'error': 'Unknown error'}
            return jsonify({'error': f'Gemini API error: {json.dumps(error_detail)}'}), 500
        
        ai_data = api_response.json()
        
        # Extract text from Gemini response
        ai_text = ai_data['candidates'][0]['content']['parts'][0]['text']
        recommendations = json.loads(ai_text)
        
        # Match with full anime data
        full_recommendations = []
        for rec in recommendations:
            # Find matching anime
            matching_anime = None
            for anime in planning:
                title_en = anime['title']['english'] or ''
                title_ro = anime['title']['romaji'] or ''
                if rec['title'] == title_en or rec['title'] == title_ro:
                    matching_anime = anime
                    break
            
            if matching_anime:
                full_recommendations.append({
                    'id': matching_anime['id'],
                    'title': rec['title'],
                    'predictedScore': rec['predictedScore'],
                    'reasoning': rec['reasoning'],
                    'matchingElements': rec['matchingElements'],
                    'genres': matching_anime['genres'],
                    'coverImage': matching_anime['coverImage']['large'],
                    'averageScore': matching_anime['averageScore']
                })
        
        return jsonify({
            'success': True,
            'recommendations': full_recommendations
        })
        
    except requests.exceptions.Timeout:
        return jsonify({'error': 'The AI took too long to respond. Please try again.'}), 504    
    except Exception as e:
        return jsonify({'error': f'Failed to generate recommendations: {str(e)}'}), 500

@app.route('/reset', methods=['POST'])
def reset():
    # Clear cache if exists
    if 'user_id' in session and 'username' in session:
        cache_key = f"{session['user_id']}_{session['username']}"
        if cache_key in app.user_cache:
            del app.user_cache[cache_key]
        if cache_key in app.cache_timestamps:
            del app.cache_timestamps[cache_key]
    
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)