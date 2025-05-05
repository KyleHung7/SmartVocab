from flask import Flask, render_template, request, redirect, url_for, flash, session
import random
import os
from dotenv import load_dotenv
import requests
import json
from datetime import datetime
import re

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')

# Gemini API configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent'

# In-memory storage
users = {}  # {username: user_id}
vocabularies = []  # List of dicts: {'id': int, 'prefix': str, 'suffix': str, 'english': str, 'chinese': str, 'user_id': int}
progress_records = []  # List of dicts: {'id': int, 'user_id': int, 'vocab_id': int, 'correct': bool, 'mode': str, 'timestamp': datetime}
next_user_id = 1
next_vocab_id = 1
next_progress_id = 1

# Predefined vocabulary by prefix and suffix
PREDEFINED_VOCAB = [
    # Prefix: pre-
    {"prefix": "pre-", "suffix": "", "english": "predict", "chinese": "預測"},
    {"prefix": "pre-", "suffix": "", "english": "prepare", "chinese": "準備"},
    {"prefix": "pre-", "suffix": "", "english": "prevent", "chinese": "防止"},
    # Prefix: un-
    {"prefix": "un-", "suffix": "", "english": "undo", "chinese": "撤銷"},
    {"prefix": "un-", "suffix": "", "english": "unlike", "chinese": "不像"},
    {"prefix": "un-", "suffix": "", "english": "unaware", "chinese": "未察覺"},
    # Suffix: -tion
    {"prefix": "", "suffix": "-tion", "english": "education", "chinese": "教育"},
    {"prefix": "", "suffix": "-tion", "english": "information", "chinese": "資訊"},
    {"prefix": "", "suffix": "-tion", "english": "solution", "chinese": "解決方案"},
    # Suffix: -able
    {"prefix": "", "suffix": "-able", "english": "comfortable", "chinese": "舒適的"},
    {"prefix": "", "suffix": "-able", "english": "reliable", "chinese": "可靠的"},
    {"prefix": "", "suffix": "-able", "english": "available", "chinese": "可用的"},
]

# Define group order for sorting
GROUP_PREFIXES = ['pre-', 'un-']
GROUP_SUFFIXES = ['-tion', '-able']

