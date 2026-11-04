# デモの作業範囲

このディレクトリでデモを解く場合は .harness/TASK.md を読む。
修正対象は src/merge.py。tests/ と .harness/checks.json は合格基準として固定する。
変更前に検証し、修正後に同じ検証を実行する。テストを書き換えて合格させない。
実験結果と未達条件を .harness/STATE.md と .harness/EXPERIMENTS.md に短く残す。
合格条件を満たしたら終了し、追加機能を作り始めない。
