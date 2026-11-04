# Hugging Face Spaces（Docker 方式）用の実行環境
FROM python:3.12-slim

# Spaces の推奨どおり、管理者ではない利用者（UID 1000）で動かす
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# 公開環境はローカル文字起こしを含まない軽い構成（requirements.txt）
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
# Spaces はアプリを埋め込み表示（iframe）するため、ファイルのアップロードが動くよう
# XSRF 対策と CORS を無効にする（Spaces で一般的な設定。認証のない公開デモ用途に限定）
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true", \
     "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
