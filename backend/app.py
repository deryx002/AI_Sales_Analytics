from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import io
from datetime import datetime
import os
from dotenv import load_dotenv

# Gemini (NEW SDK)
from google import genai
from google.genai.errors import ClientError

# --------------------
# SETUP
# --------------------
load_dotenv()

app = Flask(__name__)
CORS(app)

client = None
if os.getenv("GOOGLE_API_KEY"):
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

sales_data = []
file_history = []

# --------------------
# DATA UTILITIES
# --------------------

def get_dataframe():
    if not sales_data:
        return None
    rows = [r["data"] for r in sales_data if "data" in r]
    df = pd.DataFrame(rows)
    df.columns = df.columns.str.lower()
    return df


def process_csv(file_bytes):
    df = pd.read_csv(io.StringIO(file_bytes.decode("utf-8", errors="ignore")))
    return [{"data": row.to_dict(), "timestamp": datetime.now().isoformat()} for _, row in df.iterrows()]


def process_excel(file_bytes):
    df = pd.read_excel(io.BytesIO(file_bytes))
    return [{"data": row.to_dict(), "timestamp": datetime.now().isoformat()} for _, row in df.iterrows()]


# --------------------
# FACTUAL (PANDAS) ENGINE
# --------------------

def answer_factual_query(query):
    df = get_dataframe()
    if df is None or df.empty:
        return None

    q = query.lower()

    if "revenue" in df.columns:
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")

    if "total revenue" in q:
        return f"📊 Total Revenue: ₹{df['revenue'].sum():,.2f}"

    if "average revenue" in q:
        return f"📊 Average Revenue: ₹{df['revenue'].mean():,.2f}"

    if "top region" in q and "region" in df.columns:
        return f"🌍 Top Region: {df['region'].value_counts().idxmax()}"

    if "top product" in q and "product" in df.columns:
        return f"📦 Top Product: {df['product'].value_counts().idxmax()}"

    if "record" in q:
        return f"🧾 Total Records: {len(df)}"

    return None


# --------------------
# GEMINI (LOGICAL) ENGINE
# --------------------

def ask_gemini(query):
    if not client:
        return "AI service unavailable (API key missing)."

    df = get_dataframe()
    summary = df.describe(include="all").to_string() if df is not None else "No data"

    prompt = f"""
You are a sales analytics expert.

USER QUESTION:
{query}

DATA SUMMARY:
{summary}

Explain clearly and concisely.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text

    except ClientError as e:
        if e.status_code == 429:
            return "⚠️ AI quota exceeded. Please try again later."
        return f"AI Error: {str(e)}"


# --------------------
# ROUTES
# --------------------

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    ext = file.filename.split(".")[-1].lower()
    content = file.read()

    if ext == "csv":
        records = process_csv(content)
    elif ext in ["xls", "xlsx"]:
        records = process_excel(content)
    else:
        return jsonify({"error": "Unsupported file type"}), 400

    sales_data.extend(records)
    file_history.append({
        "filename": file.filename,
        "records": len(records),
        "time": datetime.now().isoformat()
    })

    return jsonify({
        "message": "File uploaded",
        "records_added": len(records),
        "total_records": len(sales_data)
    })


@app.route("/api/query", methods=["POST"])
def query():
    query = request.json.get("query", "")
    if not query:
        return jsonify({"error": "No query provided"}), 400

    # 1️⃣ Try pandas first
    factual_answer = answer_factual_query(query)
    if factual_answer:
        return jsonify({
            "query": query,
            "response": factual_answer,
            "engine": "pandas"
        })

    # 2️⃣ Use Gemini for reasoning
    ai_answer = ask_gemini(query)
    return jsonify({
        "query": query,
        "response": ai_answer,
        "engine": "gemini"
    })


# --------------------
# CHARTS API
# --------------------

@app.route("/api/charts/revenue-trend")
def revenue_trend():
    df = get_dataframe()
    if df is None or "date" not in df.columns or "revenue" not in df.columns:
        return jsonify({"error": "Required columns missing"}), 400

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    trend = df.groupby(df["date"].dt.to_period("M"))["revenue"].sum()

    return jsonify({
        "labels": trend.index.astype(str).tolist(),
        "values": trend.values.tolist()
    })


@app.route("/api/charts/top-regions")
def top_regions():
    df = get_dataframe()
    if df is None or "region" not in df.columns:
        return jsonify({"error": "Region column missing"}), 400

    counts = df["region"].value_counts().head(5)
    return jsonify({
        "labels": counts.index.tolist(),
        "values": counts.values.tolist()
    })


@app.route("/api/charts/top-products")
def top_products():
    df = get_dataframe()
    if df is None or "product" not in df.columns:
        return jsonify({"error": "Product column missing"}), 400

    counts = df["product"].value_counts().head(5)
    return jsonify({
        "labels": counts.index.tolist(),
        "values": counts.values.tolist()
    })


@app.route("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "records": len(sales_data),
        "ai_enabled": bool(client)
    })


# --------------------
# RUN
# --------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
