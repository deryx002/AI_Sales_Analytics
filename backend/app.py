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

load_dotenv()

app = Flask(__name__)
CORS(app)

api_key = os.getenv('GOOGLE_API_KEY')
if not api_key:
    print("ERROR: GOOGLE_API_KEY not found in .env file")
    print("Please add your API key to the .env file:")
    print("GOOGLE_API_KEY=your_api_key_here")

client = genai.Client(api_key=api_key)

model_name = "gemini-2.5-flash"

visualizer = SalesVisualizer()

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
        'market', 'state', 'country', 'city', 'branch',
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


# Stores original column name → canonical name mapping (set during normalize)
_original_column_map = {}


def normalize_dataframe(df):
    global _original_column_map
    raw_cols = [str(col).strip() for col in df.columns]
    df.columns = raw_cols
    canonical_cols = [get_canonical_name(col) for col in raw_cols]

    # Remember original name for each canonical name (first occurrence wins)
    for raw, canon in zip(raw_cols, canonical_cols):
        if canon not in _original_column_map:
            _original_column_map[canon] = raw

    df.columns = make_unique_columns(canonical_cols)

    for col in df.columns:
        if str(df[col].dtype) == 'object':
            df[col] = df[col].astype(str).str.strip()

    # Derive revenue = price × quantity when no explicit revenue column exists
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
    """Process CSV file content"""
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
    """Process Excel file content"""
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
    """Derive a user-friendly label from the original column name."""
    original = _original_column_map.get(canonical_name)
    if not original:
        return fallback
    # Title-case the original header, e.g. 'Customer Location' → 'Locations'
    clean = original.replace('_', ' ').strip().title()
    # Map common originals to concise plural labels
    label_map = {
        'location': 'Locations', 'customer_location': 'Locations',
        'city': 'Cities', 'state': 'States', 'country': 'Countries',
        'branch': 'Branches', 'zone': 'Zones', 'area': 'Areas',
        'territory': 'Territories', 'market': 'Markets',
        'geography': 'Geographies', 'geo': 'Geographies',
        'region': 'Regions',
    }
    key = normalize_column_key(original)
    # Check if any label_map key is contained in the normalized name
    for pattern, label in label_map.items():
        if pattern in key:
            return label
    return fallback


