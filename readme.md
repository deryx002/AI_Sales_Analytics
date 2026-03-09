# 🚀 AI Sales Analytics Agent
### Conversational AI Platform for Sales Intelligence

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Flask](https://img.shields.io/badge/Flask-Backend-black)
![MongoDB](https://img.shields.io/badge/Database-MongoDB-green)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-orange)
![Status](https://img.shields.io/badge/Project-Active-success)

AI Sales Analytics Agent is a **SaaS-style analytics platform** that allows users to upload sales datasets and analyze them using **natural language conversations with AI**.

Instead of manually building dashboards or writing queries, users simply **upload their dataset and ask questions** like they would to a human data analyst.

The system automatically generates:

- 📊 Data insights  
- 📈 Visualizations  
- 🤖 AI explanations  
- 🔮 Future sales predictions  

---

# 🧠 Problem Statement

Businesses collect large amounts of sales data in **CSV or Excel files**, but extracting meaningful insights from these datasets often requires:

- Data analysts
- Complex tools
- Time-consuming manual analysis

Traditional analytics tools like **Excel, Tableau, and Power BI** require technical skills to build dashboards.

Our solution simplifies this process by introducing an **AI-powered conversational analytics platform**.

---

# 💡 Solution

AI Sales Analytics Agent acts as a **virtual sales analyst**.

Users can:

1️⃣ Upload a dataset  
2️⃣ Ask questions in natural language  
3️⃣ Instantly receive insights and charts  

This removes the need for manual analysis and makes **data-driven decision making accessible to everyone**.

---

# ⭐ Key Features

## 📂 Dataset Upload
Users can upload sales datasets in:

- CSV
- Excel (.xlsx)
- Excel (.xls)

The system automatically processes and standardizes the data.

---

## 🧹 Automatic Data Processing

The backend performs:

- Column normalization
- Data cleaning
- Revenue calculation
- Structured data transformation

Powered by **Pandas**.

---

## 🤖 Conversational AI Analytics

Users can ask questions like:

What is the total revenue?  
Which region has the highest sales?  
Show product performance.

The AI analyzes the dataset and provides accurate insights.

Powered by **Google Gemini AI**.

---

## 📊 Automatic Data Visualization

The platform automatically generates charts including:

- Revenue trends
- Regional sales comparison
- Product performance charts
- Monthly revenue trends
- Sales distribution

Charts are generated using:

- Matplotlib
- Seaborn

---

## 🔮 Sales Prediction Engine

The system analyzes historical trends and predicts:

- Future top-performing products
- Sales growth patterns

AI also explains **why a prediction is made**.

---

## ☁️ Cloud Data Storage

Datasets and user interactions are stored in **MongoDB Atlas**.

This enables:

- Persistent storage
- Multi-user capability
- Dataset management
- Chat history tracking

---

# 🏗 System Architecture

User Interface (HTML / JS)
        │
        ▼
Flask Backend API
        │
        ├── Dataset Processing (Pandas)
        ├── AI Query Engine (Gemini)
        ├── Visualization Engine
        │
        ▼
MongoDB Atlas Database

---

# 🧩 Database Structure

Database: **sales_ai**

Collections:

sales_ai
│
├── datasets
├── users
├── chats
└── files

Example dataset document:

{
  "dataset_id": "ds_1772980601687",
  "username": "dharun",
  "format": "csv",
  "type": "structured",
  "data": [
    { "product": "Laptop", "region": "North", "revenue": 20000 }
  ]
}

---

# ⚙️ Technology Stack

## Backend
- Python
- Flask
- Flask-CORS
- Pandas
- NumPy

## AI
- Google Gemini API

## Visualization
- Matplotlib
- Seaborn

## Database
- MongoDB Atlas

## Frontend
- HTML
- CSS
- JavaScript

---

# 🚀 Installation

Clone the repository

git clone https://github.com/deryx002/ai-sales-analytics-agent.git

Navigate to project

cd ai-sales-analytics-agent

Install dependencies

pip install -r requirements.txt

---

# 🔑 Environment Variables

Create a `.env` file in the project root.

Example:

MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority  
GOOGLE_API_KEY=your_google_api_key

---

# ▶ Running the Application

Start the backend server:

python app.py

Server will run on:

http://localhost:5000

---

# 📊 Example Workflow

Upload Dataset  
      │  
      ▼  
Data Processing  
      │  
      ▼  
Ask AI Questions  
      │  
      ▼  
Insights + Charts  
      │  
      ▼  
Predictions  

---

# 🔥 What Makes This Project Unique

Unlike traditional analytics tools, this system introduces **Conversational Data Analytics**.

Users interact with their dataset like they are **talking to a human analyst**.

This combines:

- AI assistant
- Business intelligence
- Data visualization
- Sales forecasting

into one intelligent platform.

---

# 📈 Future Enhancements

Possible improvements include:

- Multi-user authentication
- Dataset workspace management
- Dashboard sharing
- Automated business recommendations
- Real-time analytics

---

# 👥 Team

Developed by a **team of five members** as part of an AI-driven analytics system project.

---

