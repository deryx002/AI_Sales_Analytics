from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import json
import google.genai as genai
from google.genai import types
import pandas as pd
import io
from datetime import datetime
from visualization import SalesVisualizer
from pymongo import MongoClient
import bcrypt

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload
CORS(app)

api_key = os.getenv('GOOGLE_API_KEY')
mongo_uri = os.getenv("MONGO_URI")

if not api_key:
    print("ERROR: GOOGLE_API_KEY not found in .env file")

if not mongo_uri:
    print("ERROR: MONGO_URI not found in .env file")

# -------------------------------
# MongoDB Connection
# -------------------------------
try:
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client["sales_ai"]

    users_collection = db["users"]
    datasets_collection = db["datasets"]
    chats_collection = db["chats"]

    # Create indexes for performance & duplicate prevention
    users_collection.create_index("username", unique=True)
    datasets_collection.create_index([("username", 1), ("dataset_id", 1)], unique=True)
    chats_collection.create_index([("username", 1), ("dataset_id", 1)])

    print("MongoDB connected successfully")

except Exception as e:
    print("MongoDB connection failed:", e)

# -------------------------------
# Gemini AI
# -------------------------------
client = genai.Client(api_key=api_key)
model_name = "gemini-2.5-flash"
visualizer = SalesVisualizer()

# ============================================================
#  RATE LIMITER
# ============================================================

import time
import hashlib
import threading

