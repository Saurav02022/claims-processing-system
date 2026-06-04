# FastAPI Backend

This is a basic backend project built with Python and FastAPI.

## Requirements

Make sure you have Python installed.

Recommended Python version:

```bash
python3 --version
```

## How to Clone the Project

Clone the repository:

```bash
git clone <https://github.com/Saurav02022/claims-processing-system.git>
```

Go inside the project folder:

```bash
cd backend
```

> Replace `<https://github.com/Saurav02022/claims-processing-system.git>` with the actual GitHub repository URL.

## Create Virtual Environment

Create a virtual environment:

```bash
python3 -m venv venv
```

Activate the virtual environment:

### Mac / Linux

```bash
source venv/bin/activate
```

### Windows

```bash
venv\Scripts\activate
```

## Install Dependencies

Install all required packages:

```bash
pip install -r requirements.txt
```

## Run the Project

Start the FastAPI development server:

```bash
fastapi dev app/main.py
```

Or run using Uvicorn:

```bash
uvicorn app.main:app --reload
```

## Open in Browser

After running the server, open:

```text
http://127.0.0.1:8000
```

API documentation will be available at:

```text
http://127.0.0.1:8000/docs
```

## Basic Project Structure

```text
backend/
  app/
    __init__.py
    main.py
  requirements.txt
  README.md
  .gitignore
```

## Health Check

You can check if the backend is running by opening:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```