# Function to generate sentence using Gemini API
def generate_sentence(word):
    if not GEMINI_API_KEY:
        return f"Placeholder sentence with {word}."
    
    headers = {
        'Content-Type': 'application/json',
    }
    payload = {
        "contents": [{
            "parts": [{
                "text": f"Generate a short English sentence (5-10 words) using the exact word '{word}' (not a variation like '{word}ing' or '{word}s'). The sentence should be simple, clear, and suitable for vocabulary learning. Ensure '{word}' appears exactly once."
            }]
        }]
    }
    
    try:
        response = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        if 'candidates' in result and result['candidates']:
            sentence = result['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()
            # Verify the word appears exactly once
            if sentence.lower().count(word.lower()) != 1:
                return f"Invalid sentence for {word}: word does not appear exactly once."
            return sentence
        return f"No valid response from API for {word}."
    except Exception as e:
        print(f"Error generating sentence: {e}")
        return f"Failed to generate sentence for {word}. Try again later."

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    global next_user_id, next_vocab_id
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            flash('Username is required!', 'danger')
            return redirect(url_for('login'))
        if username not in users:
            users[username] = next_user_id
            user_id = next_user_id
            next_user_id += 1
            # Add predefined vocabulary for new user
            for vocab in PREDEFINED_VOCAB:
                vocabularies.append({
                    'id': next_vocab_id,
                    'prefix': vocab['prefix'] or '',
                    'suffix': vocab['suffix'] or '',
                    'english': vocab['english'].strip(),
                    'chinese': vocab['chinese'].strip(),
                    'user_id': user_id
                })
                next_vocab_id += 1
        session['user_id'] = users[username]
        print(f"Login: username={username}, user_id={session['user_id']}")
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/word_quiz', methods=['GET', 'POST'])
def word_quiz():
    global next_progress_id
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    direction = request.args.get('direction', 'eng_to_chi')
    user_vocab = [v for v in vocabularies if v['user_id'] == session['user_id']]
    
    if not user_vocab:
        flash('Please add vocabulary first!', 'warning')
        return redirect(url_for('manage_vocab'))
    
    # To prevent a mismatch between the displayed word and the validated word,
    # a hidden `vocab_id` field is included in the form to ensure consistency.
    if request.method == 'POST':
        vocab_id = request.form.get('vocab_id')
        user_answer = request.form.get('answer', '').strip()
        # Find the word by vocab_id to ensure consistency
        word = next((v for v in user_vocab if str(v['id']) == vocab_id), None)
        if not word:
            flash('Invalid vocabulary selection!', 'danger')
            return redirect(url_for('word_quiz', direction=direction))
        
        expected_answer = (word['chinese'] if direction == 'eng_to_chi' else word['english']).strip()
        correct = user_answer == expected_answer if direction == 'eng_to_chi' else user_answer.lower() == expected_answer.lower()
        print(f"Word Quiz: vocab_id={vocab_id}, question={word['english' if direction == 'eng_to_chi' else 'chinese']}, "
              f"user_answer={user_answer}, expected={expected_answer}, correct={correct}")
        
        progress_records.append({
            'id': next_progress_id,
            'user_id': session['user_id'],
            'vocab_id': word['id'],
            'correct': correct,
            'mode': 'word_quiz',
            'timestamp': datetime.now()
        })
        next_progress_id += 1
        
        flash('Correct!' if correct else f'Incorrect. The answer is {expected_answer}', 
              'success' if correct else 'danger')
        
        return redirect(url_for('word_quiz', direction=direction))
    
    # Select a random word for GET request
    word = random.choice(user_vocab)
    return render_template('word_quiz.html', 
                         word=word, 
                         direction=direction,
                         question=word['english'] if direction == 'eng_to_chi' else word['chinese'])

@app.route('/sentence_quiz', methods=['GET', 'POST'])
def sentence_quiz():
    global next_progress_id
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_vocab = [v for v in vocabularies if v['user_id'] == session['user_id']]
    
    if not user_vocab:
        flash('Please add vocabulary first!', 'warning')
        return redirect(url_for('manage_vocab'))
    
    if request.method == 'POST':
        vocab_id = request.form.get('vocab_id')
        user_answer = request.form.get('answer', '').strip()
        # Find the word by vocab_id to ensure consistency
        word = next((v for v in user_vocab if str(v['id']) == vocab_id), None)
        if not word:
            flash('Invalid vocabulary selection!', 'danger')
            return redirect(url_for('sentence_quiz'))
        
        expected_answer = word['english'].strip()
        correct = user_answer.lower() == expected_answer.lower()
        print(f"Sentence Quiz: vocab_id={vocab_id}, user_answer={user_answer}, "
              f"expected={expected_answer}, correct={correct}")
        
        progress_records.append({
            'id': next_progress_id,
            'user_id': session['user_id'],
            'vocab_id': word['id'],
            'correct': correct,
            'mode': 'sentence_quiz',
            'timestamp': datetime.now()
        })
        next_progress_id += 1
        
        flash('Correct!' if correct else f'Incorrect. The answer is {expected_answer}', 
              'success' if correct else 'danger')
        
        return redirect(url_for('sentence_quiz'))
    
    # Select a random word for GET request
    word = random.choice(user_vocab)
    sentence = generate_sentence(word['english'])
    
    if "Failed" in sentence or "Invalid" in sentence:
        flash('Error generating sentence. Try again.', 'danger')
        return redirect(url_for('sentence_quiz'))
    
    # Replace the word with a blank (case-insensitive)
    blanked_sentence = re.sub(r'\b' + re.escape(word['english']) + r'\b', '____', sentence, flags=re.IGNORECASE)
    return render_template('sentence_quiz.html', sentence=blanked_sentence, word=word)

@app.route('/manage_vocab', methods=['GET', 'POST'])
def manage_vocab():
    global next_vocab_id
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        prefix = request.form.get('prefix', '').strip()
        suffix = request.form.get('suffix', '').strip()
        english = request.form.get('english', '').strip()
        chinese = request.form.get('chinese', '').strip()
        
        if not (english and chinese):
            flash('English and Chinese fields are required!', 'danger')
            return redirect(url_for('manage_vocab'))
        
        # Check for duplicates
        if any(v['english'] == english and v['user_id'] == session['user_id'] for v in vocabularies):
            flash('This English word already exists in your vocabulary!', 'danger')
            return redirect(url_for('manage_vocab'))
        
        vocabularies.append({
            'id': next_vocab_id,
            'prefix': prefix,
            'suffix': suffix,
            'english': english,
            'chinese': chinese,
            'user_id': session['user_id']
        })
        next_vocab_id += 1
        flash('Vocabulary added successfully!', 'success')
        return redirect(url_for('manage_vocab'))
    
    user_vocab = [v for v in vocabularies if v['user_id'] == session['user_id']]
    # Sort vocabulary by prefix, suffix, and then english word
    user_vocab.sort(key=lambda x: (
        GROUP_PREFIXES.index(x['prefix']) if x['prefix'] in GROUP_PREFIXES else len(GROUP_PREFIXES),
        GROUP_SUFFIXES.index(x['suffix']) if x['suffix'] in GROUP_SUFFIXES else len(GROUP_SUFFIXES),
        x['english'].lower()
    ))
    print(f"Manage Vocab GET: user_id={session.get('user_id')}, vocab_count={len(user_vocab)}")
    return render_template('manage_vocab.html', vocab_list=user_vocab)

@app.route('/edit_vocab/<int:vocab_id>', methods=['GET', 'POST'])
def edit_vocab(vocab_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    vocab = next((v for v in vocabularies if v['id'] == vocab_id and v['user_id'] == session['user_id']), None)
    if not vocab:
        flash('Vocabulary not found or not authorized!', 'danger')
        return redirect(url_for('manage_vocab'))
    
    if request.method == 'POST':
        prefix = request.form.get('prefix', '').strip()
        suffix = request.form.get('suffix', '').strip()
        english = request.form.get('english', '').strip()
        chinese = request.form.get('chinese', '').strip()
        
        if not (english and chinese):
            flash('English and Chinese fields are required!', 'danger')
            return redirect(url_for('edit_vocab', vocab_id=vocab_id))
        
        # Check for duplicates (excluding current vocab)
        if any(v['english'] == english and v['user_id'] == session['user_id'] and v['id'] != vocab_id for v in vocabularies):
            flash('This English word already exists in your vocabulary!', 'danger')
            return redirect(url_for('edit_vocab', vocab_id=vocab_id))
        
        # Update vocabulary
        vocab['prefix'] = prefix
        vocab['suffix'] = suffix
        vocab['english'] = english
        vocab['chinese'] = chinese
        flash('Vocabulary updated successfully!', 'success')
        return redirect(url_for('manage_vocab'))
    
    return render_template('edit_vocab.html', vocab=vocab)

@app.route('/delete_vocab/<int:vocab_id>', methods=['POST'])
def delete_vocab(vocab_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    global vocabularies, progress_records
    print(f"Delete Vocab: vocab_id={vocab_id}, user_id={session.get('user_id')}")
    vocab = next((v for v in vocabularies if v['id'] == vocab_id and v['user_id'] == session['user_id']), None)
    if vocab:
        try:
            vocabularies[:] = [v for v in vocabularies if v['id'] != vocab_id]
            progress_records[:] = [p for p in progress_records if p['vocab_id'] != vocab_id]
            flash('Vocabulary deleted successfully!', 'success')
        except Exception as e:
            print(f"Error deleting vocabulary: {e}")
            flash(f'Error deleting vocabulary: {str(e)}', 'danger')
    else:
        print(f"Vocab not found: vocab_id={vocab_id}, user_id={session.get('user_id')}")
        flash('Vocabulary not found or not authorized!', 'danger')
    
    return redirect(url_for('manage_vocab'))

@app.route('/progress')
def progress():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_progress = [p for p in progress_records if p['user_id'] == session['user_id']]
    # Attach vocabulary details for rendering
    for record in user_progress:
        vocab = next((v for v in vocabularies if v['id'] == record['vocab_id']), None)
        record['vocabulary'] = vocab if vocab else {'english': 'Deleted Word', 'chinese': ''}
    print(f"Progress: user_id={session.get('user_id')}, progress_count={len(user_progress)}")
    return render_template('progress.html', progress_records=user_progress)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)