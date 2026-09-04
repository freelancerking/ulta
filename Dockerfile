FROM apify/actor-python-playwright:latest

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

CMD ["python", "-u", "src/main.py"]
