# 公開手順

## 現在の公開先：Hugging Face Spaces（Docker方式）
公開URL：https://yukon2051-readyproof-ai.hf.space　管理画面：https://huggingface.co/spaces/yukon2051/readyproof-ai

- Docker方式のスペースは有料プラン（PRO・月9ドル）が必要（2026-11-04時点）。サーバーは無料の CPU basic（2vCPU・16GB）
- 実行環境は `Dockerfile`（Python 3.12、`requirements.txt`、ポート7860）
- 更新方法：GitHub にコミットした後、次を実行（`.streamlit/secrets.toml` の `HF_TOKEN` を使う。GitHub のリポジトリは変更しない）
  ```powershell
  .venv\Scripts\python scripts\deploy_hf.py yukon2051
  ```
- Spaces はアプリを埋め込み表示するため、ファイルのアップロードが動くよう XSRF 対策を無効にしている（認証のない公開デモ用途に限定）
- 公開版には APIキーを設定しない（有料AIは停止）。実在の社内資料をアップロードしないよう案内する

## 自社の案件でAIを使う設定（公開サイト）

1. `scripts/setup_hf_ai.py <ユーザー名>`（AIパスワードは環境変数 `RP_AI_PASSWORD`）：利用記録の非公開の置き場所（dataset `<ユーザー名>/readyproof-usage`）を作り、Space の秘密情報（APIキー・AIパスワード・記録先・書き込み用トークン）を登録する。2026-11-04 に利用者が実行済み。
2. 書き込み用トークン（`RP_HF_TOKEN`）を、権限を絞ったものに差し替える（最初の登録ではアカウント全体に書ける管理用トークンを使ったため）。**2026-11-05 に利用者が実行済み**。差し替え後、公開サイトでAIパスワードの確認・利用状況の表示・実行ボタンの表示を確認した：
   1. Hugging Face の Settings → Access Tokens → **Create new token** → **Fine-grained** を選ぶ
   2. 名前：`readyproof-usage-writer`
   3. Presets で **Custom** を選び、「Repositories permissions」で `<ユーザー名>/readyproof-usage` だけを選んで、**Read contents** と **Write contents/settings** にチェック（Write に連動して「View access requests」も付くが、選んだリポジトリだけの権限なので問題ない）。ほかの権限は付けない
   4. 作成したトークンをコピーし、VS Code のターミナルで実行（トークンはチャットに貼らない）：
      `$env:RP_USAGE_TOKEN="（コピーしたトークン）"; .venv\Scripts\python scripts\set_usage_token.py <ユーザー名>`
   5. スクリプトは、Fine-grained でなければ中止し、新しいトークンで記録の書き込み・読み戻しを確認してから Space に登録する
   6. 終わったら、ターミナルを閉じる（環境変数を残さない）

## 以前の公開先：Streamlit Community Cloud（断念）
以下は当初の手順。画面が表示されなかった経緯は `test_results.md` 2-3 を参照。


## 前提
- GitHub アカウントと、このフォルダを置くリポジトリ（公開リポジトリ推奨。ポートフォリオとして閲覧してもらうため）
- Streamlit Community Cloud（https://share.streamlit.io）に GitHub アカウントでログインできること

## 1. GitHub に置く
1. GitHub で空のリポジトリを作る（例：`readyproof-ai`。README などは追加しない）
2. このフォルダで次を実行（URL は自分のものに置き換える）
   ```powershell
   git remote add origin https://github.com/<ユーザー名>/readyproof-ai.git
   git branch -M main
   git push -u origin main
   ```
   `.venv`・`data/`・`.streamlit/secrets.toml` は `.gitignore` で除外済み（APIキーは入らない）

## 2. Community Cloud でデプロイ
1. share.streamlit.io →「Create app」→ リポジトリ・ブランチ `main`・メインファイル `app.py` を選ぶ
2. 「Advanced settings」で **Python 3.12** を選ぶ
3. Secrets は**最初は空のまま**にする（APIキーなし＝デモと手動機能のみの安全な公開）
4. Deploy

## 3. 公開環境での注意
- 公開環境は `requirements.txt`（ローカル文字起こしを含まない軽い構成）でインストールされます。録画は会議ツールの文字起こし（VTT/SRT/テキスト）を読み込む使い方になります
- 公開環境では利用記録の保存先が永続でないため、`RP_USAGE_STORE_PERSISTENT` を設定しない限り**有料のAI処理は自動停止**します（仕様どおり）
- 公開URLには架空のデモだけを載せ、実際の社内資料はアップロードしないよう案内してください
- アプリは12時間アクセスがないと休止し、次のアクセスで起動します（数十秒かかります）

## 4. 公開後の確認項目
- [ ] トップページと3件のデモが開ける
- [ ] Excel・JSON がダウンロードできる
- [ ] 「設定・利用枠」で「APIキーが設定されていません」「永続的な利用記録の保存先が…」と表示され、AI実行ボタンが出ない
- [ ] 確認結果を `docs/test_results.md` に追記する
