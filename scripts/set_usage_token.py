"""公開サイトの「利用記録の書き込み用トークン」を、権限を絞ったものに差し替える。

実行：.venv\\Scripts\\python scripts\\set_usage_token.py <ユーザー名>
- 新しいトークンは環境変数 RP_USAGE_TOKEN で渡す（コード・記録・画面に残さない）
- Space への登録には、管理用の HF_TOKEN（.streamlit/secrets.toml）を使う

処理：
1. 新しいトークンの種類を確認する（権限を絞った fine-grained でなければ中止）
2. 新しいトークンで、利用記録の置き場所に料金0円の確認用の記録を書き、読み戻せることを確かめる
3. 確認できたら、Space の秘密情報 RP_HF_TOKEN を新しいトークンに置き換える（Space は再起動する）
"""
from __future__ import annotations

import os
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SPACE = "readyproof-ai"
DATASET = "readyproof-usage"


def main():
    if len(sys.argv) < 2:
        sys.exit("使い方：python scripts/set_usage_token.py <ユーザー名>（新しいトークンは環境変数 RP_USAGE_TOKEN）")
    user = sys.argv[1]
    new = os.environ.get("RP_USAGE_TOKEN", "").strip()
    if not new:
        sys.exit("環境変数 RP_USAGE_TOKEN に、新しく作ったトークンを入れてください。")
    with open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb") as f:
        admin = tomllib.load(f).get("HF_TOKEN", "")
    if not admin:
        sys.exit(".streamlit/secrets.toml に管理用の HF_TOKEN がありません。")

    from huggingface_hub import HfApi

    from readyproof.config import Budget
    from readyproof.usage import HubLedger

    info = HfApi(token=new).whoami()
    role = ((info.get("auth") or {}).get("accessToken") or {}).get("role", "不明")
    print(f"新しいトークンの種類：{role}")
    if role != "fineGrained":
        sys.exit("権限を絞ったトークン（Fine-grained）ではありません。手順どおりに作り直してください。中止します。")

    repo = f"{user}/{DATASET}"
    lg = HubLedger(repo, new)
    rid = lg.reserve(Budget(), "check", "", 0.0, "トークン差し替えの確認")
    lg.finalize(rid, "成功", 0.0)
    if not any(r.get("run_id") == rid for r in lg.entries()):
        sys.exit("新しいトークンで書いた記録を読み戻せません。中止します（Space の設定は変えていません）。")
    print(f"新しいトークンで {repo} への書き込み・読み戻しOK（料金0円の確認用の記録）")

    HfApi(token=admin).add_space_secret(f"{user}/{SPACE}", "RP_HF_TOKEN", new)
    print("Space の秘密情報 RP_HF_TOKEN を新しいトークンに置き換えました。Space が再起動します（数分）。")
    print("このあと、Hugging Face の設定画面で、管理用トークンが Space の秘密情報に残っていないことを確認してください。")


if __name__ == "__main__":
    main()
