FROM python:3.11-slim

# Evita criação de arquivos .pyc e faz flush imediato do stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROBOT_REPORT_HOST=0.0.0.0 \
    ROBOT_REPORT_PORT=5000 \
    ROBOT_REPORT_NO_BROWSER=1

WORKDIR /app

# Instala dependências do sistema necessárias para compilação eventual
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências do projeto
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

# Copia o código da aplicação
COPY . .

# Diretórios para dados persistentes e saída
RUN mkdir -p /app/data /app/reports

EXPOSE 5000

# Por padrão, inicia a interface web. Pode ser substituído para rodar 'python main.py ...'
ENTRYPOINT ["python"]
CMD ["gui.py"]
