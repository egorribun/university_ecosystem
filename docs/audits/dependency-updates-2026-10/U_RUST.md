# U_RUST

Срез: 2026-10-12 07:31 UTC (от него считается cooldown). База: снимок origin/egorribun 04fdd84c2. Рабочий репозиторий не трогался.

## Политика
- Cooldown 7 дней: `renovate.json` задаёт `minimumReleaseAge: "7 days"` для cargo. Версия моложе 7 дней помечена «рано до DATE». В `.github/dependabot.yml` нет ecosystem `cargo`, Cargo обновляет только Renovate.
- Renovate: cargo patch — автомерж по выходным (группа «Rust dependencies (patch)»); minor/major — только ручной review (`automerge: false`). Security-алерты (`vulnerabilityAlerts`, `minimumReleaseAge: null`) не автомержатся; `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md` описывает процедуру для uv/PyPI и требует advisory ID.
- Точные пины `=X` (комментарии TD-22-02): rayon, hmac, sha2, hex, subtle, zeroize, base64ct (native/rust_ext, rust-crypto) и wasm-bindgen-test (rust-crypto). Менять только отдельным PR, Cargo.toml и Cargo.lock вместе (CI работает с `--locked`).
- Дрейф: rust-toolchain файлов в снимке нет; Rust 1.97.1 в CI и frontend.Dockerfile, но 1.94.1 в backend.Dockerfile; wasm-bindgen 0.2.114 (rust-crypto) против 0.2.129 (wasm-sanitizer). AGENTS.md версию Rust не закрепляет.

## Patch/minor — можно обновить
| Пакет | Где | Сейчас | → Версия | Дата | Cooldown | Security | Риск |
|---|---|---|---|---|---|---|---|
| pyo3 | native/rust_ext (`0.29`) | 0.29.2 | 0.29.3 | 2026-09-30 | ok | нет; 0.29.2 уже выше фикса GHSA (<0.29.0) | низкий |
| rayon | native/rust_ext (`=1.11.0`) | 1.11.0 | 1.12.0 | 2026-04-14 | ok | нет (GHSA 0); в CHANGELOG починен unsafe-баг `Range<char>`, не security | низкий; ручной пин |
| zeroize | native/rust_ext, rust-crypto (`=1.8.1`) | 1.8.1 | 1.9.0 | 2026-06-12 | ok (1.9.1 рано до 2026-10-13) | нет | низкий; проверить тест `ZeroizeDropProbe` (`atomic_fence` заменён на `optimization_barrier`) |
| wasm-bindgen | frontend/rust-crypto (`0.2`) | 0.2.114 | 0.2.129 | 2026-09-25 | ok | нет | средний: пересборка WASM и provenance; 0.2.122 убрал неявные экспорты `__heap_base`/`__data_end` (во фронте не используются); Node-тесты требуют ≥22.22.3 (в проекте Node 24) |
| wasm-bindgen-test | frontend/rust-crypto (`=0.3.64`) | 0.3.64 | 0.3.79 | 2026-09-25 | ok | нет | низкий; только вместе с wasm-bindgen 0.2.129 |
| ammonia | frontend/wasm-sanitizer (`4.1.4`, lock 4.2.0) | 4.2.0 | 4.2.3 | 2026-10-11 | рано до 2026-10-18 (4.2.1 от 2026-10-03: ok) | ДА по CHANGELOG: «Security fix» в 4.2.1 и 4.2.3; GHSA/CVE не найдено | низкий по конфигу (style-тег и style-атрибут не разрешены, `wasm-sanitizer/src/lib.rs`), но это фикс санитайзера, работающего в проде (`SafeHtml.tsx`) |
| arbitrary | native/rust_ext/fuzz (`1`) | 1.4.2 | 1.5.0 | 2026-10-06 | рано до 2026-10-13 | нет (GHSA 0); в CHANGELOG «Fixed soundness» | низкий; только fuzz |
| proptest | native/rust_ext, rust-crypto, wasm-sanitizer (dev, `1`) | 1.11.0 | 1.12.0 | 2026-10-10 | рано до 2026-10-17 | нет | средний: по CHANGELOG breaking (MSRV 1.88, rand 0.10, bit-set 0.11); в коде нет TestRng/rand/BitSet |
| Rust toolchain | CI (9 workflow, 11 мест), frontend.Dockerfile, backend.Dockerfile | 1.97.1 / 1.94.1 | 1.99.0 | 2026-09-28 (rustc; manifest 2026-10-01) | ok | нет | средний: правка пинов и `tests/test_frontend_docker_wasm_parity.py`; backend отстаёт |

