# StudyBuddyWB টেলিগ্রাম বট: সম্পূর্ণ কোড

# প্রথম অংশ: ইমপোর্ট এবং ডাটা
import sqlite3
import json
import random
import logging
import re
from typing import Dict, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from fuzzywuzzy import fuzz
from transformers import pipeline
import nest_asyncio
nest_asyncio.apply()

# লগিং সেটআপ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ডাটাবেস ইনিশিয়ালাইজেশন
def init_db():
    conn = sqlite3.connect('user_points.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS points (user_id INTEGER PRIMARY KEY, points INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (user_id INTEGER, rating INTEGER, comment TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS study_partners (user_id INTEGER PRIMARY KEY, class_level TEXT, board TEXT, subjects TEXT, study_time TEXT)''')
    conn.commit()
    conn.close()

init_db()

# পয়েন্ট যোগ করা
def add_points(user_id: int, points: int):
    conn = sqlite3.connect('user_points.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO points (user_id, points) VALUES (?, COALESCE((SELECT points FROM points WHERE user_id = ?) + ?, ?))",
              (user_id, user_id, points, points))
    conn.commit()
    conn.close()

# ফিডব্যাক সেভ
def save_feedback(user_id: int, rating: Optional[int], comment: str):
    conn = sqlite3.connect('user_points.db')
    c = conn.cursor()
    c.execute("INSERT INTO feedback (user_id, rating, comment) VALUES (?, ?, ?)", (user_id, rating, comment))
    conn.commit()
    conn.close()

# স্টাডি পার্টনার সেভ এবং ম্যাচিং
def save_study_partner(user_id: int, class_level: str, board: str, subjects: str, study_time: str):
    conn = sqlite3.connect('user_points.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO study_partners (user_id, class_level, board, subjects, study_time) VALUES (?, ?, ?, ?, ?)",
              (user_id, class_level, board, subjects, study_time))
    conn.commit()
    conn.close()

def find_study_partner(user_id: int, class_level: str, board: str, subjects: str) -> list:
    conn = sqlite3.connect('user_points.db')
    c = conn.cursor()
    c.execute("SELECT user_id, class_level, board, subjects, study_time FROM study_partners WHERE user_id != ? AND class_level = ? AND board = ?",
              (user_id, class_level, board))
    matches = c.fetchall()
    conn.close()
    return [m for m in matches if any(subj in m[3] for subj in subjects.split("-"))]

# ডাটা (ইনটেন্ট, রেসপন্স, কুইজ, ইত্যাদি)
intents_data = [
    {"intent": "greeting", "text": "হাই, হ্যালো, কেমন আছো"},
    {"intent": "quiz_query", "text": "কুইজ, কুইজ দাও, ম্যাথ কুইজ, সায়েন্স কুইজ"},
    {"intent": "math_logic", "text": "ম্যাথ লজিক, লজিক প্রশ্ন"},
    {"intent": "doctor_career", "text": "ডাক্তার হতে চাই, ডাক্তারি পড়া"},
    {"intent": "neet_preparation", "text": "NEET প্রিপারেশন, NEET টিপস"},
    {"intent": "jee_preparation", "text": "JEE প্রিপারেশন, JEE টিপস"},
    {"intent": "upsc_preparation", "text": "UPSC প্রিপারেশন, UPSC টিপস"},
    {"intent": "ssc_preparation", "text": "SSC প্রিপারেশন, SSC টিপস"},
    {"intent": "ca_career", "text": "CA হতে চাই, চার্টার্ড অ্যাকাউন্ট্যান্ট"},
    {"intent": "gate_preparation", "text": "GATE প্রিপারেশন, GATE টিপস"},
    {"intent": "nda_preparation", "text": "NDA প্রিপারেশন, NDA টিপস"},
    {"intent": "rrb_group_d", "text": "RRB Group D প্রিপারেশন"},
    {"intent": "wbjee_preparation", "text": "WBJEE প্রিপারেশন, WBJEE টিপস"},
    {"intent": "ssc_mts", "text": "SSC MTS প্রিপারেশন"},
    {"intent": "ctet_preparation", "text": "CTET প্রিপারেশন, CTET টিপস"},
    {"intent": "medical_duration", "text": "ডাক্তারি পড়তে কত বছর লাগে"},
    {"intent": "medical_cost", "text": "ডাক্তারি পড়ার খরচ"},
    {"intent": "doctor_specialization", "text": "ডাক্তারি স্পেশালাইজেশন"},
    {"intent": "study_tip", "text": "পড়ার টিপস, স্টাডি টিপস"},
    {"intent": "smart_suggestion", "text": "পড়ার রুটিন, স্মার্ট সাজেশন"},
    {"intent": "gk_query", "text": "জেনারেল নলেজ, GK"},
    {"intent": "dictionary", "text": "অর্থ, শব্দের অর্থ"},
    {"intent": "wb_history", "text": "পশ্চিমবঙ্গের ইতিহাস, বাংলার ইতিহাস"},
    {"intent": "psychology_fact", "text": "সাইকোলজি ফ্যাক্ট, মনস্তত্ত্ব"},
    {"intent": "relationship_advice", "text": "রিলেশনশিপ পরামর্শ, সম্পর্ক"},
    {"intent": "study_partner", "text": "পড়ার পার্টনার, স্টাডি পার্টনার"},
    {"intent": "feedback", "text": "ফিডব্যাক, মতামত"},
    {"intent": "share", "text": "শেয়ার, বন্ধুদের বলো"},
    {"intent": "joke", "text": "জোকস, মজার গল্প"},
    {"intent": "puzzle", "text": "পাজল, ধাঁধা"},
    {"intent": "poem", "text": "কবিতা, কবিতা শোনাও"},
    {"intent": "book_suggestion", "text": "বই সাজেশন, বইয়ের নাম"},
    {"intent": "bodmas_calc", "text": "BODMAS, অংক করো"},
    {"intent": "casual_chat", "text": "কী খবর, কী করছি"},
    {"intent": "career_continue", "text": "আরও জানতে চাই, ক্যারিয়ার"},
]

