# AI Service

A FastAPI-based AI service for document processing and intelligent search using AWS services.

## Features

- **Document Extraction**: Extract and process text from various document formats
- **Intelligent Search**: RAG (Retrieval-Augmented Generation) powered search using 
Pinecore
- **Image Processing**: Analyze and extract information from images
- **Vietnamese NLP**: Specialized text processing for Vietnamese language
- **Ontology Relations**: Manage and query knowledge relationships

## Architecture

```
ai-service/
├── app/
│   ├── main.py                    # FastAPI application
│   ├── config.py                  # Configuration and secrets
│   ├── models/                    # Pydantic models
│   ├── services/                  # Business logic services
│   ├── utils/                     # Utility functions
│   └── api/v1/                    # API endpoints
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Technology Stack

- **Framework**: FastAPI
- **Search Engine**: Pinecore
- **LLM**: AWS Bedrock
- **Embeddings**: Amazon Titan
- **Message Queue**: RabbitMQ
- **Language Processing**: Vietnamese NLP tools

## Getting Started

### Prerequisites

- Python 3.8+
- Docker & Docker Compose
- AWS Account with Bedrock access

### Installation

1. Clone the repository
```bash
git clone <repository-url>
cd AI_service
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Configure environment variables
```bash
cp .env.example .env
# Edit .env with your configurations
```

4. Run with Docker Compose
```bash
docker-compose up -d
```

### Development

Run locally:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Extraction API
- `POST /api/v1/extract/` - Extract text from documents
- `POST /api/v1/extract/image` - Process and analyze images

### Search API
- `GET /api/v1/search/` - Intelligent search with RAG
- `POST /api/v1/search/semantic` - Semantic similarity search

## Configuration

Key configuration options in `app/config.py`:

- AWS Bedrock settings
- OpenSearch connection
- RabbitMQ configuration
- Vietnamese NLP models