## Major — отдельно
| Пакет | Где | Сейчас | Последний major | Дата | Breaking changes (кратко) | Затронутый код | Оценка |
|---|---|---|---|---|---|---|---|
| hmac | native/rust_ext (`=0.12.1`), rust-crypto (`0.12`) | 0.12.1 | 0.13.0 | 2026-03-29 | edition 2024, MSRV 1.85; digest 0.11; `new_from_slice` теперь через трейт `KeyInit` (README: `use hmac::{Hmac, KeyInit, Mac}`); удалены фичи `std`, `reset` | native `src/lib.rs:900, 977` (прод) и 10 вызовов в тестах; rust-crypto `src/lib.rs:2, 81`: нужен импорт KeyInit | средняя; мигрировать одним PR вместе с sha2, pbkdf2, scrypt |
| sha2 | native/rust_ext (`=0.10.9`), rust-crypto (`0.10`) | 0.10.9 | 0.11.0 | 2026-03-25 | edition 2024, MSRV 1.85; digest 0.11; удалены фичи `std`, `asm`, `soft`, `compress` и др.; `Sha256` остаётся типом | native `src/lib.rs:873`; rust-crypto `src/lib.rs:5, 9, 55` (вызовы без изменений) | низкая по коду; связка с hmac 0.13 |
| pbkdf2 | frontend/rust-crypto (`0.12`) | 0.12.2 | 0.13.0 | 2026-04-21 | `pbkdf2_hmac<D: EagerHash>(password, salt, rounds, res)`: сигнатура та же (проверено по исходнику); удалены `parallel`, `std`, `sha1`; тянет hmac 0.13 и sha2 0.11 | rust-crypto `src/lib.rs:3, 55` | низкая по коду; связка |
| scrypt | frontend/rust-crypto (`0.11`) | 0.11.0 | 0.12.0 | 2026-04-22 | `Params::new(log_n, r, p)` без длины выхода; `new_with_output_len(log_n, r, p, len)` только с фичей `phc`; `scrypt(password, salt, params, output)` без изменений; тянет pbkdf2 0.13, sha2 0.11 (проверено по исходнику) | rust-crypto `src/lib.rs:141`: `ScryptParams::new(log_n as u8, r, p, dk_len)` перестанет компилироваться; `tests/wasm.rs:90` (r=0 → Err) | средняя: точечная поломка плюс перенос проверки длины выхода |
| getrandom | frontend/rust-crypto (`0.2` + js; `0.3` для wasm32 + wasm_js) | 0.2.17 / 0.3.4 | 0.4.3 | 2026-06-17 | `getrandom()` переименован в `fill()` (с 0.3; проверено по исходнику 0.4.3); feature `js` удалён в 0.3 (вместо него `wasm_js` и cfg-флаги); MSRV 1.85, edition 2024 | `frontend/rust-crypto/src/tests.rs:12` (`getrandom::getrandom`); прод-кода вызовов нет | низкая |
| criterion | native/rust_ext (dev, `0.5`, html_reports) | 0.5.1 | 0.8.2 | 2026-02-04 | `criterion::black_box` помечен deprecated (нужен `std::hint::black_box`); MSRV 1.86; feature `html_reports` сохранён (проверено по исходнику) | `native/rust_ext/benches/conflict_bench.rs:1, 29`; CI `clippy --all-targets -- -D warnings` (`ci.yml:565`) упадёт на deprecation | низкая по коду, но правка обязательна для CI |
| cargo-fuzz (tool) | `.github/workflows/rust-fuzz.yml:81, 165` (`--version 0.12.0 --locked`) | 0.12.0 | 0.13.2 | 2026-06-09 | 0.13.0: новые флаги (`--codegen-units`, `--strip-dead-code`, `--disable-branch-folding`), dev-сборки без strip debug info, line tables по умолчанию; 0.13.1: фикс debug info; 0.13.2: обновление зависимостей | `rust-fuzz.yml` (pin с комментарием про rustix и nightly) | средняя; валидировать на текущем nightly |
| wasm-pack (tool) | 10 workflow (taiki-e `wasm-pack@0.13.1`), `frontend.Dockerfile:23` (`cargo install --locked`) | 0.13.1 | 0.15.0 (0.14.0 от 2026-01-20) | 2026-05-15 | 0.14: WASI и другие wasm-таргеты, aarch64-apple-darwin, `--split-linked-modules`, npm-пакет переехал; 0.15: wasm64, `--panic-unwind`, шаблон в репо; явных breaking по notes не найдено; репозиторий переехал в `wasm-bindgen/wasm-pack` | `frontend/scripts/build-wasm.mjs` (вызывает wasm-pack); комментарии в workflow: taiki-e хардкодит старый репозиторий (404 для ≥0.14) | средняя; сначала проверить установку, pin через `cargo install --locked` |