def extract_sales_insights(data):
    """Extract basic insights from sales data"""
    insights = {
        'total_revenue': 0,
        'avg_revenue': 0,
        'regions': set(),
        'products': set(),
        'time_periods': set(),
        'record_count': len(data),
        'columns': set(),
        'metrics_available': {
            'revenue': False,
            'region': False,
            'product': False,
            'date': False
        },
        'region_label': _friendly_label('region', 'Regions'),
        'product_label': _friendly_label('product', 'Products'),
    }
    
    revenue_values = []
    
    for record in data:
        if 'data' in record:
            data_dict = record['data']
            
            # Track columns
            insights['columns'].update(data_dict.keys())
            
            # Extract revenue (alias-aware)
            revenue_key = first_matching_key(data_dict, 'revenue')
            
            if revenue_key:
                try:
                    rev_value = str(data_dict[revenue_key])
                    rev_value = rev_value.replace('$', '').replace(',', '').replace('₹', '').strip()
                    if rev_value and rev_value.lower() != 'nan':
                        rev = float(rev_value)
                        revenue_values.append(rev)
                        insights['metrics_available']['revenue'] = True
                except:
                    pass
            else:
                # Fallback: derive revenue = price × quantity when explicit revenue is absent
                price_key = first_matching_key(data_dict, 'price')
                quantity_key = first_matching_key(data_dict, 'quantity')

                if price_key and quantity_key:
                    try:
                        price_val = to_float(data_dict.get(price_key))
                        quantity_val = to_float(data_dict.get(quantity_key))
                        if price_val is not None and quantity_val is not None:
                            revenue_values.append(price_val * quantity_val)
                            insights['metrics_available']['revenue'] = True
                    except:
                        pass
            
            # Extract region (alias-aware)
            region_key = first_matching_key(data_dict, 'region')
            
            if region_key:
                region_value = str(data_dict[region_key]).strip()
                if region_value and region_value.lower() != 'nan':
                    insights['regions'].add(region_value)
                    insights['metrics_available']['region'] = True
            
            # Extract product (alias-aware)
            product_key = first_matching_key(data_dict, 'product')
            
            if product_key:
                product_value = str(data_dict[product_key]).strip()
                if product_value and product_value.lower() != 'nan':
                    insights['products'].add(product_value)
                    insights['metrics_available']['product'] = True
            
            # Extract date/time
            date_key = first_matching_key(data_dict, 'date')
            if date_key:
                date_value = str(data_dict[date_key]).strip()
                if date_value and date_value.lower() != 'nan':
                    insights['time_periods'].add(date_value)
                    insights['metrics_available']['date'] = True
    
    if revenue_values:
        insights['total_revenue'] = sum(revenue_values)
        insights['avg_revenue'] = sum(revenue_values) / len(revenue_values)
    
    # Convert sets to lists
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

    numerator = 0
    denominator = 0
    for i, y in enumerate(values):
        dx = i - x_mean
        numerator += dx * (y - y_mean)
        denominator += dx * dx

    if denominator == 0:
        return values[-1]

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    next_value = intercept + slope * n
    return max(0, next_value)


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
- No markdown, no numbering
"""

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )

        text = (response.text or '').strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.startswith('json'):
                text = text[4:].strip()

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
    has_quantity = False
    has_revenue = False
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
            aggregates[product_name] = {
                'quantity': 0.0,
                'revenue': 0.0,
                'records': 0,
                'dated_revenue': [],
                'dated_quantity': []
            }

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
            # Fallback: derive revenue = price × quantity
            price_key = first_matching_key(data_dict, 'price')
            if price_key and quantity_val is not None:
                price_val = to_float(data_dict.get(price_key))
                if price_val is not None:
                    revenue_val = price_val * quantity_val
                    has_revenue = True
                    aggregates[product_name]['revenue'] += revenue_val

        date_key = first_matching_key(data_dict, 'date')
        if date_key:
            parsed_date = pd.to_datetime(str(data_dict.get(date_key)).strip(), errors='coerce')
            if not pd.isna(parsed_date):
                all_dates.add(parsed_date)
                if revenue_val is not None:
                    aggregates[product_name]['dated_revenue'].append((parsed_date, revenue_val))
                if quantity_val is not None:
                    aggregates[product_name]['dated_quantity'].append((parsed_date, quantity_val))

    if not aggregates:
        return {
            'available': False,
            'message': 'Product insights are not available for this dataset.'
        }

    metric_key = 'quantity' if has_quantity else 'revenue'
    metric_label = 'Units Sold' if metric_key == 'quantity' else 'Revenue'

    ranked_products = sorted(
        aggregates.items(),
        key=lambda item: item[1][metric_key],
        reverse=True
    )

    most_product, most_stats = ranked_products[0]
    least_product, least_stats = ranked_products[-1]

    forecast_candidates = []
    for product_name, stats in aggregates.items():
        dated_points = sorted(stats['dated_revenue'], key=lambda item: item[0])
        revenue_series = [point[1] for point in dated_points]
        projected = forecast_next_value(revenue_series)
        if projected is not None:
            forecast_candidates.append((product_name, projected, len(revenue_series)))

    if forecast_candidates:
        forecast_candidates.sort(key=lambda item: item[1], reverse=True)
        predicted_product, projected_revenue, sample_size = forecast_candidates[0]
        prediction = {
            'name': predicted_product,
            'projected_revenue': projected_revenue,
            'confidence': 'High' if sample_size >= 6 else 'Medium',
            'basis': 'Time trend forecast from historical product revenue'
        }
    else:
        fallback_product, fallback_stats = max(
            aggregates.items(),
            key=lambda item: (item[1]['revenue'] / max(1, item[1]['records']))
        )
        prediction = {
            'name': fallback_product,
            'projected_revenue': fallback_stats['revenue'] / max(1, fallback_stats['records']),
            'confidence': 'Low',
            'basis': 'Fallback using average revenue per record (insufficient date trend)'
        }

    prediction_product_stats = aggregates.get(prediction['name'], {})
    prediction_series_len = len(prediction_product_stats.get('dated_revenue', []))
    if prediction_series_len >= 3:
        prediction_reasons = generate_ai_future_reasons(
            prediction['name'],
            prediction_product_stats,
            prediction
        )
    else:
        prediction_reasons = [
            f"{prediction['name']} leads current dataset on tracked sales metric.",
            "Recent observed demand stays stable without major drop-offs.",
            "Projected value remains above competing products in this dataset."
        ]

    def build_trend_points(product_name, preferred_metric):
        stats = aggregates.get(product_name, {})
        if preferred_metric == 'quantity':
            raw_points = stats.get('dated_quantity', [])
            metric_for_plot = 'quantity'
            if not raw_points:
                raw_points = stats.get('dated_revenue', [])
                metric_for_plot = 'revenue'
        else:
            raw_points = stats.get('dated_revenue', [])
            metric_for_plot = 'revenue'

        if not raw_points:
            return {
                'metric': metric_for_plot,
                'points': []
            }

        grouped = {}
        for dt, val in raw_points:
            key = dt.strftime('%Y-%m-%d')
            grouped[key] = grouped.get(key, 0) + val

        # Build continuous timeline for better spike detection (0 on non-sale dates)
        timeline_dates = sorted(all_dates) if all_dates else sorted(dt for dt, _ in raw_points)
        points = []
        for dt in timeline_dates:
            date_key = dt.strftime('%Y-%m-%d')
            points.append({'x': date_key, 'y': grouped.get(date_key, 0)})

        return {
            'metric': metric_for_plot,
            'points': points
        }

    return {
        'available': True,
        'metric_used': metric_key,
        'metric_label': metric_label,
        'most_sold_product': {
            'name': most_product,
            'value': most_stats[metric_key]
        },
        'least_sold_product': {
            'name': least_product,
            'value': least_stats[metric_key]
        },
        'most_sold_trend': build_trend_points(most_product, metric_key),
        'least_sold_trend': build_trend_points(least_product, metric_key),
        'predicted_highest_future_sales': {
            **prediction,
            'reasons': prediction_reasons
        }
    }

@app.route('/api/upload', methods=['POST'])
def upload_data():
    """Handle file uploads"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        file_content = file.read()
        file_extension = file.filename.split('.')[-1].lower()
        
        print(f"Processing {file.filename} ({file_extension})")
        
        if file_extension == 'csv':
            records = process_csv(file_content)
        elif file_extension in ['xlsx', 'xls']:
            records = process_excel(file_content)
        else:
            return jsonify({'error': f'Unsupported file type: {file_extension}'}), 400
        
        sales_data.extend(records)
        
        file_history.append({
            'filename': file.filename,
            'type': file_extension,
            'records': len(records),
            'timestamp': datetime.now().isoformat()
        })
        
        insights = extract_sales_insights(records)
        product_insights = get_product_insights(sales_data)
        
        return jsonify({
            'message': 'File processed successfully',
            'records_added': len(records),
            'total_records': len(sales_data),
            'insights': insights,
            'product_insights': product_insights
        })
    
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/query', methods=['POST'])
def handle_query():
    """Handle user queries with visualization support"""
    try:
        data = request.json
        query = data.get('query', '').lower()
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        data_summary = extract_sales_insights(sales_data)
        
        if data_summary['record_count'] == 0:
            return jsonify({
                'query': query,
                'response': 'No sales data available. Please upload a CSV or Excel file first.',
                'analysis': {'has_data': False},
                'data_summary': data_summary,
                'visualizations': []
            })
        
        # Check if user is asking for visualization
        visualization_keywords = ['chart', 'graph', 'plot', 'visualize', 'diagram', 
                                 'trend', 'bar', 'pie', 'histogram', 'scatter']
        needs_visualization = any(keyword in query for keyword in visualization_keywords)
        
        # Generate charts if needed
        charts = {}
        if needs_visualization and len(sales_data) > 0:
            charts = visualizer.generate_all_charts(sales_data)
        
        # Create FULL dataset text (not just samples) - this is critical for accurate answers
        full_data_text = ""
        if sales_data:
            # Include ALL records so AI can answer accurately
            # Limit to 500 records to avoid token limits, but this covers most use cases
            max_records = min(len(sales_data), 500)
            for i, record in enumerate(sales_data[:max_records]):
                if 'data' in record:
                    full_data_text += f"Row {i+1}: {json.dumps(record['data'])}\n"
            
            if len(sales_data) > max_records:
                full_data_text += f"\n[Note: Showing first {max_records} of {len(sales_data)} total records]\n"

        # Pre-compute key metrics so the AI doesn't have to do arithmetic
        precomputed = ""
        if data_summary['metrics_available']['revenue']:
            precomputed += f"\n• Total Revenue (pre-computed, verified): ₹{data_summary['total_revenue']:,.2f}"
            precomputed += f"\n• Average Revenue per record: ₹{data_summary['avg_revenue']:,.2f}"
            precomputed += f"\n• Number of records: {data_summary['record_count']}"

        # Revenue by region
        region_rev = {}
        product_rev = {}
        for record in sales_data:
            if 'data' not in record:
                continue
            d = record['data']
            rev_key = first_matching_key(d, 'revenue')
            rev_val = to_float(d.get(rev_key)) if rev_key else None
            if rev_val is None:
                p_key = first_matching_key(d, 'price')
                q_key = first_matching_key(d, 'quantity')
                if p_key and q_key:
                    pv = to_float(d.get(p_key))
                    qv = to_float(d.get(q_key))
                    if pv is not None and qv is not None:
                        rev_val = pv * qv
            if rev_val is None:
                continue
            r_key = first_matching_key(d, 'region')
            if r_key:
                rname = str(d[r_key]).strip()
                region_rev[rname] = region_rev.get(rname, 0) + rev_val
            pr_key = first_matching_key(d, 'product')
            if pr_key:
                pname = str(d[pr_key]).strip()
                product_rev[pname] = product_rev.get(pname, 0) + rev_val

        if region_rev:
            precomputed += "\n\n• Revenue by Region (pre-computed):"
            for rg, rv in sorted(region_rev.items(), key=lambda x: -x[1]):
                precomputed += f"\n  - {rg}: ₹{rv:,.2f}"

        if product_rev:
            precomputed += "\n\n• Revenue by Product (pre-computed):"
            for pr, rv in sorted(product_rev.items(), key=lambda x: -x[1]):
                precomputed += f"\n  - {pr}: ₹{rv:,.2f}"
        
        # Create prompt for Gemini with COMPLETE data
        prompt = f"""You are a Sales Analytics Agent.

CRITICAL: You MUST ONLY use the EXACT data provided below. The COMPLETE dataset is included.

ABSOLUTE RULES (VIOLATION = FAILURE):
1. ONLY use data from the "COMPLETE DATASET" section below - this is ALL the data that exists
2. DO NOT invent, assume, estimate, or hallucinate ANY values
3. DO NOT use any external knowledge or typical patterns
4. If information is not in the dataset, respond: "This information is not available in the uploaded data."
5. Every number you mention MUST be directly from or calculated from the dataset below
6. Show your calculation when providing totals or averages
7. Use Indian Rupee (₹) for all revenue/currency values
8. For totals, averages, sums, and breakdowns: ALWAYS use the PRE-COMPUTED VALUES below. They are mathematically verified and authoritative. Do NOT re-calculate them yourself.

PRE-COMPUTED VERIFIED METRICS (use these directly, do not recalculate):
{precomputed}

COMPLETE DATASET ({data_summary['record_count']} records):
{full_data_text}

DATASET COLUMNS: {', '.join(data_summary['columns'])}

USER QUESTION: {query}

AVAILABLE VISUALIZATIONS: {list(charts.keys()) if charts else 'None generated'}

RESPONSE FORMAT:
- For questions about totals, sums, averages, or breakdowns: use the PRE-COMPUTED VERIFIED METRICS above directly
- Answer based ONLY on the exact data above
- Be concise but accurate
- Use bullet points for clarity

YOUR ANSWER (using ONLY the data above):"""
        
        # Generate response using NEW Google AI API
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        
        return jsonify({
            'query': query,
            'response': response.text,
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
                'product_insights': get_product_insights(sales_data),
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

@app.route('/api/visualizations', methods=['GET'])
def get_visualizations():
    """Generate and return all available visualizations"""
    try:
        if len(sales_data) == 0:
            return jsonify({'error': 'No data available for visualization'}), 400
        
        charts = visualizer.generate_all_charts(sales_data)
        
        if not charts:
            return jsonify({'error': 'No charts could be generated from the data'}), 400
        
        return jsonify({
            'message': f'Generated {len(charts)} visualization(s)',
            'charts': charts,
            'chart_types': list(charts.keys())
        })
    
    except Exception as e:
        print(f"Visualization error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/visualize/<chart_type>', methods=['GET'])
def get_specific_visualization(chart_type):
    """Get specific type of visualization"""
    try:
        if len(sales_data) == 0:
            return jsonify({'error': 'No data available'}), 400
        
        chart = None
        chart_types = {
            'revenue_trend': visualizer.create_revenue_trend,
            'regional_sales': visualizer.create_regional_sales,
            'product_performance': visualizer.create_product_performance,
            'sales_distribution': visualizer.create_sales_distribution,
            'monthly_trend': visualizer.create_monthly_trend,
            'pipeline_stages': visualizer.create_pipeline_stage_chart,
        }
        
        if chart_type in chart_types:
            chart = chart_types[chart_type](sales_data)
        
        if chart:
            return jsonify({
                'chart_type': chart_type,
                'image': chart,
                'message': 'Chart generated successfully'
            })
        else:
            return jsonify({'error': f'Could not generate {chart_type} chart'}), 400
    
    except Exception as e:
        print(f"Specific visualization error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data/summary', methods=['GET'])
def get_data_summary():
    """Get summary of ingested data"""
    insights = extract_sales_insights(sales_data)
    product_insights = get_product_insights(sales_data)
    
    summary = {
        'total_records': len(sales_data),
        'file_history': file_history[-5:],
        'revenue': {
            'total': insights['total_revenue'],
            'average': insights['avg_revenue']
        },
        'categories': {
            'regions': insights['regions'],
            'products': insights['products'],
            'time_periods': insights['time_periods'][:10]
        },
        'available_columns': insights['columns'],
        'product_insights': product_insights,
        'metrics_available': insights['metrics_available'],
        'dynamic_stats': [
            {
                'id': 'records',
                'label': 'Records',
                'value': len(sales_data),
                'type': 'count'
            },
            {
                'id': 'revenue',
                'label': 'Revenue',
                'value': insights['total_revenue'] if insights['metrics_available']['revenue'] else None,
                'type': 'currency',
                'available': insights['metrics_available']['revenue']
            },
            {
                'id': 'regions',
                'label': insights.get('region_label', 'Regions'),
                'value': len(insights['regions']) if insights['metrics_available']['region'] else None,
                'type': 'count',
                'available': insights['metrics_available']['region']
            },
            {
                'id': 'products',
                'label': insights.get('product_label', 'Products'),
                'value': len(insights['products']) if insights['metrics_available']['product'] else None,
                'type': 'count',
                'available': insights['metrics_available']['product']
            }
        ]
    }
    
    return jsonify(summary)

@app.route('/api/clear', methods=['POST'])
def clear_data():
    """Clear all data"""
    global sales_data, file_history, _original_column_map
    sales_data = []
    file_history = []
    _original_column_map = {}
    
    return jsonify({'message': 'All data cleared successfully'})

@app.route('/api/samples', methods=['GET'])
def list_samples():
    """List available sample data files"""
    sample_dir = os.path.join(os.path.dirname(__file__), 'sample_data')
    samples = []
    if os.path.isdir(sample_dir):
        for fname in sorted(os.listdir(sample_dir)):
            if fname.lower().endswith(('.csv', '.xlsx', '.xls')):
                fpath = os.path.join(sample_dir, fname)
                size = os.path.getsize(fpath)
                samples.append({'name': fname, 'size': size})
    return jsonify({'samples': samples})


@app.route('/api/samples/<path:filename>', methods=['GET'])
def get_sample(filename):
    """Load a sample data file as if it were uploaded"""
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

    sales_data.extend(records)
    file_history.append({
        'filename': filename,
        'type': ext,
        'records': len(records),
        'timestamp': datetime.now().isoformat()
    })

    insights = extract_sales_insights(records)
    product_insights = get_product_insights(sales_data)

    return jsonify({
        'message': 'Sample file loaded successfully',
        'records_added': len(records),
        'total_records': len(sales_data),
        'insights': insights,
        'product_insights': product_insights
    })


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    """Generate comprehensive predictions, alternatives, and improvement suggestions"""
    try:
        if not sales_data:
            return jsonify({
                'available': False,
                'message': 'No data loaded. Please upload a CSV or Excel file first.'
            })

        data_summary = extract_sales_insights(sales_data)
        product_insights = get_product_insights(sales_data)

        # Build full data text for Gemini (limit to 500 records)
        full_data_text = ""
        max_records = min(len(sales_data), 500)
        for i, record in enumerate(sales_data[:max_records]):
            if 'data' in record:
                full_data_text += f"Row {i+1}: {json.dumps(record['data'])}\n"

        # Precompute metrics
        precomputed = f"Total Records: {data_summary['record_count']}"
        if data_summary['metrics_available']['revenue']:
            precomputed += f"\nTotal Revenue: ₹{data_summary['total_revenue']:,.2f}"
            precomputed += f"\nAverage Revenue per record: ₹{data_summary['avg_revenue']:,.2f}"
        if data_summary['regions']:
            precomputed += f"\nRegions: {', '.join(data_summary['regions'])}"
        if data_summary['products']:
            precomputed += f"\nProducts: {', '.join(data_summary['products'])}"

        # Revenue breakdowns
        region_rev = {}
        product_rev = {}
        for record in sales_data:
            if 'data' not in record:
                continue
            d = record['data']
            rev_key = first_matching_key(d, 'revenue')
            rev_val = to_float(d.get(rev_key)) if rev_key else None
            if rev_val is None:
                p_key = first_matching_key(d, 'price')
                q_key = first_matching_key(d, 'quantity')
                if p_key and q_key:
                    pv = to_float(d.get(p_key))
                    qv = to_float(d.get(q_key))
                    if pv is not None and qv is not None:
                        rev_val = pv * qv
            if rev_val is None:
                continue
            r_key = first_matching_key(d, 'region')
            if r_key:
                rname = str(d[r_key]).strip()
                region_rev[rname] = region_rev.get(rname, 0) + rev_val
            pr_key = first_matching_key(d, 'product')
            if pr_key:
                pname = str(d[pr_key]).strip()
                product_rev[pname] = product_rev.get(pname, 0) + rev_val

        if region_rev:
            precomputed += "\n\nRevenue by Region:"
            for rg, rv in sorted(region_rev.items(), key=lambda x: -x[1]):
                precomputed += f"\n  - {rg}: ₹{rv:,.2f}"
        if product_rev:
            precomputed += "\n\nRevenue by Product:"
            for pr, rv in sorted(product_rev.items(), key=lambda x: -x[1]):
                precomputed += f"\n  - {pr}: ₹{rv:,.2f}"

        prompt = f"""You are an expert Sales Analytics & Strategy AI.

Analyze this sales dataset and provide a COMPREHENSIVE prediction & improvement report.

DATASET SUMMARY:
{precomputed}

COLUMNS AVAILABLE: {', '.join(data_summary['columns'])}

COMPLETE DATA ({data_summary['record_count']} records):
{full_data_text}

Respond in STRICT JSON with this exact structure (no markdown, no code fences):
{{
  "sales_forecast": {{
    "title": "Sales Forecast",
    "items": [
      {{
        "label": "short title",
        "value": "predicted value or key metric",
        "detail": "1-2 sentence explanation",
        "trend": "up|down|stable",
        "confidence": "High|Medium|Low"
      }}
    ]
  }},
  "product_predictions": {{
    "title": "Product Predictions",
    "items": [
      {{
        "label": "product-related prediction title",
        "value": "predicted value",
        "detail": "explanation",
        "trend": "up|down|stable",
        "confidence": "High|Medium|Low"
      }}
    ]
  }},
  "regional_predictions": {{
    "title": "Regional Predictions",
    "items": [
      {{
        "label": "region-related prediction title",
        "value": "predicted value",
        "detail": "explanation",
        "trend": "up|down|stable",
        "confidence": "High|Medium|Low"
      }}
    ]
  }},
  "alternatives": {{
    "title": "Alternative Strategies",
    "items": [
      {{
        "label": "strategy title",
        "detail": "what to do and why",
        "impact": "High|Medium|Low",
        "category": "pricing|marketing|product|distribution|customer"
      }}
    ]
  }},
  "improvements": {{
    "title": "Sales Improvement Recommendations",
    "items": [
      {{
        "label": "improvement title",
        "detail": "specific actionable recommendation with expected outcome",
        "impact": "High|Medium|Low",
        "category": "pricing|marketing|product|distribution|customer",
        "expected_boost": "estimated % or value improvement"
      }}
    ]
  }}
}}

RULES:
1. Use ONLY the data provided - do not invent numbers
2. Use Indian Rupees (₹) for currency
3. Provide 3-5 items per section
4. If a category (regions/products) is not in the data, adapt that section to what IS available
5. Be specific and actionable - reference actual products, regions, and numbers from the data
6. Output ONLY valid JSON, no extra text"""

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )

        text = (response.text or '').strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.startswith('json'):
                text = text[4:].strip()

        predictions = json.loads(text)

        return jsonify({
            'available': True,
            'predictions': predictions,
            'data_summary': {
                'total_records': data_summary['record_count'],
                'total_revenue': data_summary['total_revenue'],
                'products': data_summary['products'],
                'regions': data_summary['regions']
            }
        })

    except json.JSONDecodeError:
        return jsonify({
            'available': False,
            'message': 'Failed to parse AI predictions. Please try again.'
        }), 500
    except Exception as e:
        print(f"Predictions error: {str(e)}")
        return jsonify({
            'available': False,
            'message': f'Error generating predictions: {str(e)}'
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'ai_service': 'Google GenAI',
        'visualization': 'available',
        'data_records': len(sales_data),
        'files_uploaded': len(file_history)
    })

if __name__ == '__main__':
    print("=" * 50)
    print("Sales Analytics Agent with Google GenAI")
    print("=" * 50)
    print(f"API Key: {'Set' if api_key else 'NOT SET!'}")
    print(f"Model: {model_name}")
    print(f"Visualization: Available")
    print(f"Server: http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  GET  /api/health")
    print("  GET  /api/data/summary")
    print("  GET  /api/visualizations")
    print("  GET  /api/visualize/<chart_type>")
    print("  GET  /api/samples")
    print("  GET  /api/samples/<filename>")
    print("  POST /api/upload")
    print("  POST /api/query")
    print("  POST /api/clear")
    print("=" * 50)
    
    app.run(debug=True, port=5000, host='0.0.0.0')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
