FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py .

EXPOSE 8501

# Streamlit atrás do proxy do EasyPanel (Traefik): sem CORS/XSRF para o
# websocket conectar através do domínio; app é só-leitura e protegido por senha.
CMD ["streamlit", "run", "monitor.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
