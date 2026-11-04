"""Hugging Face Spaces へ公開用のコピーを送る（GitHub のリポジトリは変更しない）。

実行：.venv\\Scripts\\python scripts\\deploy_hf.py <Hugging Face のユーザー名>
アクセストークン：.streamlit/secrets.toml の HF_TOKEN（画面・記録には出さない）

処理：
1. 最新のコミット内容（git archive）を一時フォルダに展開
2. Spaces 用の設定（YAML）を README の先頭に付ける
3. 資料・動画などのファイルを Git LFS で扱う（Hugging Face の要件）
4. Space のリポジトリへ送信（毎回まるごと置き換え）
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPACE = "readyproof-ai"
YAML = """---
title: ReadyProof AI
emoji: 📋
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: AI受入テスト・導入確認支援システム（架空データのデモ）
---

"""
LFS_PATTERNS = ["*.pdf", "*.pptx", "*.docx", "*.xlsx", "*.mp4", "*.png"]


def run(cmd, cwd, token=""):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout + p.stderr).replace(token, "***") if token else p.stdout + p.stderr
    if p.returncode != 0:
        sys.exit(f"失敗：{' '.join(c.replace(token, '***') if token else c for c in cmd[:3])}\n{out[-1500:]}")
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("使い方：python scripts/deploy_hf.py <Hugging Face のユーザー名>")
    user = sys.argv[1]
    with open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb") as f:
        token = tomllib.load(f).get("HF_TOKEN", "")
    if not token:
        sys.exit(".streamlit/secrets.toml に HF_TOKEN がありません。")
    tmp = tempfile.mkdtemp(prefix="rp_hf_")
    try:
        data = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, capture_output=True,
                              check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            t.extractall(tmp, filter="data")
        readme = os.path.join(tmp, "README.md")
        with open(readme, encoding="utf-8") as f:
            body = f.read()
        with open(readme, "w", encoding="utf-8", newline="\n") as f:
            f.write(YAML + body)
        run(["git", "init", "-q", "-b", "main"], tmp)
        run(["git", "lfs", "install", "--local"], tmp)
        run(["git", "lfs", "track", *LFS_PATTERNS], tmp)
        run(["git", "add", "-A"], tmp)
        run(["git", "-c", f"user.name={user}", "-c", "user.email=noreply@huggingface.co", "commit", "-q",
             "-m", "ReadyProof AI を公開（GitHub の最新コミットから作成）"], tmp)
        url = f"https://{user}:{token}@huggingface.co/spaces/{user}/{SPACE}"
        run(["git", "-c", "credential.helper=", "push", "--force", url, "main"], tmp, token)
        print(f"送信しました：https://huggingface.co/spaces/{user}/{SPACE}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
