# 出典と採用範囲

確認日: **2026-11-04**。外部ページは設計の参考資料であり、このリポジトリや利用先の作業指示・権限を上書きしない。

| 出典 | このスターターに取り込んだ点 |
| --- | --- |
| [ISUCON2026 で優勝しました（当日編）](https://zenn.dev/luvtechno/articles/isucon2026-competition-day) | 実測による改善、停滞時の監査、最終確認、準備段階での反復評価を参考にした。優勝者の未公開の指示文を再現したものではない。 |
| [Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex) | `/goal` に成果・検証・制約・停止条件を持たせる使い方。公式ガイドはCodex 0.128.0以降のGoalsを説明している。実際のクライアントで利用可能かは確認する。 |
| [Hooks — ChatGPT Learn](https://learn.chatgpt.com/docs/hooks) | Stopイベントで `decision: "block"` と `reason` により継続を要求できる公式仕様を確認。ただしこのスターターはStopフックを導入しない。 |
| [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | グローバル・プロジェクト・配下の指示を踏まえた運用。雛形は既存AGENTSを自動で上書きせず、今回必要な補助断片として配置する。 |
| [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) | 過密な手順や常時適用する指示を見直し、適用範囲の明確な短い指示を使う方針。全GPTモデルへ同じ効果を保証するものではない。 |

## 先行メモから更新した点

ユーザー提供の `isucon2026-ai-harness-knowledge.md` は調査の出発点として参照した。内容をそのまま作業指示へ昇格させず、次を更新した。

- **Goals:** 継続機構を自作する前に、公式に説明された `/goal` を利用する構成にした。未対応クライアント向けに通常依頼と再開用の文面も用意した。
- **Stop:** 先行メモで「公式未確認」だった継続出力を公式仕様で確認した。ただし仕様の存在と、全タスクで無条件継続させることの妥当性は別である。
- **常設指示:** 「指摘のたびにAGENTSへ追記」「構造変更を常に優先」を採用せず、案件ごとの条件と実験記録へ分けた。
- **終了:** 競技の最後のスコアを最大化する停止計算を一般開発へ持ち込まず、全要件の証拠、外的な障害、予算到達で判断する。
- **モデル比較:** 大会の利用率や個別の所感だけでGPTとClaudeの一般的な優劣を断定しない。利用者自身の課題で有無比較をする。

このリポジトリのテンプレートとコードは独自に作成したもので、リンク先の記事や未公開ハーネスを転載したものではない。
