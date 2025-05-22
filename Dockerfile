FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV HF_HOME=/models
ENV TRANSFORMERS_CACHE=/models

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    build-essential cmake git curl wget git && \
    rm -rf /var/lib/apt/lists/*

# 전체 코드 복사
COPY . .

# Python 패키지 설치 및 nltk 리소스
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install llama-cpp-python==0.3.8 --no-cache-dir --config-settings=cmake.define.LLAMA_CUBLAS=OFF && \
    python -m nltk.downloader vader_lexicon punkt

# ✅ 모델 최초 다운로드 및 캐시 (이미지에 포함)
RUN python3 -c "\
from huggingface_hub import snapshot_download; \
snapshot_download(repo_id='youngbongbong/empathymodel', local_dir='/models/empathy', local_dir_use_symlinks=False); \
snapshot_download(repo_id='youngbongbong/mimodel', local_dir='/models/mi', local_dir_use_symlinks=False); \
snapshot_download(repo_id='youngbongbong/cbt1model', local_dir='/models/cbt1', local_dir_use_symlinks=False); \
snapshot_download(repo_id='youngbongbong/cbt2model', local_dir='/models/cbt2', local_dir_use_symlinks=False); \
snapshot_download(repo_id='youngbongbong/cbt3model', local_dir='/models/cbt3', local_dir_use_symlinks=False);"

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
