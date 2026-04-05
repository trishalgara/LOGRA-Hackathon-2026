import os, json, time
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "logra_hackathon_final_2026")
# Database stored in 'instance' folder
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///logra_database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- THE 2026 STABLE MODEL ---
AI_MODEL = "gemini-2.5-flash" 

client = None
if os.getenv("GEMINI_API_KEY"):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# --- AUTH ROUTES ---
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email, pw = request.form.get("email"), request.form.get("password")
        if not email or not pw: return "Missing fields"
        if User.query.filter_by(email=email.lower().strip()).first():
            return "User already exists!"
        user = User(email=email.lower().strip(), password=generate_password_hash(pw))
        db.session.add(user); db.session.commit(); login_user(user)
        return redirect(url_for('home'))
    return render_template("auth.html", mode="signup")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email, pw = request.form.get("email"), request.form.get("password")
        user = User.query.filter_by(email=email.lower().strip()).first()
        if user and check_password_hash(user.password, pw):
            login_user(user); return redirect(url_for('home'))
        flash("Invalid login")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    logout_user(); return redirect(url_for('home'))

# --- NAVIGATION ---
@app.route("/")
def home(): return render_template("index.html")

@app.route("/market-trends")
@login_required
def trends_page(): return render_template("trends.html")

@app.route("/roadmap")
@login_required
def roadmap_page(): return render_template("roadmap.html")

@app.route("/counselor")
@login_required
def counselor_page(): return render_template("counselor.html")

@app.route("/anti-career")
@login_required
def anticareer_page(): return render_template("anticareer.html")

@app.route("/simulation")
@login_required
def simulation_page(): return render_template("simulation.html")

# --- CENTRALIZED AI ENGINE ---
@app.route("/api/logra-engine", methods=["POST"])
@login_required
def logra_engine():
    if not client: return jsonify({"status": "error", "error": "AI client not ready"}), 503
    
    data = request.get_json()
    feature = data.get("feature")
    user_input = data.get("input")
    
    # Updated simulation prompt to include consequences for the game loop
    prompts = {
        "roadmap": f"Recommend 3 careers for: {user_input}. Return ONLY a JSON array with keys: title, reason, roadmap_step_1, roadmap_step_2.",
        "counselor": f"Answer as a career expert in 3 sentences: {user_input}",
        "anticareer": f"User hates: {user_input}. Suggest 3 careers using reverse psychology. Return JSON array with keys: title, reason, perk.",
        "simulation": f"""
            The user is starting a virtual 'Day in the Life' as a {user_input}. 
            Current Time: 9:00 AM. 
            Task: Describe a realistic, high-pressure scenario they face immediately.
            Return ONLY a JSON object with these EXACT keys:
            "time": "9:00 AM",
            "narrative": "A 2-sentence description of the situation.",
            "choice_a": "A professional action they can take.",
            "choice_b": "A risky or alternative action.",
            "consequence_a": "The outcome of picking A.",
            "consequence_b": "The outcome of picking B."
        """,
        "trends": "Generate 10 trending jobs for 2026. Return JSON array with keys: title, salary, growth, sector."
    }

    try:
        # Respect Free Tier RPM
        time.sleep(0.5) 
        
        response = client.models.generate_content(
            model=AI_MODEL, 
            contents=prompts.get(feature, "Hello"),
            config=types.GenerateContentConfig(
                response_mime_type="application/json" if feature != "counselor" else "text/plain"
            )
        )
        
        if feature == "counselor":
            return jsonify({"status": "success", "data": response.text})
        
        # Robust Cleaning of AI response
        raw_text = response.text.strip()
        clean_text = raw_text.replace('```json', '').replace('```', '').strip()
        
        try:
            parsed_data = json.loads(clean_text)
            return jsonify({"status": "success", "data": parsed_data})
        except json.JSONDecodeError:
            # Fallback if AI produces invalid JSON
            print(f"FAILED TO PARSE: {clean_text}")
            return jsonify({"status": "error", "error": "AI returned malformed data. Please try again."}), 500

    except Exception as e:
        error_str = str(e)
        print(f"DEBUG ERROR: {error_str}")
        return jsonify({"status": "error", "error": error_str}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)