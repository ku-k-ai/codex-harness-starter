# Codex Harness Starter

**会社・自宅のCodexで「目標 → 実装 → 検証 → 判断」を試すための、日本語テンプレートと小さな検証ツール。**

前提は **ネイティブWindows・PowerShell・uv・Codex**。案件の目的と合格条件を固定し、Codexに実装方法を考えさせます。目標の継続は対応版Codexの `/goal` を使います。

- Python **3.9以降・標準ライブラリのみ**。環境はuvで管理し、Pythonの実行は `uv run python` に統一する。
- `pyproject.toml` と `uv.lock` を同梱。`uv sync` で準備でき、仮想環境の手動activateは不要。
- 既存のAGENTS.mdやCodex設定を勝手に上書きしない。
- 検証したソースと設定の指紋を保存し、変更後の古い結果を `stale` と表示する。
- チェック成功と、業務要件の完了は区別する。

## まず試す：お題付きデモ

このデモは「レコードを再取り込みしても重複しないようにする」という小さい修正です。**最初の検証が失敗するのは正常**です。

```powershell
git clone https://github.com/ku-k-ai/codex-harness-starter.git
cd codex-harness-starter
uv sync
uv run python tools/harness.py run examples/dedupe-demo --label baseline
```

取得済みなら、このリポジトリで `git pull` → `uv sync` を実行します。

次に、デモのディレクトリでCodexを起動します。

```powershell
cd examples/dedupe-demo
codex
```

Codexに次の1行を渡してください。

```text
/goal .harness/TASK.md を読み、受入条件を満たすように src/merge.py を修正してください。Pythonは uv run python で実行し、TASKにあるコマンドで変更前後を検証してください。tests/ と合格基準は変更せず、最終結果と変更理由を短く示してください。
```

`/goal` が使えない版では、先頭の `/goal` を除いた同じ依頼を使います。この場合、標準の自動継続が有効になるわけではありません。途中終了時は [再開用の指示](prompts/RESUME.md) を使います。

完了後、デモのディレクトリで確認します。

```powershell
uv run python ../../tools/harness.py run . --label candidate
uv run python ../../tools/harness.py status .
```

受入テスト9件の成功に加え、TASKにある計算量の説明と記録も確認します。`PASS` だけで業務完了とはしません。

## 実際の仕事で使う

### 1. 対象プロジェクトに案件用ファイルを作る

**作業したいプロジェクトのルートへ移動してから**実行します。以下はスターターを `C:\tools\codex-harness-starter` に置いた例です。

```powershell
cd "C:\work\my-project"
uv run python "C:\tools\codex-harness-starter\tools\harness.py" init .
```

2つのパスを実際の場所に置き換えます。**対象側のuv環境を使うため、実案件のコマンドは対象プロジェクト内で実行します。** `uv run python` の `python` は省略しません。作られるのは次のファイルです。

| 対象プロジェクト内のファイル | 役割 |
| --- | --- |
| `.harness/TASK.md` | 今回の目的、固定条件、完了条件、検証、予算 |
| `.harness/STATE.md` | 現在地、未達条件、次の一手 |
| `.harness/EXPERIMENTS.md` | 仮説・実験結果・採否の短い記録 |
| `.harness/checks.json` | 実行する検証コマンドと、変更検知するパス |
| `.harness/AGENTS.fragment.md` | 必要な部分だけ既存規約へ統合する共通原則 |

再実行しても既存ファイルを上書きしません。既存の `.gitignore` に `.harness/runs/` を追加し、検証出力を不用意にコミットしないようにしてください。導入先に機密情報を含む場合、案件ファイルもその環境の中で管理します。

### 2. お題と判定方法を埋める

[START.md](prompts/START.md) を対象プロジェクトのCodexに渡し、今回の依頼とスターターの絶対パスを埋めます。Codexがリポジトリを読んでTASKとchecksを具体化し、そのまま実装・検証まで進めます。重要な業務判断や正解が不足するときは、その不足を明示します。

**自分で決める必要があるのは、何を達成したいか、何を変えてはいけないか、どの結果なら合格か。** 実装の細かい順序まで指定する必要はありません。

`checks.json` は初期状態では検証未設定です。空欄のままでは実行できません。例えばPythonのテストなら次のようにします。

```json
{
  "schema_version": 1,
  "fingerprint_paths": ["src", "tests", ".harness/TASK.md"],
  "checks": [
    {
      "id": "unit-tests",
      "argv": ["{python}", "-m", "unittest", "discover", "-s", "tests", "-v"],
      "timeout_seconds": 120
    }
  ]
}
```

