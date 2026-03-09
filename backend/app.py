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
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = (response.text or '').strip()
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
#  QUERY (Multi-user with MongoDB)
# ============================================================

@app.route('/api/query', methods=['POST'])
def handle_query():
    try:
        data = request.json
        query = data.get('query', '').lower()
        username = data.get('username', '').strip().lower()
        dataset_id = data.get('dataset_id', '').strip()

        if not query:
            return jsonify({'error': 'No query provided'}), 400

        if username and dataset_id:
            current_data = get_records_from_db(username, dataset_id)
        else:
            current_data = sales_data

        data_summary = extract_sales_insights(current_data)

        if data_summary['record_count'] == 0:
            return jsonify({
                'query': query,
                'response': 'No sales data available. Please upload a CSV or Excel file first.',
                'analysis': {'has_data': False},
                'data_summary': data_summary,
                'visualizations': []
            })

        visualization_keywords = ['chart', 'graph', 'plot', 'visualize', 'diagram',
                                  'trend', 'bar', 'pie', 'histogram', 'scatter']
        needs_visualization = any(kw in query for kw in visualization_keywords)
        charts = {}
        if needs_visualization and len(current_data) > 0:
            charts = visualizer.generate_all_charts(current_data)

        full_data_text = ""
        if current_data:
            max_records = min(len(current_data), 200)
            for i, record in enumerate(current_data[:max_records]):
                if 'data' in record:
                    full_data_text += f"Row {i+1}: {json.dumps(record['data'])}\n"
            if len(current_data) > max_records:
                full_data_text += f"\n[Note: Showing first {max_records} of {len(current_data)} total records]\n"

        precomputed = ""
        if data_summary['metrics_available']['revenue']:
            precomputed += f"\n• Total Revenue (pre-computed, verified): ₹{data_summary['total_revenue']:,.2f}"
            precomputed += f"\n• Average Revenue per record: ₹{data_summary['avg_revenue']:,.2f}"
            precomputed += f"\n• Number of records: {data_summary['record_count']}"

        region_rev = {}
        product_rev = {}
        for record in current_data:
            if 'data' not in record:
                continue
            d = record['data']
            rev_key = first_matching_key(d, 'revenue')
            rev_val = to_float(d.get(rev_key)) if rev_key else None
            if rev_val is None:
                p_key = first_matching_key(d, 'price')
                q_key = first_matching_key(d, 'quantity')
                if p_key and q_key:
                    pv, qv = to_float(d.get(p_key)), to_float(d.get(q_key))
                    if pv is not None and qv is not None:
                        rev_val = pv * qv
            if rev_val is None:
                continue
            r_key = first_matching_key(d, 'region')
            if r_key:
                region_rev[str(d[r_key]).strip()] = region_rev.get(str(d[r_key]).strip(), 0) + rev_val
            pr_key = first_matching_key(d, 'product')
            if pr_key:
                product_rev[str(d[pr_key]).strip()] = product_rev.get(str(d[pr_key]).strip(), 0) + rev_val

        if region_rev:
            precomputed += "\n\n• Revenue by Region (pre-computed):"
            for rg, rv in sorted(region_rev.items(), key=lambda x: -x[1]):
                precomputed += f"\n  - {rg}: ₹{rv:,.2f}"
        if product_rev:
            precomputed += "\n\n• Revenue by Product (pre-computed):"
            for pr, rv in sorted(product_rev.items(), key=lambda x: -x[1]):
                precomputed += f"\n  - {pr}: ₹{rv:,.2f}"

        skip_canonical = {'revenue', 'price', 'quantity', 'date', 'region', 'product'}
        extra_breakdowns = {}
        for record in current_data:
            if 'data' not in record:
                continue
            d = record['data']
            rev_key = first_matching_key(d, 'revenue')
            rev_val = to_float(d.get(rev_key)) if rev_key else None
            if rev_val is None:
                p_key = first_matching_key(d, 'price')
                q_key = first_matching_key(d, 'quantity')
                if p_key and q_key:
                    pv, qv = to_float(d.get(p_key)), to_float(d.get(q_key))
                    if pv is not None and qv is not None:
                        rev_val = pv * qv
            if rev_val is None:
                continue
            for col_name, col_value in d.items():
                # For deduplicated columns like "region_1", check the canonical
                # of the full name, not a stripped version
                col_canonical = get_canonical_name(col_name)
                if col_canonical in skip_canonical:
                    continue
                str_val = str(col_value).strip()
                if not str_val or str_val.lower() == 'nan':
                    continue
                if to_float(str_val) is not None and col_canonical not in ('region',):
                    continue
                if col_name not in extra_breakdowns:
                    extra_breakdowns[col_name] = {}
                extra_breakdowns[col_name][str_val] = extra_breakdowns[col_name].get(str_val, 0) + rev_val

        for col_name, breakdown in extra_breakdowns.items():
            if len(breakdown) < 2 or len(breakdown) > 50:
                continue
            label = col_name.replace('_', ' ').title()
            precomputed += f"\n\n• Revenue by {label} (pre-computed):"
            for name, rev in sorted(breakdown.items(), key=lambda x: -x[1]):
                precomputed += f"\n  - {name}: ₹{rev:,.2f}"

        prompt = f"""You are a Sales Analytics Agent.

CRITICAL: You MUST ONLY use the EXACT data provided below.

ABSOLUTE RULES:
1. ONLY use data from the "COMPLETE DATASET" section below
2. DO NOT invent, assume, estimate, or hallucinate ANY values
3. If information is truly not present in ANY column of the dataset, respond: "This information is not available in the uploaded data."
4. Every number you mention MUST be traceable to the dataset below
5. Use Indian Rupee (₹) for all revenue/currency values
6. For overall totals/averages: use the PRE-COMPUTED VALUES directly
7. For filtered or cross-dimensional queries (e.g. "sales of X by Y", "total of A where B = C"), you MUST calculate by scanning the COMPLETE DATASET rows below and summing/filtering the relevant values
8. Cross-reference multiple columns as needed to answer the question — the dataset has many columns beyond the pre-computed ones
9. When the user asks about a specific subset (e.g. a specific district/region, payment mode, product line), iterate through the rows, filter matches, and compute the answer

PRE-COMPUTED VERIFIED METRICS (use for overall totals):
{precomputed}

COMPLETE DATASET ({data_summary['record_count']} records):
{full_data_text}

DATASET COLUMNS: {', '.join(data_summary['columns'])}

USER QUESTION: {query}

AVAILABLE VISUALIZATIONS: {list(charts.keys()) if charts else 'None generated'}

YOUR ANSWER (using ONLY the data above — scan rows for filtered/cross-dimensional queries):"""

        response = client.models.generate_content(model=model_name, contents=prompt)
        ai_response = response.text

        # Save chat to MongoDB
        if username and dataset_id:
            chats_collection.insert_one({
                "username": username, "dataset_id": dataset_id,
                "query": query, "response": ai_response,
                "timestamp": datetime.now().isoformat()
            })

        return jsonify({
            'query': query,
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
                'revenue': {'total': data_summary['total_revenue'], 'average': data_summary['avg_revenue']},
                'categories': {
                    'regions': data_summary['regions'],
                    'products': data_summary['products'],
                    'time_periods': data_summary['time_periods'][:10]
                },
                'metrics_available': data_summary['metrics_available'],
                'product_insights': get_product_insights(current_data),
                'dynamic_stats': [
                    {'id': 'records', 'label': 'Records', 'value': data_summary['record_count'], 'type': 'count'},
                    {'id': 'revenue', 'label': 'Revenue',
                     'value': data_summary['total_revenue'] if data_summary['metrics_available']['revenue'] else None,
                     'type': 'currency', 'available': data_summary['metrics_available']['revenue']},
                    {'id': 'regions', 'label': data_summary.get('region_label', 'Regions'),
                     'value': len(data_summary['regions']) if data_summary['metrics_available']['region'] else None,
                     'type': 'count', 'available': data_summary['metrics_available']['region']},
                    {'id': 'products', 'label': data_summary.get('product_label', 'Products'),
                     'value': len(data_summary['products']) if data_summary['metrics_available']['product'] else None,
                     'type': 'count', 'available': data_summary['metrics_available']['product']}
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

        response = client.models.generate_content(model=model_name, contents=prompt)
        text = (response.text or '').strip()
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
