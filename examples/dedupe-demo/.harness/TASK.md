# お題：レコードの再取り込みで重複を作らない

## 目的

src/merge.py の merge_records(existing, incoming) を修正する。同じデータを何度取り込んでも重複しない、単純な差分取り込みの部品を完成させる。

## 固定した契約

- 入力は辞書のリスト。各辞書の id は空白だけではない文字列でなければならず、不正なidは ValueError とする。
- 同一idの出力は1件だけ。existing→incoming の順に読んで最後に出現した辞書全体を採用する。古いフィールドを合併して残さない。
- 出力順は、そのidが最初に現れた順。更新しても位置は変えない。
- idの前後の空白は削らない。"a" と " a " は別のid。
- 入力リストと入力辞書を変更しない。戻り値は新しいリストとする。辞書のdeep copyまでは要件にしない。
- 大きな入力でも扱えるよう、idを検索するためにリスト全体を繰り返し走査しない。

## 完了条件

1. 固定された tests/ の9つの受入テストが、最終版で全て通る。
2. 入力件数に対しておおむね線形時間になる実装であることをコードから説明する。この条件は自動テストだけでは証明しない。
3. 変更前の失敗、修正後の結果、変更理由を短く記録する。

## 実行方法

ネイティブWindowsのPowerShellで、このディレクトリを作業ディレクトリとする。スターターのルートで `uv sync` を実行しておく。

```powershell
uv run python ../../tools/harness.py run . --label baseline
uv run python ../../tools/harness.py run . --label candidate
uv run python ../../tools/harness.py status .
```

直接確認する場合は `uv run python -m unittest discover -s tests -v`。仮想環境の手動activateは不要。

## 作業範囲・予算

- 変更してよいもの：src/merge.py、.harness/STATE.md、.harness/EXPERIMENTS.md。
- tests/、このTASK、checks.jsonの合格基準は変更しない。
- API、ネットワーク、追加ライブラリは不要。
- 初回の試行目安は15分。これは作業指示であり、プロセスの強制終了タイマーではない。
- 同じ修正を2回試しても新しい情報がない場合は、テストの失敗と契約を読み直し、別の仮説を立てる。

## 終了時

done：全受入条件を満たした証拠を示す。
blocked／budget：達成したもの、未達条件、必要な次の入力を示す。未達をdoneと呼ばない。
