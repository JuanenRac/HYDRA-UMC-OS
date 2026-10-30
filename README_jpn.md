<!-- =============================================================================
HYDRA-UMC-OS - Platform layer for a CM5 node on Raspberry Pi OS
Copyright (C) JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS banner" width="100%">
</p>

# 🖥️ HYDRA-UMC-OS

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | 🇯🇵 <b>日本語</b> | <a href="README_por.md">🇵🇹 Português</a></p>

### Raspberry Pi OS 上の HYDRA-UMC ノードの再現可能なプラットフォーム層

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Platform">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Services">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Stack">
  <img src="https://img.shields.io/badge/Tests-20%20passing-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Version-0.5.4-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-functional-0F6CBD.svg" alt="Maturity">
</p>

---

> **安全性とセキュリティの現状:** このエコシステムは認証された安全システムではありません。ハードウェアの E-STOP 経路、ファームウェアが強制する制限やインターロック、検証済みの動作コマンドはまだありません。ファームウェアイメージは CRC-32 と Ed25519 署名で検査し、リリースビルドは公開済みの開発用鍵を拒否します(リレーの先のツールヘッドと拡張ボードは引き続き URTC のブートローダーを使い、署名ではなく共有鍵の HMAC-SHA256 を使います)。TLS と相互 TLS は任意で、既定では無効です。独自基板はまだ実装も試験もされていません。ここに書かれた内容を人の安全のために頼る前に、[セキュリティベースライン](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)と[脅威モデル](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)をお読みください。

---

## 📋 ひと目で

| | |
|---|---|
| バージョン | `0.5.4` |
| 成熟度 | 機能する |
| テスト | 20 (`python -m unittest discover -s agent/tests`) |
| 技術 | Raspberry Pi OS ARM64 / Debian/apt / systemd / udev / NetworkManager |
| 対象 | HYDRA-UMC セルの Raspberry Pi CM5 |
| 実機での確認 | ベンチ環境で動作：上の正直さの確認に、どの部分が実機で動いたかが書かれています |

