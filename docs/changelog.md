# Myffmpeg 変更ログ

## 2026-07-23 修正対応

### 修正内容一覧

| 修正項目 | 対象ファイル | 状態 |
|---|---|---|
| コマンドプレビューをSettings Pane下部に移動、QTextEdit化・折り返し対応 | `settings_pane.py`, `output_pane.py`, `main_window.py` | ✅ 完了 |
| 2パス表示を Pass1 / Pass2 の2行表示に対応 | `settings_pane.py`, `main_window.py` | ✅ 完了 |
| コマンドプレビュー対象ファイルをプレビュー指定ファイルに追従 | `settings_pane.py`, `main_window.py` | ✅ 完了 |
| 10秒プレビュー：2回目以降再生されない問題 (setSource後に再生すると黒画面) | `settings_pane.py` | ✅ 完了 |
| ログ表示：progress key=value行を専用ステータス欄に分離、通常ログに流れないよう修正 | `ffmpeg_worker.py`, `output_pane.py` | ✅ 完了 |
| 出力サフィックス (_targetsize 等) をタブ内で編集可能なテキストフィールドに変更 | `settings_pane.py` | ✅ 完了 |
| 赤線（構文エラー）3箇所の修正 | `ffmpeg_worker.py` Tuple型アノテーション, `output_pane.py` 未使用import削除, `preset_manager.py` 括弧修正 | ✅ 完了 |
| テスト: QCoreApplication/QApplication競合修正 | `test_ffmpeg_worker.py` | ✅ 完了 |

---

### 詳細説明

#### コマンドプレビュー変更
- `OutputPane` の `txt_command_preview` (`QLineEdit`) を削除し、代わりに `SettingsPane` の `QGroupBox(10秒プレビュー)` の下に `QPlainTextEdit` で配置
- `QPlainTextEdit` は `setReadOnly(True)` + `setWordWrapMode(True)` により、長い文字列も折り返し表示
- 2パスの場合は「Pass1:」「Pass2:」の2行で表示

#### コマンドプレビュー対象ファイル連動
- `cmb_preview_file` (ComboBox) の変更時に `command_preview_changed` シグナルを発火
- `MainWindow` でそのシグナルを受け取り `_update_command_preview` を呼び出す
- `_update_command_preview` はプレビュードロップダウンで選択されているファイルを使用（なければ先頭のファイル）

#### 10秒プレビュー 2回目以降再生バグ修正
- PySide6 の `QMediaPlayer` は同一ソースを再設定する際、`stop()` → `setSource(QUrl())` でクリア → 新しいソース設定 → `play()` の順序が必要
- `_on_preview_worker_finished` メソッドで `setSource(QUrl())` で一度クリアしてから再セットするよう修正

#### ログ表示の分離
- `FFmpegWorker` で `progress_stats_updated` 新シグナルを追加 (`Signal(dict)`)
- `out_time_us=`, `fps=`, `speed=`, `bitrate=`, `size=` などの `key=value` 行は `progress_stats_updated` で送信し、通常ログには流さない
- `OutputPane` に `lbl_ffmpeg_stats` ラベルを追加し、進捗情報を上書き更新表示する
- `\n` を含む通常のログ行のみ `txt_log` に追記

#### 出力サフィックス編集可能化
- `SettingsPane` の各タブ (Tab A / B / C) にサフィックス入力 `QLineEdit` を追加
- `get_current_settings()` でその値を返し、プリセット保存・読み込みにも対応

#### 赤線（Lint エラー）修正
- `preset_manager.py`: `load_settings((self)` の二重括弧（初回作成時の typo）→ 修正済み
- `ffmpeg_worker.py`: `-> (bool, str)` という戻り値型アノテーションが Python 3 では `-> tuple[bool, str]` が正式。ただし PySide6 互換のため `Any` に
- `output_pane.py`: `QWidget` のインポート整理（使われていない import を削除）

#### アイコン指定追記 by user
- `path_helper.py`: `get_icon_path` メソッド追加 (assets/icon/app_icon.ico を参照)
- `main_window.py`: `QIcon` を追加インポート、`setWindowIcon` でアイコン設定
- `app_icon.ico` を `assets/icon/` に配置（要pyinstaller時同梱設定）

#### 配布ファイル作成 by user
- `pyinstaller --noconsole --onedir --name "Myffmpeg" --icon "assets/app_icon.ico" --add-data "assets;assets" --add-data "tools;tools" --add-data "LICENSE_FFmpeg.txt;." --add-data "LICENSE;." main.py` で実行

## 追加修正対応
### ファイルリストの項目表示幅調整
- `input_pane.py` : QTableWidget の列幅調整モードを `Interactive` に変更し、ユーザーが列幅をマウスで自由に変更できるように修正。
- パスやファイル名などの長い文字列が見切れないよう、初期幅 (`150` や `200`) を設定。

### エンコーダーの動的検知と追加
- `settings_pane.py` : H.264, H.265 (HEVC), AV1 形式における CPU, NVIDIA NVENC, AMD AMF, Intel QSV などの各種エンコーダーに対応。
- 実行時にバックグラウンドで空出力のテストエンコードを実行し、実際のPC環境で利用可能なエンコーダーのみをドロップダウンに表示 (`detect_available_encoders` メソッド追加)。
- 選択されたエンコーダーに応じた画質パラメータ (CRF, VBR, CQP, Global Quality等) を自動生成する `build_quality_args` メソッドを実装。

#### libsvtav1が認識されない問題
- essential版にはそもそも入ってなかった。

### 複数ファイル選択時のビットレート一括計算
- `settings_pane.py` : サイズ指定圧縮 (2パス) 時の推定映像ビットレート計算ロジックを変更。
- リストに登録された全ファイルについて一括で計算し、`〇〇 〜 〇〇 kbps` のように最小〜最大の幅で全体推定を表示するように変更。
- 一部ファイルでも計算エラー（動画長が不明等）が発生した場合は、「エラーとなるファイルがあります」と警告表示するよう処理を実装。

音声と映像のビットレートの項目を入力ファイルリストのところに追加した。

コマンド作成機能を`command_build.py`に統合した。

あといろいろ