class GeminiRateLimiter:
    def __init__(self, rpm=15):
        self.rpm = rpm
        self.requests = []
        self.lock = threading.Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            self.requests = [r for r in self.requests if now - r < 60]
            if len(self.requests) >= self.rpm:
                sleep_time = 60 - (now - self.requests[0])
                if sleep_time > 0:
                    print(f"Rate limit approaching. Waiting {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
            self.requests.append(time.time())

rate_limiter = GeminiRateLimiter(rpm=14)


# ============================================================
#  RESPONSE CACHE
# ============================================================

_query_cache = {}
CACHE_TTL = 300  # 5 minutes

def get_cache_key(dataset_id, query):
    return hashlib.md5(f"{dataset_id}:{query.lower().strip()}".encode()).hexdigest()

def get_cached_response(dataset_id, query):
    key = get_cache_key(dataset_id, query)
    if key in _query_cache:
        cached, timestamp = _query_cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return cached
    return None

def set_cached_response(dataset_id, query, response):
    key = get_cache_key(dataset_id, query)
    _query_cache[key] = (response, time.time())


# ============================================================
#  GEMINI CALLER (retry + backoff + cache)
# ============================================================

def call_gemini(prompt, dataset_id='', query=''):
    if dataset_id and query:
        cached = get_cached_response(dataset_id, query)
        if cached:
            print("Cache hit — skipping API call")
            return cached

    for attempt in range(3):
        try:
            rate_limiter.wait_if_needed()
            response = client.models.generate_content(
                model=model_name, contents=prompt
            )
            result = response.text
            if dataset_id and query:
                set_cached_response(dataset_id, query, result)
            return result
        except Exception as e:
            err = str(e).lower()
            if '429' in err or 'quota' in err or 'rate' in err:
                wait = (2 ** attempt) * 5
                print(f"Rate limit hit. Waiting {wait}s (attempt {attempt + 1}/3)...")
                time.sleep(wait)
            else:
                raise

    return "I'm currently busy due to API limits. Please wait a moment and try again."


# Legacy in-memory storage (fallback for anonymous/sample use)
sales_data = []
file_history = []
COLUMN_ALIASES = {
    'revenue': [
        'revenue', 'sales', 'sale', 'sales_amount', 'sale_amount', 'amount',
        'total_sales', 'total_amount', 'total', 'order_value', 'order_amount', 'gmv',
        'turnover', 'income', 'net_sales', 'gross_sales'
    ],
    'price': [
        'price', 'unit_price', 'unitprice', 'selling_price', 'final_price',
        'cost', 'mrp', 'rate', 'item_price'
    ],
    'region': [
        'region', 'area', 'territory', 'zone', 'location', 'geo', 'geography',
        'market', 'state', 'country', 'city', 'branch', 'district',
        'customer_location', 'customer_city', 'customer_state', 'customer_country',
        'ship_to', 'ship_city', 'ship_state', 'shipping_location',
        'billing_city', 'billing_state', 'store_location', 'store_city'
    ],
    'product': [
        'product', 'product_name', 'item', 'item_name', 'sku', 'sku_name',
        'product_id', 'product_title', 'model'
    ],
    'date': [
        'date', 'order_date', 'sale_date', 'transaction_date', 'invoice_date',
        'created_at', 'created_date', 'timestamp', 'month', 'year_month'
    ],
    'customer': [
        'customer', 'customer_name', 'client', 'client_name', 'buyer',
        'account', 'company', 'customer_id'
    ],
    'quantity': [
        'quantity', 'qty', 'units', 'unit_sold', 'units_sold', 'volume'
    ],
    'pipeline_stage': [
        'pipeline_stage', 'stage', 'status', 'deal_stage', 'sales_stage'
    ],
    'payment': [
        'payment', 'payment_mode', 'payment_method', 'payment_type',
        'pay_mode', 'pay_method', 'transaction_type'
    ]
}


def normalize_column_key(name):
    return str(name).strip().lower().replace(' ', '_').replace('-', '_')


def get_canonical_name(column_name):
    key = normalize_column_key(column_name)
    for canonical, aliases in COLUMN_ALIASES.items():
        if key == canonical or key in aliases:
            return canonical
    return key


def make_unique_columns(columns):
    seen = {}
    unique_cols = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            unique_cols.append(col)
            continue
        seen[col] += 1
        unique_cols.append(f"{col}_{seen[col]}")
    return unique_cols


_original_column_map = {}


def normalize_dataframe(df):
    global _original_column_map
    raw_cols = [str(col).strip() for col in df.columns]
    df.columns = raw_cols
    canonical_cols = [get_canonical_name(col) for col in raw_cols]

    # Smart dedup: when multiple columns share a canonical name (e.g. both
    # "Branch" and "District" → "region"), promote the column with the most
    # unique values so it gets the primary unsuffixed name.
    from collections import defaultdict
    canon_groups = defaultdict(list)
    for i, c in enumerate(canonical_cols):
        canon_groups[c].append(i)

    for canon, indices in canon_groups.items():
        if len(indices) < 2:
            continue
        best = max(indices, key=lambda i: df.iloc[:, i].nunique())
        first = indices[0]
        if best != first:
            # Swap column data so the most diverse column is first
            temp = df.iloc[:, first].values.copy()
            df.iloc[:, first] = df.iloc[:, best].values
            df.iloc[:, best] = temp
            raw_cols[first], raw_cols[best] = raw_cols[best], raw_cols[first]

    # Build original-column-name map (after potential swaps)
    _original_column_map = {}
    for raw, canon in zip(raw_cols, canonical_cols):
        if canon not in _original_column_map:
            _original_column_map[canon] = raw

    df.columns = make_unique_columns(canonical_cols)

    for col in df.columns:
        if str(df[col].dtype) == 'object':
            df[col] = df[col].astype(str).str.strip()

    if 'revenue' not in df.columns and 'price' in df.columns and 'quantity' in df.columns:
        try:
            price_numeric = pd.to_numeric(
                df['price'].astype(str).str.replace(r'[$₹,]', '', regex=True),
                errors='coerce'
            )
            quantity_numeric = pd.to_numeric(df['quantity'], errors='coerce')
            df['revenue'] = (price_numeric * quantity_numeric).fillna(0)
        except Exception:
            pass

    return df


def first_matching_key(data_dict, canonical_name):
    for key in data_dict.keys():
        if get_canonical_name(key) == canonical_name:
            return key
    return None


def process_csv(file_content):
    try:
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1']:
            try:
                df = pd.read_csv(io.StringIO(file_content.decode(encoding)))
                break
            except:
                continue
        else:
            df = pd.read_csv(io.StringIO(file_content.decode('utf-8', errors='ignore')))

        df = normalize_dataframe(df)
        records = []
        for _, row in df.iterrows():
            record = {
                'type': 'structured',
                'format': 'csv',
                'data': row.to_dict(),
                'columns': list(df.columns),
                'timestamp': datetime.now().isoformat()
            }
            records.append(record)
        return records
    except Exception as e:
        print(f"Error processing CSV: {str(e)}")
        return []


def process_excel(file_content):
    try:
        df = pd.read_excel(io.BytesIO(file_content))
        df = normalize_dataframe(df)
        records = []
        for _, row in df.iterrows():
            record = {
                'type': 'structured',
                'format': 'excel',
                'data': row.to_dict(),
                'columns': list(df.columns),
                'timestamp': datetime.now().isoformat()
            }
            records.append(record)
        return records
    except Exception as e:
        print(f"Error processing Excel: {str(e)}")
        return []


def _friendly_label(canonical_name, fallback):
    original = _original_column_map.get(canonical_name)
    if not original:
        return fallback
    label_map = {
        'location': 'Locations', 'customer_location': 'Locations',
        'city': 'Cities', 'state': 'States', 'country': 'Countries',
        'branch': 'Branches', 'zone': 'Zones', 'area': 'Areas',
        'territory': 'Territories', 'market': 'Markets',
        'geography': 'Geographies', 'geo': 'Geographies',
        'region': 'Regions', 'district': 'Districts',
    }
    key = normalize_column_key(original)
    for pattern, label in label_map.items():
        if pattern in key:
            return label
    return fallback


def extract_sales_insights(data):
    insights = {
        'total_revenue': 0, 'avg_revenue': 0,
        'regions': set(), 'products': set(), 'time_periods': set(),
        'record_count': len(data), 'columns': set(),
        'metrics_available': {'revenue': False, 'region': False, 'product': False, 'date': False},
        'region_label': _friendly_label('region', 'Regions'),
        'product_label': _friendly_label('product', 'Products'),
    }
    revenue_values = []
    for record in data:
        if 'data' in record:
            data_dict = record['data']
            insights['columns'].update(data_dict.keys())
            revenue_key = first_matching_key(data_dict, 'revenue')
            if revenue_key:
                try:
                    rev_value = str(data_dict[revenue_key]).replace('$', '').replace(',', '').replace('₹', '').strip()
                    if rev_value and rev_value.lower() != 'nan':
                        revenue_values.append(float(rev_value))
                        insights['metrics_available']['revenue'] = True
                except:
                    pass
            else:
                price_key = first_matching_key(data_dict, 'price')
                quantity_key = first_matching_key(data_dict, 'quantity')
                if price_key and quantity_key:
                    try:
                        pv = to_float(data_dict.get(price_key))
                        qv = to_float(data_dict.get(quantity_key))
                        if pv is not None and qv is not None:
                            revenue_values.append(pv * qv)
                            insights['metrics_available']['revenue'] = True
                    except:
                        pass
            region_key = first_matching_key(data_dict, 'region')
            if region_key:
                rv = str(data_dict[region_key]).strip()
                if rv and rv.lower() != 'nan':
                    insights['regions'].add(rv)
                    insights['metrics_available']['region'] = True
            product_key = first_matching_key(data_dict, 'product')
            if product_key:
                pv = str(data_dict[product_key]).strip()
                if pv and pv.lower() != 'nan':
                    insights['products'].add(pv)
                    insights['metrics_available']['product'] = True
            date_key = first_matching_key(data_dict, 'date')
            if date_key:
                dv = str(data_dict[date_key]).strip()
                if dv and dv.lower() != 'nan':
                    insights['time_periods'].add(dv)
                    insights['metrics_available']['date'] = True
    if revenue_values:
        insights['total_revenue'] = sum(revenue_values)
        insights['avg_revenue'] = sum(revenue_values) / len(revenue_values)
    insights['regions'] = list(insights['regions'])
    insights['products'] = list(insights['products'])
    insights['time_periods'] = list(insights['time_periods'])
    insights['columns'] = list(insights['columns'])
    return insights


def to_float(value):
    try:
        cleaned = str(value).replace('$', '').replace(',', '').replace('₹', '').strip()
        if not cleaned or cleaned.lower() == 'nan':
            return None
        return float(cleaned)
    except:
        return None


def forecast_next_value(values):
    n = len(values)
    if n < 3:
        return None
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = denominator = 0
    for i, y in enumerate(values):
        dx = i - x_mean
        numerator += dx * (y - y_mean)
        denominator += dx * dx
    if denominator == 0:
        return values[-1]
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    return max(0, intercept + slope * n)


def generate_ai_future_reasons(product_name, product_stats, prediction):
    fallback_reasons = [
        f"{product_name} has strong cumulative revenue in current data.",
        "Recent sales pattern shows consistent momentum across time periods.",
        "Projected trend remains above baseline compared to historical average."
    ]
    if not api_key:
        return fallback_reasons
    try:
        dated_revenue = sorted(product_stats.get('dated_revenue', []), key=lambda item: item[0])
        recent_values = [value for _, value in dated_revenue[-3:]] if dated_revenue else []
        recent_avg = (sum(recent_values) / len(recent_values)) if recent_values else 0
        projected = float(prediction.get('projected_revenue', 0) or 0)
        growth_pct = ((projected - recent_avg) / recent_avg * 100) if recent_avg > 0 else 0
        prompt = f"""You are an AI sales analyst.
Give exactly 3 concise reasons why this product can sell higher in future.
Product: {product_name}
Total Revenue: {product_stats.get('revenue', 0):.2f}
Total Units: {product_stats.get('quantity', 0):.2f}
Records: {product_stats.get('records', 0)}
Projected Revenue: {projected:.2f}
Recent Average Revenue: {recent_avg:.2f}
Projected vs Recent Growth %: {growth_pct:.2f}
Confidence: {prediction.get('confidence', 'N/A')}
Rules:
- Output JSON array only
- Exactly 3 strings
- Each reason max 16 words
- No markdown, no numbering"""
        text = (call_gemini(prompt) or '').strip()
        import re as _re
        text = _re.sub(r'^```(?:json)?\s*', '', text)
        text = _re.sub(r'\s*```$', '', text).strip()
        parsed = json.loads(text)
        if isinstance(parsed, list):
            cleaned = [str(item).strip() for item in parsed if str(item).strip()]
            if len(cleaned) >= 3:
                return cleaned[:3]
        return fallback_reasons
    except Exception:
        return fallback_reasons


def get_product_insights(data):
    aggregates = {}
    has_quantity = has_revenue = False
    all_dates = set()

    for record in data:
        if 'data' not in record:
            continue
        data_dict = record['data']
        product_key = first_matching_key(data_dict, 'product')
        if not product_key:
            continue
        product_name = str(data_dict[product_key]).strip()
        if not product_name or product_name.lower() == 'nan':
            continue
        if product_name not in aggregates:
            aggregates[product_name] = {'quantity': 0.0, 'revenue': 0.0, 'records': 0, 'dated_revenue': [], 'dated_quantity': []}
        aggregates[product_name]['records'] += 1
        quantity_val = None
        quantity_key = first_matching_key(data_dict, 'quantity')
        if quantity_key:
            quantity_val = to_float(data_dict.get(quantity_key))
            if quantity_val is not None:
                has_quantity = True
                aggregates[product_name]['quantity'] += quantity_val
        revenue_key = first_matching_key(data_dict, 'revenue')
        revenue_val = None
        if revenue_key:
            revenue_val = to_float(data_dict.get(revenue_key))
            if revenue_val is not None:
                has_revenue = True
                aggregates[product_name]['revenue'] += revenue_val
        else:
            price_key = first_matching_key(data_dict, 'price')
            if price_key and quantity_val is not None:
                price_val = to_float(data_dict.get(price_key))
                if price_val is not None:
                    revenue_val = price_val * quantity_val
                    has_revenue = True
                    aggregates[product_name]['revenue'] += revenue_val
        date_key = first_matching_key(data_dict, 'date')
        if date_key:
            parsed_date = pd.to_datetime(str(data_dict.get(date_key)).strip(), errors='coerce', dayfirst=True)
            if not pd.isna(parsed_date):
                all_dates.add(parsed_date)
                if revenue_val is not None:
                    aggregates[product_name]['dated_revenue'].append((parsed_date, revenue_val))
                if quantity_val is not None:
                    aggregates[product_name]['dated_quantity'].append((parsed_date, quantity_val))

    if not aggregates:
        return {'available': False, 'message': 'Product insights are not available for this dataset.'}

    metric_key = 'quantity' if has_quantity else 'revenue'
    metric_label = 'Units Sold' if metric_key == 'quantity' else 'Revenue'
    ranked_products = sorted(aggregates.items(), key=lambda item: item[1][metric_key], reverse=True)
    most_product, most_stats = ranked_products[0]
    least_product, least_stats = ranked_products[-1]

    forecast_candidates = []
    for pn, stats in aggregates.items():
        dated_points = sorted(stats['dated_revenue'], key=lambda item: item[0])
        revenue_series = [pt[1] for pt in dated_points]
        projected = forecast_next_value(revenue_series)
        if projected is not None:
            forecast_candidates.append((pn, projected, len(revenue_series)))

    if forecast_candidates:
        forecast_candidates.sort(key=lambda item: item[1], reverse=True)
        predicted_product, projected_revenue, sample_size = forecast_candidates[0]
        prediction = {'name': predicted_product, 'projected_revenue': projected_revenue,
                      'confidence': 'High' if sample_size >= 6 else 'Medium',
                      'basis': 'Time trend forecast from historical product revenue'}
    else:
        fb_product, fb_stats = max(aggregates.items(), key=lambda item: (item[1]['revenue'] / max(1, item[1]['records'])))
        prediction = {'name': fb_product, 'projected_revenue': fb_stats['revenue'] / max(1, fb_stats['records']),
                      'confidence': 'Low', 'basis': 'Fallback using average revenue per record'}

    pred_stats = aggregates.get(prediction['name'], {})
    if len(pred_stats.get('dated_revenue', [])) >= 3:
        prediction_reasons = generate_ai_future_reasons(prediction['name'], pred_stats, prediction)
    else:
        prediction_reasons = [
            f"{prediction['name']} leads current dataset on tracked sales metric.",
            "Recent observed demand stays stable without major drop-offs.",
            "Projected value remains above competing products in this dataset."
        ]

    def build_trend_points(pname, preferred_metric):
        stats = aggregates.get(pname, {})
        if preferred_metric == 'quantity':
            raw_points = stats.get('dated_quantity', [])
            mfp = 'quantity'
            if not raw_points:
                raw_points = stats.get('dated_revenue', [])
                mfp = 'revenue'
        else:
            raw_points = stats.get('dated_revenue', [])
            mfp = 'revenue'
        if not raw_points:
            return {'metric': mfp, 'points': []}
        grouped = {}
        for dt, val in raw_points:
            key = dt.strftime('%Y-%m-%d')
            grouped[key] = grouped.get(key, 0) + val
        timeline_dates = sorted(all_dates) if all_dates else sorted(dt for dt, _ in raw_points)
        points = [{'x': dt.strftime('%Y-%m-%d'), 'y': grouped.get(dt.strftime('%Y-%m-%d'), 0)} for dt in timeline_dates]
        return {'metric': mfp, 'points': points}

    return {
        'available': True, 'metric_used': metric_key, 'metric_label': metric_label,
        'most_sold_product': {'name': most_product, 'value': most_stats[metric_key]},
        'least_sold_product': {'name': least_product, 'value': least_stats[metric_key]},
        'most_sold_trend': build_trend_points(most_product, metric_key),
        'least_sold_trend': build_trend_points(least_product, metric_key),
        'predicted_highest_future_sales': {**prediction, 'reasons': prediction_reasons}
    }


def get_records_from_db(username, dataset_id):
    """Fetch dataset document from MongoDB and expand its records array"""
    doc = datasets_collection.find_one(
        {"username": username, "dataset_id": dataset_id},
        {"_id": 0}
    )
    if not doc:
        return []
    columns = doc.get('columns', [])
    doc_type = doc.get('type', 'structured')
    doc_format = doc.get('format', 'csv')
    records = []
    for row_data in doc.get('records', []):
        records.append({
            'type': doc_type,
            'format': doc_format,
            'data': row_data,
            'columns': columns,
        })
    return records


# ============================================================
#  AUTH ROUTES
# ============================================================

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        if len(password) < 4:
            return jsonify({'error': 'Password must be at least 4 characters'}), 400
        if users_collection.find_one({"username": username}):
            return jsonify({'error': 'Username already exists'}), 409
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        users_collection.insert_one({
            "username": username,
            "password": hashed.decode('utf-8'),
            "created_at": datetime.now().isoformat()
        })
        return jsonify({'message': 'Registration successful', 'username': username}), 201
    except Exception as e:
        print(f"Registration error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({'error': 'Invalid username or password'}), 401
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            return jsonify({'error': 'Invalid username or password'}), 401
        return jsonify({'message': 'Login successful', 'username': username})
    except Exception as e:
        print(f"Login error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


# ============================================================
#  UPLOAD (Multi-user with MongoDB)
# ============================================================

@app.route('/api/upload', methods=['POST'])
def upload_data():
    try:
        username = request.form.get("username", "").strip().lower()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        file_content = file.read()
        file_extension = file.filename.split('.')[-1].lower()
        print(f"Processing {file.filename} ({file_extension}) for user: {username or 'anonymous'}")

        if file_extension == 'csv':
            records = process_csv(file_content)
        elif file_extension in ['xlsx', 'xls']:
            records = process_excel(file_content)
        else:
            return jsonify({'error': f'Unsupported file type: {file_extension}'}), 400

        if not records:
            return jsonify({'error': 'No records could be parsed from the file'}), 400

        import time
        dataset_id = "ds_" + str(int(time.time() * 1000))  # ms precision to avoid collisions

        if username:
            # Build single document: 1 CSV = 1 MongoDB document
            dataset_doc = {
                "dataset_id": dataset_id,
                "username": username,
                "filename": file.filename,
                "rows": len(records),
                "columns": records[0].get('columns', []) if records else [],
                "type": records[0].get('type', 'structured') if records else 'structured',
                "format": records[0].get('format', file_extension) if records else file_extension,
                "records": [r.get('data', {}) for r in records],
                "upload_time": datetime.now().isoformat()
            }
            try:
                datasets_collection.insert_one(dataset_doc)
            except Exception as dup_err:
                return jsonify({'error': 'Duplicate upload detected. Please try again.'}), 409
            current_records = records
        else:
            global sales_data
            sales_data = records
            file_history.append({'filename': file.filename, 'type': file_extension,
                                 'records': len(records), 'timestamp': datetime.now().isoformat()})
            current_records = records

        insights = extract_sales_insights(current_records)
        product_insights = get_product_insights(current_records)

        return jsonify({
            'message': 'File processed successfully',
            'dataset_id': dataset_id,
            'records_added': len(records),
            'total_records': len(current_records),
            'insights': insights,
            'product_insights': product_insights
        })
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


# ============================================================
#  QUERY HELPERS
# ============================================================

def compute_all_aggregations(df):
    """Run all meaningful aggregations in pandas — exact, never hallucinated."""
    result = {}

    # Convert numeric-looking columns
    for col in df.columns:
        converted = pd.to_numeric(
            df[col].astype(str).str.replace(r'[$₹,]', '', regex=True),
            errors='coerce'
        )
        if converted.notna().sum() > len(df) * 0.5:
            df[col] = converted

    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    categorical_cols = [c for c in df.columns if c not in numeric_cols]

    # Overall stats for each numeric column
    result['overall'] = {}
    for col in numeric_cols:
        result['overall'][col] = {
            'total': round(float(df[col].sum()), 2),
            'average': round(float(df[col].mean()), 2),
            'max': round(float(df[col].max()), 2),
            'min': round(float(df[col].min()), 2),
            'count': int(df[col].count())
        }

    # Breakdowns: every categorical x every numeric
    result['breakdowns'] = {}
    for cat in categorical_cols:
        unique_vals = df[cat].nunique()
        if unique_vals < 2 or unique_vals > 100:
            continue
        result['breakdowns'][cat] = {}
        for num in numeric_cols:
            grouped = (
                df.groupby(cat)[num]
                .agg(['sum', 'mean', 'count'])
                .round(2)
                .sort_values('sum', ascending=False)
            )
            result['breakdowns'][cat][num] = grouped.to_dict(orient='index')

    # ── Cross-category aggregations (categorical × categorical) ─────────
    result['category_cross'] = {}
    valid_cats = [c for c in categorical_cols if 2 <= df[c].nunique() <= 100]
    for i, cat_a in enumerate(valid_cats):
        for cat_b in valid_cats[i + 1:]:
            cross_size = df[cat_a].nunique() * df[cat_b].nunique()
            if cross_size > 500:
                continue
            cross_key = f"{cat_a}__{cat_b}"
            cross = df.groupby([cat_a, cat_b]).size().reset_index(name='count')
            # Also add numeric sums for each cross-group
            for num in numeric_cols:
                cross[num] = df.groupby([cat_a, cat_b])[num].sum().values
                cross[num] = cross[num].round(2)
            result['category_cross'][cross_key] = cross.to_dict(orient='records')

    # Date-based monthly breakdown
    date_col = next((c for c in df.columns if get_canonical_name(c) == 'date'), None)
    if date_col:
        df['_parsed_date'] = pd.to_datetime(df[date_col].astype(str), errors='coerce', dayfirst=True)
        df['_month'] = df['_parsed_date'].dt.to_period('M').astype(str)
        result['by_month'] = {}
        for num in numeric_cols:
            monthly = df.groupby('_month')[num].sum().round(2).to_dict()
            result['by_month'][num] = dict(sorted(monthly.items()))

    result['total_rows'] = len(df)
    result['columns'] = list(df.columns)
    return result


def build_query_context(computed):
    """Build a compact, structured context string from pre-computed aggregations."""
    lines = []
    lines.append(f"Total rows in dataset: {computed['total_rows']}")
    lines.append(f"Available columns: {', '.join(computed['columns'])}")

    if computed.get('overall'):
        lines.append("\n--- OVERALL TOTALS (exact) ---")
        for col, stats in computed['overall'].items():
            lines.append(
                f"  {col}: total={stats['total']:,}  avg={stats['average']:,}  "
                f"max={stats['max']:,}  min={stats['min']:,}  count={stats['count']}"
            )

    if computed.get('breakdowns'):
        lines.append("\n--- BREAKDOWNS BY CATEGORY (exact) ---")
        for cat, num_breakdowns in computed['breakdowns'].items():
            for num_col, data in num_breakdowns.items():
                lines.append(f"\n  {num_col} grouped by '{cat}':")
                for group, stats in list(data.items())[:50]:
                    lines.append(
                        f"    {group}: total={stats['sum']:,}  avg={stats['mean']:,}  count={stats['count']}"
                    )

    if computed.get('category_cross'):
        lines.append("\n--- CROSS-CATEGORY BREAKDOWNS (exact) ---")
        for cross_key, rows in computed['category_cross'].items():
            cat_a, cat_b = cross_key.split('__', 1)
            lines.append(f"\n  '{cat_a}' × '{cat_b}':")
            for row in rows[:80]:
                parts = [f"{k}={v}" for k, v in row.items()]
                lines.append(f"    {', '.join(parts)}")

    if computed.get('by_month'):
        lines.append("\n--- MONTHLY TRENDS (exact) ---")
        for col, monthly in computed['by_month'].items():
            lines.append(f"\n  {col} by month:")
            for month, val in monthly.items():
                lines.append(f"    {month}: {val:,}")

    return '\n'.join(lines)


# ============================================================
#  SEMANTIC COLUMN MATCHING
# ============================================================

# Extended synonym map: user term → list of canonical column names it could mean
_QUERY_SYNONYMS = {
    'sales': ['revenue', 'price', 'quantity'],
    'revenue': ['revenue'],
    'income': ['revenue'],
    'turnover': ['revenue'],
    'earnings': ['revenue'],
    'amount': ['revenue', 'price'],
    'money': ['revenue', 'price'],
    'total': ['revenue'],
    'city': ['region'],
    'location': ['region'],
    'area': ['region'],
    'place': ['region'],
    'state': ['region'],
    'branch': ['region'],
    'zone': ['region'],
    'territory': ['region'],
    'items': ['product'],
    'goods': ['product'],
    'product': ['product'],
    'products': ['product'],
    'sku': ['product'],
    'model': ['product'],
    'category': ['product'],
    'payment': ['payment'],
    'pay': ['payment'],
    'payment_method': ['payment'],
    'transaction': ['payment'],
    'mode': ['payment'],
    'customer': ['customer'],
    'client': ['customer'],
    'buyer': ['customer'],
    'account': ['customer'],
    'date': ['date'],
    'time': ['date'],
    'period': ['date'],
    'month': ['date'],
    'when': ['date'],
    'quantity': ['quantity'],
    'qty': ['quantity'],
    'units': ['quantity'],
    'volume': ['quantity'],
    'sold': ['quantity', 'revenue'],
    'price': ['price'],
    'cost': ['price'],
    'rate': ['price'],
    'mrp': ['price'],
    'stage': ['pipeline_stage'],
    'pipeline': ['pipeline_stage'],
    'status': ['pipeline_stage'],
    'deal': ['pipeline_stage'],
    'region': ['region'],
    'regions': ['region'],
}


def _match_query_term_to_column(term, df_columns):
    """Match a single query term to the best actual DataFrame column.

    Priority:
      1. Exact canonical match via COLUMN_ALIASES
      2. Synonym lookup via _QUERY_SYNONYMS
      3. Fuzzy string matching via difflib
    Returns the actual df column name or None.
    """
    import difflib
    term_lower = term.strip().lower().replace(' ', '_')
    col_canonicals = {col: get_canonical_name(col) for col in df_columns}

    # 1. Direct canonical check — "revenue" in query, "revenue" column exists
    for col, canon in col_canonicals.items():
        if term_lower == canon or term_lower == col.lower():
            return col

    # 2. Synonym lookup
    synonyms = _QUERY_SYNONYMS.get(term_lower, [])
    for syn_canon in synonyms:
        for col, canon in col_canonicals.items():
            if canon == syn_canon:
                return col

    # 3. Check COLUMN_ALIASES directly
    for canonical, aliases in COLUMN_ALIASES.items():
        if term_lower in aliases or term_lower == canonical:
            for col, canon in col_canonicals.items():
                if canon == canonical:
                    return col

    # 4. Fuzzy match against column names + aliases
    all_targets = {}
    for col in df_columns:
        all_targets[col.lower()] = col
        canon = col_canonicals[col]
        all_targets[canon] = col
        for canonical, aliases in COLUMN_ALIASES.items():
            if canon == canonical:
                for alias in aliases:
                    all_targets[alias] = col

    matches = difflib.get_close_matches(term_lower, all_targets.keys(), n=1, cutoff=0.6)
    if matches:
        return all_targets[matches[0]]

    return None


def semantic_column_match(query_text, df_columns):
    """Map all meaningful words in a user query to actual DataFrame columns.

    Returns dict: {matched_term: actual_column_name}
    """
    import re as _re
    stop_words = {
        'in', 'by', 'of', 'the', 'a', 'an', 'for', 'and', 'or', 'vs',
        'with', 'from', 'to', 'is', 'are', 'was', 'were', 'what', 'which',
        'how', 'many', 'much', 'show', 'tell', 'me', 'give', 'list', 'get',
        'find', 'display', 'per', 'each', 'all', 'between', 'on', 'at',
        'distribution', 'breakdown', 'analysis', 'report', 'data', 'total',
        'count', 'number', 'average', 'sum', 'max', 'min', 'top', 'bottom',
        'highest', 'lowest', 'most', 'least',
    }
    tokens = _re.findall(r'[a-z_]+', query_text.lower())
    matched = {}
    for token in tokens:
        if token in stop_words:
            continue
        col = _match_query_term_to_column(token, df_columns)
        if col and col not in matched.values():
            matched[token] = col
    return matched


# ============================================================
#  QUERY INTENT DETECTION & DIRECT EXECUTION
# ============================================================

def detect_query_intent(query, df):
    """Detect simple query intents that can be answered directly from pandas.

    Returns a dict with 'type' and relevant keys, or None if the query
    should be forwarded to Gemini.
    """
    import re as _re
    q = query.strip().lower()
    columns = list(df.columns)
    col_match = semantic_column_match(q, columns)

    if len(col_match) < 1:
        return None

    matched_cols = list(col_match.values())
    matched_terms = list(col_match.keys())

    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    categorical_cols = [c for c in columns if c not in numeric_cols
                        and not c.startswith('_')]

    # Detect filter values: words in the query that match actual category values
    def find_filter_value(col):
        unique_vals = df[col].dropna().astype(str).str.lower().unique()
        tokens = _re.findall(r'[a-z0-9_]+', q)
        for token in tokens:
            for val in unique_vals:
                if token == val.lower() or token in val.lower().split():
                    return val
        # Try multi-word match
        for val in unique_vals:
            if val.lower() in q:
                return val
        return None

    # ── Pattern 1: "<column> in <value>" → category filter
    # e.g., "payment in coimbatore", "products in chennai"
    for col in matched_cols:
        if col in categorical_cols:
            for other_col in categorical_cols:
                if other_col != col:
                    fv = find_filter_value(other_col)
                    if fv:
                        return {
                            'type': 'category_filter',
                            'column': col,
                            'filter_column': other_col,
                            'filter_value': fv,
                        }

    # ── Pattern 2: "<numeric> in/by <category_value>" → numeric for a filter
    # e.g., "sales in coimbatore", "revenue in chennai"
    for col in matched_cols:
        if col in numeric_cols:
            for cat in categorical_cols:
                fv = find_filter_value(cat)
                if fv:
                    return {
                        'type': 'numeric_filter',
                        'column': col,
                        'filter_column': cat,
                        'filter_value': fv,
                    }

    # ── Pattern 3: "<numeric> by <category>" → grouped aggregation
    # e.g., "revenue by region", "quantity by product"
    by_patterns = ['by', 'per', 'for each', 'grouped by', 'across']
    has_by = any(p in q for p in by_patterns)
    if has_by and len(matched_cols) >= 2:
        num_found = [c for c in matched_cols if c in numeric_cols]
        cat_found = [c for c in matched_cols if c in categorical_cols]
        if num_found and cat_found:
            return {
                'type': 'grouped_aggregation',
                'column': num_found[0],
                'group_by': cat_found[0],
            }

    # ── Pattern 4: "<category> vs <category>" → cross-category
    # e.g., "region vs payment", "product by payment"
    vs_patterns = ['vs', 'versus', 'against', 'compared to']
    has_vs = any(p in q for p in vs_patterns)
    if has_vs or has_by:
        cat_found = [c for c in matched_cols if c in categorical_cols]
        if len(cat_found) >= 2:
            return {
                'type': 'cross_category',
                'column_a': cat_found[0],
                'column_b': cat_found[1],
            }

    # ── Pattern 5: Single categorical column mentioned with a filter value
    # e.g., just "coimbatore" or "payment coimbatore"
    for cat in categorical_cols:
        fv = find_filter_value(cat)
        if fv:
            # Find something to report about that value
            target_col = None
            for col in matched_cols:
                if col != cat:
                    target_col = col
                    break
            if target_col:
                if target_col in numeric_cols:
                    return {
                        'type': 'numeric_filter',
                        'column': target_col,
                        'filter_column': cat,
                        'filter_value': fv,
                    }
                else:
                    return {
                        'type': 'category_filter',
                        'column': target_col,
                        'filter_column': cat,
                        'filter_value': fv,
                    }

    return None


def execute_intent(intent, df):
    """Execute a detected intent directly using pandas. Returns a formatted
    response string and a structured data dict, or (None, None) on failure."""
    import re as _re
    itype = intent['type']

    numeric_cols = df.select_dtypes(include='number').columns.tolist()

    try:
        if itype == 'category_filter':
            col = intent['column']
            fcol = intent['filter_column']
            fval = intent['filter_value']
            mask = df[fcol].astype(str).str.lower() == fval.lower()
            subset = df.loc[mask, col]
            counts = subset.value_counts()
            if counts.empty:
                return None, None
            original_fcol = _original_column_map.get(fcol, fcol)
            original_col = _original_column_map.get(col, col)
            lines = [f"**{original_col} distribution where {original_fcol} = {fval.title()}:**\n"]
            data_rows = []
            for val, cnt in counts.items():
                lines.append(f"- {val}: {cnt}")
                data_rows.append({col: val, 'count': int(cnt)})
            # Also add numeric totals for this filter if available
            for ncol in numeric_cols:
                if ncol != col:
                    total = df.loc[mask, ncol].sum()
                    if total > 0:
                        lines.append(f"\nTotal {_original_column_map.get(ncol, ncol)}: ₹{total:,.2f}")
            return '\n'.join(lines), {'intent': intent, 'results': data_rows}

        elif itype == 'numeric_filter':
            col = intent['column']
            fcol = intent['filter_column']
            fval = intent['filter_value']
            mask = df[fcol].astype(str).str.lower() == fval.lower()
            series = pd.to_numeric(df.loc[mask, col], errors='coerce').dropna()
            if series.empty:
                return None, None
            original_fcol = _original_column_map.get(fcol, fcol)
            original_col = _original_column_map.get(col, col)
            stats = {
                'total': round(float(series.sum()), 2),
                'average': round(float(series.mean()), 2),
                'max': round(float(series.max()), 2),
                'min': round(float(series.min()), 2),
                'count': int(series.count()),
            }
            lines = [
                f"**{original_col} for {original_fcol} = {fval.title()}:**\n",
                f"- Total: ₹{stats['total']:,.2f}",
                f"- Average: ₹{stats['average']:,.2f}",
                f"- Max: ₹{stats['max']:,.2f}",
                f"- Min: ₹{stats['min']:,.2f}",
                f"- Count: {stats['count']}",
            ]
            return '\n'.join(lines), {'intent': intent, 'results': stats}

        elif itype == 'grouped_aggregation':
            col = intent['column']
            grp = intent['group_by']
            grouped = df.groupby(grp)[col].agg(['sum', 'mean', 'count']).round(2)
            grouped = grouped.sort_values('sum', ascending=False)
            original_col = _original_column_map.get(col, col)
            original_grp = _original_column_map.get(grp, grp)
            lines = [f"**{original_col} by {original_grp}:**\n"]
            data_rows = []
            for idx, row in grouped.iterrows():
                lines.append(f"- {idx}: Total=₹{row['sum']:,.2f}, Avg=₹{row['mean']:,.2f}, Count={int(row['count'])}")
                data_rows.append({grp: idx, 'total': row['sum'], 'average': row['mean'], 'count': int(row['count'])})
            return '\n'.join(lines), {'intent': intent, 'results': data_rows}

        elif itype == 'cross_category':
            col_a = intent['column_a']
            col_b = intent['column_b']
            cross = df.groupby([col_a, col_b]).size().reset_index(name='count')
            cross = cross.sort_values('count', ascending=False)
            original_a = _original_column_map.get(col_a, col_a)
            original_b = _original_column_map.get(col_b, col_b)
            lines = [f"**{original_a} × {original_b} distribution:**\n"]
            data_rows = []
            for _, row in cross.iterrows():
                lines.append(f"- {row[col_a]} + {row[col_b]}: {int(row['count'])}")
                data_rows.append({col_a: row[col_a], col_b: row[col_b], 'count': int(row['count'])})
            # Add numeric totals per cross-group if available
            for ncol in numeric_cols:
                num_cross = df.groupby([col_a, col_b])[ncol].sum().round(2)
                if num_cross.sum() > 0:
                    lines.append(f"\n{_original_column_map.get(ncol, ncol)} totals:")
                    for (va, vb), total in num_cross.items():
                        lines.append(f"  {va} + {vb}: ₹{total:,.2f}")
            return '\n'.join(lines), {'intent': intent, 'results': data_rows}

    except Exception as e:
        print(f"Intent execution error: {e}")
    return None, None


# ============================================================
#  QUERY (Multi-user with MongoDB)
# ============================================================

@app.route('/api/query', methods=['POST'])
def handle_query():
    try:
        data = request.json
        raw_query = data.get('query', '')
        query = raw_query.lower()
        username = data.get('username', '').strip().lower()
        dataset_id = data.get('dataset_id', '').strip()

        if not raw_query:
            return jsonify({'error': 'No query provided'}), 400

        if username and dataset_id:
            current_data = get_records_from_db(username, dataset_id)
        else:
            current_data = sales_data

        data_summary = extract_sales_insights(current_data)

        if data_summary['record_count'] == 0:
            return jsonify({
                'query': raw_query,
                'response': 'No sales data available. Please upload a CSV or Excel file first.',
                'analysis': {'has_data': False},
                'data_summary': data_summary,
                'visualizations': []
            })

        # ── 1. Rebuild DataFrame from records ──────────────────────────────
        rows = [r['data'] for r in current_data if 'data' in r]
        df = pd.DataFrame(rows)

        # ── 2. Compute ALL aggregations in Python (exact math) ─────────────
        computed = compute_all_aggregations(df)

        # ── 3. Try direct pandas answer via intent detection ───────────────
        ai_response = None
        intent = detect_query_intent(raw_query, df)
        if intent:
            direct_answer, intent_data = execute_intent(intent, df)
            if direct_answer:
                ai_response = direct_answer
                print(f"Intent hit: {intent['type']} — skipped Gemini call")

        # ── 4. Fallback to Gemini for complex queries ──────────────────────
        if ai_response is None:
            context = build_query_context(computed)

            prompt = f"""You are a Sales Analytics Agent. A user has asked a question about their sales data.

ALL NUMBERS BELOW HAVE BEEN CALCULATED BY PYTHON — they are 100% accurate.
Your ONLY job is to:
1. Read the pre-computed data below
2. Find the answer to the user's question
3. State it directly and clearly in the first sentence
4. Add 1-2 lines of business insight if genuinely useful
5. NEVER recalculate, guess, or make up any number

USER QUESTION: {raw_query}

PRE-COMPUTED DATA FROM THE DATASET:
{context}

STRICT RULES:
- Answer the question directly in your first sentence
- Use ₹ for all currency/revenue values
- Use exact numbers from the data above only
- If the question is about something not in the data, say: "This information is not available in the uploaded dataset." and list what IS available
- Keep response concise — no unnecessary padding
- For "top N" questions, list them ranked by the relevant metric
- For "compare" questions, show both values side by side

YOUR ANSWER:"""

            ai_response = call_gemini(prompt, dataset_id=dataset_id, query=raw_query)

        # ── 5. Visualizations ──────────────────────────────────────────────
        visualization_keywords = ['chart', 'graph', 'plot', 'visualize', 'diagram',
                                  'trend', 'bar', 'pie', 'histogram', 'scatter']
        needs_visualization = any(kw in query for kw in visualization_keywords)
        charts = {}
        if needs_visualization and len(current_data) > 0:
            charts = visualizer.generate_all_charts(current_data)

        # ── 6. Save chat to MongoDB ────────────────────────────────────────
        if username and dataset_id:
            chats_collection.insert_one({
                "username": username,
                "dataset_id": dataset_id,
                "query": raw_query,
                "response": ai_response,
                "timestamp": datetime.now().isoformat()
            })

        return jsonify({
            'query': raw_query,
            'response': ai_response,
            'analysis': {
                'has_data': True,
                'data_points': data_summary['record_count'],
                'revenue_available': data_summary['total_revenue'] > 0,
                'needs_visualization': needs_visualization
            },
            'data_summary': {
                'total_records': data_summary['record_count'],
                'total_revenue': data_summary['total_revenue'],
                'regions_count': len(data_summary['regions']),
                'products_count': len(data_summary['products']),
                'revenue': {
                    'total': data_summary['total_revenue'],
                    'average': data_summary['avg_revenue']
                },
                'categories': {
                    'regions': data_summary['regions'],
                    'products': data_summary['products'],
                    'time_periods': data_summary['time_periods'][:10]
                },
                'metrics_available': data_summary['metrics_available'],
                'product_insights': get_product_insights(current_data),
                'dynamic_stats': [
                    {
                        'id': 'records',
                        'label': 'Records',
                        'value': data_summary['record_count'],
                        'type': 'count'
                    },
                    {
                        'id': 'revenue',
                        'label': 'Revenue',
                        'value': data_summary['total_revenue'] if data_summary['metrics_available']['revenue'] else None,
                        'type': 'currency',
                        'available': data_summary['metrics_available']['revenue']
                    },
                    {
                        'id': 'regions',
                        'label': data_summary.get('region_label', 'Regions'),
                        'value': len(data_summary['regions']) if data_summary['metrics_available']['region'] else None,
                        'type': 'count',
                        'available': data_summary['metrics_available']['region']
                    },
                    {
                        'id': 'products',
                        'label': data_summary.get('product_label', 'Products'),
                        'value': len(data_summary['products']) if data_summary['metrics_available']['product'] else None,
                        'type': 'count',
                        'available': data_summary['metrics_available']['product']
                    }
                ]
            },
            'visualizations': charts
        })

    except Exception as e:
        print(f"Query error: {str(e)}")
        return jsonify({'error': f'AI service error: {str(e)}'}), 500

# ============================================================
#  USER DATASETS
# ============================================================

@app.route('/api/datasets/<username>', methods=['GET'])
def get_user_datasets(username):
    try:
        username = username.strip().lower()
        # Project out the heavy 'records' field for listing
        docs = list(datasets_collection.find(
            {"username": username},
            {"_id": 0, "records": 0}
        ).sort("upload_time", -1))
        return jsonify(docs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
#  CHAT HISTORY
# ============================================================

@app.route('/api/chats/<username>/<dataset_id>', methods=['GET'])
def get_chat_history(username, dataset_id):
    try:
        username = username.strip().lower()
        chat_docs = list(chats_collection.find(
            {"username": username, "dataset_id": dataset_id}, {"_id": 0}
        ).sort("timestamp", 1))
        return jsonify(chat_docs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
#  DELETE DATASET
# ============================================================

@app.route('/api/datasets/<username>/<dataset_id>', methods=['DELETE'])
def delete_dataset(username, dataset_id):
    try:
        username = username.strip().lower()
        datasets_collection.delete_one({"username": username, "dataset_id": dataset_id})
        chats_collection.delete_many({"username": username, "dataset_id": dataset_id})
        return jsonify({'message': 'Dataset deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
#  DATA SUMMARY
# ============================================================

@app.route('/api/data/summary', methods=['GET'])
def get_data_summary():
    username = request.args.get('username', '').strip().lower()
    dataset_id = request.args.get('dataset_id', '').strip()
    if username and dataset_id:
        current_data = get_records_from_db(username, dataset_id)
    else:
        current_data = sales_data
    insights = extract_sales_insights(current_data)
    product_insights = get_product_insights(current_data)
    return jsonify({
        'total_records': len(current_data),
        'file_history': file_history[-5:],
        'revenue': {'total': insights['total_revenue'], 'average': insights['avg_revenue']},
        'categories': {
            'regions': insights['regions'], 'products': insights['products'],
            'time_periods': insights['time_periods'][:10]
        },
        'available_columns': insights['columns'],
        'product_insights': product_insights,
        'metrics_available': insights['metrics_available'],
        'dynamic_stats': [
            {'id': 'records', 'label': 'Records', 'value': len(current_data), 'type': 'count'},
            {'id': 'revenue', 'label': 'Revenue',
             'value': insights['total_revenue'] if insights['metrics_available']['revenue'] else None,
             'type': 'currency', 'available': insights['metrics_available']['revenue']},
            {'id': 'regions', 'label': insights.get('region_label', 'Regions'),
             'value': len(insights['regions']) if insights['metrics_available']['region'] else None,
             'type': 'count', 'available': insights['metrics_available']['region']},
            {'id': 'products', 'label': insights.get('product_label', 'Products'),
             'value': len(insights['products']) if insights['metrics_available']['product'] else None,
             'type': 'count', 'available': insights['metrics_available']['product']}
        ]
    })


# ============================================================
#  VISUALIZATIONS
# ============================================================

@app.route('/api/visualizations', methods=['GET'])
def get_visualizations():
    try:
        username = request.args.get('username', '').strip().lower()
        dataset_id = request.args.get('dataset_id', '').strip()
        if username and dataset_id:
            current_data = get_records_from_db(username, dataset_id)
        else:
            current_data = sales_data
        if not current_data:
            return jsonify({'error': 'No data available for visualization'}), 400
        charts = visualizer.generate_all_charts(current_data)
        if not charts:
            return jsonify({'error': 'No charts could be generated from the data'}), 400
        return jsonify({'message': f'Generated {len(charts)} visualization(s)', 'charts': charts, 'chart_types': list(charts.keys())})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/visualize/<chart_type>', methods=['GET'])
def get_specific_visualization(chart_type):
    try:
        username = request.args.get('username', '').strip().lower()
        dataset_id = request.args.get('dataset_id', '').strip()
        if username and dataset_id:
            current_data = get_records_from_db(username, dataset_id)
        else:
            current_data = sales_data
        if not current_data:
            return jsonify({'error': 'No data available'}), 400
        chart_types = {
            'revenue_trend': visualizer.create_revenue_trend,
            'regional_sales': visualizer.create_regional_sales,
            'product_performance': visualizer.create_product_performance,
            'sales_distribution': visualizer.create_sales_distribution,
            'monthly_trend': visualizer.create_monthly_trend,
            'pipeline_stages': visualizer.create_pipeline_stage_chart,
        }
        chart = chart_types.get(chart_type, lambda _: None)(current_data) if chart_type in chart_types else None
        if chart:
            return jsonify({'chart_type': chart_type, 'image': chart, 'message': 'Chart generated successfully'})
        return jsonify({'error': f'Could not generate {chart_type} chart'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
#  PREDICTIONS
# ============================================================

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    try:
        username = request.args.get('username', '').strip().lower()
        dataset_id = request.args.get('dataset_id', '').strip()
        if username and dataset_id:
            current_data = get_records_from_db(username, dataset_id)
        else:
            current_data = sales_data
        if not current_data:
            return jsonify({'available': False, 'message': 'No data loaded. Please upload a CSV or Excel file first.'})

        summary = extract_sales_insights(current_data)
        product_stats = {}
        region_stats = {}
        category_stats = {}

        for record in current_data:
            if 'data' not in record:
                continue
            d = record['data']
            rev_val = None
            rev_key = first_matching_key(d, 'revenue')
            if rev_key:
                rev_val = to_float(d.get(rev_key))
            if rev_val is None:
                p_key = first_matching_key(d, 'price')
                q_key = first_matching_key(d, 'quantity')
                if p_key and q_key:
                    pv, qv = to_float(d.get(p_key)), to_float(d.get(q_key))
                    if pv is not None and qv is not None:
                        rev_val = pv * qv
            qty_val = None
            q_key = first_matching_key(d, 'quantity')
            if q_key:
                qty_val = to_float(d.get(q_key))
            pr_key = first_matching_key(d, 'product')
            if pr_key:
                pname = str(d[pr_key]).strip()
                if pname and pname.lower() != 'nan':
                    if pname not in product_stats:
                        product_stats[pname] = {'revenue': 0, 'quantity': 0, 'count': 0}
                    product_stats[pname]['count'] += 1
                    if rev_val is not None: product_stats[pname]['revenue'] += rev_val
                    if qty_val is not None: product_stats[pname]['quantity'] += qty_val
            r_key = first_matching_key(d, 'region')
            if r_key:
                rname = str(d[r_key]).strip()
                if rname and rname.lower() != 'nan':
                    if rname not in region_stats:
                        region_stats[rname] = {'revenue': 0, 'quantity': 0, 'count': 0}
                    region_stats[rname]['count'] += 1
                    if rev_val is not None: region_stats[rname]['revenue'] += rev_val
                    if qty_val is not None: region_stats[rname]['quantity'] += qty_val
            for cat_alias in ['category', 'product_line', 'product line', 'segment', 'type']:
                cat_key = None
                for k in d:
                    if normalize_column_key(k) == cat_alias.replace(' ', '_'):
                        cat_key = k
                        break
                if cat_key:
                    cname = str(d[cat_key]).strip()
                    if cname and cname.lower() != 'nan':
                        if cname not in category_stats:
                            category_stats[cname] = {'revenue': 0, 'quantity': 0, 'count': 0}
                        category_stats[cname]['count'] += 1
                        if rev_val is not None: category_stats[cname]['revenue'] += rev_val
                        if qty_val is not None: category_stats[cname]['quantity'] += qty_val
                    break

        product_text = ""
        if product_stats:
            product_text = "\nPER-PRODUCT BREAKDOWN:\n"
            for p, s in sorted(product_stats.items(), key=lambda x: -x[1]['revenue']):
                product_text += f"  * {p}: Revenue ₹{s['revenue']:,.2f}, Qty {s['quantity']:.0f}, Records {s['count']}\n"
        region_text = ""
        if region_stats:
            region_text = "\nPER-REGION BREAKDOWN:\n"
            for r, s in sorted(region_stats.items(), key=lambda x: -x[1]['revenue']):
                region_text += f"  * {r}: Revenue ₹{s['revenue']:,.2f}, Qty {s['quantity']:.0f}, Records {s['count']}\n"
        category_text = ""
        if category_stats:
            category_text = "\nPER-CATEGORY BREAKDOWN:\n"
            for c, s in sorted(category_stats.items(), key=lambda x: -x[1]['revenue']):
                category_text += f"  * {c}: Revenue ₹{s['revenue']:,.2f}, Qty {s['quantity']:.0f}, Records {s['count']}\n"

        prompt = f"""You are an expert Sales Analytics & Strategy AI.

COMPLETE SALES DATA METRICS:
- Total Records: {summary['record_count']}
- Total Revenue: ₹{summary['total_revenue']:,.2f}
- Average Revenue per record: ₹{summary['avg_revenue']:,.2f}
- Available Columns: {', '.join(summary['columns'])}
{product_text}{region_text}{category_text}

CRITICAL INSTRUCTIONS:
1. Use the EXACT numbers from the breakdowns above
2. Do NOT say "Data Unavailable"
3. Use Indian Rupees (₹) for all currency values
4. Be specific with actual product/region names and numbers
5. Provide 3-5 items per section
6. Output STRICT JSON ONLY — no markdown, no code fences

JSON FORMAT:
{{
  "sales_forecast": {{"title": "Sales Forecast", "items": [{{"label": "short title", "value": "predicted value", "detail": "1-2 sentence explanation", "trend": "up|down|stable", "confidence": "High|Medium|Low"}}]}},
  "product_predictions": {{"title": "Product Predictions", "items": [{{"label": "product name", "value": "metric", "detail": "explanation", "trend": "up|down|stable", "confidence": "High|Medium|Low"}}]}},
  "regional_predictions": {{"title": "Regional Predictions", "items": [{{"label": "region name", "value": "metric", "detail": "explanation", "trend": "up|down|stable", "confidence": "High|Medium|Low"}}]}},
  "alternatives": {{"title": "Alternative Strategies", "items": [{{"label": "strategy", "detail": "what to do and why", "impact": "High|Medium|Low", "category": "pricing|marketing|product|distribution|customer"}}]}},
  "improvements": {{"title": "Sales Improvement Recommendations", "items": [{{"label": "improvement", "detail": "recommendation", "impact": "High|Medium|Low", "category": "pricing|marketing|product|distribution|customer", "expected_boost": "estimated improvement"}}]}}
}}"""

        text = (call_gemini(prompt) or '').strip()
        import re as _re
        text = _re.sub(r'^```(?:json)?\s*', '', text)
        text = _re.sub(r'\s*```$', '', text).strip()
        predictions = json.loads(text)

        return jsonify({
            'available': True, 'predictions': predictions,
            'data_summary': {
                'total_records': summary['record_count'],
                'total_revenue': summary['total_revenue'],
                'products': list(product_stats.keys())[:10],
                'regions': list(region_stats.keys())[:10]
            }
        })
    except json.JSONDecodeError:
        return jsonify({'available': False, 'message': 'Failed to parse AI predictions. Please try again.'}), 500
    except Exception as e:
        print(f"Predictions error: {str(e)}")
        return jsonify({'available': False, 'message': f'Error generating predictions: {str(e)}'}), 500


# ============================================================
#  LEGACY / UTILS
# ============================================================

@app.route('/api/clear', methods=['POST'])
def clear_data():
    global sales_data, file_history, _original_column_map
    sales_data = []
    file_history = []
    _original_column_map = {}
    return jsonify({'message': 'All data cleared successfully'})


@app.route('/api/samples', methods=['GET'])
def list_samples():
    sample_dir = os.path.join(os.path.dirname(__file__), 'sample_data')
    samples = []
    if os.path.isdir(sample_dir):
        for fname in sorted(os.listdir(sample_dir)):
            if fname.lower().endswith(('.csv', '.xlsx', '.xls')):
                fpath = os.path.join(sample_dir, fname)
                samples.append({'name': fname, 'size': os.path.getsize(fpath)})
    return jsonify({'samples': samples})


@app.route('/api/samples/<path:filename>', methods=['GET'])
def get_sample(filename):
    username = request.args.get('username', '').strip().lower()
    sample_dir = os.path.join(os.path.dirname(__file__), 'sample_data')
    fpath = os.path.join(sample_dir, filename)
    if not os.path.isfile(fpath):
        return jsonify({'error': 'Sample file not found'}), 404

    with open(fpath, 'rb') as f:
        file_content = f.read()

    ext = filename.rsplit('.', 1)[-1].lower()
    if ext == 'csv':
        records = process_csv(file_content)
    elif ext in ('xlsx', 'xls'):
        records = process_excel(file_content)
    else:
        return jsonify({'error': f'Unsupported file type: {ext}'}), 400

    import time
    dataset_id = "ds_" + str(int(time.time() * 1000))  # ms precision to avoid collisions

    if username:
        # Build single document: 1 sample file = 1 MongoDB document
        dataset_doc = {
            "dataset_id": dataset_id,
            "username": username,
            "filename": filename,
            "rows": len(records),
            "columns": records[0].get('columns', []) if records else [],
            "type": records[0].get('type', 'structured') if records else 'structured',
            "format": records[0].get('format', ext) if records else ext,
            "records": [r.get('data', {}) for r in records],
            "upload_time": datetime.now().isoformat()
        }
        try:
            datasets_collection.insert_one(dataset_doc)
        except Exception:
            return jsonify({'error': 'Duplicate load detected. Please try again.'}), 409
    else:
        global sales_data
        sales_data = records
        file_history.append({'filename': filename, 'type': ext,
                             'records': len(records), 'timestamp': datetime.now().isoformat()})

    insights = extract_sales_insights(records)
    product_insights = get_product_insights(records)

    return jsonify({
        'message': 'Sample file loaded successfully',
        'dataset_id': dataset_id,
        'records_added': len(records),
        'total_records': len(records),
        'insights': insights,
        'product_insights': product_insights
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'ai_service': 'Google GenAI',
        'visualization': 'available',
        'data_records': len(sales_data),
        'files_uploaded': len(file_history)
    })


# ============================================================
#  CRASH REPORTS API
# ============================================================

crashreports_collection = db["crashreports"]
crashreports_collection.create_index([("created_at", -1)])


@app.route('/api/crashreports/posts', methods=['GET'])
def get_crashreport_posts():
    try:
        posts = list(
            crashreports_collection.find({}, {'_id': 0}).sort("created_at", -1)
        )
        return jsonify({'posts': posts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crashreports/posts', methods=['POST'])
def create_crashreport_post():
    try:
        data = request.get_json()
        required = ['title', 'strategy', 'wrong', 'lesson', 'category', 'username']
        for field in required:
            if not str(data.get(field, '')).strip():
                return jsonify({'error': f'Missing field: {field}'}), 400

        post = {
            'post_id':   'cr_' + str(int(datetime.now().timestamp() * 1000)),
            'username':  data['username'].strip(),
            'author':    'Anonymous' if data.get('anon') else data['username'].strip(),
            'anon':      bool(data.get('anon', False)),
            'category':  data['category'].strip(),
            'title':     data['title'].strip(),
            'strategy':  data['strategy'].strip(),
            'wrong':     data['wrong'].strip(),
            'lesson':    data['lesson'].strip(),
            'upvotes':   0,
            'metoo':     0,
            'bookmarks': 0,
            'created_at': datetime.now().isoformat()
        }
        crashreports_collection.insert_one(post)
        post.pop('_id', None)
        return jsonify({'message': 'Crash report created', 'post': post}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crashreports/posts/<post_id>/react', methods=['POST'])
def react_crashreport_post(post_id):
    try:
        data     = request.get_json()
        reaction = data.get('reaction')
        action   = data.get('action')

        if reaction not in ('upvotes', 'metoo', 'bookmarks'):
            return jsonify({'error': 'Invalid reaction'}), 400

        delta = 1 if action == 'add' else -1
        crashreports_collection.update_one(
            {'post_id': post_id},
            {'$inc': {reaction: delta}}
        )
        post = crashreports_collection.find_one({'post_id': post_id}, {'_id': 0})
        return jsonify({'post': post})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crashreports/posts/<post_id>', methods=['DELETE'])
def delete_crashreport_post(post_id):
    try:
        username = request.args.get('username', '').strip()
        if not username:
            return jsonify({'error': 'Username required'}), 400

        post = crashreports_collection.find_one({'post_id': post_id}, {'_id': 0})
        if not post:
            return jsonify({'error': 'Post not found'}), 404

        if post.get('username') != username:
            return jsonify({'error': 'You can only delete your own posts'}), 403

        crashreports_collection.delete_one({'post_id': post_id})
        return jsonify({'message': 'Post deleted'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crashreports/posts/<post_id>/comments', methods=['GET'])
def get_crashreport_comments(post_id):
    try:
        post = crashreports_collection.find_one({'post_id': post_id}, {'_id': 0})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        return jsonify({'comments': post.get('comments', [])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crashreports/posts/<post_id>/comments', methods=['POST'])
def add_crashreport_comment(post_id):
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        text = data.get('text', '').strip()

        if not username or not text:
            return jsonify({'error': 'Username and text required'}), 400

        comment = {
            'comment_id': 'cc_' + str(int(datetime.now().timestamp() * 1000)),
            'username': username,
            'text': text,
            'created_at': datetime.now().isoformat()
        }

        crashreports_collection.update_one(
            {'post_id': post_id},
            {'$push': {'comments': comment}}
        )
        return jsonify({'comment': comment}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