responses = {
    "greeting": (
        "হাই! কেমন আছো? 😄\n"
        "কী নিয়ে কথা বলতে চাও?\n"
        "- পড়াশোনার টিপস\n"
        "- কুইজ বা ম্যাথ লজিক\n"
        "- ক্যারিয়ার গাইড\n"
        "- জোকস, কবিতা, পাজল\n"
        "বলো, কী চাও?"
    ),
    "about_us": (
        "আমি @StudyBuddyWB, MythraLux দ্বারা তৈরি! 😎\n"
        "ভার্সন: v1.0 Supreme\n"
        "আমার কাজ? তোমার পড়াশোনা আর ক্যারিয়ারকে সুপার ফান আর সহজ করে দেওয়া!\n"
        "কী চাও? /help দিয়ে দেখো!"
    ),
    "feedback": (
        "আমাকে কেমন লাগল? 😊\n"
        "১ থেকে ৫ এর মধ্যে রেটিং দাও (১=খারাপ, ৫=দারুণ)।\n"
        "অথবা কোনো মতামত থাকলে বলো!"
    ),
    "share": (
        "আমাকে বন্ধুদের সাথে শেয়ার করো! 😄\n"
        "লিঙ্ক: t.me/StudyBuddyWB\n"
        "তুমি ১০ পয়েন্ট পেলে! 🌟"
    ),
    "neet_preparation": (
        "NEET প্রিপারেশনের জন্য টিপস:\n"
        "- NCERT বই ভালো করে পড়ো, বিশেষ করে বায়োলজি।\n"
        "- ফিজিক্সে HC Verma আর DC Pandey প্র্যাকটিস করো।\n"
        "- প্রতিদিন ১০০-১৫০ MCQ সলভ করো।\n"
        "- মক টেস্ট দিয়ে সময় ম্যানেজমেন্ট শেখো।\n"
        "আরও কিছু জানতে চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
    ),
}

quiz_data = {
    "math": [
        {"question": "২ + ৩ * ৪ = ?", "answer": "১৪"},
        {"question": "১০০ এর ১৫% কত?", "answer": "১৫"},
    ],
    "science": [
        {"question": "পানির রাসায়নিক সূত্র কী?", "answer": "H2O"},
        {"question": "গ্রাভিটি আবিষ্কার করেন কে?", "answer": "নিউটন"},
    ],
    "gk": [
        {"question": "ভারতের রাজধানী কী?", "answer": "দিল্লি"},
        {"question": "পশ্চিমবঙ্গের রাজধানী কী?", "answer": "কলকাতা"},
    ],
}