**移動：** [概要](#-概要) · [アーキテクチャ](#-アーキテクチャ) · [クイックスタート](#-クイックスタート) · [テスト](#-テスト) · [リポジトリの構成](#-リポジトリの構成) · [関連プロジェクト](#-関連プロジェクト)

## 🚦 プロジェクトの状況

各行はこのリポジトリの一部分で、信号は今日どこまで進んでいるかを示します。計画ではなく、リポジトリが示せるもの（テスト、ビルド、実行）に基づいて書かれています。

🟢 完了・検証済み · 🟡 動作する（既知の制限あり） · 🟠 一部のみ、または未検証 · 🔴 未実装または動作しない

| 領域 | 状態 | ここでの意味 |
|---|---|---|
| ソフトウェア | 🟡 | 主な目的では動作します。足りない点は上の正直さの確認に書かれています |
| テスト | 🟢 | 自動テスト 20 件。変更のたびに実行されます |
| 実機 | 🟡 | ベンチ環境で動作：上の正直さの確認に、どの部分が実機で動いたかが書かれています |
| ドキュメント | 🟢 | 8 言語の README。変更のたびにマニフェストと照合されます |

## 🎯 概要

HYDRA-UMC-OS は、HYDRA-UMC CM5 ノードにインストール可能なプラットフォーム層です。
Raspberry Pi OS ARM64 上に構築されています。 Linux に代わるものではありません。
Raspberry Pi カーネル、systemd、NetworkManager、libcamera、またはベンダー SDK。

その責任は、再現可能な HYDRA-UMC デバイス プロファイルを提供することです。
構成、サービス ライフサイクル、ローカル ID、診断、ビジュアル
ブランド化、および HYDRA-UMC コンポーネントの更新の調整。

**正直な現状確認 - 実際に今動くもの:** 読み取り専用のデバイスエージェント（`agent/src/hydra_umc_os/agent.py`: `DeviceDescriptor`/`HealthReport`、温度・ストレージ・ネットワークのチェック、設定プロファイルの読み込み）は本物であり、テスト済みです（13件のユニットテスト、`agent/tests/test_agent.py`、`python -m unittest discover`）。`provisioning/preflight_cm5.py` は、2回実行して出力を比較する実際のテスト（`tools/verify_preflight_idempotent.py`）により冪等かつ副作用がないことが検証されており、さらに5件の実際のネガティブパスチェック（`tools/verify_preflight_negative.py`）もあります。`provisioning/rollback.py` のバックアップ/復元メカニズムは、実際の部分的失敗シナリオを含む8件の実際のチェックで検証されています（`tools/verify_rollback.py`）。`provisioning/wifi_provision.py` のAPモード・フォールバック状態機械は、偽のNetworkManagerに対する46件の実際のチェックで検証されており、その中には実際のループバックソケット上での本物のエンドツーエンドHTTPラウンドトリップも含まれます（`tools/verify_wifi_provision.py`）- これら3つはいずれも検証にroot権限や物理的なCM5を必要としません。これまでに検証されていないもの: 実機のCM5ハードウェアそのものです。`image-builder/` は現時点ではドキュメントのみです（再現性に関するメモのREADMEで、まだイメージ組み立てコードはありません）。`packages/debian/` には `hydra-umc-platform-base` パッケージのメンテナースクリプトと著作権ファイルがあり、`tools/build_deb.py` がそれを実際の `.deb` にビルドし（純粋な Python で dpkg 不要、毎回同じバイト列）、`tools/verify_deb_package.py` が読み戻して検証します。実際の CM5 にはまだインストールされていません。これまでに実際に出荷されたものの詳細は `CHANGELOG.md` を、ここで検証済みのものと物理ハードウェアが依然として必要なものとの正確な境界線は `docs/CM5_SOFTWARE_READINESS.md` を参照してください。

## 🧩 HYDRA-UMC での役割

**HYDRA-UMC-OS** は CM5 ノードのプラットフォーム層です。Raspberry Pi OS の上で、設定、サービスのライフサイクル、ローカルな識別、診断、見た目、調整された更新を提供し、読み取り専用のデバイスエージェントを備えます。Linux、systemd、ベンダーの SDK を置き換えるものではなく、イメージは `HYDRA-UMC-OS-REBUILDER` が作ります。

## 🏛️ アーキテクチャ

<p align="center">
  <img src="images/architecture.svg" alt="HYDRA-UMC-OS architecture" width="100%">
</p>

## 🚀 クイックスタート

エージェントのテストに必要なのは Python 3.11 以上だけです。イメージ自体は `HYDRA-UMC-OS-REBUILDER` が作ります。

```bash
PYTHONPATH=agent/src python3 -m unittest discover -s agent/tests
./build-test.sh  # non-mutating build check (build-test.bat on Windows)
```

## 🧪 テスト

`python -m unittest discover -s agent/tests` で自動テスト 20 件を実行します。 ハードウェアも、このマシンの外にあるものも必要ありません。

CI は `HYDRA_UMC_CI=1 python tools/ci_validate.py` を実行し、マニフェスト、文書、8 つの README、図を検査します。

## 🏗️ ビルドとリリース

リリースビルドの前に、バージョンを変更しないビルドチェックを使用してください。

| 操作 | Windows | Linux / macOS |
|---|---|---|
| ビルドチェック（バージョンと CHANGELOG を変更しない） | `build-test.bat` | `./build-test.sh` |
| 実行 / 開発（提供されている場合） | `run*.bat` または `dev*.bat` | `./run*.sh` または `./dev*.sh` |

`build-test.bat` と `build-test.sh` は、`hydra-umc.project.json` をインクリメントせず、`CHANGELOG.md` も変更せずにプロジェクトのスタックをコンパイルまたは検証します。通常のコンパイラ出力だけが作成される場合があります。既存の `build*.bat`、`build*.sh`、`run*`、`dev*` は、各プロジェクト固有のバージョン化または実行時の動作を維持します。その動作が必要な場合はそれらを使用してください。

## 📂 リポジトリの構成

<p align="center">
  <img src="images/repository-structure.svg" alt="Repository structure of HYDRA-UMC-OS" width="100%">
</p>

<details>
<summary>ツリーのテキスト版</summary>

```text
HYDRA-UMC-OS/
├── docs/                      アーキテクチャ、インストール、サービス、およびアップデートの仕様。
├── image-builder/             公式の Raspberry Pi OS イメージアセンブリの境界と再現性に関するメモ。
├── packages/                  Debian パッケージ `hydra-umc-platform-base` のメンテナースクリプトと著作権（`tools/build_deb.py` でビルド）。
├── agent/                     単体テストを備えた読み取り専用の Python デバイス記述子とヘルスエージェント。
├── systemd/                   強化された `hydra-umc-agent.service` と `hydra-umc-wifi-provision.service` のライフサイクルユニット。
├── config/                    デフォルトのスキーマと非シークレット構成。
├── provisioning/              CM5 のインストーラー (サービスごとに1つ)、初回起動、診断、復旧、設定のバックアップと復元、ファイアウォール、MQTT 用 TLS、キオスクとスプラッシュ画面、polkit ルール、インストールの検査。
├── tools/                     パッケージとリリースのツール (`build_deb.py`、`package_component.py`)、プロビジョニングスクリプトの `verify_*.py` 検査、共有の CI 検査。
├── .github/                   CI ワークフローと Issue テンプレート
├── images/                    バナーと README の図
├── CHANGELOG.md               各バージョンの変更点
├── build-test.sh              変更を伴わないビルド確認
├── build.sh                   ビルドと検査。バージョンは変更しない
├── bump_manifest_version.py   マニフェストのバージョンを同期
├── bump_version.py            明示的なバージョン更新
├── hydra-umc.project.json     マニフェスト：バージョン、成熟度、ファミリー
├── run.sh                     プログラムを起動
└── test.sh                    テストを実行
```

</details>

## 🗺️ ロードマップと既知の制限

**現時点の既知の制限**

**現時点の既知の制限**

### ステータス

基本エージェント、検証済みの非機密構成、強化された systemd
ユニットとホスト側のテストが実装されます。エージェントは意図的に
読み取り専用: 製品イメージ アセンブリと CM5 ハードウェア検証は残ります
個別のリリースゲート。

インストールのプリフライト（`provisioning/preflight_cm5.py`）は、実際のテストによって冪等性があり副作用がないことが証明されている——2回連続で実行してもバイト単位で同一の出力が得られ、このリポジトリ内のファイルには一切触れない——そして、実際のホスト非依存なバックアップ/ロールバック機構（`provisioning/rollback.py`）が、`install_local_agent.sh` が実行のたびに無条件で上書きする唯一のシステムファイルを保護する。どちらも root 権限や CM5 なしで検証されている——`tools/verify_preflight_idempotent.py` と `tools/verify_rollback.py` を参照。

**WiFi 初回接続プロビジョニングも実際に動作する**（`provisioning/wifi_provision.py` / `hydra-umc-wifi-provision.service`）——まだ既知のネットワークを持たないヘッドレス CM5 のための、実際の NetworkManager AP モードのフォールバック。実際のホットスポット（`nmcli device wifi hotspot`）を起動し、オペレーターの携帯電話やノート PC がそれに接続して、小さなローカル HTTP フォームを通じて実際のターゲット SSID/パスワードを送信できるようにする。成功時には AP を停止して実際のネットワークに参加し、失敗時には AP を復元してデバイスが孤立しないようにする。この状態機械は、疑似的な NetworkManager に対して完全に単体テストされており、実際のループバックソケット上での実際のエンドツーエンド HTTP 往復も含まれる——`tools/verify_wifi_provision.py` を参照。`install_cm5_base.sh` によってインストールされるが、実際に必要とするデバイスでのみ動かすべきであるため、意図的に自動有効化はされない——アクセスポイントのパスワードと一度限りのセットアップコードは、デバイスごとに初回起動時に生成され、ジャーナルから一度だけ読み取る。`provisioning/CM5_DEPLOYMENT_SEQUENCE.md` のセクション 3 を参照。

**シークレットはデバイスごとに生成され、テンプレートから流用されることはありません。** `install_server.sh` と `install_voice_ui.sh` は、env ファイルがなければ例から作成し、例の値（`JWT_SECRET`、最初の管理者パスワード、音声リレートークン）をすべてこのデバイス固有のランダム値に置き換えます（`provisioning/generate_secrets.py`。運用者がすでに選んだ値は残り、管理者パスワードは一度だけ表示されます）。例の値や短すぎるシークレットが残っていれば先へ進みません。`preflight_cm5.py` は、まだそれらを含む `/etc/hydra-umc/*.env` を拒否します。`install_industrial_gateway.sh` はスタックのシークレットを `/etc/hydra-umc/gateway.env` に書きます(root のみ、ユーザーのチェックアウトの外、compose が `--env-file` で読み込む。以前のバージョンがチェックアウトに残した `.env` はそこへ移動されます)（`provisioning/gateway_env.py`：ゲートウェイのシークレットと、マシンブリッジごとの MQTT 認証情報と ACL ルール）。Wi-Fi セットアップネットワークはソースコード内にパスワードを持たなくなりました。各デバイスが初回起動時に自分のパスワードと使い捨てのセットアップコードを生成し（ジャーナルで一度だけ読み取り、ラベルに書く）、フォームはコードを要求し（5 回間違えると 1 分間ロック）、セットアップネットワークは起動のたびに 30 分間だけ開き、フォームは大きすぎるリクエストを拒否します。`tools/verify_generate_secrets.py`、`tools/verify_gateway_env.py`、`tools/verify_wifi_provision.py` で検証しています。 ホスト名とセットアップ用ネットワーク名の末尾にも、デバイスから取った 6 文字（Raspberry Pi のシリアル番号、なければ MAC アドレス）が付くため、同じイメージから書き込んだ 2 台が同じ名前を共有することはなくなりました（`provisioning/device_identity.py`、`tools/verify_device_identity.py` で検証）。`HYDRA_UMC_DEVICE_SUFFIX=off` で固定名に戻せ、ご自身で決めた名前は変更されません。

**署名鍵はインストーラーが配布します。** Voice UI が確認結果に署名する鍵(`HYDRA_UMC_VOICE_UI_RESULT_KEY`)は、`install_server.sh` と `install_voice_ui.sh` のうち先に実行された方がデバイスごとに 1 回だけ生成し、`/etc/hydra-umc/server.env` と `/etc/hydra-umc/voice-ui.env` の両方に書き込みます(古いテンプレートのファイルには行が追加されます)。あわせてサーバー用に `HYDRA_UMC_VOICE_CONFIRM_REQUIRE_SIGNATURE=1`、Voice UI 用に `HYDRA_UMC_VOICE_UI_REQUIRE_SUBJECT=1` も設定されます(`generate_secrets.py --ensure`。運用者がすでに持っている行は、どんな値でも変更されません)。`install_local_technician.sh` は各ツールの結果に署名する鍵を `/etc/hydra-umc-local-technician/result.key` に作り(`provisioning/make_result_key.py`:ランダムな 16 進 64 文字、最初のバイトから権限 0600、root のみ、表示せず、存在すれば置き換えず、シンボリックリンクはたどらない)、設定ファイルをそれに向けます。`--no-signing`(または `HYDRA_UMC_LOCAL_TECHNICIAN_SIGNING=off`)でこの行は書かれません。鍵がイメージやリポジトリに入ることはなく、2 台のデバイスが同じ鍵を共有することもありません。`tools/verify_result_keys.py` で検証済みです。

**監査ジャーナル(既定は有効)。** `install_local_technician.sh` は技術者の追記専用・ハッシュ連鎖の監査ジャーナルを、`install_node_healing.sh` は監視役のジャーナルを有効にします(どちらも 5 MiB で切り替わり、5 ファイルを保持)。技術者に何を頼んだか、監視役がノードについて何を判断したかは障害後に重要な証拠なので、インストーラーは設定を有効な状態で文書化された設定ファイル(`/etc/hydra-umc-local-technician/local-technician.env`、`/etc/hydra-umc-node-healing/journal.env`)に書きます。`--no-audit` / `--no-journal`(または `HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT=off`、`HYDRA_UMC_NODE_HEALING_JOURNAL=off`)はジャーナルを無効のままにし、有効な行をコメントアウトします。記録済みの内容は決して削除せず、既存の設定ファイルは上書きしません。`tools/verify_optional_journals.py` がオプションと名前を静的に確認します。実機の CM5 へのインストールはまだ行われていません。

**Go サービス用に固定した Go。** ジョブディスパッチャー、ノード監視役、テレメトリコレクターはデバイス上でビルドされ、その `go.mod` は Debian アーカイブの `golang-go` より新しい Go を求めるため、それではビルドできませんでした。インストーラーは `provisioning/go_toolchain.sh` を読み込みます。go.dev の公式リリースを、固定した SHA-256 と照合してから `/usr/local/go-<バージョン>` に展開します(システムの Go には手を触れません)。`tools/verify_go_toolchain.py` は、ダウンロードを模したもの(正しいアーカイブ、壊れたもの、インストール済みのもの)でヘルパーを実行し、固定バージョンを兄弟プロジェクトの `go.mod` と比べます。実機の CM5 へのインストールはまだ行われていません。

**サービスレジストリは 1 つ。** 各サービスのポート、ヘルスルート、systemd ユニットは `provisioning/ports.yaml`(プロジェクトのマニフェストから生成される SDK の `contracts/ports.yaml` のコピー)から取得します。サービスの各インストーラーは、起動後にどこを確認すればよいかを表示して終わり、`verify_cm5_runtime.sh --with-services` は実行中の各サービスのヘルスルートを確認します(読み取り専用。動いていないものはスキップ)。`tools/verify_service_registry.py` が、ヘルパー、インストーラー、実行時チェックをスタブで検証します。実機の CM5 へのインストールはまだ行われていません。

### 最初のマイルストーン

完了済み。上記のステータスセクションの通り(実際のコード、実際の
テスト、実機の CM5 ハードウェアに対してはまだ検証されていない):

1. ✅ CM5 用の Raspberry Pi OS ARM64 プロファイルを構築します。
2. ✅ `hydra-umc-platform-base` と `hydra-umc-agent` をインストールします。
3. ✅ CM5 インターフェイスを検出し、`DeviceDescriptor` と `HealthReport` を報告します。
4. ✅ systemd を介して有効なサービスのみを開始します。
5. ✅ ローカルで READY、DEGRADED、または FAULT を表示します。

## 🌍 言語

この README とリポジトリの文書は、英語・スペイン語・ドイツ語・フランス語・イタリア語・日本語・中国語・ポルトガル語（ポルトガル）の 8 言語で提供されています。8 つのファイルは同時に書かれ、同じ節と同じリンクを持つことを CI が確認します。 このリポジトリには独自の画面もメッセージカタログもないため、翻訳すべきインターフェース文字列はありません。

## 🔗 関連プロジェクト

本プロジェクトは、同じ作者(JuanenRac / Electro Hobby 3D)による HYDRA-UMC ロボティクスエコシステムの一部です。リクエストが実はこの中のどれかについてのものである可能性があるため、知っておく価値があります。

**子プロジェクト**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — すべてのブリッジが自身のコマンドを検証する共有 JSON-Schema 契約とソフトウェアのジョブゲート境界(認証済みの安全機能ではない)。本 OS 自身のデバイスエージェントが使用する、バージョン管理された契約・シンクライアント・適合性フィクスチャ。
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — エコシステムの最新バージョンをプリロードし、Raspberry Pi Imager方式の初回起動設定を備えた、CM5向けの書き込み可能なこのOSのイメージを構築するWindows/Linuxデスクトップツール。

**直接関連**
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — ロボットアームのマザーボードの設計——CM5 ホスト + デュアルコア STM32H745、CAN-OTA/SPI-OTA 経由で最大 8 本のツールアームを統括することを目指す(ファームウェアは初期段階で、実装済みの基板はまだない)。本 OS 層が設定・監督する CM5/MCU ハードウェア・ファームウェアプラットフォーム。
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — すべての制御クライアントが実際に通信する、本物のヘッドレスバックエンド(REST/WebSocket)。本ノードの管理対象統合のための認証済みサービス境界。
- **[URTC](https://github.com/JuanenRac/URTC)** — 物理的な Universal Robot Tool Controller 基板向けファームウェア、CAN バス経由の 25 以上のツールプロファイル。明示的でバージョン管理されたアダプター経由で統合される独立したツールコントローラープラットフォーム。
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — このエコシステム内のすべてのリポジトリを検出・クローン・更新する、管理用デスクトップツール。そのアーティファクトレジストリ、互換性メタデータ、調整された更新ワークフロー。
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — 外部マシン用コネクタのための宣言的アダプターマニフェストのレジストリとバリデーター。SDK 自身の契約という発想を外部マシンにまで拡張し、産業用ゲートウェイ系のプロジェクトを置き換えることはありません。
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — 保守インシデントコーディネーター: 低権限のエッジ役割がサニタイズされたインベントリ/ヘルスのスナップショットを収集し、コントロールプレーン役割がそれを読み取り専用でレンダリングして AI プロバイダーに診断の提案を依頼します - パッチを適用することも、何かをデプロイすることも決してありません。
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — 再現可能な開発ホスト（Raspberry Pi 5 / CM5）。エコシステムのソースコードを保管し、永続キューのもとで境界の明確なビルド/テストタスクを実行する。運用中の CM5 とは明確に異なる、開発専用の役割。

**エコシステムの他のプロジェクト**

*コアバックエンド&クライアント*
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — リアルタイムのマルチロボット 3D 可視化を備えたウェブ制御ダッシュボード。
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — 複数のサーバーを同時に扱えるデスクトップ(PySide6)スウォームコマンドセンター、スタンドアロン実行ファイルとしてパッケージ化。
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — 生体認証ログインとペアリングされた Wear OS コンパニオンを備えたネイティブ Android 制御アプリ。
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — リアルタイム WebSocket 同期を備えた iOS/iPadOS 制御アプリ(Flutter)。
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — 本体搭載の 7 インチ DSI タッチスクリーン向けネイティブタッチ UI、CM5 自体に組み込み。
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — 完成したモデルを STUDIO 自身のカタログへ送信するデスクトップ用グラフィカル URDF 作成/編集ツール。
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — HYDRA-UMC-EDITOR-URDF も編集する同じモデルカタログ内で、実在するパーツを変換/置換/削除/追加するデスクトップ STL モデルエディタ。
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — VDA 5050 MQTT パブリッシャーによる AGV/AMR フリートの調整境界(エミュレートしたフリートに対してのみテスト済み)。
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — GRBL ステータス/制御バイトへのアクセスを持つ、CNC セルの高レベルコーディネーター(エミュレーターに対してのみテスト済み)。
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — Boston Dynamics Spot コマンド送信機能を持つ、脚型/ヒューマノイドドロイドの調整境界(エミュレーターに対してのみテスト済み)。
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — キー/筐体/インターロックの GPIO 信号 3 系統を読み取るレーザーセルのコーディネーター(模擬チップに対してのみテスト済み。レーザーの武装や発射はできない)。
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — OpenPnP ピックアンドプレースの基板フローを安全に統括する高レベルコーディネーター。
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — 実際にゲート制御されたジョブコマンドを持つ、Moonraker/Klipper 3D プリンター向けの安全な調整境界。
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — 遅延インポートの rclpy ROS 2 トランスポートを持つコーディネーター(ROS 2 環境ではまだ実行していない)。
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — MAVLink コマンド送信機能を持つ、カメラ搭載 UAV の調整境界(エミュレーターに対してのみテスト済み)。

*URTC ツールプラットフォーム*
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — URTC 基板用のデスクトップ GUI 書き込みツール、CAN-OTA およびフルチップ SWD/JTAG。
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — URTC 基板向けのデスクトップ CAN バスライブ診断ツール、ツールプロファイルごとに 1 パネル。
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — Web Serial API を使ったブラウザベースの URTC-TESTER の代替、ローカルインストール不要。
- **[URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY)** — URTC の CAN バスの前に置くゲートウェイ：許可する識別子のリスト、レート制限、セッション鍵。コンピューター上でテスト済みで、実際のバスではまだ試していません。

*ビジョン AI ノード(Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — Hailo-8 ビジョンパイプラインの統合ハブ、段階ごとの実際のハードウェア準備状況チェック付き。
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — Hailo アーキテクチャ/チェックサムによる安全読み込み検証を備えた、実際のコンパイル済みモデルレジストリ。
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — 実際の HailoRT 統合境界を持つ、実際の GStreamer パイプライン + MediaMTX 設定生成器。
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — ゾーン状態を条件に承認する Position-Based Visual Servoing 補正則。カメラによる姿勢推定はまだない。
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — ファイルから物体位置を受け取る、ゾーン侵入・キャリブレーション鮮度・E-STOP 要求の v0 ロジック。検出器は接続されておらず、物理 E-STOP もまだ配線されていない。

*コグニティブ AI ノード(Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — Hailo-10 コグニティブパイプライン(LLM/VLA/音声オーケストレーション)の統合ハブ。
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — Vision-Language-Action モデル向けの、実際のアクショントークンのエンコード/デコードと軌道生成。
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — 確認ゲート付きの限定的な Watch リレーを備えた、実際の音声フロントエンド(VAD + 意図解析)。
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — MCU エラーコードに対する、実際のルールベースのタスク分解と意味的エラー復旧。
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — このエコシステム自身の Markdown ドキュメントに対する、標準ライブラリのみの実際の TF-IDF 文書検索。
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — エコシステム自身のための、ローカルでポリシーゲート付きのAIメンテナンス技術者 — 観察、診断し、修正を提案する;最上位の2つのリスクレベルは意図的にまだ実装されていない。

*オーケストレーション&スウォーム*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — 実際の gRPC/Protobuf ヘルスレポート契約とミッションステートマシンを持つ統合ハブ。
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — 実際の HTTP API 上に構築された、優先度ベースの実際のジョブキュー(重複排除付き)。
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — リトライ/バックオフとアイデンティティ不一致検出を備えた、実際の gRPC ベースのフリートヘルスウォッチドッグ。
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — 実際の障害物/ワークスペース衝突検証を備えた、実際の RRT ベースの 3D 経路プランナー。
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — 複数セルの収束についてプロパティテストされた、実際の CRDT LWW-Element-Map 状態同期。

*デジタルツイン&シミュレーション*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — 実際のバージョン互換性同期契約を持つ、デジタルツインエンジンの統合ハブ。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — シミュレーションと実機の間にソフトウェアの衝突インターロックを備えたハードウェア・イン・ザ・ループのルーター(実機なしでテスト済み)。
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — 実際の URDF サブセットに対する、実際の順運動学と関節限界検証。
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — YOLO/COCO アノテーションのエクスポート機能を持つ、実際のプロシージャル 2D シーンジェネレーター。

*データ&分析*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — 実際の取り込み/クエリ HTTP API を備えた、実際の sqlite3 ベースの時系列ストア。
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — ドリフト監視を備えた、実際の FFT + 統計ベースラインによる異常検知器。
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — DATALAKE の履歴に対する実際の OEE/稼働率計算、再現可能な CSV エクスポート付き。
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — シーケンス重複排除機能を備えた、DATALAKE への実際の CAN/WebSocket 取り込みパイプライン。

*産業用ゲートウェイ*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — 実際のコマンド許可リスト/バックプレッシャー層を持つ、産業用プロトコルへ中継する統合ハブ。
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — 実際のバイナリプロトコルクライアントセッションで検証された、実際の OPC-UA アドレス空間。
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — クライアント単位のオプション認証とトピック ACL を備えた、実際の MQTT ブローカー。
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — 縮退モード出力を備えた、実際の MTConnect `/probe` および `/current` XML エンドポイント。

*補完ツール&エコシステム運用*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — 誠実な統計フォールバックを備えた、DATALAKE/ANOMALY-DETECTOR 上のスマートサマリーと異常ハイライトパネル。
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — 実際の安定した終了コード契約を持つフリート CLI、HYDRA-UMC-SERVER 自身の API の本物のライブクライアント。
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — 触覚アラートのパターンとペアリング済みスマートフォンへの音声リレーを備えた WearOS コンパニオンアプリ(物理的なウォッチではまだ実行していない)。
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — 実際の工具 ID デコードと Smart Idle 予熱ロジックを備えた、基板搭載ラック用ファームウェア。
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — サーマル/RGB 検査ツールヘッド向けの、ファームウェアと実際の Python ビジョンコンパニオン。

## 📚 ドキュメント

さらに読むには：

* **[`docs/AGENT_REFERENCE.md`](docs/AGENT_REFERENCE.md)** —— 読み取り専用の診断 CLI である `hydra-umc-agent` の実際のコマンド/出力リファレンス。
* **[`docs/INSTALLATION.md`](docs/INSTALLATION.md)** —— インストール設計:対象プラットフォームと想定されるインストール手順。
* **[`docs/CM5_PROVISIONING.md`](docs/CM5_PROVISIONING.md)** —— Raspberry Pi OS Lite を HYDRA-UMC-OS に変換する完全なガイド。
* **[`docs/CM5_WINDOWS_HOST_FLASHING.md`](docs/CM5_WINDOWS_HOST_FLASHING.md)** —— Windows ホストから CM5 に書き込むための検証済み手順。
* **[`docs/CM5_FIRST_BOOT_CHECKLIST.md`](docs/CM5_FIRST_BOOT_CHECKLIST.md)** —— CM5 の初回起動用の BASE プラットフォームチェックリスト。
* **[`docs/CM5_PACKAGE_MANIFEST.md`](docs/CM5_PACKAGE_MANIFEST.md)** —— デプロイフェーズごとの実際のパッケージ一覧。
* **[`docs/CM5_ECOSYSTEM_DEPLOYMENT.md`](docs/CM5_ECOSYSTEM_DEPLOYMENT.md)** —— CM5 上にエコシステムの残りをフェーズごとに展開する、各フェーズが個別にロールバック可能な計画。
* **[`docs/CM5_SOFTWARE_READINESS.md`](docs/CM5_SOFTWARE_READINESS.md)** —— 物理的な CM5 ハードウェアなしで何が検証済みか、その検証がどこで止まるか。
* **[`docs/SERVICE_MODEL.md`](docs/SERVICE_MODEL.md)** —— HYDRA-UMC サービスの実行方法:専用ユーザー、設定パス、依存/準備状態の順序。
* **[`docs/UPDATE_MODEL.md`](docs/UPDATE_MODEL.md)** —— OS、HYDRA-UMC パッケージ、Hailo ランタイム、MCU/URTC ファームウェアそれぞれの独立した更新チャネル。
* **[`docs/SDK_INTEGRATION_BOUNDARY.md`](docs/SDK_INTEGRATION_BOUNDARY.md)** —— このリポジトリが HYDRA-UMC-SDK の公開された契約をベンダリングせずに利用する方法。
* **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** —— 開発ルール:Raspberry Pi OS のネイティブインターフェースを優先し、必須のテスト順序に従う。
* **[`docs/HEADER_CONVENTION.md`](docs/HEADER_CONVENTION.md)** —— 新しいソース/ドキュメントファイル向けの著作権・ライセンスヘッダー規約。
* **[`provisioning/ssh_hardening.md`](provisioning/ssh_hardening.md)** —— CM5 の実際の SSH 強化手順(パスワード認証を無効化する前に鍵ログインを確認する)。
* [エコシステムのセキュリティ基準](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)
* [エコシステムの脅威モデル](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)
* [このリポジトリの変更履歴](CHANGELOG.md)
* [このリポジトリのライセンス](LICENSE.md)

## 🤝 コントリビュートとコミュニティ

* プルリクエストの前に `HYDRA_UMC_CI=1 py -3 tools/ci_validate.py`（または `HYDRA_UMC_CI=1 python3 tools/ci_validate.py`）を実行してください。`CI_VALIDATION=PASS` と表示される必要があります。この確認に `build.sh` や `build.bat` は使わないでください。ビルドは検査ではありません。
* 8 つの README は HYDRA-UMC-DOCS の 1 つのソースから書かれます。手で編集しないでください。ソースを変更し、`tools/make_readmes.py` で書き直します。
* 実行していないことを README に書かないでください。事実であれば「シミュレーションのみ」「実機では未確認」と書きます。
* [CONTRIBUTING.md](CONTRIBUTING.md)、[行動規範](CODE_OF_CONDUCT.md)、[SECURITY.md](SECURITY.md)、[SUPPORT.md](SUPPORT.md) を参照してください。

## 👤 作者

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 ライセンス

GPL-3.0-or-later - [LICENSE](LICENSE).