## Уже актуально
- Последняя версия: chrono 0.4.45 (native); hex 0.4.3 (native, rust-crypto); subtle 2.6.1 (native); base64ct 1.8.3 (rust-crypto); libfuzzer-sys 0.4.13 (3 fuzz-крейта); wasm-bindgen 0.2.129 и wasm-bindgen-test 0.3.79 (wasm-sanitizer); cargo-udeps 0.1.61; cargo-audit 0.22.2; cargo-llvm-cov 0.9.1; cargo-deny 0.20.2 (версия в `EmbarkStudios/cargo-deny-action@v2.1.1`); maturin 1.15.0 (uv.lock; нижняя граница расходится: `>=1.12` в `native/rust_ext/pyproject.toml` против `>=1.13.1` в корневом `pyproject.toml`); frontend/tools/stryker-process-host (зависимостей нет).
- В своей линии, но есть major: sha2 0.10.9, hmac 0.12.1, pbkdf2 0.12.2, scrypt 0.11.0, criterion 0.5.1, getrandom 0.2.17 и 0.3.4, wasm-pack 0.13.1.

## Не удалось проверить
- Сборка, `cargo test`/`clippy`, `cargo-deny`, `cargo-audit` не запускались: по условиям задачи только чтение. deny.toml проверен статически (`[advisories]` db-path/db-urls, `[licenses]` allow, `[bans]` warn), на схему cargo-deny 0.20.2 не сверял.
- Уязвимости: GitHub Advisory DB (`advisories?ecosystem=rust&affects=`) для 212 locked-пар и 4 инструментов; контроль: chrono 0.4.19 вернул 1 advisory. RustSec advisory-db напрямую не сверял, RustSec-only записи могли выпасть. В CI cargo-audit (`sbom.yml`) только для native/rust_ext и с `severity_threshold = "high"` (`native/rust_ext/.cargo/audit.toml`).
- ammonia 4.2.1 и 4.2.3: security-характер известен только из CHANGELOG, CVE/GHSA-ID не найдены.
- criterion 0.8: CHANGELOG в репозитории устарел (последняя запись 0.7.0); breaking проверены по исходникам опубликованного criterion-0.8.2.
- wasm-pack 0.14/0.15 и cargo-fuzz 0.13.x: notes разобраны по ключевым словам, построчно не читал; поведение на текущем nightly не проверено.
- wasm-bindgen 0.2.115–0.2.129: breaking-пункты из CHANGELOG; влияние на сгенерированный `pkg/*.js` проверяется только сборкой.
- Транзитивные зависимости: GHSA 0 по всем locked-парам, поэтому их changelog не разбирал.
- binaryen (`wasm-opt`, version_117 в frontend.Dockerfile; текущая version_133 от 2026-09-21): не Rust-крейт, в таблицы не включён.
- Rust 1.99.0: дата по channel manifest; changelog Rust не читал.