physics_math_logic = [
    {"question": "৩, ৬, ১২, ২৪, ? পরের সংখ্যা কী?", "answer": "৪৮", "explanation": "প্রতিটি সংখ্যা আগেরটির দ্বিগুণ।"},
    {"question": "একটি গাড়ি ৬০ কিমি/ঘণ্টা গতিতে ৩ ঘণ্টা চলে। দূরত্ব কত?", "answer": "১৮০ কিমি", "explanation": "দূরত্ব = গতি * সময় = ৬০ * ৩ = ১৮০ কিমি।"},
]

study_tips = [
    "পড়ার সময় ছোট ছোট ব্রেক নাও, যেমন ২৫ মিনিট পড়া, ৫ মিনিট রেস্ট।",
    "নোট তৈরি করো, মনে রাখতে সহজ হবে।",
    "গ্রুপ স্টাডি করো, বন্ধুদের সাথে আলোচনা মজার।",
]

book_suggestions = {
    "class_10_wbbse": ["পাঠ্যপুস্তক (WBBSE)", "এবিসি ম্যাথেমেটিক্স", "ফিজিক্যাল সায়েন্স (রায় এন্ড মার্টিন)"],
    "neet": ["NCERT Biology", "HC Verma Physics", "DC Pandey Objective Physics"],
    "jee": ["HC Verma Physics", "RD Sharma Mathematics", "NCERT Chemistry"],
}

wb_history_facts = [
    "পশ্চিমবঙ্গ ১৯৪৭ সালে ভারত ভাগের সময় গঠিত হয়।",
    "রবীন্দ্রনাথ ঠাকুর পশ্চিমবঙ্গের গর্ব, তিনি প্রথম নোবেল পুরস্কার জয়ী ভারতীয়।",
]

psychology_facts = [
    "মানুষ দিনে গড়ে ৭০,০০০ বার চিন্তা করে।",
    "নীল রঙ মনকে শান্ত করে।",
]

jokes = [
    "প্রশ্ন: ম্যাথ কেন কাঁদে? উত্তর: কারণ তার অনেক সমস্যা! 😅",
    "প্রশ্ন: কোন স্কুলে ভূত পড়ে? উত্তর: ভূত বিদ্যালয়! 👻",
]

puzzles = [
    {"question": "আমার ৩টি মুখ আছে, কিন্তু চোখ নেই। আমি কী?", "answer": "মুদ্রা"},
    {"question": "৫, ১০, ২০, ৪০, ? পরের সংখ্যা কী?", "answer": "৮০"},
]

poems = [
    "আকাশে মেঘের নাচন, মনের কোণে স্বপন।",
    "নদীর কলতানে, জীবনের গান বাজে।",
]

dictionary = {
    "hope": "আশা",
    "success": "সাফল্য",
    "study": "পড়াশোনা",
}

# NLP ক্লাসিফায়ার
classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