- `argv` はコマンドと引数の配列。`{python}` は、`uv run python` で選ばれた対象プロジェクトのPythonに置き換わります。
- 実行場所は対象プロジェクトのルート。シェル文字列は実行しません。
- `fingerprint_paths` は、結果に関係するソース・評価データ・テスト・仕様を列挙します。対象外のファイルの変更までは検出できません。
- 依存関係が結果に影響する案件では、存在する `pyproject.toml` と `uv.lock` も `fingerprint_paths` に含めます。
- コマンドは現在の利用者の権限で動きます。このツール自体に隔離機能はありません。既存の会社・Codexの権限設定を維持します。
- Node等のコマンドは、そのプロジェクトで通常使っているものを指定します。Windowsの `.cmd` 呼び出し等が必要なら明示した実行ファイルと引数を設定してください。

### 3. 条件を手で埋めた場合・設定済みの案件を動かす場合

この場合は [RUN.md](prompts/RUN.md) の `/goal` を使います。STARTで既に実装まで進んでいるなら、RUNを重ねて送る必要はありません。検証コマンドのharness.pyの場所は、TASKに実際の絶対パスで記入しておくと移動しても迷いません。

```powershell
cd "C:\work\my-project"
uv run python "C:\tools\codex-harness-starter\tools\harness.py" run . --label baseline
uv run python "C:\tools\codex-harness-starter\tools\harness.py" run . --label candidate
uv run python "C:\tools\codex-harness-starter\tools\harness.py" status .
```

これは例のパスです。クローンした場所と対象プロジェクトの場所に置き換えます。

## 途中で使う指示

| 状況 | 渡すファイル |
| --- | --- |
| お題を具体化して最初の準備をする | [START.md](prompts/START.md) |
| 実装と検証を進める | [RUN.md](prompts/RUN.md) |
| 同じ修正が続き、改善も新情報もない | [REVIEW.md](prompts/REVIEW.md) |
| 中断や別セッションから続ける | [RESUME.md](prompts/RESUME.md) |
| 最終版を検証して報告する | [FINISH.md](prompts/FINISH.md) |

監査は必要なときだけ、独立した会話で行います。仕様・観測事実は渡し、主担当の説明を最初から正解として渡さないようにします。監査役は直接同じファイルを編集しません。

## 検証ツールの結果

`run` は `.harness/runs/` にJSONレポートとコマンドの出力を保存します。

- 正常に完了した検証、失敗、タイムアウト、起動失敗を区別する。
- `status` は最新の結果を読み、ソースや検証設定の変更があれば古い結果として扱う。
- 最新の実行が中断・実行中でレポート未完成なら `incomplete` とし、過去の成功結果へ戻さない。
- 終了コード：`0` は自動検証成功、`1` は失敗／古い結果／結果なし、`2` は設定等のエラー。
- 時間上限は各検証コマンドのタイムアウト。TASKに書くCodex全体の時間・費用上限は、別途管理する作業条件であり、このツールが強制するものではない。
- 指定コマンドの終了コードを検証結果とします。APIの品質や業務要件は、その要件を確認する検証コマンド／人の確認が必要です。

最良の実装はGitで保持します。最後の1回の測定値が高くなるまで繰り返す運用はしません。

## 会社と自宅で共通にするもの

共通化するのは作業原則・テンプレート・検証の手順です。Azure／ChatGPTの認証、モデル名、接続先、社内データ、端末ごとのパスは各環境に持たせます。このスターターはCodexの `config.toml` を変更しません。

会社の特許業務への当てはめ例は [PATENT_TASKS.md](docs/PATENT_TASKS.md) を参照してください。未記入の基準を勝手に数値で埋めないようにしています。

## スターター自体の検証

```powershell
uv run --locked python -m unittest discover -s tests -v
```

これはスターターを開発・変更する場合の検証です。デモの受入テストは初期状態で失敗します。GitHub Actionsでもuvを使い、WindowsとUbuntu、Python 3.9と3.12で検証します。実際の実行状況はリポジトリのActionsで確認してください。

## 設計の根拠と範囲

- [設計方針と導入順](docs/DESIGN.md)
- [出典・公式機能の確認範囲](docs/SOURCES.md)
- [このスターターの検証記録](docs/VALIDATION.md)

このリポジトリはCodexを置き換えるものではありません。無条件に継続するフック、独自の常駐エージェント、API呼び出し、課金やモデルの自動設定は含めていません。
