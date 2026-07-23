「構成の計画」を立てるのは、**AIを使って開発する上で最も成功率が上がる素晴らしいアプローチ**です！

1つのファイル（`main.py`）にすべてのコードを詰め込むと、コードが長くなった時にAIが全体を把握しきれなくなり、バグや修正漏れが急増します。

ソフトウェア開発では、この作業を「アーキテクチャ設計」**や**「モジュール設計（ディレクトリ構成・クラス設計）」と呼びます。

## Myffmpeg の推奨ディレクトリ・モジュール構成案

AIに「1ファイルずつ順番に作らせる」ことができるよう、役割ごとに綺麗に分離した設計案を作成しました。

Plaintext

```
Myffmpeg/
│
├─ .venv/                  ← 仮想環境（触らない）
├─ tools/                  ← ffmpeg.exe, ffprobe.exe
│
├─ src/                    ← ソースコード本体
│   │
│   ├─ core/               ← 【バックエンド】FFmpeg実行や計算処理
│   │   ├─ ffprobe_parser.py  # ffprobeで動画情報をJSON取得・解析
│   │   ├─ bitrate_calc.py    # 2パス用のビットレート自動計算
│   │   └─ ffmpeg_worker.py   # QThreadを使ったFFmpeg非同期実行・進捗通知
│   │
│   ├─ ui/                 ← 【フロントエンド】PySide6の画面部品
│   │   ├─ input_pane.py      # 入力ブロック（ファイルリスト・D&D）
│   │   ├─ settings_pane.py   # 設定ブロック（各タブ・プレビュー）
│   │   ├─ output_pane.py     # 出力ブロック（ログ・実行・進捗バー）
│   │   └─ main_window.py     # 3ブロックをまとめるメイン画面
│   │
│   └─ utils/              * 【共通補助】設定保存やパス解決
│       ├─ path_helper.py     # exeやファイルのパス解決（PyInstaller対策）
│       └─ preset_manager.py # 設定（settings.json）の保存・読み込み
│
├─ presets/                ← プリセット保存用フォルダ
│   └─ settings.json
│
└─ main.py                 ← アプリ起動エントリーポイント
```

## 各モジュール（クラス）の役割設計

AIに実装指示を出す際、以下のように「役割」を定義しておくと、AIが迷わずにコードを書けます。

### 1. `core/` （ロジック層）

- **`ffprobe_parser.py` (`FFprobeParser` クラス)**
    
    - 動画ファイルのパスを受け取り、`ffprobe` を実行して「解像度・フレームレート・動画の長さ（秒）・ファイルサイズ」を辞書型で返す。
        
- **`bitrate_calc.py` (`BitrateCalculator` クラス)**
    
    - 「動画の長さ」「オーディオビットレート」「目標ファイルサイズ(MB)」を受け取り、最適な映像ビットレートを計算する。不可能なサイズの場合は例外（エラー）を投げる。
        
- **`ffmpeg_worker.py` (`FFmpegWorker` クラス / `QThread` 継承)**
    
    - コマンド文字列とファイル情報を受け取り、バックグラウンドで `subprocess` を実行。
        
    - `-progress -` の出力を監視し、進捗率（%）をUIにシグナル送信（`pyqtSignal`）する。キャンセル処理（`terminate()`）もここで持つ。
        

### 2. `ui/` （UI表示層）

- **`input_pane.py` (`InputPane` クラス)**
    
    - ファイル追加・削除ボタン、ドラッグ＆ドロップ領域、ファイル一覧リスト（`QTableWidget` または `QListWidget`）の表示。
        
- **`settings_pane.py` (`SettingsPane` クラス)**
    
    - 「映像消去」「圧縮」「サイズ指定」のタブUI。プレビュー用の再生プレイヤー（`QMediaPlayer`）を配置。
        
- **`output_pane.py` (`OutputPane` クラス)**
    
    - プログレスバー、実行/キャンセルボタン、処理ログ（`QTextEdit`）の表示。
        
- **`main_window.py` (`MainWindow` クラス)**
    
    - 上記3つのPaneを画面に配置し、それぞれのシグナル（例: 入力リストが変わったら設定画面を更新する等）を連携させる司令塔。
        

### 3. `utils/` （ユーティリティ層）

- **`path_helper.py` (`get_tool_path` 関数)**
    
    - `tools/ffmpeg.exe` などのパスを安全に取得する関数。
        

## AI開発を進めるコツ（ステップバイステップ戦略）

一度に全ファイルを作成させるのではなく、**依存関係の低い「土台」から1ファイルずつAIに書かせる**のが一番スムーズです。

1. **Step 1:** `utils/path_helper.py` を作らせる（一番単純）
    
2. **Step 2:** `core/ffprobe_parser.py` と `core/bitrate_calc.py` を作らせて、単体で動くか試す
    
3. **Step 3:** `core/ffmpeg_worker.py` （QThread）を作らせる
    
4. **Step 4:** `ui/` 系の画面パーツを1つずつ作らせる
    
5. **Step 5:** `main_window.py` で全部をガッチャンコする
    

こうすると、万が一エラーが起きても「どのファイルのどこに原因があるか」がすぐ特定できます。