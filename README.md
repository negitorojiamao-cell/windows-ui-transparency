# Windows UI Transparency

Windows 11 のタスクバー背景を調整し、対応するビルドでは時計やアプリアイコン領域の個別透明度も試せるデスクトップアプリです。

## 機能

- タスクバー背景: 透明 / ぼかし / アクリル風 / 標準に戻す
- タスクバー背景の色の濃さを調整
- 保存した設定を次回起動時に再適用
- 対応するWindowsビルドで時計・アプリアイコン領域の不透明度を個別調整
- Explorer再起動後の効果再適用
- EXE版からWindowsサインイン時の自動起動を登録・解除
- GitHub ActionsによるWindows用EXEの自動ビルド

## EXEの入手方法

1. GitHubリポジトリの Actions タブを開く
2. 最新の **Build Windows EXE** ワークフローを選ぶ
3. 成功した実行の Artifacts から `WindowsUITransparency-Windows` ZIP をダウンロード
4. ZIPを展開して `WindowsUITransparency.exe` を実行

未署名EXEのため、SmartScreenの警告が表示される場合があります。

## スタートアップ登録

ビルド済みの `WindowsUITransparency.exe` を起動し、**Windowsへのサインイン時に起動**にチェックを入れてください。ユーザー単位の `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run` に登録するため、通常は管理者権限は不要で、タスクマネージャーの「スタートアップ アプリ」に表示されます。

チェックを外すと登録解除します。登録後にEXEを移動・削除すると起動できなくなるため、置き場所を決めてから登録してください。Pythonソースから起動した場合は誤ってPython自体を登録しないよう、この機能を無効にしています。

## ソースから起動

WindowsにPython 3.10以降をインストールし、リポジトリ内で実行します。

    py -3 windows_ui_transparency.py

または `起動.bat` から起動できます。

## 時計などの個別透明化について

アプリはタスクバー配下に `TrayClockWClass`（時計）と `MSTaskListWClass`（アプリアイコン領域）が実在するかを検出し、見つかった場合に限り、そのウィンドウの不透明度変更を試します。アプリアイコンは1個ずつではなくグループ全体が対象です。個別ウィンドウが検出されない場合は、このWindows 11ビルドの共有XAML/DirectComposition描画構造により対象外となります。時計・アイコンの個別透明度はすべてのWindows 11ビルドで保証される機能ではありません。

個別透明度はアプリ終了時に、変更したウィンドウスタイルを元に戻す安全側の動作にしています。再度利用する場合はアプリを起動し、保存済み設定の再適用を試してください。

## 制限

- スタートメニュー、通知センター、クイック設定、ウィジェットを個別に透明化する機能はありません。
- タスクバー背景の効果には `SetWindowCompositionAttribute` というMicrosoftが使用を推奨していないAPIを使うため、Windowsの更新で挙動が変わる可能性があります。
- 透明度スライダーは効果モードとWindowsビルドによって見え方が異なります。
- Windows 11のシステムUIの全要素を一律に透明化するものではありません。

## 技術資料

- [Microsoft: SetWindowCompositionAttribute](https://learn.microsoft.com/en-us/windows/win32/dwm/setwindowcompositionattribute)
- [Microsoft: DWM overviews](https://learn.microsoft.com/en-us/windows/win32/dwm/dwm-overviews)
- [Microsoft: Customize the Windows 11 Taskbar](https://learn.microsoft.com/en-us/windows-hardware/customize/desktop/customize-the-taskbar)
