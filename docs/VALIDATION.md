# 検証記録

日付：2026-11-04

## 実行した確認

環境：Linux、Python 3.12.14。外部APIは使用していない。

| 確認 | 結果 |
| --- | --- |
| スターターのunittest | 16件成功 |
| 初期デモをharnessから実行 | 意図した失敗を記録、終了コード1 |
| デモを一時ディレクトリへ複製して修正 | 固定の受入テスト9件成功、終了コード0 |
| 修正版のstatus | 現在のソースに対応する成功と判定 |
| 合格後にソースを変更してstatus | stale、終了コード1 |
| 検証中断・最新レポートなし | incomplete、過去のPASSへ戻らないことをテスト |
| Python 3.9としての構文解析 | 成功 |
| Markdown内のローカルリンク | リンク切れなし |

初期デモの不具合は、実際にCodexで修正を試せるように残している。修正版の確認は一時コピーで行い、デモの初期ソースを置き換えていない。

## 2026-11-05：ネイティブWindows・uv向けの手順

- `pyproject.toml` とuv 0.13.5で生成した `uv.lock` を追加。
- Linux・Python 3.12で `uv sync --locked --offline --python 3.12` と、uv経由の既存16テストが成功。
- デモの子ディレクトリから起動すると、スターターの `.venv` を使い、作業場所はデモに保たれることを確認。
- 別の対象プロジェクトから起動すると、チェック内の `{python}` と作業場所が対象プロジェクトの環境になることを確認。
- GitHub Actionsもuv経由のWindows/Ubuntu・Python 3.9/3.12に変更。各コミットの実行結果は[Actions](https://github.com/ku-k-ai/codex-harness-starter/actions)を参照。

## この確認で保証していないこと

- 会社・自宅の実機でのCodex認証や `/goal` の利用可否。
- 実際のGPTモデルにデモを解かせた際の成績や所要時間。
- 任意の案件の業務上の正しさ。判定対象は、その案件のTASKとchecksで決まる。
- 利用者のWindows端末そのものでの実行結果。GitHub ActionsのWindowsランナーによる検証とは区別する。

再確認コマンド（リポジトリルート）：

```text
uv run --locked python -m unittest discover -s tests -v
```
