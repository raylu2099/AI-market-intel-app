FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create runtime dirs
RUN mkdir -p data/sources data/analyses data/pushes data/costs data/cache logs

EXPOSE 8000

# Run web server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
