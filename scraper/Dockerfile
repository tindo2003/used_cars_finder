# Version pinned to match requirements.txt's playwright==1.61.0 -- this
# image ships browser binaries for that exact release, so the pip package
# and the browsers must stay in lockstep. Bump both together.
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT ["python3"]
CMD ["main.py"]
