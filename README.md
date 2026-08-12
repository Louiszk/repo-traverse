# RepoTraverse

RepoTraverse is an AI-powered architectural and structural code analysis tool for exploring GitHub repositories. It provides a chat interface backed by an AI agent that can navigate, query, and explain complex codebases.

**Live Application:** [https://repo-tools.com](https://repo-tools.com)

## Features

The agent is equipped with several tools to analyze the repository via an Abstract Syntax Tree (AST) knowledge graph:

- **Architecture Overview**: Extracts repository structure, entry points, HTTP routes, and module clusters.
- **Symbol Search**: Locates exact function, class, or variable definitions across the codebase.
- **Code Search**: Performs text pattern matching enriched with symbol context.
- **Call Path Tracing**: Traces caller/callee dependencies and cross-service data flows.
- **Code Snippet Fetcher**: Retrieves source code implementations by qualified name or file path.
- **Graph Queries**: Supports custom (read-only) openCypher queries directly against the codebase graph.

## Tech Stack

- **Frontend**: TypeScript, React, Vite, TailwindCSS.
- **Backend**: Python, FastAPI, Pydantic, LangGraph, LangChain OpenAI integration.
- **Workers & Data**: Celery, Redis, SQLite, [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp/).
- **Deployment & CI**: Docker Compose, Nginx, GitHub Actions.

## Local Setup

### Prerequisites
- Docker and Docker Compose
- An OpenAI API Key
- A GitHub Personal Access Token (PAT)

### 1. Clone the repository
```bash
git clone https://github.com/Louiszk/repo-traverse.git
cd repo-traverse
```

### 2. Configure environment variables
Copy the provided example files to set up your local environment:
```bash
cp .env.shared.example .env.shared
cp .env.frontend.example .env.frontend
cp .env.backend.example .env.backend
```

**Important:** You must open `.env.backend` and add your API keys:
*   `OPENAI_API_KEY=sk-...`
*   `GITHUB_PAT=github_pat_...`

You should also verify `.env.shared` and ensure `REDIS_PASSWORD` is set. To ensure performance and prevent abuse, the application enforces a few default limits (which can also be adjusted in this `.env.shared` file).

### 3. Configure Docker Compose (Development)
To enable local development features like hot-reloading and exposed ports, create the local override file:
```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

### 4. Run the application
Start the services using Docker Compose:
```bash
docker compose up --build
```
*Note: The initial build may take a few minutes as it compiles Python wheels and downloads the AST parser binaries.*

## Usage

1. Open the application in your browser (at **http://localhost** if running locally, or via the live URL).
2. Enter a **public** GitHub repository URL (with an open-source license) into the input field. 
3. The backend Celery worker will clone and index the repository into a knowledge graph.
4. Once indexed, use the chat interface to ask architectural questions. You can click on any generated folder, files, or symbols to view them in the side panel.