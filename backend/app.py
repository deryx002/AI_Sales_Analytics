from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import json
import google.genai as genai  # CHANGED: New import
from google.genai import types  # NEW: For model configuration
import pandas as pd
import io
from datetime import datetime
from visualization import SalesVisualizer

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure Google AI with NEW API
api_key = os.getenv('GOOGLE_API_KEY')
if not api_key:
    print("ERROR: GOOGLE_API_KEY not found in .env file")
    print("Please add your API key to the .env file:")
    print("GOOGLE_API_KEY=your_api_key_here")

# Initialize Google AI client
client = genai.Client(api_key=api_key)

# Initialize model - using the new syntax
model_name = "gemini-2.5-flash"  # or "gemini-1.5-pro"

# Initialize visualizer
visualizer = SalesVisualizer()

# In-memory storage
sales_data = []
file_history = []

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

def extract_sales_insights(data):
    """Extract basic insights from sales data"""
    insights = {
        'total_revenue': 0,
        'avg_revenue': 0,
        'regions': set(),
        'products': set(),
        'time_periods': set(),
        'record_count': len(data),
        'columns': set()
    }
    
    revenue_values = []
    
    for record in data:
        if 'data' in record:
            data_dict = record['data']
            
            # Track columns
            insights['columns'].update(data_dict.keys())
            
            # Extract revenue
            if 'revenue' in data_dict:
                try:
                    rev_value = str(data_dict['revenue'])
                    rev_value = rev_value.replace('$', '').replace(',', '').strip()
                    if rev_value:
                        rev = float(rev_value)
                        revenue_values.append(rev)
                except:
                    pass
            
            # Extract region
            if 'region' in data_dict:
                region_value = str(data_dict['region']).strip()
                if region_value:
                    insights['regions'].add(region_value)
            
            # Extract product
            if 'product' in data_dict:
                product_value = str(data_dict['product']).strip()
                if product_value:
                    insights['products'].add(product_value)
            
            # Extract date/time
            date_fields = ['date', 'Date', 'DATE', 'transaction_date', 'sale_date']
            for field in date_fields:
                if field in data_dict:
                    date_value = str(data_dict[field]).strip()
                    if date_value:
                        insights['time_periods'].add(date_value)
                        break
    
    if revenue_values:
        insights['total_revenue'] = sum(revenue_values)
        insights['avg_revenue'] = sum(revenue_values) / len(revenue_values)
    
    # Convert sets to lists
    insights['regions'] = list(insights['regions'])
    insights['products'] = list(insights['products'])
    insights['time_periods'] = list(insights['time_periods'])
    insights['columns'] = list(insights['columns'])
    
    return insights

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
        
        return jsonify({
            'message': 'File processed successfully',
            'records_added': len(records),
            'total_records': len(sales_data),
            'insights': insights
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
        
        # Create sample data text
        sample_data_text = ""
        if sales_data:
            for i, record in enumerate(sales_data[:3]):
                if 'data' in record:
                    sample_data_text += f"Record {i+1}: {json.dumps(record['data'], indent=2)}\n"
        
        # Create prompt for Gemini
        prompt = f"""You are a Sales Analytics Assistant with visualization capabilities.

USER QUERY: {query}

SALES DATA SUMMARY:
- Total Records: {data_summary['record_count']}
- Total Revenue: ${data_summary['total_revenue']:,.2f}
- Average Revenue: ${data_summary['avg_revenue']:,.2f}
- Regions: {', '.join(data_summary['regions'][:10])}
- Products: {', '.join(data_summary['products'][:10])}
- Time Periods: {', '.join(data_summary['time_periods'][:5])}
- Available Columns: {', '.join(data_summary['columns'][:15])}

SAMPLE DATA (first 3 records):
{sample_data_text}

AVAILABLE VISUALIZATIONS: {list(charts.keys()) if charts else 'None generated'}

INSTRUCTIONS:
1. Answer the user's question based on the sales data
2. If visualizations are available and relevant, mention them in your response
3. Provide insights that could be visualized
4. If asking for specific visualization, explain what it shows
5. Format: Friendly, helpful, with bullet points for key insights

ANSWER:"""
        
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
                'products_count': len(data_summary['products'])
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
        'available_columns': insights['columns']
    }
    
    return jsonify(summary)

@app.route('/api/clear', methods=['POST'])
def clear_data():
    """Clear all data"""
    global sales_data, file_history
    sales_data = []
    file_history = []
    
    return jsonify({'message': 'All data cleared successfully'})

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
    print("  POST /api/upload")
    print("  POST /api/query")
    print("  POST /api/clear")
    print("=" * 50)
    
    app.run(debug=True, port=5000, host='0.0.0.0')