# দ্বিতীয় অংশ: হেল্পার ফাংশন এবং কমান্ড হ্যান্ডলার
def save_context(user_id: int, context_data: Dict):
    try:
        with open(f'context_{user_id}.json', 'w', encoding='utf-8') as f:
            json.dump(context_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving context for user {user_id}: {e}")

def load_context(user_id: int) -> Dict:
    try:
        with open(f'context_{user_id}.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"last_command": None, "last_topic": None, "current_quiz": None, "current_mathlogic": None, "awaiting_feedback": False, "awaiting_study_partner": False, "awaiting_book_suggestion": False, "awaiting_bodmas": False}
    except Exception as e:
        logger.error(f"Error loading context for user {user_id}: {e}")
        return {}

def detect_banglish(text: str) -> bool:
    banglish_pattern = re.compile(r'[a-zA-Z]+[a-zA-Z0-9]*')
    words = text.split()
    banglish_count = sum(1 for word in words if banglish_pattern.match(word))
    return banglish_count > len(words) / 2

def evaluate_bodmas(expression: str) -> str:
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        explanation = (
            f"BODMAS অনুযায়ী:\n"
            f"- ব্র্যাকেট প্রথমে\n"
            f"- তারপর অর্ডার (যেমন, পাওয়ার)\n"
            f"- তারপর ডিভিশন/মাল্টিপ্লিকেশন (বাঁ থেকে ডানে)\n"
            f"- তারপর অ্যাডিশন/সাবট্রাকশন\n"
            f"তোমার অংক: {expression} = {result}"
        )
        return explanation
    except Exception as e:
        return f"দুঃখিত, অংকটা ঠিক নয়। 😅 উদাহরণ: ২ + ৩ * ৪"

def get_user_tone(text: str) -> str:
    text = text.lower()
    if any(word in text for word in ["চিন্তিত", "ভয়", "সমস্যা", "কঠিন"]):
        return "worried"
    elif any(word in text for word in ["খুশি", "দারুণ", "ভালো", "উৎসাহ"]):
        return "excited"
    elif any(word in text for word in ["কী", "কেন", "কীভাবে", "?"]):
        return "curious"
    else:
        return "neutral"

def predict_intent(user_input: str) -> str:
    user_input = user_input.lower().strip()
    max_score = 0
    matched_intent = "unknown"
    for item in intents_data:
        score = fuzz.partial_ratio(user_input, item["text"].lower())
        if score > max_score and score > 85:
            max_score = score
            matched_intent = item["intent"]
    if matched_intent == "unknown":
        try:
            scores = classifier(user_input, candidate_labels=[item["intent"] for item in intents_data], multi_label=False)
            matched_intent = scores["labels"][0]
        except Exception as e:
            logger.error(f"Error in NLP prediction: {e}")
            matched_intent = "casual_chat"
    return matched_intent

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    add_points(user_id, 5)
    context_data = load_context(user_id)
    context_data["last_command"] = "start"
    save_context(user_id, context_data)
    welcome_message = (
        "হাই! আমি @StudyBuddyWB, তোমার পড়াশোনার বন্ধু! 😎\n"
        "আমি কী কী করতে পারি?\n"
        "- 📚 পড়ার টিপস, রুটিন, বই সাজেশন\n"
        "- 🧠 কুইজ, ম্যাথ লজিক, পাজল\n"
        "- 💼 ক্যারিয়ার গাইড (NEET, JEE, UPSC, SSC...)\n"
        "- 😄 জোকস, কবিতা, মোটিভেশন\n"
        "- 👥 পড়ার পার্টনার খুঁজে দেওয়া\n"
        "কী চাও? নিচের কমান্ড ট্রাই করো বা বলো:\n"
        "- /quiz: কুইজ নাও\n"
        "- /help: সাহায্য\n"
        "- /about: আমাদের সম্পর্কে\n"
        "- /feedback: মতামত দাও\n"
        "- /share: বন্ধুদের বলো\n"
        "তুমি ৫ পয়েন্ট পেলে! 🌟"
    )
    await update.message.reply_text(welcome_message)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    add_points(user_id, 5)
    context_data = load_context(user_id)
    context_data["last_command"] = "help"
    save_context(user_id, context_data)
    help_message = (
        "আমি তোমার পড়াশোনার বন্ধু! 😄 এখানে কমান্ড:\n"
        "- /start: শুরু করো\n"
        "- /quiz: কুইজ নাও (ম্যাথ, সায়েন্স, GK)\n"
        "- /help: সাহায্য\n"
        "- /about: আমাদের সম্পর্কে\n"
        "- /feedback: রেটিং বা মতামত দাও\n"
        "- /share: বট শেয়ার করো\n"
        "অন্য কিছু চাও? যেমন:\n"
        "- পড়ার টিপস\n"
        "- ক্যারিয়ার গাইড (NEET, JEE, UPSC...)\n"
        "- জোকস, কবিতা, পাজল\n"
        "বলো, কী নিয়ে কথা বলব? তুমি ৫ পয়েন্ট পেলে! 🌟"
    )
    await update.message.reply_text(help_message)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    add_points(user_id, 5)
    context_data = load_context(user_id)
    context_data["last_command"] = "about"
    save_context(user_id, context_data)
    await update.message.reply_text(responses["about_us"])

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    context_data = load_context(user_id)
    context_data["last_command"] = "feedback"
    context_data["awaiting_feedback"] = True
    save_context(user_id, context_data)
    add_points(user_id, 5)
    await update.message.reply_text(responses["feedback"])

async def share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    add_points(user_id, 10)
    context_data = load_context(user_id)
    context_data["last_command"] = "share"
    save_context(user_id, context_data)
    await update.message.reply_text(responses["share"])

# তৃতীয় + চতুর্থ অংশ: handle_message ফাংশন
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_input = update.message.text.strip()
    logger.info(f"User {user_id} input: {user_input}")
    
    # বাংলিশ শনাক্তকরণ
    if detect_banglish(user_input):
        await update.message.reply_text(
            "দুঃখিত, তুমি মনে হয় বাংলিশে লিখেছ। 😅 দয়া করে বাংলা বা ইংরেজিতে লেখো, যাতে আমি ভালো বুঝতে পারি! 😊 কী বলতে চাও?"
        )
        add_points(user_id, 2)
        return
    
    # ইউজার টোন শনাক্তকরণ
    user_tone = get_user_tone(user_input)
    tone_response = ""
    if user_tone == "worried":
        tone_response = "চিন্তা করো না, আমি তোমাকে সাহায্য করব! 😊 "
    elif user_tone == "excited":
        tone_response = "দারুণ, তোমার উৎসাহ দেখে ভালো লাগছে! 😎 "
    elif user_tone == "curious":
        tone_response = "কৌতূহলী মন? চলো, জেনে নিই! 😄 "
    
    # কনটেক্সট লোড
    context_data = load_context(user_id)
    
    # ফিডব্যাক মোড
    if context_data.get("awaiting_feedback", False):
        rating_pattern = r'^\s*[1-5]\s*$'
        if re.match(rating_pattern, user_input):
            rating = int(user_input)
            save_feedback(user_idವಿಷ್ಕারে save_feedback(user_id, rating, "")
            context_data["awaiting_feedback"] = False
            save_context(user_id, context_data)
            await update.message.reply_text(
                f"ধন্যবাদ {rating}/৫ রেটিং দেওয়ার জন্য! 😊 আর কিছু বলতে চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            add_points(user_id, 5)
            return
        else:
            save_feedback(user_id, None, user_input)
            context_data["awaiting_feedback"] = False
            save_context(user_id, context_data)
            await update.message.reply_text(
                f"ধন্যবাদ তোমার মতামতের জন্য! 😊 '{user_input}' নোট করলাম। আর কী নিয়ে কথা বলতে চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            add_points(user_id, 5)
            return
    
    # ইনটেন্ট প্রেডিক্ট
    intent = predict_intent(user_input)
    logger.info(f"Predicted intent: {intent}")
    context_data["last_topic"] = intent
    save_context(user_id, context_data)
    
    # ইনটেন্ট হ্যান্ডলিং
    if intent == "greeting":
        await update.message.reply_text(tone_response + responses["greeting"])
        add_points(user_id, 5)
    
    elif intent == "quiz_query":
        if context_data.get("current_quiz"):
            current_quiz = context_data["current_quiz"]
            if user_input.lower() == current_quiz["answer"].lower():
                response = (
                    "শাবাশ! সঠিক উত্তর! 🎉\n"
                    "আরেকটা কুইজ চাও? বলো: ম্যাথ, সায়েন্স, বা জেনারেল নলেজ।\n"
                    "তুমি ১০ পয়েন্ট পেলে! 🌟"
                )
                context_data["current_quiz"] = None
                add_points(user_id, 10)
            else:
                response = (
                    f"ভুল হয়ে গেছে। 😅 সঠিক উত্তর: {current_quiz['answer']}।\n"
                    "আরেকটা কুইজ চাও? বলো: ম্যাথ, সায়েন্স, বা জেনারেল নলেজ।"
                )
                context_data["current_quiz"] = None
                add_points(user_id, 2)
        else:
            quiz_type = None
            if any(word in user_input.lower() for word in ["ম্যাথ", "math"]):
                quiz_type = "math"
            elif any(word in user_input.lower() for word in ["সায়েন্স", "science"]):
                quiz_type = "science"
            elif any(word in user_input.lower() for word in ["জেনারেল নলেজ", "gk"]):
                quiz_type = "gk"
            if quiz_type and quiz_data.get(quiz_type):
                question = random.choice(quiz_data[quiz_type])
                context_data["current_quiz"] = question
                response = (
                    f"{tone_response}চলো, একটা {quiz_type} কুইজ! 😄\n"
                    f"প্রশ্ন: {question['question']}\n"
                    "উত্তর দাও! তুমি ৫ পয়েন্ট পেলে! 🌟"
                )
                add_points(user_id, 5)
            else:
                response = (
                    f"{tone_response}কুইজ নিতে চাও? 😄 কোনটা চাও?\n"
                    "- ম্যাথ\n"
                    "- সায়েন্স\n"
                    "- জেনারেল নলেজ\n"
                    "বলো, কোনটা দিব? তুমি ৫ পয়েন্ট পেলে! 🌟"
                )
                add_points(user_id, 5)
        save_context(user_id, context_data)
        await update.message.reply_text(response)
    
    elif intent == "math_logic":
        if context_data.get("current_mathlogic"):
            current_logic = context_data["current_mathlogic"]
            if user_input.lower() == current_logic["answer"].lower():
                response = (
                    "দারুণ! সঠিক উত্তর! 🎉\n"
                    f"ব্যাখ্যা: {current_logic['explanation']}\n"
                    "আরেকটা লজিক প্রশ্ন চাও? তুমি ১০ পয়েন্ট পেলে! 🌟"
                )
                context_data["current_mathlogic"] = None
                add_points(user_id, 10)
            else:
                response = (
                    f"ভুল হয়ে গেছে। 😅 সঠিক উত্তর: {current_logic['answer']}।\n"
                    f"ব্যাখ্যা: {current_logic['explanation']}\n"
                    "আরেকটা প্রশ্ন চাও? তুমি ২ পয়েন্ট পেলে! 🌟"
                )
                context_data["current_mathlogic"] = None
                add_points(user_id, 2)
        else:
            logic = random.choice(physics_math_logic)
            context_data["current_mathlogic"] = logic
            response = (
                f"{tone_response}চলো, একটা ম্যাথ লজিক প্রশ্ন! 😎\n"
                f"প্রশ্ন: {logic['question']}\n"
                "উত্তর দাও! তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            add_points(user_id, 5)
        save_context(user_id, context_data)
        await update.message.reply_text(response)
    
    elif intent in ["doctor_career", "neet_preparation", "jee_preparation", "upsc_preparation",
                    "ssc_preparation", "ca_career", "gate_preparation", "nda_preparation",
                    "rrb_group_d", "wbjee_preparation", "ssc_mts", "ctet_preparation",
                    "medical_duration", "medical_cost", "doctor_specialization"]:
        response = tone_response + responses.get(intent, "এই ক্যারিয়ার নিয়ে বিস্তারিত তথ্য শিগগিরই যোগ করব! 😊")
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "study_tip":
        tip = random.choice(study_tips)
        response = (
            f"{tone_response}পড়াশোনায় মন বসাতে চাও? এখানে একটা টিপস:\n"
            f"- {tip}\n"
            "আরেকটা টিপস চাও? 😄 তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "smart_suggestion":
        suggestion = random.choice(book_suggestions["class_10_wbbse"])
        response = (
            f"{tone_response}পড়ার রুটিন চাও? এখানে একটা আইডিয়া:\n"
            f"- বই সাজেশন: {suggestion}\n"
            "- সকাল ৬-৮: ম্যাথ বা সায়েন্স\n"
            "- দুপুর ২-৪: ইংরেজি বা বাংলা\n"
            "- রাত ৮-১০: রিভিশন\n"
            "তোমার রুটিন শেয়ার করবে? 😊 তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "gk_query":
        fact = random.choice(wb_history_facts)
        response = (
            f"{tone_response}জেনারেল নলেজ চাও? এখানে একটা ফ্যাক্ট:\n"
            f"- {fact}\n"
            "আরেকটা চাও? নাকি তুমি প্রশ্ন করবে? 😄 তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "dictionary":
        word = user_input.lower().strip()
        meaning = dictionary.get(word, None)
        if meaning:
            response = (
                f"{tone_response}'{word}' এর অর্থ: {meaning}\n"
                "আরেকটা শব্দ জানতে চাও? 😊 তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
        else:
            response = (
                f"{tone_response}দুঃখিত, '{word}' আমার ডিকশনারিতে নেই। 😅\n"
                "আরেকটা শব্দ বলো, বাংলা বা ইংরেজি! তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "wb_history":
        fact = random.choice(wb_history_facts)
        response = (
            f"{tone_response}পশ্চিমবঙ্গের ইতিহাস জানতে চাও? এখানে একটা ফ্যাক্ট:\n"
            f"- {fact}\n"
            "আরও জানতে চাও? স্বাধীনতা আন্দোলন বা বিখ্যাত ব্যক্তি নিয়ে বলতে পারি! 😄 তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "psychology_fact":
        fact = random.choice(psychology_facts)
        response = (
            f"{tone_response}সাইকোলজি ফ্যাক্ট চাও? এখানে একটা:\n"
            f"- {fact}\n"
            "আরেকটা ফ্যাক্ট শুনবে? 😊 তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "relationship_advice":
        response = (
            f"{tone_response}রিলেশনশিপ নিয়ে টিপস চাও? 😄 এখানে একটা:\n"
            "- বন্ধু বা ফ্যামিলির সাথে খোলামেলা কথা বলো, ভুল বোঝাবুঝি কমবে।\n"
            "কোনো নির্দিষ্ট সমস্যা নিয়ে কথা বলতে চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "study_partner":
        if context_data.get("awaiting_study_partner"):
            try:
                class_level, board, subjects, study_time = user_input.split(",")
                save_study_partner(user_id, class_level.strip(), board.strip(), subjects.strip(), study_time.strip())
                matches = find_study_partner(user_id, class_level.strip(), board.strip(), subjects.strip())
                if matches:
                    match_list = "\n".join([f"User {m[0]}: ক্লাস {m[1]}, বোর্ড {m[2]}, সাবজেক্ট {m[3]}, সময় {m[4]}" for m in matches])
                    response = (
                        f"{tone_response}তোমার ডিটেইল সেভ করলাম! 😊 এখানে ম্যাচিং পার্টনার:\n"
                        f"{match_list}\n"
                        "কারো সাথে কানেক্ট করতে চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
                    )
                else:
                    response = (
                        f"{tone_response}তোমার ডিটেইল সেভ করলাম! 😊 এখনো ম্যাচিং পার্টনার পাইনি।\n"
                        "পরে আবার চেক করো। আর কিছু জানতে চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
                    )
                context_data["awaiting_study_partner"] = False
                add_points(user_id, 5)
            except ValueError:
                response = (
                    f"{tone_response}দুঃখিত, ডিটেইল ঠিক নয়। 😅 ফরম্যাট: ক্লাস,বোর্ড,সাবজেক্ট,সময়\n"
                    "উদাহরণ: ১০,WBBSE,ম্যাথ-সায়েন্স,সন্ধ্যা ৬-৮\n"
                    "আবার চেষ্টা করো! তুমি ২ পয়েন্ট পেলে! 🌟"
                )
                add_points(user_id, 2)
        else:
            context_data["awaiting_study_partner"] = True
            response = (
                f"{tone_response}পড়ার পার্টনার চাও? 😄 নিচের ফরম্যাটে ডিটেইল দাও:\n"
                "- ক্লাস, বোর্ড, সাবজেক্ট, পড়ার সময়\n"
                "উদাহরণ: ১০,WBBSE,ম্যাথ-সায়েন্স,সন্ধ্যা ৬-৮\n"
                "বলো, তোমার ডিটেইল কী? তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            add_points(user_id, 5)
        save_context(user_id, context_data)
        await update.message.reply_text(response)
    
    elif intent == "feedback":
        context_data["awaiting_feedback"] = True
        save_context(user_id, context_data)
        await update.message.reply_text(responses["feedback"])
        add_points(user_id, 5)
    
    elif intent == "share":
        await update.message.reply_text(responses["share"])
        add_points(user_id, 10)
    
    elif intent == "joke":
        joke = random.choice(jokes)
        response = (
            f"{tone_response}চলো, একটা জোকস শোনাই! 😅\n"
            f"- {joke}\n"
            "আরেকটা শুনবে? তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "puzzle":
        if context_data.get("current_puzzle"):
            current_puzzle = context_data["current_puzzle"]
            if user_input.lower() == current_puzzle["answer"].lower():
                response = (
                    "শাবাশ! সঠিক উত্তর! 🎉\n"
                    "আরেকটা পাজল চাও? তুমি ১০ পয়েন্ট পেলে! 🌟"
                )
                context_data["current_puzzle"] = None
                add_points(user_id, 10)
            else:
                response = (
                    f"ভুল হয়ে গেছে। 😅 সঠিক উত্তর: {current_puzzle['answer']}।\n"
                    "আরেকটা পাজল চাও? তুমি ২ পয়েন্ট পেলে! 🌟"
                )
                context_data["current_puzzle"] = None
                add_points(user_id, 2)
        else:
            puzzle = random.choice(puzzles)
            context_data["current_puzzle"] = puzzle
            response = (
                f"{tone_response}চলো, একটা পাজল দিচ্ছি! 😎\n"
                f"প্রশ্ন: {puzzle['question']}\n"
                "উত্তর দাও! তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            add_points(user_id, 5)
        save_context(user_id, context_data)
        await update.message.reply_text(response)
    
    elif intent == "poem":
        poem = random.choice(poems)
        response = (
            f"{tone_response}একটা কবিতা শোনো! 🌟\n"
            f"- {poem}\n"
            "আরেকটা কবিতা চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "book_suggestion":
        if context_data.get("awaiting_book_suggestion"):
            book_key = user_input.lower().replace(" ", "_")
            books = book_suggestions.get(book_key, None)
            if books:
                book_list = "\n".join([f"- {book}" for book in books])
                response = (
                    f"{tone_response}তোমার জন্য বই সাজেশন:\n"
                    f"{book_list}\n"
                    "আরও সাজেশন চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
                )
                context_data["awaiting_book_suggestion"] = False
                add_points(user_id, 5)
            else:
                response = (
                    f"{tone_response}দুঃখিত, এই ক্লাস/পরীক্ষার জন্য সাজেশন নেই। 😅\n"
                    "আরেকটা ক্লাস বা পরীক্ষা বলো (যেমন, class_10_wbbse, neet)। তুমি ২ পয়েন্ট পেলে! 🌟"
                )
                add_points(user_id, 2)
        else:
            context_data["awaiting_book_suggestion"] = True
            response = (
                f"{tone_response}কোন ক্লাস বা পরীক্ষার জন্য বই চাও? 😊\n"
                "উদাহরণ: class_10_wbbse, neet, jee\n"
                "বলো, কোনটা? তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            add_points(user_id, 5)
        save_context(user_id, context_data)
        await update.message.reply_text(response)
    
    elif intent == "bodmas_calc":
        if context_data.get("awaiting_bodmas"):
            result = evaluate_bodmas(user_input)
            response = (
                f"{tone_response}{result}\n"
                "আরেকটা অংক দিবে? তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            context_data["awaiting_bodmas"] = False
            add_points(user_id, 5)
        else:
            context_data["awaiting_bodmas"] = True
            response = (
                f"{tone_response}একটা BODMAS অংক দাও, আমি হিসাব করে দেব! 😄\n"
                "উদাহরণ: ২ + ৩ * ৪\n"
                "তোমার অংক বলো! তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
            add_points(user_id, 5)
        save_context(user_id, context_data)
        await update.message.reply_text(response)
    
    elif intent == "career_continue":
        last_topic = context_data.get("last_topic", "")
        if last_topic in responses:
            response = (
                f"{tone_response}আরও জানতে চাও? দারুণ! 😊 কী নিয়ে ভাবছো?\n"
                f"- প্রস্তুতি টিপস\n"
                f"- বই সাজেশন\n"
                f"- খরচ বা স্কলারশিপ\n"
                "বলো, কোনটা? তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
        else:
            response = (
                f"{tone_response}কোন ক্যারিয়ার নিয়ে কথা বলতে চাও? 😊\n"
                "- NEET, JEE, UPSC, SSC, CA...\n"
                "বলো, কোনটা? তুমি ৫ পয়েন্ট পেলে! 🌟"
            )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    elif intent == "casual_chat":
        response = (
            f"{tone_response}আরে, কী খবর? 😎\n"
            "- কী করছো? পড়াশোনা, নাকি মজা?\n"
            "গল্প করতে চাও? তুমি ৫ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 5)
        await update.message.reply_text(response)
    
    else:
        response = (
            f"{tone_response}দুঃখিত, আমি ঠিক বুঝতে পারলাম না। 😅\n"
            "কী নিয়ে কথা বলতে চাও? যেমন:\n"
            "- পড়ার টিপস\n"
            "- কুইজ বা ম্যাথ লজিক\n"
            "- ক্যারিয়ার গাইড (NEET, JEE...)\n"
            "- জোকস, কবিতা\n"
            "বলো, কী চাও? তুমি ২ পয়েন্ট পেলে! 🌟"
        )
        add_points(user_id, 2)
        await update.message.reply_text(response)

# পঞ্চম অংশ: মেইন ফাংশন এবং এরর হ্যান্ডলার
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "দুঃখিত, কিছু একটা সমস্যা হয়েছে। 😅 আবার চেষ্টা করো বা /help দিয়ে দেখো!"
        )

def main():
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("feedback", feedback))
    application.add_handler(CommandHandler("share", share))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
  
