# 🤖 AI Document Assistant — RAG Chatbot

> An enterprise-grade, consumer-friendly chatbot that lets you **chat with your own documents** — powered by Google Gemini & LangChain.

---

## 📌 What is this?

This is a **Retrieval-Augmented Generation (RAG) Chatbot**. In simple terms, it allows you to upload your business documents and then ask questions about them in plain English — just like texting a colleague who has read all your files!

Unlike generic AI assistants, this chatbot **only answers from the documents you upload**, making it accurate, private, and reliable for real business use.

---

## ✨ Features

- 📄 **Upload any document** — PDF, Word (DOCX), Excel (XLSX), CSV, TXT, HTML
- 🧠 **Smart Q&A** — Answers questions using only your uploaded content
- 📚 **Knowledge Base** — All uploaded documents are permanently stored; they persist even after restarting the app
- 🗑️ **Document Management** — View all stored documents in the sidebar and delete them with one click
- 💬 **Conversation Memory** — The chatbot remembers your previous questions within a session for natural back-and-forth conversation
- 🔒 **Secure** — Your API key is stored locally in a `.env` file and is never exposed

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **UI / Frontend** | [Streamlit](https://streamlit.io/) |
| **AI / LLM** | Google Gemini 2.5 Flash |
| **Embeddings** | Google Gemini Embedding 2 |
| **Vector Database** | [ChromaDB](https://www.trychroma.com/) (local, persistent) |
| **AI Orchestration** | [LangChain](https://python.langchain.com/) |
| **Document Parsing** | PyPDF, Docx2txt, Pandas, BeautifulSoup |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10 or higher
- A [Google AI API Key](https://aistudio.google.com/app/apikey) (free)

### 1. Clone the Repository
```bash
git clone https://github.com/vridhichaudhary/CHATBOT.git
cd CHATBOT
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Up Your API Key
Create a `.env` file in the project root:
```bash
cp .env.example .env
```
Open `.env` and add your Google API key:
```
GOOGLE_API_KEY=your_api_key_here
```

### 5. Run the App
```bash
streamlit run RAG_app.py
```

Then open your browser at **http://localhost:8501**

---

## 📖 How to Use

1. **Upload Documents** — Use the sidebar to drag and drop any supported file
2. **Add to Knowledge Base** — Click the "📥 Add to Knowledge Base" button
3. **Chat** — Type your question in the chat box and get instant, document-backed answers
4. **Manage Files** — See all stored documents in the sidebar; click the 🗑️ icon to remove any

---

## 📁 Project Structure

```
CHATBOT/
│
├── RAG_app.py            # Main application file
├── requirements.txt      # Python dependencies
├── .env.example          # Template for environment variables
├── .gitignore            # Files excluded from version control
│
└── data/
    ├── knowledge_base/   # ChromaDB persistent vector store (auto-created)
    └── tmp/              # Temporary file processing directory (auto-created)
```

---

## ⚠️ Important Notes

- The `.env` file containing your API key is **never committed to GitHub** (it's in `.gitignore`)
- The `data/knowledge_base/` folder is also excluded from GitHub as it contains your private indexed documents
- This app runs entirely locally on your machine — your documents never leave your computer
