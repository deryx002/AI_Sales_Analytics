import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt 
import seaborn as sns
import pandas as pd
import numpy as np
from datetime import datetime
import io
import base64
import json

# Set style for better looking charts
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

class SalesVisualizer:
    """Generate visualizations for sales data"""
    
    def __init__(self):
        self.figure_size = (10, 6)
    
    def plot_to_base64(self, plt_figure):
        """Convert matplotlib figure to base64 string"""
        img_bytes = io.BytesIO()
        plt_figure.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
        img_bytes.seek(0)
        img_base64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
        plt.close(plt_figure)
        return img_base64
    
    def create_revenue_trend(self, sales_data):
        """Create revenue trend over time"""
        try:
            # Extract data
            dates = []
            revenues = []
            
            for record in sales_data:
                if 'data' in record:
                    data = record['data']
                    if 'date' in data and 'revenue' in data:
                        try:
                            # Parse date
                            date_str = str(data['date'])
                            # Try to convert to datetime
                            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d'):
                                try:
                                    date = datetime.strptime(date_str, fmt)
                                    break
                                except:
                                    date = None
                            
                            if date:
                                revenue = float(str(data['revenue']).replace('$', '').replace(',', ''))
                                dates.append(date)
                                revenues.append(revenue)
                        except:
                            continue
            
            if len(dates) < 2:
                return None
            
            # Sort by date
            sorted_data = sorted(zip(dates, revenues), key=lambda x: x[0])
            dates = [d[0] for d in sorted_data]
            revenues = [d[1] for d in sorted_data]
            
            # Create plot
            fig, ax = plt.subplots(figsize=self.figure_size)
            
            # Line plot
            ax.plot(dates, revenues, marker='o', linewidth=2, markersize=6)
            
            # Add trend line
            if len(dates) > 2:
                x_numeric = np.arange(len(dates))
                z = np.polyfit(x_numeric, revenues, 1)
                p = np.poly1d(z)
                ax.plot(dates, p(x_numeric), "r--", alpha=0.5, label='Trend')
            
            ax.set_title('Revenue Trend Over Time', fontsize=16, fontweight='bold')
            ax.set_xlabel('Date', fontsize=12)
            ax.set_ylabel('Revenue (₹)', fontsize=12)
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='x', rotation=45)
            
            # Format y-axis as currency
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₹{x:,.0f}'))
            
            plt.tight_layout()
            
            return self.plot_to_base64(fig)
            
        except Exception as e:
            print(f"Error creating revenue trend: {e}")
            return None
    
    def create_regional_sales(self, sales_data):
        """Create bar chart of sales by region"""
        try:
            # Extract regional data
            region_revenues = {}
            
            for record in sales_data:
                if 'data' in record:
                    data = record['data']
                    if 'region' in data and 'revenue' in data:
                        try:
                            region = str(data['region']).strip()
                            revenue = float(str(data['revenue']).replace('$', '').replace(',', ''))
                            
                            if region:
                                region_revenues[region] = region_revenues.get(region, 0) + revenue
                        except:
                            continue
            
            if not region_revenues:
                return None
            
            # Prepare data for plotting
            regions = list(region_revenues.keys())
            revenues = list(region_revenues.values())
            
            # Sort by revenue
            sorted_data = sorted(zip(regions, revenues), key=lambda x: x[1], reverse=True)
            regions = [d[0] for d in sorted_data]
            revenues = [d[1] for d in sorted_data]
            
            # Create plot
            fig, ax = plt.subplots(figsize=self.figure_size)
            
            # Bar plot
            bars = ax.bar(regions, revenues, color=sns.color_palette("husl", len(regions)))
            
            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'₹{height:,.0f}',
                        ha='center', va='bottom', fontsize=10)
            
            ax.set_title('Sales by Region', fontsize=16, fontweight='bold')
            ax.set_xlabel('Region', fontsize=12)
            ax.set_ylabel('Total Revenue (₹)', fontsize=12)
            ax.tick_params(axis='x', rotation=45)
            
            # Format y-axis as currency
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₹{x:,.0f}'))
            
            plt.tight_layout()
            
            return self.plot_to_base64(fig)
            
        except Exception as e:
            print(f"Error creating regional sales chart: {e}")
            return None
    
    def create_product_performance(self, sales_data):
        """Create pie chart of product performance"""
        try:
            # Extract product data
            product_revenues = {}
            
            for record in sales_data:
                if 'data' in record:
                    data = record['data']
                    if 'product' in data and 'revenue' in data:
                        try:
                            product = str(data['product']).strip()
                            revenue = float(str(data['revenue']).replace('$', '').replace(',', ''))
                            
                            if product:
                                product_revenues[product] = product_revenues.get(product, 0) + revenue
                        except:
                            continue
            
            if not product_revenues:
                return None
            
            # Prepare data
            products = list(product_revenues.keys())
            revenues = list(product_revenues.values())
            
            # Sort by revenue
            sorted_data = sorted(zip(products, revenues), key=lambda x: x[1], reverse=True)
            products = [d[0] for d in sorted_data]
            revenues = [d[1] for d in sorted_data]
            
            # Create plot
            fig, ax = plt.subplots(figsize=self.figure_size)
            
            # Pie chart
            wedges, texts, autotexts = ax.pie(
                revenues, 
                labels=products,
                autopct='%1.1f%%',
                startangle=90,
                explode=[0.05] * len(products),  # Slight explosion for better visibility
                shadow=True
            )
            
            # Style the text
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
            
            ax.set_title('Product Performance (Revenue Share)', fontsize=16, fontweight='bold')
            ax.axis('equal')  # Equal aspect ratio ensures pie is drawn as circle
            
            # Add legend
            ax.legend(wedges, products, title="Products", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
            
            plt.tight_layout()
            
            return self.plot_to_base64(fig)
            
        except Exception as e:
            print(f"Error creating product performance chart: {e}")
            return None
    
    def create_sales_distribution(self, sales_data):
        """Create histogram of sales distribution"""
        try:
            # Extract revenue data
            revenues = []
            
            for record in sales_data:
                if 'data' in record:
                    data = record['data']
                    if 'revenue' in data:
                        try:
                            revenue = float(str(data['revenue']).replace('$', '').replace(',', ''))
                            revenues.append(revenue)
                        except:
                            continue
            
            if len(revenues) < 3:
                return None
            
            # Create plot
            fig, ax = plt.subplots(figsize=self.figure_size)
            
            # Histogram with KDE
            sns.histplot(revenues, kde=True, bins=15, color='skyblue', edgecolor='black')
            
            # Add statistics
            mean_val = np.mean(revenues)
            median_val = np.median(revenues)
            
            ax.axvline(mean_val, color='red', linestyle='--', linewidth=2, label=f'Mean: ₹{mean_val:,.0f}')
            ax.axvline(median_val, color='green', linestyle='--', linewidth=2, label=f'Median: ₹{median_val:,.0f}')
            
            ax.set_title('Sales Distribution', fontsize=16, fontweight='bold')
            ax.set_xlabel('Revenue (₹)', fontsize=12)
            ax.set_ylabel('Frequency', fontsize=12)
            
            # Format x-axis as currency
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₹{x:,.0f}'))
            
            ax.legend()
            plt.tight_layout()
            
            return self.plot_to_base64(fig)
            
        except Exception as e:
            print(f"Error creating sales distribution chart: {e}")
            return None
    
    def create_monthly_trend(self, sales_data):
        """Create monthly revenue trend"""
        try:
            # Extract monthly data
            monthly_revenues = {}
            
            for record in sales_data:
                if 'data' in record:
                    data = record['data']
                    if 'date' in data and 'revenue' in data:
                        try:
                            date_str = str(data['date'])
                            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d'):
                                try:
                                    date = datetime.strptime(date_str, fmt)
                                    break
                                except:
                                    date = None
                            
                            if date:
                                month_key = date.strftime('%Y-%m')
                                revenue = float(str(data['revenue']).replace('$', '').replace(',', ''))
                                monthly_revenues[month_key] = monthly_revenues.get(month_key, 0) + revenue
                        except:
                            continue
            
            if len(monthly_revenues) < 2:
                return None
            
            # Sort by month
            months = sorted(monthly_revenues.keys())
            revenues = [monthly_revenues[m] for m in months]
            
            # Create plot
            fig, ax = plt.subplots(figsize=self.figure_size)
            
            # Bar plot for monthly data
            bars = ax.bar(months, revenues, color='teal', alpha=0.7)
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'₹{height:,.0f}',
                        ha='center', va='bottom', fontsize=9, rotation=90)
            
            ax.set_title('Monthly Revenue Trend', fontsize=16, fontweight='bold')
            ax.set_xlabel('Month', fontsize=12)
            ax.set_ylabel('Total Revenue (₹)', fontsize=12)
            ax.tick_params(axis='x', rotation=45)
            
            # Format y-axis as currency
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₹{x:,.0f}'))
            
            plt.tight_layout()
            
            return self.plot_to_base64(fig)
            
        except Exception as e:
            print(f"Error creating monthly trend chart: {e}")
            return None
    
    def create_pipeline_stage_chart(self, sales_data):
        """Create chart of pipeline stages"""
        try:
            # Extract pipeline stage data
            stage_counts = {}
            
            for record in sales_data:
                if 'data' in record:
                    data = record['data']
                    if 'pipeline_stage' in data:
                        try:
                            stage = str(data['pipeline_stage']).strip()
                            if stage:
                                stage_counts[stage] = stage_counts.get(stage, 0) + 1
                        except:
                            continue
            
            if not stage_counts:
                return None
            
            # Prepare data
            stages = list(stage_counts.keys())
            counts = list(stage_counts.values())
            
            # Create plot
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
            
            # Bar chart on left
            bars = ax1.bar(stages, counts, color=sns.color_palette("Set2", len(stages)))
            ax1.set_title('Deals by Pipeline Stage', fontsize=14, fontweight='bold')
            ax1.set_xlabel('Pipeline Stage', fontsize=12)
            ax1.set_ylabel('Number of Deals', fontsize=12)
            ax1.tick_params(axis='x', rotation=45)
            
            # Add count labels
            for bar in bars:
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}',
                        ha='center', va='bottom')
            
            # Pie chart on right
            wedges, texts, autotexts = ax2.pie(
                counts,
                labels=stages,
                autopct='%1.1f%%',
                startangle=90,
                colors=sns.color_palette("Set2", len(stages))
            )
            
            ax2.set_title('Stage Distribution', fontsize=14, fontweight='bold')
            
            plt.tight_layout()
            
            return self.plot_to_base64(fig)
            
        except Exception as e:
            print(f"Error creating pipeline stage chart: {e}")
            return None
    
    def generate_all_charts(self, sales_data):
        """Generate all available charts"""
        charts = {}
        
        # Try each chart type
        charts['revenue_trend'] = self.create_revenue_trend(sales_data)
        charts['regional_sales'] = self.create_regional_sales(sales_data)
        charts['product_performance'] = self.create_product_performance(sales_data)
        charts['sales_distribution'] = self.create_sales_distribution(sales_data)
        charts['monthly_trend'] = self.create_monthly_trend(sales_data)
        charts['pipeline_stages'] = self.create_pipeline_stage_chart(sales_data)
        
        # Remove None values
        charts = {k: v for k, v in charts.items() if v is not None}
        
        return charts
    
    def generate_custom_chart(self, sales_data, chart_type, x_column=None, y_column=None):
        """Generate custom chart based on user request"""
        try:
            # Convert sales_data to pandas DataFrame for flexibility
            df_data = []
            for record in sales_data:
                if 'data' in record:
                    df_data.append(record['data'])
            
            if not df_data:
                return None
            
            df = pd.DataFrame(df_data)
            
            # Clean numeric columns
            for col in df.columns:
                if df[col].dtype == 'object':
                    try:
                        # Try to convert to numeric
                        df[col] = pd.to_numeric(df[col].astype(str).str.replace('$', '').str.replace(',', ''), errors='ignore')
                    except:
                        pass
            
            if chart_type == 'scatter' and x_column and y_column:
                if x_column in df.columns and y_column in df.columns:
                    fig, ax = plt.subplots(figsize=self.figure_size)
                    ax.scatter(df[x_column], df[y_column], alpha=0.6)
                    ax.set_title(f'{y_column} vs {x_column}', fontsize=16, fontweight='bold')
                    ax.set_xlabel(x_column, fontsize=12)
                    ax.set_ylabel(y_column, fontsize=12)
                    plt.tight_layout()
                    return self.plot_to_base64(fig)
            
            elif chart_type == 'correlation':
                # Select only numeric columns
                numeric_df = df.select_dtypes(include=[np.number])
                if len(numeric_df.columns) > 1:
                    fig, ax = plt.subplots(figsize=self.figure_size)
                    corr_matrix = numeric_df.corr()
                    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0, ax=ax)
                    ax.set_title('Correlation Matrix', fontsize=16, fontweight='bold')
                    plt.tight_layout()
                    return self.plot_to_base64(fig)
            
            return None
            
        except Exception as e:
            print(f"Error creating custom chart: {e}")
            return None