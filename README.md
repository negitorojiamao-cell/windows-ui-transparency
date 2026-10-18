# Windows UI Transparency

Windows 11 のタスクバー背景を透明・ぼかし・アクリル風に変更するデスクトップアプリです。

## 機能

- タスクバー背景の透明 / ぼかし / アクリル風モード
- 色の濃さの調整
- 標準状態に戻す
- Explorer 再起動時の効果再適用
- GitHub Actions による Windows 用 EXE の自動ビルド

## EXE の入手方法

1. GitHub リポジトリの Actions タブを開く
2. 最新の Build Windows EXE ワークフローを選ぶ
3. 成功した実行の Artifacts から WindowsUITransparency-Windows ZIP をダウンロード
4. ZIP を展開して WindowsUITransparency.exe を実行

未署名 EXE のため、SmartScreen の警告が表示される場合があります。

## ソースから起動

Windows に Python 3.10 以降をインストールし、リポジトリ内で実行します。

    py -3 windows_ui_transparency.py

起動.bat からも起動できます。

## 対応範囲と制限

初期版が変更するのは Windows 11 のタスクバー背景です。アイコンや時計そのものを透明化する機能ではありません。スタートメニュー、通知センター、クイック設定、およびすべてのアプリのウィンドウ枠を一括で透明化するものではありません。

タスクバー効果には Windows の未公開 API を使用するため、Windows の更新で動作が変わる可能性があります。詳しくは docs/SCOPE.md を参照してください。

## 技術メモ

タスクバー効果には SetWindowCompositionAttribute と ACCENT_POLICY を利用します。これは安定した公開カスタマイズ API ではありません。DWM の公開 API によるタイトルバーや背景効果は、基本的に各ウィンドウのアプリ側で設定する仕組みです。

参考:
- https://learn.microsoft.com/en-us/windows/win32/dwm/desktop-window-manager-overviews
- https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type
- https://support.microsoft.com/ja-jp/windows/experience/personalization/customize-the-taskbar-in-windows
