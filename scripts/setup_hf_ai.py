"""公開サイト（Hugging Face Spaces）で、自分の案件の AI を使えるようにする設定。

実行：.venv\\Scripts\\python scripts\\setup_hf_ai.py <ユーザー名>
- AIパスワードは環境変数 RP_AI_PASSWORD で渡す（コード・記録に残さない）
- APIキー・トークンは .streamlit/secrets.toml から読む（画面には出さない）

処理：
1. 利用記録を置く非公開の dataset リポジトリ <ユーザー名>/readyproof-usage を作る（既にあればそのまま）
2. 接続確認として、料金0円の記録を1行書き込み、読み戻せることを確かめる
3. Space の秘密情報（Secrets）に、APIキー・AIパスワード・記録先を登録する（登録後、Space は再起動する）
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
        sys.exit("使い方：python scripts/setup_hf_ai.py <ユーザー名>（AIパスワードは環境変数 RP_AI_PASSWORD）")
    user = sys.argv[1]
    pw = os.environ.get("RP_AI_PASSWORD", "").strip()
    if not pw:
        sys.exit("環境変数 RP_AI_PASSWORD にAIパスワードを入れてください。")
    with open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb") as f:
        sec = tomllib.load(f)
    token, key = sec.get("HF_TOKEN", ""), sec.get("ANTHROPIC_API_KEY", "")
    if not token or not key:
        sys.exit(".streamlit/secrets.toml に HF_TOKEN と ANTHROPIC_API_KEY が必要です。")

    from huggingface_hub import HfApi

    from readyproof.config import Budget
    from readyproof.usage import HubLedger

    api = HfApi(token=token)
    repo = f"{user}/{DATASET}"
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    info = api.repo_info(repo, repo_type="dataset")
    if not info.private:
        sys.exit(f"{repo} が非公開になっていません。中止します。")
    print(f"利用記録の置き場所：{repo}（非公開）")

    lg = HubLedger(repo, token)
    rid = lg.reserve(Budget(), "check", "", 0.0, "接続確認")
    lg.finalize(rid, "成功", 0.0)
    assert any(r.get("run_id") == rid for r in lg.entries()), "書き込んだ記録を読み戻せません"
    print("接続確認：書き込み・読み戻しOK（料金0円の確認用の記録）")

    space = f"{user}/{SPACE}"
    secrets = {
        "ANTHROPIC_API_KEY": key,
        "RP_ACCESS_CODES": pw,
        "RP_USAGE_STORE_PERSISTENT": "true",
        "RP_USAGE_HF_REPO": repo,
        "RP_HF_TOKEN": token,
        # 共通のAIパスワード1つで使うため、パスワードあたりの月回数を30回に（月6,000円の上限はそのまま）
        "RP_AI_RUNS_PER_CODE_PER_MONTH": "30",
    }
    for k, v in secrets.items():
        api.add_space_secret(space, k, v)
        print(f"Space の秘密情報を登録：{k}")
    print("完了。Space が再起動します（数分）。")


if __name__ == "__main__":
    main()