## Команды (не выполнены)
Все команды из корня снимка. Сначала правка точных пинов в Cargo.toml (rayon и zeroize в native/rust_ext; zeroize и wasm-bindgen-test в frontend/rust-crypto), затем `cargo update --precise`. Cargo.toml и Cargo.lock коммитить вместе.
```
cargo update --manifest-path native/rust_ext/Cargo.toml -p pyo3 --precise 0.29.3
cargo update --manifest-path native/rust_ext/Cargo.toml -p rayon --precise 1.12.0
cargo update --manifest-path native/rust_ext/Cargo.toml -p zeroize --precise 1.9.0
cargo update --manifest-path frontend/rust-crypto/Cargo.toml -p zeroize --precise 1.9.0
cargo update --manifest-path frontend/rust-crypto/Cargo.toml -p wasm-bindgen --precise 0.2.129
cargo update --manifest-path frontend/rust-crypto/Cargo.toml -p wasm-bindgen-test --precise 0.3.79
# после 2026-10-13
cargo update --manifest-path native/rust_ext/fuzz/Cargo.toml -p arbitrary --precise 1.5.0
# после 2026-10-17
cargo update --manifest-path native/rust_ext/Cargo.toml -p proptest --precise 1.12.0
cargo update --manifest-path frontend/rust-crypto/Cargo.toml -p proptest --precise 1.12.0
cargo update --manifest-path frontend/wasm-sanitizer/Cargo.toml -p proptest --precise 1.12.0
# после 2026-10-18 (или после security-ревью)
cargo update --manifest-path frontend/wasm-sanitizer/Cargo.toml -p ammonia --precise 4.2.3
```
Проверки (как в `ci.yml:565–567` и джобе «Rust - cargo test (x3 crates)»):
```
cargo clippy --manifest-path native/rust_ext/Cargo.toml --all-targets --no-default-features --locked -- -D warnings
cargo clippy --manifest-path frontend/wasm-sanitizer/Cargo.toml --all-targets --locked -- -D warnings
cargo clippy --manifest-path frontend/rust-crypto/Cargo.toml --all-targets --locked -- -D warnings
```
После изменения rust-crypto или wasm-sanitizer: `cd frontend && node scripts/build-wasm.mjs` (запускает wasm-pack и пишет `WASM_SOURCE_PROVENANCE.json`), затем `npm run test:wasm`. Сборка WASM на Windows перезаписывает `pkg/*.wasm`: после локальной сборки восстановить pkg и provenance.

Не `cargo update`, а правки кода и конфигов:
- Toolchain 1.97.1 → 1.99.0: `toolchain:` в 9 workflow, образы `rust:` с digest во `frontend.Dockerfile` и `backend.Dockerfile`, ассерты в `tests/test_frontend_docker_wasm_parity.py`.
- hmac/sha2/pbkdf2/scrypt одним PR: Cargo.toml на 0.13/0.11/0.13/0.12, импорт `KeyInit`, `ScryptParams::new` с тремя аргументами (или `new_with_output_len` с фичей `phc`).
- criterion: `criterion::black_box` → `std::hint::black_box`.
- getrandom 0.4: `getrandom()` → `fill()`.
- cargo-fuzz и wasm-pack: новый `--version` в workflow и Dockerfile после проверки установки и сборки.
