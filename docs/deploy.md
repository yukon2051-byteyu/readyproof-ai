# Streamlit Community Cloud への公開手順

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
- 公開環境では利用記録の保存先が永続でないため、`RP_USAGE_STORE_PERSISTENT` を設定しない限り**有料のAI処理は自動停止**します（仕様どおり）
- ローカル文字起こし（faster-whisper）は、公開環境では処理が遅い・メモリ不足の可能性があります（未検証）。録画は会議ツールの文字起こし（VTT/SRT）読込を推奨
- 公開URLには架空のデモだけを載せ、実際の社内資料はアップロードしないよう案内してください
- アプリは12時間アクセスがないと休止し、次のアクセスで起動します（数十秒かかります）

## 4. 公開後の確認項目
- [ ] トップページと3件のデモが開ける
- [ ] Excel・JSON がダウンロードできる
- [ ] 「設定・利用枠」で「APIキーが設定されていません」「永続的な利用記録の保存先が…」と表示され、AI実行ボタンが出ない
- [ ] 確認結果を `docs/test_results.md` に追記する
