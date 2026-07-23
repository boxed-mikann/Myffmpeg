# 🚀 Myffmpeg

![App Icon](assets/app_icon.ico) <!-- アイコン画像があれば表示 -->

面倒なビットレート計算を自動化し、一括処理やプレビュー手軽に行えるシンプルなFFmpeg GUIユーティリティ。

ffmpegでの圧縮をフォルダごと一気にやりたい、コマンド打つのめんどくさい、プレビュー見ながら圧縮したいという方向け。

重要！ 不具合発覚 av1方式および、ハードウェアエンコーダ(GPU)でのサイズ指定方式は使えません。やりたい人は各自でコマンド調べましょう。現在、この問題の修正対応中...

---

## ✨ 主な機能

- **ビットレート自動計算（2パス圧縮）**: 目標ファイルサイズ（MB）を指定するだけで最適なビットレートを自動算出。
- **1パス画質優先圧縮**: CRFやエンコーダ設定（CPU / Intel QSV対応）を指定した圧縮。
- **映像消去（音声抽出）**: 動画から映像ストリームを素早く削除。
- **バッチ（一括）処理**: 複数ファイルをリストに追加してまとめてエンコード。

---

## 対象環境

Windows 11  
IntelのGPU
NvidiaのGPU(動作未確認)
AMDのGPU(動作未確認)

---

## 📦 ダウンロード & 使い方 (一般ユーザー向け)

Pythonのインストールや環境構築は不要です。

1. [Releases](../../releases) ページから最新の `Myffmpeg_vX.X.X.zip` をダウンロードします。
2. ZIPファイルを解凍します。
3. フォルダ内の `Myffmpeg.exe` を実行します。

---

## 🛠️ 開発環境での実行・ビルド方法 (開発者向け)

### 必須要件
- Windows OS
- Python 3.12+
- FFmpeg / FFprobe エグゼクティブバイナリ

### セットアップ

1. リポジトリをクローン
   ```bash
   git clone https://github.com/boxed-mikann/Myffmpeg.git
   cd Myffmpeg

2. 仮想環境の作成とライブラリのインストール

    ```bash
    py -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```
    `.\.venv\Scripts\activate`でエラーが出たら、`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`もしくは`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`を実行してから再度実行してください。

3. FFmpegの配置
gyan.dev 等からダウンロードした ffmpeg.exe と ffprobe.exe を ./tools/ フォルダ内に配置してください。~~release-essentialsが軽量でおすすめです。~~ → av1コーデックがなかったので、fullの方で、.7zはwindowsの標準の展開のやつで展開できます。

    ```plaintext
    Myffmpeg/
    └─ tools/
        ├─ ffmpeg.exe
        └─ ffprobe.exe
    ```

4. アプリ起動

    ```bash
    python main.py
    ```
---

## 今後の展望

- プレビュー画面を最大化できるようにしたい。
- ~~NvidiaGPUの環境とかにも対応したい。~~
AIのクレジット回復待ち中

---
## ⚖️ ライセンス・権利表記

- 本アプリケーション本体は MIT License のもとで公開されています。
- 本パッケージには [FFmpeg](https://ffmpeg.org/) (ffmpeg.exe / ffprobe.exe) が同梱されています。
  FFmpeg は LGPL v2.1 / GPL v2.0 以降のライセンスに基づいて配布されているオープンソースソフトウェアです。