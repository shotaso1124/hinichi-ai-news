# ひにち AI News

AIニュース集約Webアプリ。Hacker News / HuggingFace Daily Papers / hnrss.org からAI関連記事を取得して一画面に表示します。

## 特徴
- 3ソース統合: HN Firebase API / HF Daily Papers / hnrss.org
- AI関連27キーワードによる自動フィルタ
- 30分TTLキャッシュで高速表示
- XSS対策共通バリデータ実装
- 全ソース無認証パブリックAPI（個人情報・APIキー不要）

## ローカル実行

```bash
git clone https://github.com/shotso1124/hinichi-ai-news.git
cd hinichi-ai-news
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

ブラウザで http://localhost:8501 にアクセス。

## デプロイ

[Streamlit Community Cloud](https://share.streamlit.io/) で公開可能。

## ソース・出典

| ソース | URL |
|------|-----|
| Hacker News | https://news.ycombinator.com |
| HuggingFace Daily Papers | https://huggingface.co/papers |
| hnrss.org | https://hnrss.org |

## ライセンス

MIT License

## 著作権・利用規約

本アプリはAIニュースのリンクとタイトルのみを集約・表示します。記事本文の取得・再配布は行っていません。記事本文の閲覧・引用については各一次ソースの利用規約に従ってください。
