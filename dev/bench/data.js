window.BENCHMARK_DATA = {
  "lastUpdate": 1787615817836,
  "repoUrl": "https://github.com/egorribun/university_ecosystem",
  "entries": {
    "Go Services Performance Benchmarks": [
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a4a29b04668a6d590ca126519cebf261fb5bc4d9",
          "message": "chore: trigger benchmark deployment\n\n* chore: trigger CI and benchmark workflows\n\n* chore: trigger CI and benchmark deployment",
          "timestamp": "2026-07-06T04:02:56+03:00",
          "tree_id": "0c4444c198891cd69758e0defb6bd6e86fa39395",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a4a29b04668a6d590ca126519cebf261fb5bc4d9"
        },
        "date": 1783299984975,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 867.4,
            "unit": "ns/op",
            "extra": "1361013 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.65,
            "unit": "ns/op",
            "extra": "17473732 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.9,
            "unit": "ns/op",
            "extra": "7948222 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 11.58,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 541.2,
            "unit": "ns/op",
            "extra": "2163150 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 66.33,
            "unit": "ns/op",
            "extra": "18157378 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.96,
            "unit": "ns/op",
            "extra": "39479967 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 563.9,
            "unit": "ns/op",
            "extra": "2117217 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1539,
            "unit": "ns/op",
            "extra": "747750 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14.21,
            "unit": "ns/op",
            "extra": "86755330 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 799.5,
            "unit": "ns/op",
            "extra": "1505751 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 92.75,
            "unit": "ns/op",
            "extra": "12847477 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1426,
            "unit": "ns/op",
            "extra": "759524 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 22.14,
            "unit": "ns/op",
            "extra": "55143109 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1588,
            "unit": "ns/op",
            "extra": "745560 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "35f3049c4a9b1b07018d294d4e630095e23828a6",
          "message": "chore: fix TruffleHog BASE and HEAD same commit push error\n\n* chore: trigger CI and benchmark workflows\n\n* chore: fix TruffleHog 'BASE and HEAD commits are the same' push error",
          "timestamp": "2026-07-06T04:34:52+03:00",
          "tree_id": "f8bbd3be4bb17f8cb074f32b4f270d766a2a08f2",
          "url": "https://github.com/egorribun/university_ecosystem/commit/35f3049c4a9b1b07018d294d4e630095e23828a6"
        },
        "date": 1783301873736,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 865.3,
            "unit": "ns/op",
            "extra": "1386940 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.7,
            "unit": "ns/op",
            "extra": "17439621 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 151.1,
            "unit": "ns/op",
            "extra": "7955697 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 11.31,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 540.9,
            "unit": "ns/op",
            "extra": "2160981 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 65.92,
            "unit": "ns/op",
            "extra": "17957394 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 32.66,
            "unit": "ns/op",
            "extra": "37598869 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 566.5,
            "unit": "ns/op",
            "extra": "2061780 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1570,
            "unit": "ns/op",
            "extra": "701355 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.88,
            "unit": "ns/op",
            "extra": "87011482 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 939.9,
            "unit": "ns/op",
            "extra": "1527667 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 92.52,
            "unit": "ns/op",
            "extra": "12606598 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1492,
            "unit": "ns/op",
            "extra": "782186 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.76,
            "unit": "ns/op",
            "extra": "55264542 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1633,
            "unit": "ns/op",
            "extra": "753213 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "481a1f1ca2d3c64d35ebafe59d422637223be593",
          "message": "ci(deps): Bump the github-actions group with 18 updates\n\nBumps the github-actions group with 18 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.2.0` | `8.3.0` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.2884.0` | `12.3112.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.36.2` | `4.36.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `17.7.2` | `18.0.1` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `19.1.0` | `24.0.0` |\n| [streetsidesoftware/cspell-action](https://github.com/streetsidesoftware/cspell-action) | `6.2.0` | `8.4.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.36.2` | `4.36.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.36.2` | `4.36.3` |\n| [gitleaks/gitleaks-action](https://github.com/gitleaks/gitleaks-action) | `2.3.9` | `3.0.0` |\n| [golangci/golangci-lint-action](https://github.com/golangci/golangci-lint-action) | `9.2.1` | `9.3.0` |\n| [zaproxy/action-baseline](https://github.com/zaproxy/action-baseline) | `6c5a007541891231cd9e0ddec25d4f25c59c9874` | `de8ad967d3548d44ef623df22cf95c3b0baf8b25` |\n| [codecov/codecov-action](https://github.com/codecov/codecov-action) | `5.3.0` | `7.0.0` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.2.0` | `4.4.0` |\n| [docker/setup-buildx-action](https://github.com/docker/setup-buildx-action) | `4.1.0` | `4.2.0` |\n| [docker/build-push-action](https://github.com/docker/build-push-action) | `7.2.0` | `7.3.0` |\n| [amannn/action-semantic-pull-request](https://github.com/amannn/action-semantic-pull-request) | `2d952a1bf90a6a7ab8f0293dc86f5fdf9acb1915` | `2c9480cf285c2ac02b52e26013f7d627b14a4f95` |\n| [SonarSource/sonarqube-scan-action](https://github.com/sonarsource/sonarqube-scan-action) | `5.0.0` | `8.2.0` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.90.5` | `3.95.8` |\n\n\nUpdates `astral-sh/setup-uv` from 8.2.0 to 8.3.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/fac544c07dec837d0ccb6301d7b5580bf5edae39...d31148d669074a8d0a63714ba94f3201e7020bc3)\n\nUpdates `bridgecrewio/checkov-action` from 12.2884.0 to 12.3112.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/a36096a3a272a684d48058e101498cddb9a1599d...a7683e7b72a04503521247973281ec8142e1ac1f)\n\nUpdates `github/codeql-action/upload-sarif` from 4.36.2 to 4.36.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...54f647b7e1bb85c95cddabcd46b0c578ec92bc1a)\n\nUpdates `chromaui/action` from 17.7.2 to 18.0.1\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/7ffa9343588f15ff3f4cde30e03cd23204ed6a9c...94713c544284a14195de3b50ef24301579f1877e)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 19.1.0 to 24.0.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/05f32210e84442804257b2a6f20b273450ec8265...8de2aa07cae85fd17c0b35642db70cf5495f1d25)\n\nUpdates `streetsidesoftware/cspell-action` from 6.2.0 to 8.4.0\n- [Release notes](https://github.com/streetsidesoftware/cspell-action/releases)\n- [Changelog](https://github.com/streetsidesoftware/cspell-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/streetsidesoftware/cspell-action/compare/807d7d92b7057593a2de102168506f298405339d...de2a73e963e7443969755b648a1008f77033c5b2)\n\nUpdates `github/codeql-action/init` from 4.36.2 to 4.36.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...54f647b7e1bb85c95cddabcd46b0c578ec92bc1a)\n\nUpdates `github/codeql-action/analyze` from 4.36.2 to 4.36.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...54f647b7e1bb85c95cddabcd46b0c578ec92bc1a)\n\nUpdates `gitleaks/gitleaks-action` from 2.3.9 to 3.0.0\n- [Release notes](https://github.com/gitleaks/gitleaks-action/releases)\n- [Commits](https://github.com/gitleaks/gitleaks-action/compare/ff98106e4c7b2bc287b24eaf42907196329070c7...e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e)\n\nUpdates `golangci/golangci-lint-action` from 9.2.1 to 9.3.0\n- [Release notes](https://github.com/golangci/golangci-lint-action/releases)\n- [Commits](https://github.com/golangci/golangci-lint-action/compare/82606bf257cbaff209d206a39f5134f0cfbfd2ee...ba0d7d2ec06a0ea1cb5fa41b2e4a3ab91d21278a)\n\nUpdates `zaproxy/action-baseline` from 6c5a007541891231cd9e0ddec25d4f25c59c9874 to de8ad967d3548d44ef623df22cf95c3b0baf8b25\n- [Release notes](https://github.com/zaproxy/action-baseline/releases)\n- [Changelog](https://github.com/zaproxy/action-baseline/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/zaproxy/action-baseline/compare/6c5a007541891231cd9e0ddec25d4f25c59c9874...de8ad967d3548d44ef623df22cf95c3b0baf8b25)\n\nUpdates `codecov/codecov-action` from 5.3.0 to 7.0.0\n- [Release notes](https://github.com/codecov/codecov-action/releases)\n- [Changelog](https://github.com/codecov/codecov-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/codecov/codecov-action/compare/0da7aa657d958d32c117fc47e1f977e7524753c7...fb8b3582c8e4def4969c97caa2f19720cb33a72f)\n\nUpdates `docker/login-action` from 4.2.0 to 4.4.0\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/650006c6eb7dba73a995cc03b0b2d7f5ca915bee...af1e73f918a031802d376d3c8bbc3fe56130a9b0)\n\nUpdates `docker/setup-buildx-action` from 4.1.0 to 4.2.0\n- [Release notes](https://github.com/docker/setup-buildx-action/releases)\n- [Commits](https://github.com/docker/setup-buildx-action/compare/d7f5e7f509e45cec5c76c4d5afdd7de93d0b3df5...bb05f3f5519dd87d3ba754cc423b652a5edd6d2c)\n\nUpdates `docker/build-push-action` from 7.2.0 to 7.3.0\n- [Release notes](https://github.com/docker/build-push-action/releases)\n- [Commits](https://github.com/docker/build-push-action/compare/f9f3042f7e2789586610d6e8b85c8f03e5195baf...53b7df96c91f9c12dcc8a07bcb9ccacbed38856a)\n\nUpdates `amannn/action-semantic-pull-request` from 2d952a1bf90a6a7ab8f0293dc86f5fdf9acb1915 to 2c9480cf285c2ac02b52e26013f7d627b14a4f95\n- [Release notes](https://github.com/amannn/action-semantic-pull-request/releases)\n- [Changelog](https://github.com/amannn/action-semantic-pull-request/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/amannn/action-semantic-pull-request/compare/2d952a1bf90a6a7ab8f0293dc86f5fdf9acb1915...2c9480cf285c2ac02b52e26013f7d627b14a4f95)\n\nUpdates `SonarSource/sonarqube-scan-action` from 5.0.0 to 8.2.0\n- [Release notes](https://github.com/sonarsource/sonarqube-scan-action/releases)\n- [Commits](https://github.com/sonarsource/sonarqube-scan-action/compare/0303d6b62e310685c0e34d0b9cde218036885c4d...713881670b6b3676cda39549040e2d88c70d582e)\n\nUpdates `trufflesecurity/trufflehog` from 3.90.5 to 3.95.8\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/0f58ae7c5036094a1e3e750d18772af92821b503...00155c9dc586f34d189adc83d3ac2698c2ec551f)\n\n---\nupdated-dependencies:\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 8.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3112.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.36.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: streetsidesoftware/cspell-action\n  dependency-version: 8.4.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.36.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.36.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: gitleaks/gitleaks-action\n  dependency-version: 3.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: golangci/golangci-lint-action\n  dependency-version: 9.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zaproxy/action-baseline\n  dependency-version: de8ad967d3548d44ef623df22cf95c3b0baf8b25\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: codecov/codecov-action\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.4.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: docker/setup-buildx-action\n  dependency-version: 4.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: docker/build-push-action\n  dependency-version: 7.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: amannn/action-semantic-pull-request\n  dependency-version: 2c9480cf285c2ac02b52e26013f7d627b14a4f95\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: SonarSource/sonarqube-scan-action\n  dependency-version: 8.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.95.8\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-06T17:10:06+03:00",
          "tree_id": "7c69753d65d991c3d36e927dad468c92e25383e4",
          "url": "https://github.com/egorribun/university_ecosystem/commit/481a1f1ca2d3c64d35ebafe59d422637223be593"
        },
        "date": 1783347108850,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 783.6,
            "unit": "ns/op",
            "extra": "1530552 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.4,
            "unit": "ns/op",
            "extra": "16593139 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 165.7,
            "unit": "ns/op",
            "extra": "7255557 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 10.81,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 509.7,
            "unit": "ns/op",
            "extra": "2358272 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 74.92,
            "unit": "ns/op",
            "extra": "16059434 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 28.35,
            "unit": "ns/op",
            "extra": "39150666 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 478.8,
            "unit": "ns/op",
            "extra": "2501343 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1302,
            "unit": "ns/op",
            "extra": "776780 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.39,
            "unit": "ns/op",
            "extra": "90998565 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 726.8,
            "unit": "ns/op",
            "extra": "1442647 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 88.75,
            "unit": "ns/op",
            "extra": "13688415 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1337,
            "unit": "ns/op",
            "extra": "844311 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.15,
            "unit": "ns/op",
            "extra": "56277880 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1573,
            "unit": "ns/op",
            "extra": "779893 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ae11edc3736abd35a2bde612c12df103594289e3",
          "message": "build(deps): Update fastapi requirement from <0.139,>=0.135.3 to >=0.135.3,<0.140 in the pip-dependencies group\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi) to permit the latest version.\n\nUpdates `fastapi` to 0.139.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.139.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.139.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-06T17:09:54+03:00",
          "tree_id": "29959c8fc175396fe56d40dcf0ac5fdffedc0a16",
          "url": "https://github.com/egorribun/university_ecosystem/commit/ae11edc3736abd35a2bde612c12df103594289e3"
        },
        "date": 1783347112072,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 791.8,
            "unit": "ns/op",
            "extra": "1525677 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.58,
            "unit": "ns/op",
            "extra": "16542044 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 165.9,
            "unit": "ns/op",
            "extra": "6802233 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 10.99,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 508.2,
            "unit": "ns/op",
            "extra": "2375888 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 74.14,
            "unit": "ns/op",
            "extra": "16185931 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 28.66,
            "unit": "ns/op",
            "extra": "38916284 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 482.1,
            "unit": "ns/op",
            "extra": "2477360 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1309,
            "unit": "ns/op",
            "extra": "833271 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.22,
            "unit": "ns/op",
            "extra": "91018443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 741.3,
            "unit": "ns/op",
            "extra": "1630558 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 88.53,
            "unit": "ns/op",
            "extra": "13355113 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1359,
            "unit": "ns/op",
            "extra": "858609 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.08,
            "unit": "ns/op",
            "extra": "57358695 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1564,
            "unit": "ns/op",
            "extra": "757826 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ac92b400cfb729e6aa4f2f4175ec8514a3d094b4",
          "message": "feat: complete full testing roadmap + OSS-Fuzz integration\n\nfeat: complete testing roadmap (Pytest, Go, Rust, Frontend, E2E)",
          "timestamp": "2026-07-07T18:00:35+03:00",
          "tree_id": "0657d0644d5d783cc87c9c89f1c4465790781d70",
          "url": "https://github.com/egorribun/university_ecosystem/commit/ac92b400cfb729e6aa4f2f4175ec8514a3d094b4"
        },
        "date": 1783436546395,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 108459,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 111.1,
            "unit": "ns/op",
            "extra": "10718601 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 854,
            "unit": "ns/op",
            "extra": "1410582 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.23,
            "unit": "ns/op",
            "extra": "17329238 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 151.2,
            "unit": "ns/op",
            "extra": "7955028 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 11.5,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 551.3,
            "unit": "ns/op",
            "extra": "2181519 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 65.97,
            "unit": "ns/op",
            "extra": "18219570 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.24,
            "unit": "ns/op",
            "extra": "37361822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 571.2,
            "unit": "ns/op",
            "extra": "2113737 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1533,
            "unit": "ns/op",
            "extra": "706986 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14.09,
            "unit": "ns/op",
            "extra": "85289403 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 775.8,
            "unit": "ns/op",
            "extra": "1593498 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 93.59,
            "unit": "ns/op",
            "extra": "12721027 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1449,
            "unit": "ns/op",
            "extra": "748315 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.76,
            "unit": "ns/op",
            "extra": "54907515 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1521,
            "unit": "ns/op",
            "extra": "789013 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 41.62,
            "unit": "ns/op",
            "extra": "29374474 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 780.8,
            "unit": "ns/op",
            "extra": "1500759 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 15741,
            "unit": "ns/op",
            "extra": "76726 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cf66cebab3789eeb20c055ebb4fe402a70ac3359",
          "message": "feat: maximum coverage roadmap implementation\n\n* feat(wave212): maximum coverage roadmap implementation\n\n* chore: update agents.md testing constraint rules\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-07-13T22:43:20+03:00",
          "tree_id": "80a604c64e5d60a79a8bc236c61d9dcc3a9c8aa2",
          "url": "https://github.com/egorribun/university_ecosystem/commit/cf66cebab3789eeb20c055ebb4fe402a70ac3359"
        },
        "date": 1783972036181,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation",
            "value": 121770,
            "unit": "ns/op",
            "extra": "9520 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback",
            "value": 111.8,
            "unit": "ns/op",
            "extra": "10727035 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader",
            "value": 876.6,
            "unit": "ns/op",
            "extra": "1383733 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT",
            "value": 69.03,
            "unit": "ns/op",
            "extra": "17286730 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit",
            "value": 150.8,
            "unit": "ns/op",
            "extra": "7958887 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss",
            "value": 11.37,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey",
            "value": 553.6,
            "unit": "ns/op",
            "extra": "1846310 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic",
            "value": 65.94,
            "unit": "ns/op",
            "extra": "18209289 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256",
            "value": 30.23,
            "unit": "ns/op",
            "extra": "37923006 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7e8215429e3ceea051bf51e9c0642a9b4e669e84",
          "message": "ci(deps): Bump the github-actions group with 9 updates\n\n---\nupdated-dependencies:\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 8.3.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: fa04a1451ff1842e2626ccb99004d0195b455a88\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: actions/cache\n  dependency-version: 6.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3114.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.95.9\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-13T22:43:37+03:00",
          "tree_id": "01308c2aa49e8873c0549849d5a2b47e6b6fb984",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7e8215429e3ceea051bf51e9c0642a9b4e669e84"
        },
        "date": 1783972090962,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation",
            "value": 119546,
            "unit": "ns/op",
            "extra": "9436 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback",
            "value": 111.4,
            "unit": "ns/op",
            "extra": "10666746 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader",
            "value": 869.5,
            "unit": "ns/op",
            "extra": "1343544 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT",
            "value": 70.2,
            "unit": "ns/op",
            "extra": "17332734 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit",
            "value": 152.6,
            "unit": "ns/op",
            "extra": "7690540 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss",
            "value": 11.37,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey",
            "value": 552.1,
            "unit": "ns/op",
            "extra": "2164153 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic",
            "value": 65.98,
            "unit": "ns/op",
            "extra": "18189192 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256",
            "value": 30.43,
            "unit": "ns/op",
            "extra": "38492582 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ecdd7e91f64cec8f9201df4280fe9514a8aa66c3",
          "message": "build(deps-dev): Update mypy requirement from <2.2,>=1.20.1 to >=1.20.1,<2.3 in the pip-dependencies group\n\nUpdates the requirements on [mypy](https://github.com/python/mypy) to permit the latest version.\n\nUpdates `mypy` to 2.2.0\n- [Changelog](https://github.com/python/mypy/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/python/mypy/compare/v1.20.1...v2.2.0)\n\n---\nupdated-dependencies:\n- dependency-name: mypy\n  dependency-version: 2.2.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-13T22:43:54+03:00",
          "tree_id": "fbc729bc609e7e9cace409865c738e2d55e49e52",
          "url": "https://github.com/egorribun/university_ecosystem/commit/ecdd7e91f64cec8f9201df4280fe9514a8aa66c3"
        },
        "date": 1783972219689,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation",
            "value": 98035,
            "unit": "ns/op",
            "extra": "12086 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback",
            "value": 106.9,
            "unit": "ns/op",
            "extra": "10769394 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader",
            "value": 785.4,
            "unit": "ns/op",
            "extra": "1521699 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT",
            "value": 73.6,
            "unit": "ns/op",
            "extra": "16454437 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit",
            "value": 167.8,
            "unit": "ns/op",
            "extra": "7240312 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss",
            "value": 10.95,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey",
            "value": 514.7,
            "unit": "ns/op",
            "extra": "2322836 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic",
            "value": 74.38,
            "unit": "ns/op",
            "extra": "15600986 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256",
            "value": 28.48,
            "unit": "ns/op",
            "extra": "39671395 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817265712,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 45364,
            "unit": "ns/op",
            "extra": "23020 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.31,
            "unit": "ns/op",
            "extra": "16794429 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 523,
            "unit": "ns/op",
            "extra": "2097452 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 45.03,
            "unit": "ns/op",
            "extra": "26591865 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 82.45,
            "unit": "ns/op",
            "extra": "14707543 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 26.93,
            "unit": "ns/op",
            "extra": "44604332 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 361.5,
            "unit": "ns/op",
            "extra": "3336584 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 49.43,
            "unit": "ns/op",
            "extra": "24268316 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 18.06,
            "unit": "ns/op",
            "extra": "66259995 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 349.5,
            "unit": "ns/op",
            "extra": "3435222 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 963.6,
            "unit": "ns/op",
            "extra": "1249096 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 15.85,
            "unit": "ns/op",
            "extra": "75540339 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 503.3,
            "unit": "ns/op",
            "extra": "2328672 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 67.68,
            "unit": "ns/op",
            "extra": "21312800 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 890.7,
            "unit": "ns/op",
            "extra": "1378123 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 50.19,
            "unit": "ns/op",
            "extra": "23457670 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1595,
            "unit": "ns/op",
            "extra": "913264 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 58.67,
            "unit": "ns/op",
            "extra": "20337366 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 564.6,
            "unit": "ns/op",
            "extra": "2038251 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 12019,
            "unit": "ns/op",
            "extra": "123360 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191585252,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 119108,
            "unit": "ns/op",
            "extra": "9496 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 108.6,
            "unit": "ns/op",
            "extra": "10949688 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 881.4,
            "unit": "ns/op",
            "extra": "1379823 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.97,
            "unit": "ns/op",
            "extra": "16641957 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 95.6,
            "unit": "ns/op",
            "extra": "12737086 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.78,
            "unit": "ns/op",
            "extra": "76777784 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 572.1,
            "unit": "ns/op",
            "extra": "2067961 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 66.71,
            "unit": "ns/op",
            "extra": "18030350 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.8,
            "unit": "ns/op",
            "extra": "39339982 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 572,
            "unit": "ns/op",
            "extra": "2087900 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1510,
            "unit": "ns/op",
            "extra": "711382 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.81,
            "unit": "ns/op",
            "extra": "87134408 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 848.9,
            "unit": "ns/op",
            "extra": "1423854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 91.72,
            "unit": "ns/op",
            "extra": "12508275 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1501,
            "unit": "ns/op",
            "extra": "830784 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 49.24,
            "unit": "ns/op",
            "extra": "21722012 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2010,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 63.05,
            "unit": "ns/op",
            "extra": "18966276 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 787.5,
            "unit": "ns/op",
            "extra": "1543544 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18002,
            "unit": "ns/op",
            "extra": "91990 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191779408,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 53097,
            "unit": "ns/op",
            "extra": "22018 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 75.65,
            "unit": "ns/op",
            "extra": "15789477 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 546.2,
            "unit": "ns/op",
            "extra": "2166018 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 47.27,
            "unit": "ns/op",
            "extra": "22206970 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 83.9,
            "unit": "ns/op",
            "extra": "14285337 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 27.73,
            "unit": "ns/op",
            "extra": "43300068 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 427.7,
            "unit": "ns/op",
            "extra": "3146215 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 50.73,
            "unit": "ns/op",
            "extra": "23630672 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 20.35,
            "unit": "ns/op",
            "extra": "58703770 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 369.1,
            "unit": "ns/op",
            "extra": "3296347 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1071,
            "unit": "ns/op",
            "extra": "1184059 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 16.28,
            "unit": "ns/op",
            "extra": "73781942 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 522,
            "unit": "ns/op",
            "extra": "2240871 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 66.51,
            "unit": "ns/op",
            "extra": "20231965 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 910.8,
            "unit": "ns/op",
            "extra": "1240654 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 52.92,
            "unit": "ns/op",
            "extra": "26020887 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1647,
            "unit": "ns/op",
            "extra": "899900 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 61.63,
            "unit": "ns/op",
            "extra": "19880168 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 604,
            "unit": "ns/op",
            "extra": "1941637 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 12613,
            "unit": "ns/op",
            "extra": "122295 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "496ed7f2c5c0fd33da738b4687b4c31281f14d7e",
          "message": "fix(ci): restore checks after draft pull requests become ready (#1227)\n\n* feat(wave212): remove obsolete handoff prompt\n\n* fix(ci): trigger checks when draft PR becomes ready\n\n* test(quality): cover gateway TLS certificate failure paths\n\n* fix(ci): keep required OpenAPI check live on every PR\n\n* fix(ci): run frontend mutation gate during manual recovery\n\n* test(gateway): satisfy Go lint and nil analysis\n\n* fix(ci): add manual recovery triggers for Go analysis\n\n* fix(ci): make gosec test directive effective\n\n* fix(ci): use canonical lighthouse assertions\n\n* fix(ci): eliminate ws-hub shutdown race\n\n* fix(ci): handle ws-hub socket cleanup error\n\n* fix(ci): reduce ws-hub server complexity\n\n* fix(ci): align lighthouse gates with canonical config\n\n* fix(ci): isolate backend integration test scope\n\n* fix(ci): start minio for chaos services\n\n* fix(quality): consume frontend statement coverage\n\n* fix(ci): close PR check and coverage gaps\n\n* fix(ci): close analyzer findings\n\n* fix(ci): drain file processor servers before return\n\n* fix(ci): close coverage gate deficits\n\n* fix(ci): make PR quality gate reproducible\n\n* fix(ci): prevent security scan alert drift\n\n* fix(ci): retry testcontainer image pulls\n\n* fix(ci): stabilize browser e2e execution\n\n* fix(ci): close mutation and tier0 coverage gaps\n\n* fix(ci): unblock code scanning ruleset\n\n* fix(ci): preserve scoped trivy suppressions\n\n* fix(ci): filter suppressed checkov alerts\n\n* fix(ci): write filtered checkov sarif separately\n\n* fix(ci): use one trivy ignore format\n\n* fix(ci): make Semgrep SARIF analysis reliable\n\n* fix(ci): make Semgrep pull requests diff-aware\n\n* fix(ci): close Semgrep findings in integration gate\n\n* fix(ci): make gateway race performance gate stable\n\n* fix(ci): remove golangci schema network dependency\n\n* fix(ci): avoid redundant Lighthouse dependency bootstrap\n\n* fix(ci): close session crypto coverage branch\n\n* fix(ci): include workflow contract inputs in mutmut sandbox\n\n* fix(test): bound Miri sanitizer payload\n\n* fix(test): reduce Miri sanitizer fixture\n\n* fix(test): invalidate cached JWT keys on rotation\n\n* fix(test): isolate notification metrics state\n\n* chore: update codebase test coverage reports and configuration files\n\n* fix(ci): balance incremental mutmut shards\n\n* fix(test): clean up SPIFFE stress test lint\n\n* fix(test): isolate ChatWindow render suites\n\n* fix(frontend): guard profile sync auto-fetch reruns\n\n* fix(test): isolate profile coverage suites\n\n* fix(test): isolate component coverage suites\n\n* fix(test): isolate event hero coverage suites\n\n* fix(test): isolate schedule and event file suites\n\n* chore(test): checkpoint current branch changes\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-08T21:40:49+03:00",
          "tree_id": "26101b1ba5348abe8e9c0a22c539a733d8f96e1b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/496ed7f2c5c0fd33da738b4687b4c31281f14d7e"
        },
        "date": 1786214862365,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 126663,
            "unit": "ns/op",
            "extra": "8534 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 105.3,
            "unit": "ns/op",
            "extra": "11022208 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 1024,
            "unit": "ns/op",
            "extra": "1370698 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.82,
            "unit": "ns/op",
            "extra": "17441571 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 147,
            "unit": "ns/op",
            "extra": "8097624 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.59,
            "unit": "ns/op",
            "extra": "76531568 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 567,
            "unit": "ns/op",
            "extra": "2113368 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 120.6,
            "unit": "ns/op",
            "extra": "9916476 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.84,
            "unit": "ns/op",
            "extra": "38652825 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 556.9,
            "unit": "ns/op",
            "extra": "2155828 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1508,
            "unit": "ns/op",
            "extra": "713600 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.75,
            "unit": "ns/op",
            "extra": "86886142 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 982.9,
            "unit": "ns/op",
            "extra": "1454138 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 96.74,
            "unit": "ns/op",
            "extra": "13013473 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1487,
            "unit": "ns/op",
            "extra": "824020 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 32.05,
            "unit": "ns/op",
            "extra": "34730559 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2053,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 51.14,
            "unit": "ns/op",
            "extra": "23102820 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 786.9,
            "unit": "ns/op",
            "extra": "1626800 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18610,
            "unit": "ns/op",
            "extra": "92446 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada",
          "message": "ci(deps): Bump the github-actions group with 9 updates (#1230)\n\nBumps the github-actions group with 9 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [dtolnay/rust-toolchain](https://github.com/dtolnay/rust-toolchain) | `2c7215f132e9ebf062739d9130488b56d53c060c` | `6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.3114.0` | `12.3115.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `24.1.0` | `24.2.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.1` | `4.2.2` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.1` | `0.6.2` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/v7...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `dtolnay/rust-toolchain` from 2c7215f132e9ebf062739d9130488b56d53c060c to 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n- [Release notes](https://github.com/dtolnay/rust-toolchain/releases)\n- [Commits](https://github.com/dtolnay/rust-toolchain/compare/2c7215f132e9ebf062739d9130488b56d53c060c...6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772)\n\nUpdates `bridgecrewio/checkov-action` from 12.3114.0 to 12.3115.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/7b972723c44fb3d256283fac96fae5d7c1894bb7...9b70310bcd306d11740313070b940167d6b23085)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 24.1.0 to 24.2.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/6bf21b07787794f89a243495939cd651942aeabe...21c1be1b93ad9ed58fa840aacc3f279cde2a72ff)\n\nUpdates `github/codeql-action/init` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `github/codeql-action/analyze` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `actions/attest` from 4.2.1 to 4.2.2\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/508db95dd578ae2727ebd6217d5ba78e4fbda05d...1e69f48acb82d1966a394da916b4c1698aa569d6)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.1 to 0.6.2\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6fc4b006235f201fdab3722e17240ab420d580e5...3dc1ecc9bcb9e94e9b2c709687979e1298497054)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3115.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-10T12:31:09+03:00",
          "tree_id": "943e83367d58b7cd70d48bf646ef00f5ad5c36ce",
          "url": "https://github.com/egorribun/university_ecosystem/commit/8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada"
        },
        "date": 1786354385945,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 122551,
            "unit": "ns/op",
            "extra": "9105 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 104.7,
            "unit": "ns/op",
            "extra": "11053995 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 879.3,
            "unit": "ns/op",
            "extra": "1359244 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.84,
            "unit": "ns/op",
            "extra": "16523142 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 148.1,
            "unit": "ns/op",
            "extra": "8034159 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.6,
            "unit": "ns/op",
            "extra": "76485042 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 612.2,
            "unit": "ns/op",
            "extra": "1721018 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 120.8,
            "unit": "ns/op",
            "extra": "9902468 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.35,
            "unit": "ns/op",
            "extra": "39019407 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 559.3,
            "unit": "ns/op",
            "extra": "2142549 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1514,
            "unit": "ns/op",
            "extra": "716913 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.78,
            "unit": "ns/op",
            "extra": "86627137 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 809.5,
            "unit": "ns/op",
            "extra": "1424443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 89.7,
            "unit": "ns/op",
            "extra": "12880237 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1525,
            "unit": "ns/op",
            "extra": "828267 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 36.66,
            "unit": "ns/op",
            "extra": "35317374 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2006,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 54.24,
            "unit": "ns/op",
            "extra": "23157130 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 716.7,
            "unit": "ns/op",
            "extra": "1701241 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 17653,
            "unit": "ns/op",
            "extra": "92112 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "83beb35c866c4baa10b60e2ef95c663568a3c58e",
          "message": "build(deps): Bump the go-file-processor group (#1233)\n\nBumps the go-file-processor group in /services/file-processor with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/minio](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.temporal.io/api](https://github.com/temporalio/api-go) | `1.63.4` | `1.63.5` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/minio` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.temporal.io/api` from 1.63.4 to 1.63.5\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.4...v1.63.5)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/minio\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.5\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-11T14:12:40+03:00",
          "tree_id": "d51f68500e421c60f18e4437922edb661971e41a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/83beb35c866c4baa10b60e2ef95c663568a3c58e"
        },
        "date": 1786447054567,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 103849,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 108.1,
            "unit": "ns/op",
            "extra": "10990288 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 806,
            "unit": "ns/op",
            "extra": "1308133 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.57,
            "unit": "ns/op",
            "extra": "16517539 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 156.6,
            "unit": "ns/op",
            "extra": "7634566 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.15,
            "unit": "ns/op",
            "extra": "79027190 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 524.9,
            "unit": "ns/op",
            "extra": "2313061 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 126.5,
            "unit": "ns/op",
            "extra": "9480818 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.4,
            "unit": "ns/op",
            "extra": "39540112 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 473.2,
            "unit": "ns/op",
            "extra": "2533408 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1339,
            "unit": "ns/op",
            "extra": "767064 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.23,
            "unit": "ns/op",
            "extra": "91680105 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 762.5,
            "unit": "ns/op",
            "extra": "1537620 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 87.1,
            "unit": "ns/op",
            "extra": "13241346 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1375,
            "unit": "ns/op",
            "extra": "867572 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 30.53,
            "unit": "ns/op",
            "extra": "35673810 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1935,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 46.55,
            "unit": "ns/op",
            "extra": "25941598 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 787.4,
            "unit": "ns/op",
            "extra": "1643811 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14428,
            "unit": "ns/op",
            "extra": "115788 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2f04616dfc39026d11be988ae05d33eb9403f1c5",
          "message": "build(deps): Bump the go-ws-hub group (#1231)\n\nBumps the go-ws-hub group in /services/ws-hub with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.60.0` | `0.61.0` |\n| [github.com/quic-go/webtransport-go](https://github.com/quic-go/webtransport-go) | `0.11.1` | `0.12.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `github.com/quic-go/quic-go` from 0.60.0 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.60.0...v0.61.0)\n\nUpdates `github.com/quic-go/webtransport-go` from 0.11.1 to 0.12.0\n- [Release notes](https://github.com/quic-go/webtransport-go/releases)\n- [Commits](https://github.com/quic-go/webtransport-go/compare/v0.11.1...v0.12.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/webtransport-go\n  dependency-version: 0.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:07+03:00",
          "tree_id": "af20c3ca22f350fb2734115e77c0541b42988af5",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2f04616dfc39026d11be988ae05d33eb9403f1c5"
        },
        "date": 1786447370137,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 123640,
            "unit": "ns/op",
            "extra": "9279 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 113.2,
            "unit": "ns/op",
            "extra": "10920985 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 895.2,
            "unit": "ns/op",
            "extra": "1221102 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.29,
            "unit": "ns/op",
            "extra": "17331685 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 153.4,
            "unit": "ns/op",
            "extra": "7415540 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.66,
            "unit": "ns/op",
            "extra": "76974634 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 571.7,
            "unit": "ns/op",
            "extra": "2039674 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 120,
            "unit": "ns/op",
            "extra": "9972900 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.17,
            "unit": "ns/op",
            "extra": "39448831 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 569.2,
            "unit": "ns/op",
            "extra": "2132768 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1767,
            "unit": "ns/op",
            "extra": "693519 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.77,
            "unit": "ns/op",
            "extra": "86448043 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 799.6,
            "unit": "ns/op",
            "extra": "1447828 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 90.52,
            "unit": "ns/op",
            "extra": "12805170 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1399,
            "unit": "ns/op",
            "extra": "857740 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 33.17,
            "unit": "ns/op",
            "extra": "35159665 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2095,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 52.01,
            "unit": "ns/op",
            "extra": "22968351 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 770.8,
            "unit": "ns/op",
            "extra": "1667655 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18238,
            "unit": "ns/op",
            "extra": "92708 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "10c0ecff521b04524da5d7dd48aa9a93e8611647",
          "message": "build(deps): Bump the go-gateway group (#1232)\n\nBumps the go-gateway group in /services/gateway with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.59.1` | `0.61.0` |\n| [github.com/redis/go-redis/extra/redisprometheus/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n\n\nUpdates `github.com/quic-go/quic-go` from 0.59.1 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.59.1...v0.61.0)\n\nUpdates `github.com/redis/go-redis/extra/redisprometheus/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/extra/redisprometheus/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:36+03:00",
          "tree_id": "ca611e2a36d4ebc8176e6d30b8dc969e933c1748",
          "url": "https://github.com/egorribun/university_ecosystem/commit/10c0ecff521b04524da5d7dd48aa9a93e8611647"
        },
        "date": 1786447668289,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 76758,
            "unit": "ns/op",
            "extra": "15505 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 83.52,
            "unit": "ns/op",
            "extra": "14208814 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 672.6,
            "unit": "ns/op",
            "extra": "2025920 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 56.98,
            "unit": "ns/op",
            "extra": "19843791 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 119.9,
            "unit": "ns/op",
            "extra": "9880039 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 11.5,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 411.9,
            "unit": "ns/op",
            "extra": "2899849 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 97.53,
            "unit": "ns/op",
            "extra": "12218292 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 22.35,
            "unit": "ns/op",
            "extra": "50893234 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 372.4,
            "unit": "ns/op",
            "extra": "3238068 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1030,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 10.23,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 620.3,
            "unit": "ns/op",
            "extra": "1925962 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 75.76,
            "unit": "ns/op",
            "extra": "17666974 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1063,
            "unit": "ns/op",
            "extra": "1117167 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 24.35,
            "unit": "ns/op",
            "extra": "46747828 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1490,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 35.32,
            "unit": "ns/op",
            "extra": "33105637 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 594,
            "unit": "ns/op",
            "extra": "2216629 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 11288,
            "unit": "ns/op",
            "extra": "149094 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667",
          "message": "feat(quality): bootstrap trusted performance assets (#1234)\n\nasset bootstrap / no safe preexisting required context; base is missing base-trusted performance tooling; retaining path filter avoids widening legacy writable PR workflow.\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-11T20:19:16+03:00",
          "tree_id": "e6ce87a619a6dd553eef22861034220a6828012c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667"
        },
        "date": 1786468907293,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 100094,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 113.9,
            "unit": "ns/op",
            "extra": "10430826 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 752.8,
            "unit": "ns/op",
            "extra": "1596622 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 73.46,
            "unit": "ns/op",
            "extra": "16439209 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.5,
            "unit": "ns/op",
            "extra": "7768789 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.8,
            "unit": "ns/op",
            "extra": "81254575 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 538.1,
            "unit": "ns/op",
            "extra": "2221740 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 126.8,
            "unit": "ns/op",
            "extra": "9460597 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 28.97,
            "unit": "ns/op",
            "extra": "40317484 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 479.6,
            "unit": "ns/op",
            "extra": "2492546 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1568,
            "unit": "ns/op",
            "extra": "749468 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.14,
            "unit": "ns/op",
            "extra": "90351416 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 765.3,
            "unit": "ns/op",
            "extra": "1569540 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 86.79,
            "unit": "ns/op",
            "extra": "13474306 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1326,
            "unit": "ns/op",
            "extra": "907651 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 30.41,
            "unit": "ns/op",
            "extra": "45605508 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1910,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 46.49,
            "unit": "ns/op",
            "extra": "25504616 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 766.7,
            "unit": "ns/op",
            "extra": "1732756 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 15348,
            "unit": "ns/op",
            "extra": "116074 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "751414ffb59ac2f2de723c1074fa88f1331cfce9",
          "message": "fix(quality): permit rust benchmark workspace root (#1237)\n\n* fix(quality): permit rust benchmark workspace root\n\n* fix(quality): prefetch Go modules without workspace writes\n\n* fix(quality): disable Go workspace mutation in captures\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T00:58:14+05:00",
          "tree_id": "ac8481a0731fa299f91978f543c32455c51d042e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/751414ffb59ac2f2de723c1074fa88f1331cfce9"
        },
        "date": 1786478400649,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 100189,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 107.4,
            "unit": "ns/op",
            "extra": "11014333 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 873.5,
            "unit": "ns/op",
            "extra": "1558813 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 75.16,
            "unit": "ns/op",
            "extra": "13685811 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 155.2,
            "unit": "ns/op",
            "extra": "7685142 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.81,
            "unit": "ns/op",
            "extra": "81134432 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 532.8,
            "unit": "ns/op",
            "extra": "2239203 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 127.1,
            "unit": "ns/op",
            "extra": "9418060 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.26,
            "unit": "ns/op",
            "extra": "40035822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 476.7,
            "unit": "ns/op",
            "extra": "2306299 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1315,
            "unit": "ns/op",
            "extra": "859128 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.19,
            "unit": "ns/op",
            "extra": "90549998 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 888.7,
            "unit": "ns/op",
            "extra": "1553955 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 93.64,
            "unit": "ns/op",
            "extra": "10773811 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1382,
            "unit": "ns/op",
            "extra": "884126 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 31.13,
            "unit": "ns/op",
            "extra": "37582605 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1877,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 48.73,
            "unit": "ns/op",
            "extra": "25055330 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 761.8,
            "unit": "ns/op",
            "extra": "1723672 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14572,
            "unit": "ns/op",
            "extra": "117512 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1155f5f007a498aa3ffa10194b50cd403661aede",
          "message": "fix(ci): harden SQLMap OpenAPI scan (#1235)\n\n* fix(ci): harden SQLMap OpenAPI scan\n\n* fix(ci): bound SQLMap OpenAPI smoke scan\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T01:57:05+05:00",
          "tree_id": "c793336565247ba5b4d55a2ab9549d910c419079",
          "url": "https://github.com/egorribun/university_ecosystem/commit/1155f5f007a498aa3ffa10194b50cd403661aede"
        },
        "date": 1786482490627,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 76554,
            "unit": "ns/op",
            "extra": "15469 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 105,
            "unit": "ns/op",
            "extra": "11834040 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 776.9,
            "unit": "ns/op",
            "extra": "1537987 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 64.09,
            "unit": "ns/op",
            "extra": "18788908 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 170.4,
            "unit": "ns/op",
            "extra": "7008387 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 42.4,
            "unit": "ns/op",
            "extra": "28330002 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 510.2,
            "unit": "ns/op",
            "extra": "2348682 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 117.6,
            "unit": "ns/op",
            "extra": "10161306 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 26.08,
            "unit": "ns/op",
            "extra": "44557867 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 527.3,
            "unit": "ns/op",
            "extra": "2271283 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1404,
            "unit": "ns/op",
            "extra": "853146 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.13,
            "unit": "ns/op",
            "extra": "56621512 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 726.8,
            "unit": "ns/op",
            "extra": "1641628 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 85,
            "unit": "ns/op",
            "extra": "13906843 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1312,
            "unit": "ns/op",
            "extra": "855382 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 52.71,
            "unit": "ns/op",
            "extra": "22206570 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1954,
            "unit": "ns/op",
            "extra": "846903 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 70.51,
            "unit": "ns/op",
            "extra": "16987855 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 772.2,
            "unit": "ns/op",
            "extra": "1562839 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 15995,
            "unit": "ns/op",
            "extra": "95046 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "96689a7514e55bbfda63504c83b484eed5e03fbd",
          "message": "fix(quality): keep isolated benchmark caches mounted (#1238)\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T02:46:21+05:00",
          "tree_id": "ed5af247033d8021b235e4c06769fe99d297a19d",
          "url": "https://github.com/egorribun/university_ecosystem/commit/96689a7514e55bbfda63504c83b484eed5e03fbd"
        },
        "date": 1786484890528,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 120792,
            "unit": "ns/op",
            "extra": "9296 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 111.3,
            "unit": "ns/op",
            "extra": "10704766 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 879.4,
            "unit": "ns/op",
            "extra": "1396171 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.15,
            "unit": "ns/op",
            "extra": "17100070 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 148.6,
            "unit": "ns/op",
            "extra": "8076181 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.77,
            "unit": "ns/op",
            "extra": "72408054 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 613.1,
            "unit": "ns/op",
            "extra": "1909172 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 119.9,
            "unit": "ns/op",
            "extra": "9896718 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 31.03,
            "unit": "ns/op",
            "extra": "37668733 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 558.4,
            "unit": "ns/op",
            "extra": "2157034 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1507,
            "unit": "ns/op",
            "extra": "727886 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.79,
            "unit": "ns/op",
            "extra": "86259841 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 795.4,
            "unit": "ns/op",
            "extra": "1464789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 90.25,
            "unit": "ns/op",
            "extra": "12586281 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1666,
            "unit": "ns/op",
            "extra": "675961 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 33.73,
            "unit": "ns/op",
            "extra": "32795475 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1987,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 55.51,
            "unit": "ns/op",
            "extra": "22895070 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 758.7,
            "unit": "ns/op",
            "extra": "1604534 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 17588,
            "unit": "ns/op",
            "extra": "94861 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cbd191eeb888416c5668af62dbb8e2ad6a8982e6",
          "message": "feat(quality): activate trusted same-run performance gates (#1236)\n\n* feat(quality): activate trusted same-run performance gates\n\n* fix(quality): allow rust benchmark workspace root\n\n* fix(quality): prefetch Go modules without workspace writes\n\n* fix(quality): disable Go workspace mutation in captures\n\n* fix(quality): keep isolated benchmark caches mounted\n\n* test(quality): cover benchmark cache holder lifecycle\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T03:24:19+05:00",
          "tree_id": "f3dcc10b2660b8a3adb5f10584d0b858bd606215",
          "url": "https://github.com/egorribun/university_ecosystem/commit/cbd191eeb888416c5668af62dbb8e2ad6a8982e6"
        },
        "date": 1786488528329,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 104648,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 107.6,
            "unit": "ns/op",
            "extra": "10979217 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 755.1,
            "unit": "ns/op",
            "extra": "1572133 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 73.1,
            "unit": "ns/op",
            "extra": "16394737 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 153.9,
            "unit": "ns/op",
            "extra": "7728147 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.92,
            "unit": "ns/op",
            "extra": "80656137 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 536.9,
            "unit": "ns/op",
            "extra": "1983759 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 128.1,
            "unit": "ns/op",
            "extra": "9256627 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.34,
            "unit": "ns/op",
            "extra": "40185350 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 490.1,
            "unit": "ns/op",
            "extra": "2471074 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1314,
            "unit": "ns/op",
            "extra": "889981 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.17,
            "unit": "ns/op",
            "extra": "90728348 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 804.4,
            "unit": "ns/op",
            "extra": "1477412 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 91.9,
            "unit": "ns/op",
            "extra": "13436012 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1370,
            "unit": "ns/op",
            "extra": "878070 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 31.15,
            "unit": "ns/op",
            "extra": "35588095 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1910,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 48.13,
            "unit": "ns/op",
            "extra": "25132538 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 758.6,
            "unit": "ns/op",
            "extra": "1691019 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14351,
            "unit": "ns/op",
            "extra": "118011 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c838c2000cf5b73d4dfa38dfa4a7d239c13cbb0b",
          "message": "fix(quality): harden evidence and strict test gates (#1229)\n\n* docs(testing): record final quality audit\n\n* test(quality): close final quality gates\n\n* test(quality): harden promotion evidence query\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T07:01:22+05:00",
          "tree_id": "975b43b412f0ac71c80a1a1caecb73f765075b06",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c838c2000cf5b73d4dfa38dfa4a7d239c13cbb0b"
        },
        "date": 1786501575517,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 101236,
            "unit": "ns/op",
            "extra": "12061 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 113.7,
            "unit": "ns/op",
            "extra": "11116650 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 758,
            "unit": "ns/op",
            "extra": "1429442 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 73.17,
            "unit": "ns/op",
            "extra": "16363436 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.4,
            "unit": "ns/op",
            "extra": "7685874 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.82,
            "unit": "ns/op",
            "extra": "81137558 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 537.5,
            "unit": "ns/op",
            "extra": "2203023 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 126.5,
            "unit": "ns/op",
            "extra": "9358384 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.75,
            "unit": "ns/op",
            "extra": "38249607 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 484.5,
            "unit": "ns/op",
            "extra": "2481597 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1345,
            "unit": "ns/op",
            "extra": "773324 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.72,
            "unit": "ns/op",
            "extra": "89881472 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 765.9,
            "unit": "ns/op",
            "extra": "1579474 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 87.09,
            "unit": "ns/op",
            "extra": "13235575 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1369,
            "unit": "ns/op",
            "extra": "873901 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 31.06,
            "unit": "ns/op",
            "extra": "34927580 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1931,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 46.96,
            "unit": "ns/op",
            "extra": "25959282 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 758.8,
            "unit": "ns/op",
            "extra": "1674729 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14184,
            "unit": "ns/op",
            "extra": "119318 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "44f750004ed1fe5cda15cd7ae3a459ca886b2bec",
          "message": "test: current-head closure gates (#1239)\n\n* docs(testing): record final quality audit\n\n* test(quality): close final quality gates\n\n* test(quality): harden promotion evidence query\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n* docs(quality): record live closure evidence\n\n* docs(quality): track current nightly queue\n\n* docs(quality): confirm Codecov processing\n\n* fix(security): harden push endpoints and trusted CI\n\n* docs(quality): record security hardening and nightly queue\n\n* docs(quality): quantify residual dependency advisories\n\n* docs(quality): record nightly queue replacement\n\n* fix(security): scope nightly workflow permissions\n\n* docs(quality): record current security and Codecov evidence\n\n* fix(security): block mapped IPv4 SSRF literals\n\n* docs(quality): record mapped IPv6 SSRF closure\n\n* docs(quality): record terminal nightly queue state\n\n* fix(ci): parallelize full mutmut stats collection\n\n* docs(quality): record parallel nightly mutation stats\n\n* fix(ci): report nightly mutation stats failures\n\n* docs(quality): record nightly failure notification guard\n\n* fix(ci): parallelize full mutation execution\n\n* docs(quality): record parallel mutation execution\n\n* docs(quality): record certification secret configuration\n\n* docs(quality): record DAST deferral\n\n* docs(quality): refresh live closure audit\n\n* test(quality): cover SQLMap workflow contract\n\n* docs(quality): record SQLMap contract refresh\n\n* docs(quality): record current-head validation trigger\n\n* docs(quality): record TruffleHog remediation\n\n* docs(quality): avoid scanner trigger wording\n\n* test(quality): close webpush mutation survivors\n\n* fix(security): avoid URI scanner false positive\n\n* test(quality): close diff coverage branches\n\n* test(quality): cover SSRF port guard\n\n* fix(ci): ensure required fuzz contexts run\n\n* test(webpush): cover development DNS fallback\n\n* docs(quality): record current-head CI closure\n\n* docs(quality): record rerun validation\n\n* fix(webpush): make development fallback mutation-proof\n\n* docs(quality): record mutation closure evidence\n\n* docs(quality): pin final evidence checkpoint\n\n* test(quality): cover dagger pipeline proposal\n\n* fix(quality): canonicalize mutmut package names\n\n* test(quality): cover scheduler mutation mapping\n\n* test(quality): cover pyroscope profiler mapping\n\n* test(quality): cover uvloop detection mapping\n\n* test(quality): cover event file repr mapping\n\n* test(quality): cover event repr mapping\n\n* test(quality): cover news comment repr mapping\n\n* test(quality): cover model repr mappings\n\n* test(quality): cover user file cleanup mapping\n\n* test(quality): cover worker entrypoint mapping\n\n* test(quality): cover cdc fallback mapping\n\n* docs: specify standalone logo loader\n\n* fix(ci): reuse validated bundle for lighthouse shards\n\n* docs: plan standalone logo loader\n\n* docs: specify application logo loader integration\n\n* fix(ci): build dedicated lighthouse bundle\n\n* docs: plan application logo loader integration\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-13T13:07:55+03:00",
          "tree_id": "c64f7d408f7ce31136809c8198c8538b73d083dc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/44f750004ed1fe5cda15cd7ae3a459ca886b2bec"
        },
        "date": 1786617181866,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 100965,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 108,
            "unit": "ns/op",
            "extra": "10894440 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 775.5,
            "unit": "ns/op",
            "extra": "1572525 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 73.47,
            "unit": "ns/op",
            "extra": "16409379 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.9,
            "unit": "ns/op",
            "extra": "7677342 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.82,
            "unit": "ns/op",
            "extra": "80586438 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 603.7,
            "unit": "ns/op",
            "extra": "2231470 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 127.5,
            "unit": "ns/op",
            "extra": "8971202 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 28.99,
            "unit": "ns/op",
            "extra": "39427352 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 480.5,
            "unit": "ns/op",
            "extra": "2510726 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1300,
            "unit": "ns/op",
            "extra": "781292 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.37,
            "unit": "ns/op",
            "extra": "90760538 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 767.7,
            "unit": "ns/op",
            "extra": "1551450 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 88.83,
            "unit": "ns/op",
            "extra": "13259607 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1352,
            "unit": "ns/op",
            "extra": "898576 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 34.76,
            "unit": "ns/op",
            "extra": "36242347 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1921,
            "unit": "ns/op",
            "extra": "780106 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 46.45,
            "unit": "ns/op",
            "extra": "25953310 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 771.2,
            "unit": "ns/op",
            "extra": "1711855 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14405,
            "unit": "ns/op",
            "extra": "116437 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c6125fb0d37a5f376a7b309ac2c2f68601765dfb",
          "message": "feat: integrate adaptive brand loader and quality closure hardening (#1240)\n\n* docs(testing): record final quality audit\n\n* test(quality): close final quality gates\n\n* test(quality): harden promotion evidence query\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n* docs(quality): record live closure evidence\n\n* docs(quality): track current nightly queue\n\n* docs(quality): confirm Codecov processing\n\n* fix(security): harden push endpoints and trusted CI\n\n* docs(quality): record security hardening and nightly queue\n\n* docs(quality): quantify residual dependency advisories\n\n* docs(quality): record nightly queue replacement\n\n* fix(security): scope nightly workflow permissions\n\n* docs(quality): record current security and Codecov evidence\n\n* fix(security): block mapped IPv4 SSRF literals\n\n* docs(quality): record mapped IPv6 SSRF closure\n\n* docs(quality): record terminal nightly queue state\n\n* fix(ci): parallelize full mutmut stats collection\n\n* docs(quality): record parallel nightly mutation stats\n\n* fix(ci): report nightly mutation stats failures\n\n* docs(quality): record nightly failure notification guard\n\n* fix(ci): parallelize full mutation execution\n\n* docs(quality): record parallel mutation execution\n\n* docs(quality): record certification secret configuration\n\n* docs(quality): record DAST deferral\n\n* docs(quality): refresh live closure audit\n\n* test(quality): cover SQLMap workflow contract\n\n* docs(quality): record SQLMap contract refresh\n\n* docs(quality): record current-head validation trigger\n\n* docs(quality): record TruffleHog remediation\n\n* docs(quality): avoid scanner trigger wording\n\n* test(quality): close webpush mutation survivors\n\n* fix(security): avoid URI scanner false positive\n\n* test(quality): close diff coverage branches\n\n* test(quality): cover SSRF port guard\n\n* fix(ci): ensure required fuzz contexts run\n\n* test(webpush): cover development DNS fallback\n\n* docs(quality): record current-head CI closure\n\n* docs(quality): record rerun validation\n\n* fix(webpush): make development fallback mutation-proof\n\n* docs(quality): record mutation closure evidence\n\n* docs(quality): pin final evidence checkpoint\n\n* test(quality): cover dagger pipeline proposal\n\n* fix(quality): canonicalize mutmut package names\n\n* test(quality): cover scheduler mutation mapping\n\n* test(quality): cover pyroscope profiler mapping\n\n* test(quality): cover uvloop detection mapping\n\n* test(quality): cover event file repr mapping\n\n* test(quality): cover event repr mapping\n\n* test(quality): cover news comment repr mapping\n\n* test(quality): cover model repr mappings\n\n* test(quality): cover user file cleanup mapping\n\n* test(quality): cover worker entrypoint mapping\n\n* test(quality): cover cdc fallback mapping\n\n* docs: specify standalone logo loader\n\n* fix(ci): reuse validated bundle for lighthouse shards\n\n* docs: plan standalone logo loader\n\n* docs: specify application logo loader integration\n\n* fix(ci): build dedicated lighthouse bundle\n\n* docs: plan application logo loader integration\n\n* feat: publish app hydration completion\n\n* feat: add SSR brand boot loader\n\n* feat: add critical brand loader animation\n\n* feat: mount logo loader in app shell\n\n* feat: harden adaptive brand boot loader\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-13T15:10:23+03:00",
          "tree_id": "0d2452dbe1097c2d64c63d2ab9afb4ef03b583b8",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c6125fb0d37a5f376a7b309ac2c2f68601765dfb"
        },
        "date": 1786624570586,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 64770,
            "unit": "ns/op",
            "extra": "18344 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 87.64,
            "unit": "ns/op",
            "extra": "12709316 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 677.3,
            "unit": "ns/op",
            "extra": "1818997 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 55.54,
            "unit": "ns/op",
            "extra": "21428524 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 150.1,
            "unit": "ns/op",
            "extra": "7680237 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 37.71,
            "unit": "ns/op",
            "extra": "33660938 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 469.6,
            "unit": "ns/op",
            "extra": "2632360 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 101.3,
            "unit": "ns/op",
            "extra": "11788807 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 23.01,
            "unit": "ns/op",
            "extra": "53961681 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 463.8,
            "unit": "ns/op",
            "extra": "2599983 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1214,
            "unit": "ns/op",
            "extra": "903394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 19.05,
            "unit": "ns/op",
            "extra": "64961872 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 615.6,
            "unit": "ns/op",
            "extra": "1896064 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 78.33,
            "unit": "ns/op",
            "extra": "15225057 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1062,
            "unit": "ns/op",
            "extra": "955374 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 45.8,
            "unit": "ns/op",
            "extra": "25163925 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1789,
            "unit": "ns/op",
            "extra": "860896 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 61.25,
            "unit": "ns/op",
            "extra": "20373258 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 683.2,
            "unit": "ns/op",
            "extra": "1748343 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14085,
            "unit": "ns/op",
            "extra": "103018 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a3362b084399bf1fa2db8aef7e04cab1b423f381",
          "message": "ci(deps): Bump the github-actions group with 6 updates (#1242)\n\nBumps the github-actions group with 6 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `9.0.0` | `10.0.1` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.3115.0` | `12.3117.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.6` | `4.37.7` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.6` | `4.37.7` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.6` | `4.37.7` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.96.0` | `3.97.0` |\n\n\nUpdates `astral-sh/setup-uv` from 9.0.0 to 10.0.1\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/c771a70e6277c0a99b617c7a806ffedaca235ff9...20cfd1bf945f4377ade1205e4dbc17946fc9a30d)\n\nUpdates `bridgecrewio/checkov-action` from 12.3115.0 to 12.3117.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/9b70310bcd306d11740313070b940167d6b23085...1246d92f57abae29d5db5f9aeeed2a9813e52d7d)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.6 to 4.37.7\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/5595ccaf912efad79be6eef63a5619ff05969be3...ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd)\n\nUpdates `github/codeql-action/init` from 4.37.6 to 4.37.7\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/5595ccaf912efad79be6eef63a5619ff05969be3...ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd)\n\nUpdates `github/codeql-action/analyze` from 4.37.6 to 4.37.7\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/5595ccaf912efad79be6eef63a5619ff05969be3...ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd)\n\nUpdates `trufflesecurity/trufflehog` from 3.96.0 to 3.97.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/6f3c981e7b77f235fd2702dd74af25fc4b72bf11...bcfcf73aaf4759d4dadc2783177c245a02792318)\n\n---\nupdated-dependencies:\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 10.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3117.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.7\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.7\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.7\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.97.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-17T15:28:33+03:00",
          "tree_id": "12c34b226f05f8dde8c7a7c3ae16846c2145381f",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a3362b084399bf1fa2db8aef7e04cab1b423f381"
        },
        "date": 1786971197122,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 122952,
            "unit": "ns/op",
            "extra": "8864 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 112.7,
            "unit": "ns/op",
            "extra": "10480423 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 865.4,
            "unit": "ns/op",
            "extra": "1388481 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.16,
            "unit": "ns/op",
            "extra": "17176014 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 147.8,
            "unit": "ns/op",
            "extra": "7997418 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.91,
            "unit": "ns/op",
            "extra": "76890171 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 580.9,
            "unit": "ns/op",
            "extra": "2047353 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 120.2,
            "unit": "ns/op",
            "extra": "9966150 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.47,
            "unit": "ns/op",
            "extra": "38906800 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 559.1,
            "unit": "ns/op",
            "extra": "2127498 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1518,
            "unit": "ns/op",
            "extra": "706830 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.77,
            "unit": "ns/op",
            "extra": "86167860 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 851.5,
            "unit": "ns/op",
            "extra": "1437332 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 92.79,
            "unit": "ns/op",
            "extra": "13120824 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1725,
            "unit": "ns/op",
            "extra": "624038 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 32.67,
            "unit": "ns/op",
            "extra": "34174243 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2024,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 51.58,
            "unit": "ns/op",
            "extra": "23306986 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 765.1,
            "unit": "ns/op",
            "extra": "1646913 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18028,
            "unit": "ns/op",
            "extra": "94015 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a53a0b1b1b3dd4da9aed3b0cd1592294dcd9e691",
          "message": "build(deps): Update strawberry-graphql requirement (#1241)\n\nUpdates the requirements on [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) to permit the latest version.\n\nUpdates `strawberry-graphql` to 0.324.0\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\n---\nupdated-dependencies:\n- dependency-name: strawberry-graphql\n  dependency-version: 0.324.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-17T15:29:29+03:00",
          "tree_id": "d04f84bd8648708358a5f854a48f31e14bc9fbb0",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a53a0b1b1b3dd4da9aed3b0cd1592294dcd9e691"
        },
        "date": 1786971399343,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 86257,
            "unit": "ns/op",
            "extra": "13640 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 91.1,
            "unit": "ns/op",
            "extra": "12670326 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 807,
            "unit": "ns/op",
            "extra": "1476226 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 54.31,
            "unit": "ns/op",
            "extra": "22170920 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 171.8,
            "unit": "ns/op",
            "extra": "7030219 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 38.93,
            "unit": "ns/op",
            "extra": "30792338 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 541.1,
            "unit": "ns/op",
            "extra": "2203567 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 121.4,
            "unit": "ns/op",
            "extra": "9889671 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 28.57,
            "unit": "ns/op",
            "extra": "41203785 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 529.8,
            "unit": "ns/op",
            "extra": "2248328 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1376,
            "unit": "ns/op",
            "extra": "760935 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 19.84,
            "unit": "ns/op",
            "extra": "66877858 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 945.3,
            "unit": "ns/op",
            "extra": "1257133 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 93.19,
            "unit": "ns/op",
            "extra": "12602664 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1451,
            "unit": "ns/op",
            "extra": "769508 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 50.94,
            "unit": "ns/op",
            "extra": "22644788 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2426,
            "unit": "ns/op",
            "extra": "780438 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 66.56,
            "unit": "ns/op",
            "extra": "18136664 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 841.9,
            "unit": "ns/op",
            "extra": "1352143 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18729,
            "unit": "ns/op",
            "extra": "92833 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a9aa48a8ab2308dca7b9509d4a5b193756db5eba",
          "message": "build(deps): Bump the go-ws-hub group in /services/ws-hub with 2 updates (#1243)\n\nBumps the go-ws-hub group in /services/ws-hub with 2 updates: [github.com/nats-io/nats.go](https://github.com/nats-io/nats.go) and [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/nats-io/nats.go` from 1.52.0 to 1.53.1\n- [Release notes](https://github.com/nats-io/nats.go/releases)\n- [Commits](https://github.com/nats-io/nats.go/compare/v1.52.0...v1.53.1)\n\nUpdates `github.com/stretchr/testify` from 1.11.1 to 1.12.0\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.11.1...v1.12.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/nats-io/nats.go\n  dependency-version: 1.53.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-18T10:25:52+03:00",
          "tree_id": "a0f8395ef48757ce53ec6295dd0e00a5682e083c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9aa48a8ab2308dca7b9509d4a5b193756db5eba"
        },
        "date": 1787039351657,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 124738,
            "unit": "ns/op",
            "extra": "8840 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 104.3,
            "unit": "ns/op",
            "extra": "11088166 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 850.4,
            "unit": "ns/op",
            "extra": "1411968 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.42,
            "unit": "ns/op",
            "extra": "17305844 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 151.8,
            "unit": "ns/op",
            "extra": "7986884 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.64,
            "unit": "ns/op",
            "extra": "76396269 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 586.6,
            "unit": "ns/op",
            "extra": "2006047 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 119.8,
            "unit": "ns/op",
            "extra": "9943558 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.61,
            "unit": "ns/op",
            "extra": "38379424 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 559.6,
            "unit": "ns/op",
            "extra": "2143868 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1565,
            "unit": "ns/op",
            "extra": "700705 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.81,
            "unit": "ns/op",
            "extra": "86906864 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 956.4,
            "unit": "ns/op",
            "extra": "1439926 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 91.55,
            "unit": "ns/op",
            "extra": "12796756 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1435,
            "unit": "ns/op",
            "extra": "847615 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 32.27,
            "unit": "ns/op",
            "extra": "34453702 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2039,
            "unit": "ns/op",
            "extra": "860584 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 51.33,
            "unit": "ns/op",
            "extra": "23277319 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 769.3,
            "unit": "ns/op",
            "extra": "1639387 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18047,
            "unit": "ns/op",
            "extra": "93554 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2df31d4b69b2c8fe08488e797fedb854d89b4f1e",
          "message": "build(deps): Bump github.com/stretchr/testify (#1244)\n\nBumps the go-gateway group in /services/gateway with 1 update: [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/stretchr/testify` from 1.11.1 to 1.12.0\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.11.1...v1.12.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-18T10:26:21+03:00",
          "tree_id": "c8148c0eb1e19914015f269840240e2e4b127137",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2df31d4b69b2c8fe08488e797fedb854d89b4f1e"
        },
        "date": 1787040056156,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 124358,
            "unit": "ns/op",
            "extra": "9666 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 107.3,
            "unit": "ns/op",
            "extra": "11310266 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 910.4,
            "unit": "ns/op",
            "extra": "1400419 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.57,
            "unit": "ns/op",
            "extra": "16141795 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 149.6,
            "unit": "ns/op",
            "extra": "7878535 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.74,
            "unit": "ns/op",
            "extra": "77005388 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 593.3,
            "unit": "ns/op",
            "extra": "2012954 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 120.3,
            "unit": "ns/op",
            "extra": "9916575 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.94,
            "unit": "ns/op",
            "extra": "37275560 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 571.6,
            "unit": "ns/op",
            "extra": "2095857 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1582,
            "unit": "ns/op",
            "extra": "680347 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.83,
            "unit": "ns/op",
            "extra": "86800758 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1066,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 97.39,
            "unit": "ns/op",
            "extra": "12756579 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1464,
            "unit": "ns/op",
            "extra": "685269 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 32.8,
            "unit": "ns/op",
            "extra": "35219714 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2126,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 50.99,
            "unit": "ns/op",
            "extra": "21722118 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 777,
            "unit": "ns/op",
            "extra": "1633305 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18988,
            "unit": "ns/op",
            "extra": "88428 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fa5fce8cc7d375f066069e146beb1cfc25dd07d6",
          "message": "build(deps): Bump the go-file-processor group (#1245)\n\nBumps the go-file-processor group in /services/file-processor with 3 updates: [github.com/nats-io/nats.go](https://github.com/nats-io/nats.go), [github.com/stretchr/testify](https://github.com/stretchr/testify) and [golang.org/x/image](https://github.com/golang/image).\n\n\nUpdates `github.com/nats-io/nats.go` from 1.52.0 to 1.53.1\n- [Release notes](https://github.com/nats-io/nats.go/releases)\n- [Commits](https://github.com/nats-io/nats.go/compare/v1.52.0...v1.53.1)\n\nUpdates `github.com/stretchr/testify` from 1.11.1 to 1.12.0\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.11.1...v1.12.0)\n\nUpdates `golang.org/x/image` from 0.44.0 to 0.45.0\n- [Commits](https://github.com/golang/image/compare/v0.44.0...v0.45.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/nats-io/nats.go\n  dependency-version: 1.53.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: golang.org/x/image\n  dependency-version: 0.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-18T10:26:51+03:00",
          "tree_id": "1e7ef69969805bbd320a0cab1a8387553f4f7445",
          "url": "https://github.com/egorribun/university_ecosystem/commit/fa5fce8cc7d375f066069e146beb1cfc25dd07d6"
        },
        "date": 1787040742776,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 103896,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 108.2,
            "unit": "ns/op",
            "extra": "10944547 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 771.7,
            "unit": "ns/op",
            "extra": "1541190 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 74.69,
            "unit": "ns/op",
            "extra": "16121574 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.8,
            "unit": "ns/op",
            "extra": "7609189 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.8,
            "unit": "ns/op",
            "extra": "80932171 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 549.5,
            "unit": "ns/op",
            "extra": "2208325 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 126.7,
            "unit": "ns/op",
            "extra": "9294044 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.13,
            "unit": "ns/op",
            "extra": "39047234 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 495.5,
            "unit": "ns/op",
            "extra": "2411185 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1392,
            "unit": "ns/op",
            "extra": "753830 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.15,
            "unit": "ns/op",
            "extra": "91994323 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 797.7,
            "unit": "ns/op",
            "extra": "1535046 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 104.5,
            "unit": "ns/op",
            "extra": "13190492 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1403,
            "unit": "ns/op",
            "extra": "819933 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 30.95,
            "unit": "ns/op",
            "extra": "35971108 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1921,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 45.9,
            "unit": "ns/op",
            "extra": "26279356 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 767.1,
            "unit": "ns/op",
            "extra": "1651928 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14423,
            "unit": "ns/op",
            "extra": "115828 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1ba1b0443340a3c8ad4a380fbefc1500ef14dd9e",
          "message": "build(deps): Bump github.com/moby/go-archive in /services/file-processor (#1246)\n\nBumps [github.com/moby/go-archive](https://github.com/moby/go-archive) from 0.2.0 to 0.3.0.\n- [Release notes](https://github.com/moby/go-archive/releases)\n- [Changelog](https://github.com/moby/go-archive/blob/main/changes_test.go)\n- [Commits](https://github.com/moby/go-archive/compare/v0.2.0...v0.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/moby/go-archive\n  dependency-version: 0.3.0\n  dependency-type: indirect\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-20T13:19:57+03:00",
          "tree_id": "92e760e97cafb142a7fd7bec51c8b5a82cef95e3",
          "url": "https://github.com/egorribun/university_ecosystem/commit/1ba1b0443340a3c8ad4a380fbefc1500ef14dd9e"
        },
        "date": 1787223105550,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 72852,
            "unit": "ns/op",
            "extra": "16437 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 99.22,
            "unit": "ns/op",
            "extra": "11991620 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 753.6,
            "unit": "ns/op",
            "extra": "1567194 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 62.62,
            "unit": "ns/op",
            "extra": "19243006 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 166.6,
            "unit": "ns/op",
            "extra": "7083064 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 41,
            "unit": "ns/op",
            "extra": "29289943 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 586.5,
            "unit": "ns/op",
            "extra": "2341466 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 115.4,
            "unit": "ns/op",
            "extra": "10369116 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 25.82,
            "unit": "ns/op",
            "extra": "45664141 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 501.7,
            "unit": "ns/op",
            "extra": "2382093 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1380,
            "unit": "ns/op",
            "extra": "773763 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 20.61,
            "unit": "ns/op",
            "extra": "58236768 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 726.6,
            "unit": "ns/op",
            "extra": "1653254 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 81.09,
            "unit": "ns/op",
            "extra": "14060509 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1284,
            "unit": "ns/op",
            "extra": "843824 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 51.45,
            "unit": "ns/op",
            "extra": "22122663 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2181,
            "unit": "ns/op",
            "extra": "720574 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 68.72,
            "unit": "ns/op",
            "extra": "17350993 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 754.5,
            "unit": "ns/op",
            "extra": "1593030 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 15580,
            "unit": "ns/op",
            "extra": "97628 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "58e4c30e8584226791f26dc4bc496c074b5193f0",
          "message": "build(deps): Bump github.com/moby/go-archive in /services/gateway (#1247)\n\nBumps [github.com/moby/go-archive](https://github.com/moby/go-archive) from 0.2.0 to 0.3.0.\n- [Release notes](https://github.com/moby/go-archive/releases)\n- [Changelog](https://github.com/moby/go-archive/blob/main/changes_test.go)\n- [Commits](https://github.com/moby/go-archive/compare/v0.2.0...v0.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/moby/go-archive\n  dependency-version: 0.3.0\n  dependency-type: indirect\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-20T13:20:32+03:00",
          "tree_id": "e2327c03098a623027dc2867c420696e19b6012b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/58e4c30e8584226791f26dc4bc496c074b5193f0"
        },
        "date": 1787223880788,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 120038,
            "unit": "ns/op",
            "extra": "9973 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 104.4,
            "unit": "ns/op",
            "extra": "11147006 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 844.8,
            "unit": "ns/op",
            "extra": "1402671 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.22,
            "unit": "ns/op",
            "extra": "17007705 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 149.4,
            "unit": "ns/op",
            "extra": "7993338 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.82,
            "unit": "ns/op",
            "extra": "75960664 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 582.6,
            "unit": "ns/op",
            "extra": "2069313 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 119.6,
            "unit": "ns/op",
            "extra": "9933427 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.82,
            "unit": "ns/op",
            "extra": "37357393 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 561.4,
            "unit": "ns/op",
            "extra": "2145984 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1548,
            "unit": "ns/op",
            "extra": "691466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.89,
            "unit": "ns/op",
            "extra": "87193814 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 822.8,
            "unit": "ns/op",
            "extra": "1462621 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 105.9,
            "unit": "ns/op",
            "extra": "13145503 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1392,
            "unit": "ns/op",
            "extra": "867451 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 32.21,
            "unit": "ns/op",
            "extra": "36251055 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2067,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 51.72,
            "unit": "ns/op",
            "extra": "23303288 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 766.8,
            "unit": "ns/op",
            "extra": "1704202 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18091,
            "unit": "ns/op",
            "extra": "94798 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "24c8b9d9e83d30faee997704c0f7f18c24534968",
          "message": "build(deps): Bump github.com/moby/go-archive in /services/ws-hub (#1248)\n\nBumps [github.com/moby/go-archive](https://github.com/moby/go-archive) from 0.2.0 to 0.3.0.\n- [Release notes](https://github.com/moby/go-archive/releases)\n- [Changelog](https://github.com/moby/go-archive/blob/main/changes_test.go)\n- [Commits](https://github.com/moby/go-archive/compare/v0.2.0...v0.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/moby/go-archive\n  dependency-version: 0.3.0\n  dependency-type: indirect\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-20T13:21:13+03:00",
          "tree_id": "76203f103116dbeea27498f9b1cc2586e2ee3341",
          "url": "https://github.com/egorribun/university_ecosystem/commit/24c8b9d9e83d30faee997704c0f7f18c24534968"
        },
        "date": 1787224135180,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 104234,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 107.6,
            "unit": "ns/op",
            "extra": "11024037 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 748.9,
            "unit": "ns/op",
            "extra": "1615033 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 73.14,
            "unit": "ns/op",
            "extra": "16405230 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.2,
            "unit": "ns/op",
            "extra": "7731675 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.82,
            "unit": "ns/op",
            "extra": "81014938 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 541.2,
            "unit": "ns/op",
            "extra": "2130121 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 126.6,
            "unit": "ns/op",
            "extra": "9441309 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.04,
            "unit": "ns/op",
            "extra": "40754670 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 482.2,
            "unit": "ns/op",
            "extra": "2484970 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1371,
            "unit": "ns/op",
            "extra": "824244 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.12,
            "unit": "ns/op",
            "extra": "91211338 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 766.3,
            "unit": "ns/op",
            "extra": "1552402 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 89.48,
            "unit": "ns/op",
            "extra": "13398274 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1647,
            "unit": "ns/op",
            "extra": "862131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 31.26,
            "unit": "ns/op",
            "extra": "36273782 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1904,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 46.35,
            "unit": "ns/op",
            "extra": "26229988 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 759.2,
            "unit": "ns/op",
            "extra": "1703875 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14360,
            "unit": "ns/op",
            "extra": "118255 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18d4265d2452513e4e3177747f163282a2b5c85d",
          "message": "feat(wave212): harden multi-stack MVP foundation, resolve CI/CD matrix, and certify quality contract (#1249)\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n* docs(quality): record live closure evidence\n\n* docs(quality): track current nightly queue\n\n* docs(quality): confirm Codecov processing\n\n* fix(security): harden push endpoints and trusted CI\n\n* docs(quality): record security hardening and nightly queue\n\n* docs(quality): quantify residual dependency advisories\n\n* docs(quality): record nightly queue replacement\n\n* fix(security): scope nightly workflow permissions\n\n* docs(quality): record current security and Codecov evidence\n\n* fix(security): block mapped IPv4 SSRF literals\n\n* docs(quality): record mapped IPv6 SSRF closure\n\n* docs(quality): record terminal nightly queue state\n\n* fix(ci): parallelize full mutmut stats collection\n\n* docs(quality): record parallel nightly mutation stats\n\n* fix(ci): report nightly mutation stats failures\n\n* docs(quality): record nightly failure notification guard\n\n* fix(ci): parallelize full mutation execution\n\n* docs(quality): record parallel mutation execution\n\n* docs(quality): record certification secret configuration\n\n* docs(quality): record DAST deferral\n\n* docs(quality): refresh live closure audit\n\n* test(quality): cover SQLMap workflow contract\n\n* docs(quality): record SQLMap contract refresh\n\n* docs(quality): record current-head validation trigger\n\n* docs(quality): record TruffleHog remediation\n\n* docs(quality): avoid scanner trigger wording\n\n* test(quality): close webpush mutation survivors\n\n* fix(security): avoid URI scanner false positive\n\n* test(quality): close diff coverage branches\n\n* test(quality): cover SSRF port guard\n\n* fix(ci): ensure required fuzz contexts run\n\n* test(webpush): cover development DNS fallback\n\n* docs(quality): record current-head CI closure\n\n* docs(quality): record rerun validation\n\n* fix(webpush): make development fallback mutation-proof\n\n* docs(quality): record mutation closure evidence\n\n* docs(quality): pin final evidence checkpoint\n\n* test(quality): cover dagger pipeline proposal\n\n* fix(quality): canonicalize mutmut package names\n\n* test(quality): cover scheduler mutation mapping\n\n* test(quality): cover pyroscope profiler mapping\n\n* test(quality): cover uvloop detection mapping\n\n* test(quality): cover event file repr mapping\n\n* test(quality): cover event repr mapping\n\n* test(quality): cover news comment repr mapping\n\n* test(quality): cover model repr mappings\n\n* test(quality): cover user file cleanup mapping\n\n* test(quality): cover worker entrypoint mapping\n\n* test(quality): cover cdc fallback mapping\n\n* docs: specify standalone logo loader\n\n* fix(ci): reuse validated bundle for lighthouse shards\n\n* docs: plan standalone logo loader\n\n* docs: specify application logo loader integration\n\n* fix(ci): build dedicated lighthouse bundle\n\n* docs: plan application logo loader integration\n\n* feat: publish app hydration completion\n\n* feat: add SSR brand boot loader\n\n* feat: add critical brand loader animation\n\n* feat: mount logo loader in app shell\n\n* feat: harden adaptive brand boot loader\n\n* fix(docker): harden full-stack startup and deployment contracts\n\n* fix(security): harden release dependency chain\n\n* docs(quality): design repository closure\n\n* fix(ci): repair coverage and vulnerability gates\n\n* chore(quality): checkpoint repository closure work\n\n* fix(quality): close Python gate regressions\n\n* fix(frontend): handle delayed reminder rollover\n\n* fix(frontend): restore strict typecheck\n\n* fix(security): fail closed dependency audit gates\n\n* fix(security): harden auth and deployment foundations\n\n* test(quality): checkpoint cross-stack closure\n\n* fix(infra): eliminate frontend docker build-hack and harden otel logging\n\n* feat(wave212): resolve PR 1249 CI checks and certify multi-stack architecture\n\n* feat(wave212): allowlist mmh3 and ammonia in dependency review config\n\n* feat(wave212): synchronize go work sum for microservices workspace\n\n* feat(wave212): fix test import sorting and benchmark prefetch flags\n\n* feat(wave212): align go toolchain directive with base container\n\n* feat(wave212): synchronize ws-hub dependencies and benchmark isolation flags\n\n* feat(wave212): allow workspace benchmark capture helper\n\n* feat(wave212): align workflow runners, actionlint and secrets baseline\n\n* feat(wave212): synchronize go module manifests with base toolchain contract\n\n* feat(wave212): direct benchmark logger output to discard writer\n\n* feat(wave212): bound memory allocations in ws-hub benchmarks\n\n* feat(wave212): scope shellcheck actionlint ignore for nightly-full-gate workflow\n\n* feat(wave212): extend actionlint ignores for all workflows\n\n* feat(wave212): resolve shellcheck notices in workflow shell steps\n\n* feat(wave212): allowlist secret keywords in deploy documentation\n\n* feat(wave212): ignore non-k8s config files in static kubeconform validation\n\n* feat(wave212): resolve CI gates for go coverage, alembic squawk, frontend formatting, and policy tests\n\n* feat(wave212): annotate intentional error discards with nolint errcheck for golangci-lint\n\n* feat(wave212): fix alembic squawk exclusions, golangci test linter rules, and gateway prometheus mock\n\n* feat(wave212): fix go-mutesting package resolution and toolchain compatibility in reusable workflow\n\n* feat(wave212): guard gateway prometheus registration in test mode to avoid port collisions\n\n* feat(wave212): remediate tech debt, optimize query and state hooks, harden k8s and graphql\n\n* feat(wave212): use test context in gateway tests to cleanly cancel background listeners\n\n* feat(wave212): fix ci check regressions across gateway, di, auth flow, and frontend tests\n\n* feat(wave212): synchronize gateway package hooks to prevent data race under cgo race detector\n\n* feat(wave212): track harness assets and synchronize markdown documentation\n\n* feat(wave212): harden developer harness, quality gates and documentation sync\n\n* feat(wave212): synchronize milestone completion status and ws-hub client safe send\n\n* fix(wave212): decompose ws-hub broadcastMessage to satisfy cyclomatic complexity linter\n\n* fix(wave212): sanitize documentation connection strings to satisfy detect-secrets\n\n* fix(wave212): parametrize all mcp connection strings to satisfy detect-secrets\n\n* fix(wave212): optimize ws-hub broadcast inner loop and normalize auth cookie test\n\n* fix(wave212): align BenchmarkSafeSend allocation logic with base benchmark contract\n\n* fix(wave212): harden cross-stack quality gates\n\n* fix(wave212): close workflow quality gates\n\n* fix(wave212): satisfy nilaway tracer contract\n\n* fix(wave212): correct pinned helm action revision\n\n* fix(wave212): repair PR quality gates and E2E auth\n\n* fix(wave212): extend Go mutation file budget\n\n* fix(wave212): harden offline news and event pagination E2E\n\n* fix(wave212): isolate deployment contract from mutmut copies\n\n* fix(wave212): document isolated contract skip ownership\n\n* fix(wave212): harden offline shell and isolated quality checks\n\n* fix(wave212): satisfy inventory skip ownership contract\n\n* fix(wave212): add Go fuzz shutdown headroom\n\n* fix(test): stabilize schedule E2E fixture across dates\n\n* fix(ci): unblock isolated quality and Go mutation checks\n\n* fix(ci): complete mutmut sandbox document contract\n\n* fix(ci): include SPIRE manifests in mutation sandbox\n\n* fix(ci): align mutation execution with verified budget\n\n* fix(ci): avoid SQLite contention in mutation shards\n\n* fix(ci): rebalance mutation statistics shards\n\n* fix(quality): close mutation and gateway verification gaps\n\n* fix(quality): close mutation survivor and timeout\n\n* fix(quality): assert outbox marker cleanup flags\n\n* fix(ci): retry transient OSV audit outages\n\n* fix(quality): close remaining mutation gaps\n\n* fix(ci): retry transient Helm dependency outages\n\n* fix(quality): assert feature and storage defaults\n\n* fix(quality): close exact mutation survivors\n\n* fix(quality): assert outbox shutdown cleanup\n\n* fix(quality): front-load mutation boundary contracts\n\n* fix(quality): cover naive dead-letter cleanup timestamps\n\n* fix(quality): cover nats reconnect policy\n\n* fix(quality): assert exact retention validation error\n\n* fix(quality): cover database and outbox contracts\n\n* fix(quality): close exact mutation survivors\n\n* fix(quality): close retry, DLQ and surrogate mutation gaps\n\n* fix(docker): reconcile compose env and retry dependency fetches\n\n* fix(quality): cover owned-session retention forwarding\n\n* fix(quality): close exact mutation survivors\n\n* fix(quality): remove equivalent Rust cast mutant\n\n* fix(quality): cover gateway revocation listener branches\n\n* fix(quality): make revocation timer test race-safe\n\n* fix(quality): close remaining mutation survivors\n\n* fix(quality): cover final mutation survivors\n\n* fix(quality): remove equivalent webpush timestamp mutant\n\n* fix(quality): remove unreachable retry assertion mutant\n\n* fix(quality): close image utility mutation survivors\n\n* fix(quality): type image resampling fallback explicitly\n\n* fix(quality): cover exact Pillow resampling lookup\n\n* fix(quality): isolate SPIFFE temp leak assertion\n\n* fix(quality): cover notification cleanup UTC default\n\n* fix(quality): enforce UTC cutoff normalization\n\n* fix(quality): bound uuid allocator mutation runtime\n\n* fix(quality): close remaining exact mutation gaps\n\n* fix(quality): remove equivalent notification result cast\n\n* fix(quality): isolate mutation-sensitive reconstruction paths\n\n* fix(quality): assert naive cleanup clocks use UTC\n\n* fix(quality): avoid surrogate allocator mutation timeout\n\n* fix(quality): close retry and cleanup mutation survivors\n\n* fix(quality): parallelize isolated Go mutation checks\n\n* fix(quality): satisfy shellcheck cleanup trap\n\n* fix(quality): kill UUID conversion mutant\n\n* fix(quality): close offline and mutation gaps\n\n* fix(quality): widen mutmut watchdog reserve\n\n* fix(quality): keep PWA precache within browser budgets\n\n* fix(quality): stabilize mutation watchdog and secret baseline\n\n* fix(quality): synchronize secrets baseline line numbers\n\n* fix(quality): refresh build and localization references\n\n* fix(quality): harden diagnostic build and mutation gates\n\n* fix(quality): align CI workflow checks and secret baseline\n\n* fix(quality): refresh deployment secret baseline\n\n* fix(quality): close aggregate coverage gaps\n\n* fix(quality): align mutation timeout envelope\n\n* fix(quality): correct mutation deadline diagnostic\n\n* fix(quality): disable unstable frontend AST remapping\n\n* fix(quality): close coverage and mutation regressions\n\n* fix(quality): remove synthetic frontend coverage callback\n\n* fix(docs): align ADR references with current implementation\n\n* fix(quality): cover late websocket timeout branch\n\n* fix(quality): cover fog particle recycle branch\n\n* fix(quality): clear news like celebration timer\n\n* fix(quality): cover repeated news celebration\n\n* fix(quality): stabilize SSR auth coverage mapping\n\n* fix(quality): close mutation and browser gates\n\n* fix(quality): align cache integration invalidation\n\n* fix(quality): isolate native schedule tests from mutmut\n\n* fix(quality): close gateway coverage gap\n\n* fix(quality): kill schedule conflict survivors\n\n* fix(quality): shard schemathesis and close mutation gaps\n\n* fix(quality): apply schemathesis filters before fixture resolution\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-25T00:51:11+03:00",
          "tree_id": "854a7bdf3be0cd0dc16dc7b1fa20c155aa7c0b88",
          "url": "https://github.com/egorribun/university_ecosystem/commit/18d4265d2452513e4e3177747f163282a2b5c85d"
        },
        "date": 1787613855357,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 119549,
            "unit": "ns/op",
            "extra": "9280 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 116,
            "unit": "ns/op",
            "extra": "10257480 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 840.1,
            "unit": "ns/op",
            "extra": "1303894 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.96,
            "unit": "ns/op",
            "extra": "17377165 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 147.4,
            "unit": "ns/op",
            "extra": "8143356 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.3,
            "unit": "ns/op",
            "extra": "77456733 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 567.2,
            "unit": "ns/op",
            "extra": "2112247 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 119.6,
            "unit": "ns/op",
            "extra": "10002424 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.66,
            "unit": "ns/op",
            "extra": "38085871 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 539.6,
            "unit": "ns/op",
            "extra": "2221192 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1599,
            "unit": "ns/op",
            "extra": "715104 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.84,
            "unit": "ns/op",
            "extra": "86528544 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 763.9,
            "unit": "ns/op",
            "extra": "1638798 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 43.03,
            "unit": "ns/op",
            "extra": "27208759 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1345,
            "unit": "ns/op",
            "extra": "875019 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 31.59,
            "unit": "ns/op",
            "extra": "35475566 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 59.98,
            "unit": "ns/op",
            "extra": "20223703 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 51.25,
            "unit": "ns/op",
            "extra": "23294805 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 783.7,
            "unit": "ns/op",
            "extra": "1734970 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 17698,
            "unit": "ns/op",
            "extra": "95331 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bfe06224c06acf441952513fc5f98471e4315919",
          "message": "build(deps): Bump github.com/stretchr/testify (#1251)\n\nBumps the go-ws-hub group in /services/ws-hub with 1 update: [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/stretchr/testify` from 1.12.0 to 1.12.1\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.12.0...v1.12.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-25T00:57:16+03:00",
          "tree_id": "9508721ac18bdff1a3d94bd12af7d3d968a8788a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/bfe06224c06acf441952513fc5f98471e4315919"
        },
        "date": 1787615378022,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 93853,
            "unit": "ns/op",
            "extra": "12793 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 107.2,
            "unit": "ns/op",
            "extra": "11008789 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 755.9,
            "unit": "ns/op",
            "extra": "1581788 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.54,
            "unit": "ns/op",
            "extra": "16499102 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 153.5,
            "unit": "ns/op",
            "extra": "7707514 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.36,
            "unit": "ns/op",
            "extra": "79045290 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 545.1,
            "unit": "ns/op",
            "extra": "2238514 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 125.9,
            "unit": "ns/op",
            "extra": "9452787 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.54,
            "unit": "ns/op",
            "extra": "36794440 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 484.2,
            "unit": "ns/op",
            "extra": "2469714 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1307,
            "unit": "ns/op",
            "extra": "780147 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.23,
            "unit": "ns/op",
            "extra": "91196394 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 867.2,
            "unit": "ns/op",
            "extra": "1707687 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 41.47,
            "unit": "ns/op",
            "extra": "27045726 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1278,
            "unit": "ns/op",
            "extra": "808122 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 30.33,
            "unit": "ns/op",
            "extra": "45661794 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 60.18,
            "unit": "ns/op",
            "extra": "19694256 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 46.77,
            "unit": "ns/op",
            "extra": "25891590 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 782.8,
            "unit": "ns/op",
            "extra": "1683327 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13189,
            "unit": "ns/op",
            "extra": "116726 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d8fe19f41c69a9dbaf57921884204b1b0133afa3",
          "message": "build(deps): Bump the go-file-processor group (#1252)\n\nBumps the go-file-processor group in /services/file-processor with 2 updates: [github.com/minio/minio-go/v7](https://github.com/minio/minio-go) and [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/minio/minio-go/v7` from 7.2.1 to 7.3.0\n- [Release notes](https://github.com/minio/minio-go/releases)\n- [Commits](https://github.com/minio/minio-go/compare/v7.2.1...v7.3.0)\n\nUpdates `github.com/stretchr/testify` from 1.12.0 to 1.12.1\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.12.0...v1.12.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/minio/minio-go/v7\n  dependency-version: 7.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-25T00:57:48+03:00",
          "tree_id": "bac37fca2efdc33c84e1dbd37047f9dbf09ed6f9",
          "url": "https://github.com/egorribun/university_ecosystem/commit/d8fe19f41c69a9dbaf57921884204b1b0133afa3"
        },
        "date": 1787615385290,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 55953,
            "unit": "ns/op",
            "extra": "21975 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 84.22,
            "unit": "ns/op",
            "extra": "14112805 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 657.3,
            "unit": "ns/op",
            "extra": "1811031 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 54.58,
            "unit": "ns/op",
            "extra": "22429456 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 146.2,
            "unit": "ns/op",
            "extra": "8302060 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 36.51,
            "unit": "ns/op",
            "extra": "33162308 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 416.5,
            "unit": "ns/op",
            "extra": "2875113 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 98.94,
            "unit": "ns/op",
            "extra": "12135991 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 21.51,
            "unit": "ns/op",
            "extra": "51292945 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 427.9,
            "unit": "ns/op",
            "extra": "2802242 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1158,
            "unit": "ns/op",
            "extra": "909568 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 17.82,
            "unit": "ns/op",
            "extra": "67810516 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 576.3,
            "unit": "ns/op",
            "extra": "2107449 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 35.92,
            "unit": "ns/op",
            "extra": "31690980 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 995.1,
            "unit": "ns/op",
            "extra": "1177593 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 44.38,
            "unit": "ns/op",
            "extra": "26866902 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 80.01,
            "unit": "ns/op",
            "extra": "14982190 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 59.62,
            "unit": "ns/op",
            "extra": "20252742 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 608,
            "unit": "ns/op",
            "extra": "1847425 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13027,
            "unit": "ns/op",
            "extra": "118630 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5eba3aff70220f27fd82a7d5b736cee2dc97cfad",
          "message": "build(deps): Bump github.com/stretchr/testify (#1253)\n\nBumps the go-gateway group in /services/gateway with 1 update: [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/stretchr/testify` from 1.12.0 to 1.12.1\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.12.0...v1.12.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-25T00:58:56+03:00",
          "tree_id": "7d2068a24ee67bb647451276935b105abbd5ae44",
          "url": "https://github.com/egorribun/university_ecosystem/commit/5eba3aff70220f27fd82a7d5b736cee2dc97cfad"
        },
        "date": 1787615583957,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 119689,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 108.5,
            "unit": "ns/op",
            "extra": "10872727 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 874.1,
            "unit": "ns/op",
            "extra": "1438964 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.83,
            "unit": "ns/op",
            "extra": "16303741 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 147.5,
            "unit": "ns/op",
            "extra": "8086771 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.32,
            "unit": "ns/op",
            "extra": "77539455 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 568.8,
            "unit": "ns/op",
            "extra": "2115997 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 120.1,
            "unit": "ns/op",
            "extra": "9920001 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 31.07,
            "unit": "ns/op",
            "extra": "37409318 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 558.9,
            "unit": "ns/op",
            "extra": "2207482 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1504,
            "unit": "ns/op",
            "extra": "702396 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.87,
            "unit": "ns/op",
            "extra": "87002241 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 744.7,
            "unit": "ns/op",
            "extra": "1569325 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 43.56,
            "unit": "ns/op",
            "extra": "26097904 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1627,
            "unit": "ns/op",
            "extra": "834310 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 33.51,
            "unit": "ns/op",
            "extra": "35057318 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 58.94,
            "unit": "ns/op",
            "extra": "20371741 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 51.96,
            "unit": "ns/op",
            "extra": "23073796 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 773.9,
            "unit": "ns/op",
            "extra": "1741580 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 17614,
            "unit": "ns/op",
            "extra": "97534 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "07610805c6b9a1aaf3e7f0a8832178bdb548b06e",
          "message": "ci(deps): Bump the github-actions group with 7 updates (#1250)\n\nBumps the github-actions group with 7 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.3117.0` | `12.3119.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.7` | `4.37.8` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.1.0` | `18.5.0` |\n| [streetsidesoftware/cspell-action](https://github.com/streetsidesoftware/cspell-action) | `8.4.0` | `9.0.1` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.7` | `4.37.8` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.7` | `4.37.8` |\n| [docker/setup-buildx-action](https://github.com/docker/setup-buildx-action) | `4.2.0` | `4.3.0` |\n\n\nUpdates `bridgecrewio/checkov-action` from 12.3117.0 to 12.3119.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/1246d92f57abae29d5db5f9aeeed2a9813e52d7d...59b9d7edfcad5b87fbe3f473a9a134a721ad03f8)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.7 to 4.37.8\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd...db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28)\n\nUpdates `chromaui/action` from 18.1.0 to 18.5.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/14cfaef73576e69f95f47f60058063f46ca38719...534eebfc19023579541d106f7b61d5ad70ed65c7)\n\nUpdates `streetsidesoftware/cspell-action` from 8.4.0 to 9.0.1\n- [Release notes](https://github.com/streetsidesoftware/cspell-action/releases)\n- [Changelog](https://github.com/streetsidesoftware/cspell-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/streetsidesoftware/cspell-action/compare/de2a73e963e7443969755b648a1008f77033c5b2...e0668cf020899e887ee8ad4d173c31738a79eae8)\n\nUpdates `github/codeql-action/init` from 4.37.7 to 4.37.8\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd...db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28)\n\nUpdates `github/codeql-action/analyze` from 4.37.7 to 4.37.8\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd...db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28)\n\nUpdates `docker/setup-buildx-action` from 4.2.0 to 4.3.0\n- [Release notes](https://github.com/docker/setup-buildx-action/releases)\n- [Commits](https://github.com/docker/setup-buildx-action/compare/bb05f3f5519dd87d3ba754cc423b652a5edd6d2c...37fe631027851001ddb9b187196cc803df7f5f0e)\n\n---\nupdated-dependencies:\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3119.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.8\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.5.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: streetsidesoftware/cspell-action\n  dependency-version: 9.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.8\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.8\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/setup-buildx-action\n  dependency-version: 4.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-25T01:13:49+03:00",
          "tree_id": "9d09bb6f736658d44911cbf8ca2045c3667c0e6f",
          "url": "https://github.com/egorribun/university_ecosystem/commit/07610805c6b9a1aaf3e7f0a8832178bdb548b06e"
        },
        "date": 1787615816877,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 101303,
            "unit": "ns/op",
            "extra": "12039 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 110.7,
            "unit": "ns/op",
            "extra": "10409708 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 742.5,
            "unit": "ns/op",
            "extra": "1613014 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 73.49,
            "unit": "ns/op",
            "extra": "16397642 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.5,
            "unit": "ns/op",
            "extra": "7514523 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 14.95,
            "unit": "ns/op",
            "extra": "80822247 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 530.3,
            "unit": "ns/op",
            "extra": "2258894 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 125.3,
            "unit": "ns/op",
            "extra": "9416236 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.62,
            "unit": "ns/op",
            "extra": "38699611 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 478.8,
            "unit": "ns/op",
            "extra": "2509358 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1314,
            "unit": "ns/op",
            "extra": "780133 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.59,
            "unit": "ns/op",
            "extra": "90187731 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 695.8,
            "unit": "ns/op",
            "extra": "1679424 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 43.87,
            "unit": "ns/op",
            "extra": "26359938 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1280,
            "unit": "ns/op",
            "extra": "850712 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 30.3,
            "unit": "ns/op",
            "extra": "36659004 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 59.91,
            "unit": "ns/op",
            "extra": "19793781 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 46.34,
            "unit": "ns/op",
            "extra": "25840689 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 780.4,
            "unit": "ns/op",
            "extra": "1744684 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14298,
            "unit": "ns/op",
            "extra": "116581 times\n4 procs"
          }
        ]
      }
    ],
    "Rust Criterion Benchmarks (pyo3-sanitizer)": [
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "01f5225769cacda2c9a609e9100b5b74cf5e5990",
          "message": "build(deps): Bump the pip-dependencies group with 2 updates\n\nUpdates the requirements on [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [mypy](https://github.com/python/mypy) to permit the latest version.\n\nUpdates `strawberry-graphql` to 0.322.0\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `mypy` to 2.3.0\n- [Changelog](https://github.com/python/mypy/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/python/mypy/compare/v1.20.1...v2.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: strawberry-graphql\n  dependency-version: 0.322.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: mypy\n  dependency-version: 2.3.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:53:21+03:00",
          "tree_id": "d4c90f0e6becfd187a1204cb3e998d104cc53a8b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/01f5225769cacda2c9a609e9100b5b74cf5e5990"
        },
        "date": 1784638726411,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5647,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6501,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9211,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 9584,
            "range": "± 45",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 92606,
            "range": "± 221",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5128,
            "range": "± 71",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 5954,
            "range": "± 74",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8503,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 8546,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 87174,
            "range": "± 214",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5026,
            "range": "± 71",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 5826,
            "range": "± 9",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8072,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 8409,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 85567,
            "range": "± 412",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e261ba2563a976605c4ab10149f3e7c7fd093085",
          "message": "ci(deps): Bump the github-actions group with 13 updates\n\nBumps the github-actions group with 13 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/setup-node](https://github.com/actions/setup-node) | `6.4.0` | `7.0.0` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.0` | `8.3.2` |\n| [actions/setup-go](https://github.com/actions/setup-go) | `6.5.0` | `7.0.0` |\n| [dtolnay/rust-toolchain](https://github.com/dtolnay/rust-toolchain) | `fa04a1451ff1842e2626ccb99004d0195b455a88` | `2c7215f132e9ebf062739d9130488b56d53c060c` |\n| [EmbarkStudios/cargo-deny-action](https://github.com/embarkstudios/cargo-deny-action) | `2.0.20` | `2.1.1` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.0` | `4.37.1` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `24.0.0` | `24.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.0` | `4.37.1` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.0` | `4.37.1` |\n| [actions/attest](https://github.com/actions/attest) | `4.1.1` | `4.2.0` |\n| [SonarSource/sonarqube-scan-action](https://github.com/sonarsource/sonarqube-scan-action) | `8.2.0` | `8.2.1` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.5.7` | `0.6.0` |\n\n\nUpdates `actions/setup-node` from 6.4.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-node/releases)\n- [Commits](https://github.com/actions/setup-node/compare/48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e...820762786026740c76f36085b0efc47a31fe5020)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/ece7cb06caefa5fff74198d8649806c4678c61a1...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.0 to 8.3.2\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/v8.3.0...11f9893b081a58869d3b5fccaea48c9e9e46f990)\n\nUpdates `actions/setup-go` from 6.5.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-go/releases)\n- [Commits](https://github.com/actions/setup-go/compare/924ae3a1cded613372ab5595356fb5720e22ba16...b7ad1dad31e06c5925ef5d2fc7ad053ef454303e)\n\nUpdates `dtolnay/rust-toolchain` from fa04a1451ff1842e2626ccb99004d0195b455a88 to 2c7215f132e9ebf062739d9130488b56d53c060c\n- [Release notes](https://github.com/dtolnay/rust-toolchain/releases)\n- [Commits](https://github.com/dtolnay/rust-toolchain/compare/fa04a1451ff1842e2626ccb99004d0195b455a88...2c7215f132e9ebf062739d9130488b56d53c060c)\n\nUpdates `EmbarkStudios/cargo-deny-action` from 2.0.20 to 2.1.1\n- [Release notes](https://github.com/embarkstudios/cargo-deny-action/releases)\n- [Commits](https://github.com/embarkstudios/cargo-deny-action/compare/bb137d7af7e4fb67e5f82a49c4fce4fad40782fe...3c6349835b2b7b196a839186cb8b78e02f7b5f25)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.0 to 4.37.1\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/99df26d4f13ea111d4ec1a7dddef6063f76b97e9...7188fc363630916deb702c7fdcf4e481b751f97a)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 24.0.0 to 24.1.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/8de2aa07cae85fd17c0b35642db70cf5495f1d25...6bf21b07787794f89a243495939cd651942aeabe)\n\nUpdates `github/codeql-action/init` from 4.37.0 to 4.37.1\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/99df26d4f13ea111d4ec1a7dddef6063f76b97e9...7188fc363630916deb702c7fdcf4e481b751f97a)\n\nUpdates `github/codeql-action/analyze` from 4.37.0 to 4.37.1\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/99df26d4f13ea111d4ec1a7dddef6063f76b97e9...7188fc363630916deb702c7fdcf4e481b751f97a)\n\nUpdates `actions/attest` from 4.1.1 to 4.2.0\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/a1948c3f048ba23858d222213b7c278aabede763...f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6)\n\nUpdates `SonarSource/sonarqube-scan-action` from 8.2.0 to 8.2.1\n- [Release notes](https://github.com/sonarsource/sonarqube-scan-action/releases)\n- [Commits](https://github.com/sonarsource/sonarqube-scan-action/compare/713881670b6b3676cda39549040e2d88c70d582e...22918119ff8e1ca75a623e15c8296b6ea4fbe28f)\n\nUpdates `zizmorcore/zizmor-action` from 0.5.7 to 0.6.0\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/192e21d79ab29983730a13d1382995c2307fbcaa...6599ee8b7a49aef6a770f63d261d214911a7ce02)\n\n---\nupdated-dependencies:\n- dependency-name: actions/setup-node\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 8.3.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-go\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: 2c7215f132e9ebf062739d9130488b56d53c060c\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: EmbarkStudios/cargo-deny-action\n  dependency-version: 2.1.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: SonarSource/sonarqube-scan-action\n  dependency-version: 8.2.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:53:40+03:00",
          "tree_id": "57b5cb6a159a419018c14e50e110834eb13a13d7",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e261ba2563a976605c4ab10149f3e7c7fd093085"
        },
        "date": 1784638943204,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6142,
            "range": "± 93",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7135,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9924,
            "range": "± 142",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10580,
            "range": "± 140",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95914,
            "range": "± 1378",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5526,
            "range": "± 59",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6406,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8975,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9234,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88887,
            "range": "± 5355",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5341,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6249,
            "range": "± 60",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8571,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9023,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 87436,
            "range": "± 444",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2f2421224f4f6ba51efa5c48451477a282f20daa",
          "message": "build(deps): Bump the go-ws-hub group in /services/ws-hub with 2 updates\n\nBumps the go-ws-hub group in /services/ws-hub with 2 updates: [github.com/getsentry/sentry-go](https://github.com/getsentry/sentry-go) and [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang).\n\n\nUpdates `github.com/getsentry/sentry-go` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/prometheus/client_golang` from 1.23.2 to 1.24.0\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.0/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.23.2...v1.24.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/getsentry/sentry-go\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:54:07+03:00",
          "tree_id": "ee3394ee761ed3edd5bd8c118a69eca2a8fa096e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2f2421224f4f6ba51efa5c48451477a282f20daa"
        },
        "date": 1784638952082,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5993,
            "range": "± 44",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6946,
            "range": "± 202",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9800,
            "range": "± 195",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10647,
            "range": "± 102",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100400,
            "range": "± 1046",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5410,
            "range": "± 57",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6338,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9048,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9432,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 92953,
            "range": "± 885",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5277,
            "range": "± 66",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6222,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8712,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9249,
            "range": "± 175",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91260,
            "range": "± 1451",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c697294c2667207f1231c2be4f2d271fdcaa5813",
          "message": "build(deps): Bump the go-gateway group in /services/gateway with 4 updates\n\nBumps the go-gateway group in /services/gateway with 4 updates: [github.com/getsentry/sentry-go](https://github.com/getsentry/sentry-go), [github.com/getsentry/sentry-go/gin](https://github.com/getsentry/sentry-go), [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/getsentry/sentry-go` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/getsentry/sentry-go/gin` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/prometheus/client_golang` from 1.23.2 to 1.24.0\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.0/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.23.2...v1.24.0)\n\nUpdates `google.golang.org/grpc` from 1.82.0 to 1.82.1\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.0...v1.82.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/getsentry/sentry-go\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/getsentry/sentry-go/gin\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.82.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:54:27+03:00",
          "tree_id": "eb1dd0533ca91270b20e7a19881a164cc4b4f6fa",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c697294c2667207f1231c2be4f2d271fdcaa5813"
        },
        "date": 1784639334600,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6222,
            "range": "± 248",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7040,
            "range": "± 380",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10105,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10862,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 103180,
            "range": "± 1615",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5416,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6405,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9220,
            "range": "± 41",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9448,
            "range": "± 36",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 95900,
            "range": "± 344",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5270,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6139,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8634,
            "range": "± 31",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9307,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 92931,
            "range": "± 539",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a54982147c64aeded86e81dee292376b62dcf295",
          "message": "build(deps): Bump the go-file-processor group in /services/file-processor with 3 updates\n\nBumps the go-file-processor group in /services/file-processor with 3 updates: [github.com/getsentry/sentry-go](https://github.com/getsentry/sentry-go), [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/getsentry/sentry-go` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/prometheus/client_golang` from 1.23.2 to 1.24.0\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.0/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.23.2...v1.24.0)\n\nUpdates `google.golang.org/grpc` from 1.82.0 to 1.82.1\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.0...v1.82.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/getsentry/sentry-go\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.82.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:54:44+03:00",
          "tree_id": "528ee10bf2b08828be7fc5fd0474ae642ebe64b9",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a54982147c64aeded86e81dee292376b62dcf295"
        },
        "date": 1784639382779,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5978,
            "range": "± 153",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6956,
            "range": "± 73",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9881,
            "range": "± 284",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10684,
            "range": "± 65",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 99609,
            "range": "± 5878",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5340,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6308,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8990,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9385,
            "range": "± 181",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 94057,
            "range": "± 1051",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5317,
            "range": "± 64",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6274,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8614,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9203,
            "range": "± 43",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91595,
            "range": "± 750",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817422556,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 4761,
            "range": "± 166",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 5427,
            "range": "± 45",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 7670,
            "range": "± 68",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 8199,
            "range": "± 76",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 77380,
            "range": "± 1439",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 6960,
            "range": "± 79",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 7650,
            "range": "± 46",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9710,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9927,
            "range": "± 115",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 74858,
            "range": "± 238",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 4134,
            "range": "± 13",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 4852,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 6802,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 7077,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 71432,
            "range": "± 227",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191705409,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6016,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6932,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10066,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10797,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100822,
            "range": "± 451",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5387,
            "range": "± 124",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6293,
            "range": "± 87",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8974,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9346,
            "range": "± 127",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93022,
            "range": "± 274",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5296,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6205,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8532,
            "range": "± 133",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9234,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91458,
            "range": "± 3052",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191854581,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6001,
            "range": "± 48",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6936,
            "range": "± 81",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10041,
            "range": "± 814",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10798,
            "range": "± 82",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 99656,
            "range": "± 1489",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5354,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6337,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9020,
            "range": "± 54",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9462,
            "range": "± 76",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 92897,
            "range": "± 578",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 7439,
            "range": "± 151",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 8301,
            "range": "± 372",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 10655,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 11266,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 93259,
            "range": "± 696",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f237c814f173127f3da824054e54268c0b13916c",
          "message": "build(deps): Bump github.com/prometheus/client_golang from 1.24.0 to 1.24.1 in /services/ws-hub in the go-ws-hub group\n\nBumps the go-ws-hub group in /services/ws-hub with 1 update: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:41:59+05:00",
          "tree_id": "79e11a838dd1d04b22410bddc066c133f55b7ee1",
          "url": "https://github.com/egorribun/university_ecosystem/commit/f237c814f173127f3da824054e54268c0b13916c"
        },
        "date": 1785862126641,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6193,
            "range": "± 118",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7116,
            "range": "± 199",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9803,
            "range": "± 101",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10413,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95227,
            "range": "± 396",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5495,
            "range": "± 109",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6412,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9030,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9244,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88981,
            "range": "± 366",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5341,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6310,
            "range": "± 49",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8569,
            "range": "± 107",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 8904,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 88106,
            "range": "± 241",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9ec989da7f5d0df782b673fb2d50d68768437f45",
          "message": "build(deps): Update fastapi requirement from <0.141,>=0.135.3 to >=0.135.3,<0.142 in the pip-dependencies group\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi) to permit the latest version.\n\nUpdates `fastapi` to 0.141.1\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.141.1)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.141.1\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:42:47+05:00",
          "tree_id": "7ec6b02cd9bfa17c94c0e69c3cedacb3f6fa15db",
          "url": "https://github.com/egorribun/university_ecosystem/commit/9ec989da7f5d0df782b673fb2d50d68768437f45"
        },
        "date": 1785862620363,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5979,
            "range": "± 91",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6937,
            "range": "± 270",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9888,
            "range": "± 75",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10700,
            "range": "± 39",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100504,
            "range": "± 379",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5409,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6307,
            "range": "± 45",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9121,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9359,
            "range": "± 168",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93064,
            "range": "± 519",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5251,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6179,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8625,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9201,
            "range": "± 62",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90866,
            "range": "± 990",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c2d8ff6bf96176839f211ad558dfca6d90176f0d",
          "message": "ci(deps): Bump the github-actions group with 5 updates\n\nBumps the github-actions group with 5 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.5.1` | `4.6.0` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.0` | `4.2.1` |\n\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/init` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/analyze` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `docker/login-action` from 4.5.1 to 4.6.0\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/abd2ef45e78c5afb21d64d4ca52ee8550d9572c7...dbcb813823bdd20940b903addbd779551569679f)\n\nUpdates `actions/attest` from 4.2.0 to 4.2.1\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6...508db95dd578ae2727ebd6217d5ba78e4fbda05d)\n\n---\nupdated-dependencies:\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.6.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:43:42+05:00",
          "tree_id": "d4b018610642655bc581ca575c9905429435dd0f",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c2d8ff6bf96176839f211ad558dfca6d90176f0d"
        },
        "date": 1785862885106,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6144,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7041,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9897,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10437,
            "range": "± 60",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95240,
            "range": "± 633",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5500,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6409,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8922,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9067,
            "range": "± 41",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88682,
            "range": "± 665",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5365,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6298,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8637,
            "range": "± 112",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9106,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 87783,
            "range": "± 403",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "31483859811bd2cffb4671782d4d8dfeb3e9e376",
          "message": "build(deps): Bump the go-gateway group across 1 directory with 2 updates\n\nBumps the go-gateway group with 2 updates in the /services/gateway directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:44:45+05:00",
          "tree_id": "7184b30dc72715dc394cc5ddb078f2fb3fa4742d",
          "url": "https://github.com/egorribun/university_ecosystem/commit/31483859811bd2cffb4671782d4d8dfeb3e9e376"
        },
        "date": 1785862974010,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 4774,
            "range": "± 163",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 5499,
            "range": "± 25",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 7820,
            "range": "± 91",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 8235,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 77833,
            "range": "± 514",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 4287,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 4983,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 6967,
            "range": "± 129",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 7166,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 75231,
            "range": "± 767",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 4177,
            "range": "± 8",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 4944,
            "range": "± 87",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 6766,
            "range": "± 113",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 7071,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 71708,
            "range": "± 1794",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "913c0db5636d6c86e28b1fc517288e551d5277ea",
          "message": "build(deps): Bump the go-file-processor group across 1 directory with 4 updates\n\nBumps the go-file-processor group with 4 updates in the /services/file-processor directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang), [go.temporal.io/api](https://github.com/temporalio/api-go), [go.temporal.io/sdk](https://github.com/temporalio/sdk-go) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `go.temporal.io/api` from 1.63.3 to 1.63.4\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.3...v1.63.4)\n\nUpdates `go.temporal.io/sdk` from 1.46.0 to 1.47.0\n- [Release notes](https://github.com/temporalio/sdk-go/releases)\n- [Changelog](https://github.com/temporalio/sdk-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/temporalio/sdk-go/compare/v1.46.0...v1.47.0)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/sdk\n  dependency-version: 1.47.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:02+05:00",
          "tree_id": "21adb758ca2821b4dc7f83d18e95b38375e28557",
          "url": "https://github.com/egorribun/university_ecosystem/commit/913c0db5636d6c86e28b1fc517288e551d5277ea"
        },
        "date": 1785863383911,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 3407,
            "range": "± 131",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 3897,
            "range": "± 87",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 5290,
            "range": "± 189",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 5678,
            "range": "± 351",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 52810,
            "range": "± 1159",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 3092,
            "range": "± 73",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 3406,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 4874,
            "range": "± 130",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 4991,
            "range": "± 254",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 49176,
            "range": "± 1963",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 3001,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 3536,
            "range": "± 554",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 4722,
            "range": "± 144",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 4907,
            "range": "± 207",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 47880,
            "range": "± 1138",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4d8fcde61831ab6443e1f8dbfa86e644e3c28809",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [msgpack](https://github.com/msgpack/msgpack-python) and [pip](https://github.com/pypa/pip).\n\n\nUpdates `msgpack` from 1.1.2 to 1.2.1\n- [Release notes](https://github.com/msgpack/msgpack-python/releases)\n- [Changelog](https://github.com/msgpack/msgpack-python/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/msgpack/msgpack-python/compare/v1.1.2...v1.2.1)\n\nUpdates `pip` from 26.1 to 26.1.2\n- [Changelog](https://github.com/pypa/pip/blob/main/NEWS.rst)\n- [Commits](https://github.com/pypa/pip/compare/26.1...26.1.2)\n\n---\nupdated-dependencies:\n- dependency-name: msgpack\n  dependency-version: 1.2.1\n  dependency-type: indirect\n  dependency-group: uv\n- dependency-name: pip\n  dependency-version: 26.1.2\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:28+05:00",
          "tree_id": "d8c3204dc26f383bcbfda522958a3b9258229d5e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/4d8fcde61831ab6443e1f8dbfa86e644e3c28809"
        },
        "date": 1785863636147,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6129,
            "range": "± 56",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7103,
            "range": "± 69",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9964,
            "range": "± 25",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10474,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 98747,
            "range": "± 4673",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5583,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6483,
            "range": "± 138",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9072,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9297,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 90746,
            "range": "± 722",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5318,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6272,
            "range": "± 94",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8598,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9136,
            "range": "± 39",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90298,
            "range": "± 2913",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "dd9c6405161d8ec6c5bc34bd617712f667abe2d5",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [pyasn1](https://github.com/pyasn1/pyasn1) and [aiohttp](https://github.com/aio-libs/aiohttp).\n\n\nUpdates `pyasn1` from 0.6.3 to 0.6.4\n- [Release notes](https://github.com/pyasn1/pyasn1/releases)\n- [Changelog](https://github.com/pyasn1/pyasn1/blob/main/CHANGES.rst)\n- [Commits](https://github.com/pyasn1/pyasn1/compare/v0.6.3...v0.6.4)\n\nUpdates `aiohttp` from 3.14.1 to 3.14.3\n- [Changelog](https://github.com/aio-libs/aiohttp/blob/master/CHANGES.rst)\n- [Commits](https://github.com/aio-libs/aiohttp/compare/v3.14.1...v3.14.3)\n\n---\nupdated-dependencies:\n- dependency-name: pyasn1\n  dependency-version: 0.6.4\n  dependency-type: direct:production\n  dependency-group: uv\n- dependency-name: aiohttp\n  dependency-version: 3.14.3\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-05T00:36:25+05:00",
          "tree_id": "4af11d38f9b1dc1eacfe0e5b24369e5b9f8c65b7",
          "url": "https://github.com/egorribun/university_ecosystem/commit/dd9c6405161d8ec6c5bc34bd617712f667abe2d5"
        },
        "date": 1785872421603,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6137,
            "range": "± 90",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7079,
            "range": "± 144",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10000,
            "range": "± 39",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10546,
            "range": "± 125",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 96349,
            "range": "± 596",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5397,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6361,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8869,
            "range": "± 31",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9211,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88872,
            "range": "± 2178",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5317,
            "range": "± 85",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6304,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8615,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9061,
            "range": "± 99",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86856,
            "range": "± 507",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "59a94734bf71377c8f83f1b486ae1f44d7a97070",
          "message": "ci(deps): Bump the npm_and_yarn group across 2 directories with 13 updates (#1226)\n\nBumps the npm_and_yarn group with 4 updates in the / directory: [undici](https://github.com/nodejs/undici), [handlebars](https://github.com/handlebars-lang/handlebars.js), [lodash](https://github.com/lodash/lodash) and [minimatch](https://github.com/isaacs/minimatch).\nBumps the npm_and_yarn group with 7 updates in the /frontend directory:\n\n| Package | From | To |\n| --- | --- | --- |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `5.0.7` | `5.0.9` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `2.1.2` | `2.1.4` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `1.1.16` | `1.1.18` |\n| [ip-address](https://github.com/beaugunderson/ip-address) | `10.2.0` | `10.4.0` |\n| [@vitest/browser](https://github.com/vitest-dev/vitest/tree/HEAD/packages/browser) | `3.2.6` | `4.1.10` |\n| [postcss](https://github.com/postcss/postcss) | `8.5.16` | `8.5.25` |\n| [sharp](https://github.com/lovell/sharp) | `0.34.5` | `0.35.0` |\n| [dompurify](https://github.com/cure53/DOMPurify) | `3.4.11` | `3.4.13` |\n| [fast-uri](https://github.com/fastify/fast-uri) | `3.1.2` | `3.1.5` |\n\n\n\nUpdates `undici` from 6.23.0 to 6.28.0\n- [Release notes](https://github.com/nodejs/undici/releases)\n- [Commits](https://github.com/nodejs/undici/compare/v6.23.0...v6.28.0)\n\nUpdates `handlebars` from 4.7.8 to 4.7.9\n- [Release notes](https://github.com/handlebars-lang/handlebars.js/releases)\n- [Changelog](https://github.com/handlebars-lang/handlebars.js/blob/v4.7.9/release-notes.md)\n- [Commits](https://github.com/handlebars-lang/handlebars.js/compare/v4.7.8...v4.7.9)\n\nUpdates `lodash` from 4.17.23 to 4.18.1\n- [Release notes](https://github.com/lodash/lodash/releases)\n- [Commits](https://github.com/lodash/lodash/compare/4.17.23...4.18.1)\n\nUpdates `minimatch` from 10.2.2 to 10.2.5\n- [Changelog](https://github.com/isaacs/minimatch/blob/main/changelog.md)\n- [Commits](https://github.com/isaacs/minimatch/compare/v10.2.2...v10.2.5)\n\nUpdates `sigstore` from 4.1.0 to 4.1.1\n- [Release notes](https://github.com/sigstore/sigstore-js/releases)\n- [Commits](https://github.com/sigstore/sigstore-js/compare/sigstore@4.1.0...sigstore@4.1.1)\n\nUpdates `tar` from 7.5.9 to 7.5.19\n- [Release notes](https://github.com/isaacs/node-tar/releases)\n- [Changelog](https://github.com/isaacs/node-tar/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/isaacs/node-tar/compare/v7.5.9...v7.5.19)\n\nUpdates `brace-expansion` from 5.0.7 to 5.0.9\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 2.1.2 to 2.1.4\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 1.1.16 to 1.1.18\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `ip-address` from 10.2.0 to 10.4.0\n- [Release notes](https://github.com/beaugunderson/ip-address/releases)\n- [Commits](https://github.com/beaugunderson/ip-address/compare/v10.2.0...v10.4.0)\n\nUpdates `@vitest/browser` from 3.2.6 to 4.1.10\n- [Release notes](https://github.com/vitest-dev/vitest/releases)\n- [Changelog](https://github.com/vitest-dev/vitest/blob/main/docs/releases.md)\n- [Commits](https://github.com/vitest-dev/vitest/commits/v4.1.10/packages/browser)\n\nUpdates `postcss` from 8.5.16 to 8.5.25\n- [Release notes](https://github.com/postcss/postcss/releases)\n- [Changelog](https://github.com/postcss/postcss/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/postcss/postcss/compare/8.5.16...8.5.25)\n\nUpdates `sharp` from 0.34.5 to 0.35.0\n- [Release notes](https://github.com/lovell/sharp/releases)\n- [Commits](https://github.com/lovell/sharp/compare/v0.34.5...v0.35.0)\n\nUpdates `dompurify` from 3.4.11 to 3.4.13\n- [Release notes](https://github.com/cure53/DOMPurify/releases)\n- [Commits](https://github.com/cure53/DOMPurify/compare/3.4.11...3.4.13)\n\nUpdates `fast-uri` from 3.1.2 to 3.1.5\n- [Release notes](https://github.com/fastify/fast-uri/releases)\n- [Commits](https://github.com/fastify/fast-uri/compare/v3.1.2...v3.1.5)\n\n---\nupdated-dependencies:\n- dependency-name: undici\n  dependency-version: 6.28.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: handlebars\n  dependency-version: 4.7.9\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: lodash\n  dependency-version: 4.18.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: minimatch\n  dependency-version: 10.2.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: sigstore\n  dependency-version: 4.1.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: tar\n  dependency-version: 7.5.19\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 5.0.9\n  dependency-type: direct:production\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 2.1.4\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 1.1.18\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: ip-address\n  dependency-version: 10.4.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: \"@vitest/browser\"\n  dependency-version: 4.1.10\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: postcss\n  dependency-version: 8.5.25\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: sharp\n  dependency-version: 0.35.0\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: dompurify\n  dependency-version: 3.4.13\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: fast-uri\n  dependency-version: 3.1.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T23:16:53+03:00",
          "tree_id": "358d295e79f3adb3f6a4dbcc1688157540dcc98a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/59a94734bf71377c8f83f1b486ae1f44d7a97070"
        },
        "date": 1785874849157,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6139,
            "range": "± 192",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7027,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9886,
            "range": "± 78",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10527,
            "range": "± 435",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95258,
            "range": "± 1454",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5512,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6383,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8916,
            "range": "± 178",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9214,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 87586,
            "range": "± 821",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5351,
            "range": "± 77",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6295,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8556,
            "range": "± 64",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9047,
            "range": "± 120",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 85917,
            "range": "± 625",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "496ed7f2c5c0fd33da738b4687b4c31281f14d7e",
          "message": "fix(ci): restore checks after draft pull requests become ready (#1227)\n\n* feat(wave212): remove obsolete handoff prompt\n\n* fix(ci): trigger checks when draft PR becomes ready\n\n* test(quality): cover gateway TLS certificate failure paths\n\n* fix(ci): keep required OpenAPI check live on every PR\n\n* fix(ci): run frontend mutation gate during manual recovery\n\n* test(gateway): satisfy Go lint and nil analysis\n\n* fix(ci): add manual recovery triggers for Go analysis\n\n* fix(ci): make gosec test directive effective\n\n* fix(ci): use canonical lighthouse assertions\n\n* fix(ci): eliminate ws-hub shutdown race\n\n* fix(ci): handle ws-hub socket cleanup error\n\n* fix(ci): reduce ws-hub server complexity\n\n* fix(ci): align lighthouse gates with canonical config\n\n* fix(ci): isolate backend integration test scope\n\n* fix(ci): start minio for chaos services\n\n* fix(quality): consume frontend statement coverage\n\n* fix(ci): close PR check and coverage gaps\n\n* fix(ci): close analyzer findings\n\n* fix(ci): drain file processor servers before return\n\n* fix(ci): close coverage gate deficits\n\n* fix(ci): make PR quality gate reproducible\n\n* fix(ci): prevent security scan alert drift\n\n* fix(ci): retry testcontainer image pulls\n\n* fix(ci): stabilize browser e2e execution\n\n* fix(ci): close mutation and tier0 coverage gaps\n\n* fix(ci): unblock code scanning ruleset\n\n* fix(ci): preserve scoped trivy suppressions\n\n* fix(ci): filter suppressed checkov alerts\n\n* fix(ci): write filtered checkov sarif separately\n\n* fix(ci): use one trivy ignore format\n\n* fix(ci): make Semgrep SARIF analysis reliable\n\n* fix(ci): make Semgrep pull requests diff-aware\n\n* fix(ci): close Semgrep findings in integration gate\n\n* fix(ci): make gateway race performance gate stable\n\n* fix(ci): remove golangci schema network dependency\n\n* fix(ci): avoid redundant Lighthouse dependency bootstrap\n\n* fix(ci): close session crypto coverage branch\n\n* fix(ci): include workflow contract inputs in mutmut sandbox\n\n* fix(test): bound Miri sanitizer payload\n\n* fix(test): reduce Miri sanitizer fixture\n\n* fix(test): invalidate cached JWT keys on rotation\n\n* fix(test): isolate notification metrics state\n\n* chore: update codebase test coverage reports and configuration files\n\n* fix(ci): balance incremental mutmut shards\n\n* fix(test): clean up SPIFFE stress test lint\n\n* fix(test): isolate ChatWindow render suites\n\n* fix(frontend): guard profile sync auto-fetch reruns\n\n* fix(test): isolate profile coverage suites\n\n* fix(test): isolate component coverage suites\n\n* fix(test): isolate event hero coverage suites\n\n* fix(test): isolate schedule and event file suites\n\n* chore(test): checkpoint current branch changes\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-08T21:40:49+03:00",
          "tree_id": "26101b1ba5348abe8e9c0a22c539a733d8f96e1b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/496ed7f2c5c0fd33da738b4687b4c31281f14d7e"
        },
        "date": 1786215031244,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6011,
            "range": "± 156",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6906,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9868,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10799,
            "range": "± 52",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 98468,
            "range": "± 2713",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5298,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6260,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9058,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9418,
            "range": "± 64",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 91999,
            "range": "± 298",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5299,
            "range": "± 129",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6211,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8577,
            "range": "± 179",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9191,
            "range": "± 107",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90218,
            "range": "± 2828",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada",
          "message": "ci(deps): Bump the github-actions group with 9 updates (#1230)\n\nBumps the github-actions group with 9 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [dtolnay/rust-toolchain](https://github.com/dtolnay/rust-toolchain) | `2c7215f132e9ebf062739d9130488b56d53c060c` | `6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.3114.0` | `12.3115.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `24.1.0` | `24.2.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.1` | `4.2.2` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.1` | `0.6.2` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/v7...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `dtolnay/rust-toolchain` from 2c7215f132e9ebf062739d9130488b56d53c060c to 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n- [Release notes](https://github.com/dtolnay/rust-toolchain/releases)\n- [Commits](https://github.com/dtolnay/rust-toolchain/compare/2c7215f132e9ebf062739d9130488b56d53c060c...6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772)\n\nUpdates `bridgecrewio/checkov-action` from 12.3114.0 to 12.3115.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/7b972723c44fb3d256283fac96fae5d7c1894bb7...9b70310bcd306d11740313070b940167d6b23085)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 24.1.0 to 24.2.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/6bf21b07787794f89a243495939cd651942aeabe...21c1be1b93ad9ed58fa840aacc3f279cde2a72ff)\n\nUpdates `github/codeql-action/init` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `github/codeql-action/analyze` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `actions/attest` from 4.2.1 to 4.2.2\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/508db95dd578ae2727ebd6217d5ba78e4fbda05d...1e69f48acb82d1966a394da916b4c1698aa569d6)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.1 to 0.6.2\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6fc4b006235f201fdab3722e17240ab420d580e5...3dc1ecc9bcb9e94e9b2c709687979e1298497054)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3115.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-10T12:31:09+03:00",
          "tree_id": "943e83367d58b7cd70d48bf646ef00f5ad5c36ce",
          "url": "https://github.com/egorribun/university_ecosystem/commit/8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada"
        },
        "date": 1786354514395,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6134,
            "range": "± 110",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7087,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9953,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10494,
            "range": "± 76",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95245,
            "range": "± 474",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5575,
            "range": "± 83",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6507,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8998,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9319,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88045,
            "range": "± 458",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5414,
            "range": "± 86",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6403,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8829,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9224,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86949,
            "range": "± 951",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "83beb35c866c4baa10b60e2ef95c663568a3c58e",
          "message": "build(deps): Bump the go-file-processor group (#1233)\n\nBumps the go-file-processor group in /services/file-processor with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/minio](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.temporal.io/api](https://github.com/temporalio/api-go) | `1.63.4` | `1.63.5` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/minio` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.temporal.io/api` from 1.63.4 to 1.63.5\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.4...v1.63.5)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/minio\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.5\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-11T14:12:40+03:00",
          "tree_id": "d51f68500e421c60f18e4437922edb661971e41a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/83beb35c866c4baa10b60e2ef95c663568a3c58e"
        },
        "date": 1786447212675,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6151,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7037,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9879,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10578,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 94089,
            "range": "± 1380",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5476,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6378,
            "range": "± 90",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8950,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9141,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88722,
            "range": "± 315",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5336,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6307,
            "range": "± 12",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8559,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9005,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86259,
            "range": "± 357",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2f04616dfc39026d11be988ae05d33eb9403f1c5",
          "message": "build(deps): Bump the go-ws-hub group (#1231)\n\nBumps the go-ws-hub group in /services/ws-hub with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.60.0` | `0.61.0` |\n| [github.com/quic-go/webtransport-go](https://github.com/quic-go/webtransport-go) | `0.11.1` | `0.12.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `github.com/quic-go/quic-go` from 0.60.0 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.60.0...v0.61.0)\n\nUpdates `github.com/quic-go/webtransport-go` from 0.11.1 to 0.12.0\n- [Release notes](https://github.com/quic-go/webtransport-go/releases)\n- [Commits](https://github.com/quic-go/webtransport-go/compare/v0.11.1...v0.12.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/webtransport-go\n  dependency-version: 0.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:07+03:00",
          "tree_id": "af20c3ca22f350fb2734115e77c0541b42988af5",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2f04616dfc39026d11be988ae05d33eb9403f1c5"
        },
        "date": 1786447436882,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5961,
            "range": "± 56",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6895,
            "range": "± 43",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9809,
            "range": "± 56",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10577,
            "range": "± 130",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100459,
            "range": "± 2500",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5354,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6302,
            "range": "± 193",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8958,
            "range": "± 140",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9264,
            "range": "± 69",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 94096,
            "range": "± 592",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5240,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6140,
            "range": "± 112",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8577,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9084,
            "range": "± 91",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 92156,
            "range": "± 498",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "10c0ecff521b04524da5d7dd48aa9a93e8611647",
          "message": "build(deps): Bump the go-gateway group (#1232)\n\nBumps the go-gateway group in /services/gateway with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.59.1` | `0.61.0` |\n| [github.com/redis/go-redis/extra/redisprometheus/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n\n\nUpdates `github.com/quic-go/quic-go` from 0.59.1 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.59.1...v0.61.0)\n\nUpdates `github.com/redis/go-redis/extra/redisprometheus/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/extra/redisprometheus/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:36+03:00",
          "tree_id": "ca611e2a36d4ebc8176e6d30b8dc969e933c1748",
          "url": "https://github.com/egorribun/university_ecosystem/commit/10c0ecff521b04524da5d7dd48aa9a93e8611647"
        },
        "date": 1786447795440,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6024,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6917,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9996,
            "range": "± 178",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10776,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100340,
            "range": "± 325",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5476,
            "range": "± 48",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6395,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9064,
            "range": "± 83",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9369,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 92108,
            "range": "± 364",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5238,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6230,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8662,
            "range": "± 104",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9281,
            "range": "± 96",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90772,
            "range": "± 370",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667",
          "message": "feat(quality): bootstrap trusted performance assets (#1234)\n\nasset bootstrap / no safe preexisting required context; base is missing base-trusted performance tooling; retaining path filter avoids widening legacy writable PR workflow.\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-11T20:19:16+03:00",
          "tree_id": "e6ce87a619a6dd553eef22861034220a6828012c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667"
        },
        "date": 1786469037015,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5981,
            "range": "± 83",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6920,
            "range": "± 160",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9876,
            "range": "± 230",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10490,
            "range": "± 267",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 97395,
            "range": "± 2520",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5406,
            "range": "± 88",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6235,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8989,
            "range": "± 209",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9261,
            "range": "± 232",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 91371,
            "range": "± 1987",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5209,
            "range": "± 124",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6254,
            "range": "± 146",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8593,
            "range": "± 230",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9216,
            "range": "± 210",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 88555,
            "range": "± 2193",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "751414ffb59ac2f2de723c1074fa88f1331cfce9",
          "message": "fix(quality): permit rust benchmark workspace root (#1237)\n\n* fix(quality): permit rust benchmark workspace root\n\n* fix(quality): prefetch Go modules without workspace writes\n\n* fix(quality): disable Go workspace mutation in captures\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T00:58:14+05:00",
          "tree_id": "ac8481a0731fa299f91978f543c32455c51d042e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/751414ffb59ac2f2de723c1074fa88f1331cfce9"
        },
        "date": 1786478554916,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6140,
            "range": "± 340",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7059,
            "range": "± 169",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9936,
            "range": "± 766",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10461,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95228,
            "range": "± 442",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5521,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6417,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8926,
            "range": "± 180",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9124,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88935,
            "range": "± 1907",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5353,
            "range": "± 69",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6265,
            "range": "± 149",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8555,
            "range": "± 95",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9092,
            "range": "± 156",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86724,
            "range": "± 396",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1155f5f007a498aa3ffa10194b50cd403661aede",
          "message": "fix(ci): harden SQLMap OpenAPI scan (#1235)\n\n* fix(ci): harden SQLMap OpenAPI scan\n\n* fix(ci): bound SQLMap OpenAPI smoke scan\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T01:57:05+05:00",
          "tree_id": "c793336565247ba5b4d55a2ab9549d910c419079",
          "url": "https://github.com/egorribun/university_ecosystem/commit/1155f5f007a498aa3ffa10194b50cd403661aede"
        },
        "date": 1786482596747,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5953,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6921,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10041,
            "range": "± 44",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10622,
            "range": "± 189",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100538,
            "range": "± 331",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5430,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6370,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9199,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9531,
            "range": "± 116",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93004,
            "range": "± 435",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5280,
            "range": "± 198",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6196,
            "range": "± 12",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8733,
            "range": "± 81",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9425,
            "range": "± 41",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91466,
            "range": "± 1655",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "96689a7514e55bbfda63504c83b484eed5e03fbd",
          "message": "fix(quality): keep isolated benchmark caches mounted (#1238)\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T02:46:21+05:00",
          "tree_id": "ed5af247033d8021b235e4c06769fe99d297a19d",
          "url": "https://github.com/egorribun/university_ecosystem/commit/96689a7514e55bbfda63504c83b484eed5e03fbd"
        },
        "date": 1786485010580,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5984,
            "range": "± 13",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6949,
            "range": "± 92",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10042,
            "range": "± 83",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10738,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 98050,
            "range": "± 2310",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5444,
            "range": "± 27",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6340,
            "range": "± 121",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9034,
            "range": "± 211",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9516,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 91852,
            "range": "± 470",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5211,
            "range": "± 31",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6244,
            "range": "± 104",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8533,
            "range": "± 46",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9104,
            "range": "± 25",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90475,
            "range": "± 2966",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cbd191eeb888416c5668af62dbb8e2ad6a8982e6",
          "message": "feat(quality): activate trusted same-run performance gates (#1236)\n\n* feat(quality): activate trusted same-run performance gates\n\n* fix(quality): allow rust benchmark workspace root\n\n* fix(quality): prefetch Go modules without workspace writes\n\n* fix(quality): disable Go workspace mutation in captures\n\n* fix(quality): keep isolated benchmark caches mounted\n\n* test(quality): cover benchmark cache holder lifecycle\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T03:24:19+05:00",
          "tree_id": "f3dcc10b2660b8a3adb5f10584d0b858bd606215",
          "url": "https://github.com/egorribun/university_ecosystem/commit/cbd191eeb888416c5668af62dbb8e2ad6a8982e6"
        },
        "date": 1786488531665,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5990,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7008,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9931,
            "range": "± 267",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10787,
            "range": "± 82",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 99751,
            "range": "± 392",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5357,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6373,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9211,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9481,
            "range": "± 55",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93385,
            "range": "± 333",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5301,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6213,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8702,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9211,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91472,
            "range": "± 401",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c838c2000cf5b73d4dfa38dfa4a7d239c13cbb0b",
          "message": "fix(quality): harden evidence and strict test gates (#1229)\n\n* docs(testing): record final quality audit\n\n* test(quality): close final quality gates\n\n* test(quality): harden promotion evidence query\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T07:01:22+05:00",
          "tree_id": "975b43b412f0ac71c80a1a1caecb73f765075b06",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c838c2000cf5b73d4dfa38dfa4a7d239c13cbb0b"
        },
        "date": 1786501578739,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5981,
            "range": "± 13",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6876,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9925,
            "range": "± 76",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10691,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100603,
            "range": "± 1449",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5407,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6360,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9063,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9443,
            "range": "± 44",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93211,
            "range": "± 573",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5243,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6217,
            "range": "± 13",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8599,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9140,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90733,
            "range": "± 806",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "44f750004ed1fe5cda15cd7ae3a459ca886b2bec",
          "message": "test: current-head closure gates (#1239)\n\n* docs(testing): record final quality audit\n\n* test(quality): close final quality gates\n\n* test(quality): harden promotion evidence query\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n* docs(quality): record live closure evidence\n\n* docs(quality): track current nightly queue\n\n* docs(quality): confirm Codecov processing\n\n* fix(security): harden push endpoints and trusted CI\n\n* docs(quality): record security hardening and nightly queue\n\n* docs(quality): quantify residual dependency advisories\n\n* docs(quality): record nightly queue replacement\n\n* fix(security): scope nightly workflow permissions\n\n* docs(quality): record current security and Codecov evidence\n\n* fix(security): block mapped IPv4 SSRF literals\n\n* docs(quality): record mapped IPv6 SSRF closure\n\n* docs(quality): record terminal nightly queue state\n\n* fix(ci): parallelize full mutmut stats collection\n\n* docs(quality): record parallel nightly mutation stats\n\n* fix(ci): report nightly mutation stats failures\n\n* docs(quality): record nightly failure notification guard\n\n* fix(ci): parallelize full mutation execution\n\n* docs(quality): record parallel mutation execution\n\n* docs(quality): record certification secret configuration\n\n* docs(quality): record DAST deferral\n\n* docs(quality): refresh live closure audit\n\n* test(quality): cover SQLMap workflow contract\n\n* docs(quality): record SQLMap contract refresh\n\n* docs(quality): record current-head validation trigger\n\n* docs(quality): record TruffleHog remediation\n\n* docs(quality): avoid scanner trigger wording\n\n* test(quality): close webpush mutation survivors\n\n* fix(security): avoid URI scanner false positive\n\n* test(quality): close diff coverage branches\n\n* test(quality): cover SSRF port guard\n\n* fix(ci): ensure required fuzz contexts run\n\n* test(webpush): cover development DNS fallback\n\n* docs(quality): record current-head CI closure\n\n* docs(quality): record rerun validation\n\n* fix(webpush): make development fallback mutation-proof\n\n* docs(quality): record mutation closure evidence\n\n* docs(quality): pin final evidence checkpoint\n\n* test(quality): cover dagger pipeline proposal\n\n* fix(quality): canonicalize mutmut package names\n\n* test(quality): cover scheduler mutation mapping\n\n* test(quality): cover pyroscope profiler mapping\n\n* test(quality): cover uvloop detection mapping\n\n* test(quality): cover event file repr mapping\n\n* test(quality): cover event repr mapping\n\n* test(quality): cover news comment repr mapping\n\n* test(quality): cover model repr mappings\n\n* test(quality): cover user file cleanup mapping\n\n* test(quality): cover worker entrypoint mapping\n\n* test(quality): cover cdc fallback mapping\n\n* docs: specify standalone logo loader\n\n* fix(ci): reuse validated bundle for lighthouse shards\n\n* docs: plan standalone logo loader\n\n* docs: specify application logo loader integration\n\n* fix(ci): build dedicated lighthouse bundle\n\n* docs: plan application logo loader integration\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-13T13:07:55+03:00",
          "tree_id": "c64f7d408f7ce31136809c8198c8538b73d083dc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/44f750004ed1fe5cda15cd7ae3a459ca886b2bec"
        },
        "date": 1786617184972,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5984,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6914,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9905,
            "range": "± 150",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10739,
            "range": "± 37",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100655,
            "range": "± 366",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5373,
            "range": "± 10",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6235,
            "range": "± 59",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8964,
            "range": "± 27",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9444,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93444,
            "range": "± 574",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5274,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6133,
            "range": "± 262",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8554,
            "range": "± 48",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9167,
            "range": "± 57",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91894,
            "range": "± 733",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c6125fb0d37a5f376a7b309ac2c2f68601765dfb",
          "message": "feat: integrate adaptive brand loader and quality closure hardening (#1240)\n\n* docs(testing): record final quality audit\n\n* test(quality): close final quality gates\n\n* test(quality): harden promotion evidence query\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n* docs(quality): record live closure evidence\n\n* docs(quality): track current nightly queue\n\n* docs(quality): confirm Codecov processing\n\n* fix(security): harden push endpoints and trusted CI\n\n* docs(quality): record security hardening and nightly queue\n\n* docs(quality): quantify residual dependency advisories\n\n* docs(quality): record nightly queue replacement\n\n* fix(security): scope nightly workflow permissions\n\n* docs(quality): record current security and Codecov evidence\n\n* fix(security): block mapped IPv4 SSRF literals\n\n* docs(quality): record mapped IPv6 SSRF closure\n\n* docs(quality): record terminal nightly queue state\n\n* fix(ci): parallelize full mutmut stats collection\n\n* docs(quality): record parallel nightly mutation stats\n\n* fix(ci): report nightly mutation stats failures\n\n* docs(quality): record nightly failure notification guard\n\n* fix(ci): parallelize full mutation execution\n\n* docs(quality): record parallel mutation execution\n\n* docs(quality): record certification secret configuration\n\n* docs(quality): record DAST deferral\n\n* docs(quality): refresh live closure audit\n\n* test(quality): cover SQLMap workflow contract\n\n* docs(quality): record SQLMap contract refresh\n\n* docs(quality): record current-head validation trigger\n\n* docs(quality): record TruffleHog remediation\n\n* docs(quality): avoid scanner trigger wording\n\n* test(quality): close webpush mutation survivors\n\n* fix(security): avoid URI scanner false positive\n\n* test(quality): close diff coverage branches\n\n* test(quality): cover SSRF port guard\n\n* fix(ci): ensure required fuzz contexts run\n\n* test(webpush): cover development DNS fallback\n\n* docs(quality): record current-head CI closure\n\n* docs(quality): record rerun validation\n\n* fix(webpush): make development fallback mutation-proof\n\n* docs(quality): record mutation closure evidence\n\n* docs(quality): pin final evidence checkpoint\n\n* test(quality): cover dagger pipeline proposal\n\n* fix(quality): canonicalize mutmut package names\n\n* test(quality): cover scheduler mutation mapping\n\n* test(quality): cover pyroscope profiler mapping\n\n* test(quality): cover uvloop detection mapping\n\n* test(quality): cover event file repr mapping\n\n* test(quality): cover event repr mapping\n\n* test(quality): cover news comment repr mapping\n\n* test(quality): cover model repr mappings\n\n* test(quality): cover user file cleanup mapping\n\n* test(quality): cover worker entrypoint mapping\n\n* test(quality): cover cdc fallback mapping\n\n* docs: specify standalone logo loader\n\n* fix(ci): reuse validated bundle for lighthouse shards\n\n* docs: plan standalone logo loader\n\n* docs: specify application logo loader integration\n\n* fix(ci): build dedicated lighthouse bundle\n\n* docs: plan application logo loader integration\n\n* feat: publish app hydration completion\n\n* feat: add SSR brand boot loader\n\n* feat: add critical brand loader animation\n\n* feat: mount logo loader in app shell\n\n* feat: harden adaptive brand boot loader\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-13T15:10:23+03:00",
          "tree_id": "0d2452dbe1097c2d64c63d2ab9afb4ef03b583b8",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c6125fb0d37a5f376a7b309ac2c2f68601765dfb"
        },
        "date": 1786624573382,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6327,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7226,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10138,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10709,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 97020,
            "range": "± 358",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5672,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6551,
            "range": "± 98",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9106,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9317,
            "range": "± 238",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88784,
            "range": "± 343",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5379,
            "range": "± 66",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6341,
            "range": "± 146",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8705,
            "range": "± 129",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9282,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 87541,
            "range": "± 1429",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a3362b084399bf1fa2db8aef7e04cab1b423f381",
          "message": "ci(deps): Bump the github-actions group with 6 updates (#1242)\n\nBumps the github-actions group with 6 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `9.0.0` | `10.0.1` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.3115.0` | `12.3117.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.6` | `4.37.7` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.6` | `4.37.7` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.6` | `4.37.7` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.96.0` | `3.97.0` |\n\n\nUpdates `astral-sh/setup-uv` from 9.0.0 to 10.0.1\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/c771a70e6277c0a99b617c7a806ffedaca235ff9...20cfd1bf945f4377ade1205e4dbc17946fc9a30d)\n\nUpdates `bridgecrewio/checkov-action` from 12.3115.0 to 12.3117.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/9b70310bcd306d11740313070b940167d6b23085...1246d92f57abae29d5db5f9aeeed2a9813e52d7d)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.6 to 4.37.7\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/5595ccaf912efad79be6eef63a5619ff05969be3...ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd)\n\nUpdates `github/codeql-action/init` from 4.37.6 to 4.37.7\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/5595ccaf912efad79be6eef63a5619ff05969be3...ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd)\n\nUpdates `github/codeql-action/analyze` from 4.37.6 to 4.37.7\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/5595ccaf912efad79be6eef63a5619ff05969be3...ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd)\n\nUpdates `trufflesecurity/trufflehog` from 3.96.0 to 3.97.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/6f3c981e7b77f235fd2702dd74af25fc4b72bf11...bcfcf73aaf4759d4dadc2783177c245a02792318)\n\n---\nupdated-dependencies:\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 10.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3117.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.7\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.7\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.7\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.97.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-17T15:28:33+03:00",
          "tree_id": "12c34b226f05f8dde8c7a7c3ae16846c2145381f",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a3362b084399bf1fa2db8aef7e04cab1b423f381"
        },
        "date": 1786971200001,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5984,
            "range": "± 37",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6809,
            "range": "± 115",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9862,
            "range": "± 121",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10656,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 101164,
            "range": "± 290",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5322,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6276,
            "range": "± 64",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8871,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9079,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 95220,
            "range": "± 413",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5219,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6186,
            "range": "± 49",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8632,
            "range": "± 56",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9103,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 93406,
            "range": "± 770",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a53a0b1b1b3dd4da9aed3b0cd1592294dcd9e691",
          "message": "build(deps): Update strawberry-graphql requirement (#1241)\n\nUpdates the requirements on [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) to permit the latest version.\n\nUpdates `strawberry-graphql` to 0.324.0\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\n---\nupdated-dependencies:\n- dependency-name: strawberry-graphql\n  dependency-version: 0.324.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-17T15:29:29+03:00",
          "tree_id": "d04f84bd8648708358a5f854a48f31e14bc9fbb0",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a53a0b1b1b3dd4da9aed3b0cd1592294dcd9e691"
        },
        "date": 1786971402913,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6150,
            "range": "± 57",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7008,
            "range": "± 135",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9866,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10537,
            "range": "± 45",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95562,
            "range": "± 190",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5519,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6400,
            "range": "± 41",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8931,
            "range": "± 47",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9272,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88190,
            "range": "± 699",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5471,
            "range": "± 10",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6428,
            "range": "± 94",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8747,
            "range": "± 57",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9175,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 87880,
            "range": "± 321",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a9aa48a8ab2308dca7b9509d4a5b193756db5eba",
          "message": "build(deps): Bump the go-ws-hub group in /services/ws-hub with 2 updates (#1243)\n\nBumps the go-ws-hub group in /services/ws-hub with 2 updates: [github.com/nats-io/nats.go](https://github.com/nats-io/nats.go) and [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/nats-io/nats.go` from 1.52.0 to 1.53.1\n- [Release notes](https://github.com/nats-io/nats.go/releases)\n- [Commits](https://github.com/nats-io/nats.go/compare/v1.52.0...v1.53.1)\n\nUpdates `github.com/stretchr/testify` from 1.11.1 to 1.12.0\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.11.1...v1.12.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/nats-io/nats.go\n  dependency-version: 1.53.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-18T10:25:52+03:00",
          "tree_id": "a0f8395ef48757ce53ec6295dd0e00a5682e083c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9aa48a8ab2308dca7b9509d4a5b193756db5eba"
        },
        "date": 1787039354617,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 4492,
            "range": "± 77",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 5130,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 7399,
            "range": "± 118",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 7765,
            "range": "± 64",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 77769,
            "range": "± 334",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 3937,
            "range": "± 105",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 4615,
            "range": "± 62",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 6667,
            "range": "± 47",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 6708,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 71891,
            "range": "± 164",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 3859,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 4507,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 6383,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 6577,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 71136,
            "range": "± 210",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2df31d4b69b2c8fe08488e797fedb854d89b4f1e",
          "message": "build(deps): Bump github.com/stretchr/testify (#1244)\n\nBumps the go-gateway group in /services/gateway with 1 update: [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/stretchr/testify` from 1.11.1 to 1.12.0\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.11.1...v1.12.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-18T10:26:21+03:00",
          "tree_id": "c8148c0eb1e19914015f269840240e2e4b127137",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2df31d4b69b2c8fe08488e797fedb854d89b4f1e"
        },
        "date": 1787040059840,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6025,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6950,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10005,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10662,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 101026,
            "range": "± 289",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5386,
            "range": "± 237",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6406,
            "range": "± 13",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9169,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9472,
            "range": "± 104",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93512,
            "range": "± 427",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5214,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6236,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8673,
            "range": "± 65",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9214,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91089,
            "range": "± 551",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fa5fce8cc7d375f066069e146beb1cfc25dd07d6",
          "message": "build(deps): Bump the go-file-processor group (#1245)\n\nBumps the go-file-processor group in /services/file-processor with 3 updates: [github.com/nats-io/nats.go](https://github.com/nats-io/nats.go), [github.com/stretchr/testify](https://github.com/stretchr/testify) and [golang.org/x/image](https://github.com/golang/image).\n\n\nUpdates `github.com/nats-io/nats.go` from 1.52.0 to 1.53.1\n- [Release notes](https://github.com/nats-io/nats.go/releases)\n- [Commits](https://github.com/nats-io/nats.go/compare/v1.52.0...v1.53.1)\n\nUpdates `github.com/stretchr/testify` from 1.11.1 to 1.12.0\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.11.1...v1.12.0)\n\nUpdates `golang.org/x/image` from 0.44.0 to 0.45.0\n- [Commits](https://github.com/golang/image/compare/v0.44.0...v0.45.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/nats-io/nats.go\n  dependency-version: 1.53.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: golang.org/x/image\n  dependency-version: 0.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-18T10:26:51+03:00",
          "tree_id": "1e7ef69969805bbd320a0cab1a8387553f4f7445",
          "url": "https://github.com/egorribun/university_ecosystem/commit/fa5fce8cc7d375f066069e146beb1cfc25dd07d6"
        },
        "date": 1787040746640,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6209,
            "range": "± 13",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7047,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9853,
            "range": "± 238",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10462,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 94606,
            "range": "± 1242",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5465,
            "range": "± 80",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6417,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8930,
            "range": "± 55",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9119,
            "range": "± 193",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 87322,
            "range": "± 408",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5318,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6260,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8613,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 8956,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86481,
            "range": "± 433",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1ba1b0443340a3c8ad4a380fbefc1500ef14dd9e",
          "message": "build(deps): Bump github.com/moby/go-archive in /services/file-processor (#1246)\n\nBumps [github.com/moby/go-archive](https://github.com/moby/go-archive) from 0.2.0 to 0.3.0.\n- [Release notes](https://github.com/moby/go-archive/releases)\n- [Changelog](https://github.com/moby/go-archive/blob/main/changes_test.go)\n- [Commits](https://github.com/moby/go-archive/compare/v0.2.0...v0.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/moby/go-archive\n  dependency-version: 0.3.0\n  dependency-type: indirect\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-20T13:19:57+03:00",
          "tree_id": "92e760e97cafb142a7fd7bec51c8b5a82cef95e3",
          "url": "https://github.com/egorribun/university_ecosystem/commit/1ba1b0443340a3c8ad4a380fbefc1500ef14dd9e"
        },
        "date": 1787223109322,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6149,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7029,
            "range": "± 44",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9969,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10455,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95273,
            "range": "± 1154",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5504,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6397,
            "range": "± 12",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8989,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9220,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88265,
            "range": "± 465",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5348,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6337,
            "range": "± 12",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8682,
            "range": "± 59",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9151,
            "range": "± 141",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86412,
            "range": "± 217",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "58e4c30e8584226791f26dc4bc496c074b5193f0",
          "message": "build(deps): Bump github.com/moby/go-archive in /services/gateway (#1247)\n\nBumps [github.com/moby/go-archive](https://github.com/moby/go-archive) from 0.2.0 to 0.3.0.\n- [Release notes](https://github.com/moby/go-archive/releases)\n- [Changelog](https://github.com/moby/go-archive/blob/main/changes_test.go)\n- [Commits](https://github.com/moby/go-archive/compare/v0.2.0...v0.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/moby/go-archive\n  dependency-version: 0.3.0\n  dependency-type: indirect\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-20T13:20:32+03:00",
          "tree_id": "e2327c03098a623027dc2867c420696e19b6012b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/58e4c30e8584226791f26dc4bc496c074b5193f0"
        },
        "date": 1787223883772,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6151,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7115,
            "range": "± 125",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10082,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10551,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 97610,
            "range": "± 942",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5515,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6503,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9001,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9233,
            "range": "± 47",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 89856,
            "range": "± 500",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5417,
            "range": "± 42",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6267,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8627,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9084,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 88431,
            "range": "± 754",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "24c8b9d9e83d30faee997704c0f7f18c24534968",
          "message": "build(deps): Bump github.com/moby/go-archive in /services/ws-hub (#1248)\n\nBumps [github.com/moby/go-archive](https://github.com/moby/go-archive) from 0.2.0 to 0.3.0.\n- [Release notes](https://github.com/moby/go-archive/releases)\n- [Changelog](https://github.com/moby/go-archive/blob/main/changes_test.go)\n- [Commits](https://github.com/moby/go-archive/compare/v0.2.0...v0.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/moby/go-archive\n  dependency-version: 0.3.0\n  dependency-type: indirect\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-20T13:21:13+03:00",
          "tree_id": "76203f103116dbeea27498f9b1cc2586e2ee3341",
          "url": "https://github.com/egorribun/university_ecosystem/commit/24c8b9d9e83d30faee997704c0f7f18c24534968"
        },
        "date": 1787224138074,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6017,
            "range": "± 107",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7032,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10119,
            "range": "± 86",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10728,
            "range": "± 108",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100806,
            "range": "± 411",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5482,
            "range": "± 128",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6430,
            "range": "± 52",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9129,
            "range": "± 47",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9429,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 94045,
            "range": "± 605",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5366,
            "range": "± 84",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6318,
            "range": "± 36",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8753,
            "range": "± 43",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9339,
            "range": "± 80",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91309,
            "range": "± 502",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18d4265d2452513e4e3177747f163282a2b5c85d",
          "message": "feat(wave212): harden multi-stack MVP foundation, resolve CI/CD matrix, and certify quality contract (#1249)\n\n* test(quality): harden external quality gates\n\n* test(quality): align dependency policy contract\n\n* test(quality): record remote closure evidence\n\n* test(quality): reset dishka lifecycle between runs\n\n* test(quality): record mutation regression and rerun\n\n* test(quality): add manual performance benchmark dispatch\n\n* test(quality): reset Dishka state across ASGI lifecycles\n\n* test(quality): preserve lifespan app fixture identity\n\n* test(quality): isolate dishka containers between lifespans\n\n* docs(quality): record dishka lifecycle closure evidence\n\n* test(quality): fix nested radio label markup\n\n* test(quality): make settings accordion deterministic\n\n* test(quality): reopen accordion after remount\n\n* test(quality): wait for expanded language controls\n\n* test(quality): align TOTP accordion contract\n\n* test(quality): isolate nightly permission checks\n\n* test(quality): target visible language accordion\n\n* test(quality): activate custom language radio label\n\n* test(quality): harden nightly browser and image isolation\n\n* test(quality): wait for hydrated login before tab audit\n\n* test(quality): wait for hydrated settings accordion\n\n* test(quality): retry transient browser navigations\n\n* test(quality): harden all transient e2e navigations\n\n* docs(quality): record current closure evidence\n\n* docs(quality): record frontend mutation evidence\n\n* fix(quality): harden mutation and image test isolation\n\n* fix(quality): handle mutmut non-function nodes\n\n* docs(quality): add closure handoff\n\n* fix(quality): isolate mutmut class-method fixture\n\n* fix(quality): enforce complete mutation evidence\n\n* test(quality): link legacy mutmut coverage test\n\n* fix(security): gate DAST label scans\n\n* fix(docs): satisfy markdown quality gate\n\n* fix(security): isolate manual mutation evidence\n\n* fix(quality): harden evidence and strict test gates\n\n* fix(quality): secure promotion evidence gates\n\n* fix(quality): repair mutation and coverage gates\n\n* fix(quality): stabilize Rust coverage gate\n\n* fix(quality): isolate Rust coverage artifacts\n\n* fix(quality): isolate mutmut clean baselines\n\n* test(quality): stabilize mutmut image isolation\n\n* test(quality): cover native scheduler non-spanning conflict\n\n* fix(quality): harden workflow closure gates\n\n* fix(quality): trigger required rust fuzz on workflow changes\n\n* fix(quality): copy gitignore into mutmut sandbox\n\n* docs(quality): specify same-run performance gates\n\n* fix(ci): give incremental mutmut a safe execution envelope\n\n* fix(quality): enforce portable JSON nesting limit\n\n* docs(quality): record live closure evidence\n\n* docs(quality): track current nightly queue\n\n* docs(quality): confirm Codecov processing\n\n* fix(security): harden push endpoints and trusted CI\n\n* docs(quality): record security hardening and nightly queue\n\n* docs(quality): quantify residual dependency advisories\n\n* docs(quality): record nightly queue replacement\n\n* fix(security): scope nightly workflow permissions\n\n* docs(quality): record current security and Codecov evidence\n\n* fix(security): block mapped IPv4 SSRF literals\n\n* docs(quality): record mapped IPv6 SSRF closure\n\n* docs(quality): record terminal nightly queue state\n\n* fix(ci): parallelize full mutmut stats collection\n\n* docs(quality): record parallel nightly mutation stats\n\n* fix(ci): report nightly mutation stats failures\n\n* docs(quality): record nightly failure notification guard\n\n* fix(ci): parallelize full mutation execution\n\n* docs(quality): record parallel mutation execution\n\n* docs(quality): record certification secret configuration\n\n* docs(quality): record DAST deferral\n\n* docs(quality): refresh live closure audit\n\n* test(quality): cover SQLMap workflow contract\n\n* docs(quality): record SQLMap contract refresh\n\n* docs(quality): record current-head validation trigger\n\n* docs(quality): record TruffleHog remediation\n\n* docs(quality): avoid scanner trigger wording\n\n* test(quality): close webpush mutation survivors\n\n* fix(security): avoid URI scanner false positive\n\n* test(quality): close diff coverage branches\n\n* test(quality): cover SSRF port guard\n\n* fix(ci): ensure required fuzz contexts run\n\n* test(webpush): cover development DNS fallback\n\n* docs(quality): record current-head CI closure\n\n* docs(quality): record rerun validation\n\n* fix(webpush): make development fallback mutation-proof\n\n* docs(quality): record mutation closure evidence\n\n* docs(quality): pin final evidence checkpoint\n\n* test(quality): cover dagger pipeline proposal\n\n* fix(quality): canonicalize mutmut package names\n\n* test(quality): cover scheduler mutation mapping\n\n* test(quality): cover pyroscope profiler mapping\n\n* test(quality): cover uvloop detection mapping\n\n* test(quality): cover event file repr mapping\n\n* test(quality): cover event repr mapping\n\n* test(quality): cover news comment repr mapping\n\n* test(quality): cover model repr mappings\n\n* test(quality): cover user file cleanup mapping\n\n* test(quality): cover worker entrypoint mapping\n\n* test(quality): cover cdc fallback mapping\n\n* docs: specify standalone logo loader\n\n* fix(ci): reuse validated bundle for lighthouse shards\n\n* docs: plan standalone logo loader\n\n* docs: specify application logo loader integration\n\n* fix(ci): build dedicated lighthouse bundle\n\n* docs: plan application logo loader integration\n\n* feat: publish app hydration completion\n\n* feat: add SSR brand boot loader\n\n* feat: add critical brand loader animation\n\n* feat: mount logo loader in app shell\n\n* feat: harden adaptive brand boot loader\n\n* fix(docker): harden full-stack startup and deployment contracts\n\n* fix(security): harden release dependency chain\n\n* docs(quality): design repository closure\n\n* fix(ci): repair coverage and vulnerability gates\n\n* chore(quality): checkpoint repository closure work\n\n* fix(quality): close Python gate regressions\n\n* fix(frontend): handle delayed reminder rollover\n\n* fix(frontend): restore strict typecheck\n\n* fix(security): fail closed dependency audit gates\n\n* fix(security): harden auth and deployment foundations\n\n* test(quality): checkpoint cross-stack closure\n\n* fix(infra): eliminate frontend docker build-hack and harden otel logging\n\n* feat(wave212): resolve PR 1249 CI checks and certify multi-stack architecture\n\n* feat(wave212): allowlist mmh3 and ammonia in dependency review config\n\n* feat(wave212): synchronize go work sum for microservices workspace\n\n* feat(wave212): fix test import sorting and benchmark prefetch flags\n\n* feat(wave212): align go toolchain directive with base container\n\n* feat(wave212): synchronize ws-hub dependencies and benchmark isolation flags\n\n* feat(wave212): allow workspace benchmark capture helper\n\n* feat(wave212): align workflow runners, actionlint and secrets baseline\n\n* feat(wave212): synchronize go module manifests with base toolchain contract\n\n* feat(wave212): direct benchmark logger output to discard writer\n\n* feat(wave212): bound memory allocations in ws-hub benchmarks\n\n* feat(wave212): scope shellcheck actionlint ignore for nightly-full-gate workflow\n\n* feat(wave212): extend actionlint ignores for all workflows\n\n* feat(wave212): resolve shellcheck notices in workflow shell steps\n\n* feat(wave212): allowlist secret keywords in deploy documentation\n\n* feat(wave212): ignore non-k8s config files in static kubeconform validation\n\n* feat(wave212): resolve CI gates for go coverage, alembic squawk, frontend formatting, and policy tests\n\n* feat(wave212): annotate intentional error discards with nolint errcheck for golangci-lint\n\n* feat(wave212): fix alembic squawk exclusions, golangci test linter rules, and gateway prometheus mock\n\n* feat(wave212): fix go-mutesting package resolution and toolchain compatibility in reusable workflow\n\n* feat(wave212): guard gateway prometheus registration in test mode to avoid port collisions\n\n* feat(wave212): remediate tech debt, optimize query and state hooks, harden k8s and graphql\n\n* feat(wave212): use test context in gateway tests to cleanly cancel background listeners\n\n* feat(wave212): fix ci check regressions across gateway, di, auth flow, and frontend tests\n\n* feat(wave212): synchronize gateway package hooks to prevent data race under cgo race detector\n\n* feat(wave212): track harness assets and synchronize markdown documentation\n\n* feat(wave212): harden developer harness, quality gates and documentation sync\n\n* feat(wave212): synchronize milestone completion status and ws-hub client safe send\n\n* fix(wave212): decompose ws-hub broadcastMessage to satisfy cyclomatic complexity linter\n\n* fix(wave212): sanitize documentation connection strings to satisfy detect-secrets\n\n* fix(wave212): parametrize all mcp connection strings to satisfy detect-secrets\n\n* fix(wave212): optimize ws-hub broadcast inner loop and normalize auth cookie test\n\n* fix(wave212): align BenchmarkSafeSend allocation logic with base benchmark contract\n\n* fix(wave212): harden cross-stack quality gates\n\n* fix(wave212): close workflow quality gates\n\n* fix(wave212): satisfy nilaway tracer contract\n\n* fix(wave212): correct pinned helm action revision\n\n* fix(wave212): repair PR quality gates and E2E auth\n\n* fix(wave212): extend Go mutation file budget\n\n* fix(wave212): harden offline news and event pagination E2E\n\n* fix(wave212): isolate deployment contract from mutmut copies\n\n* fix(wave212): document isolated contract skip ownership\n\n* fix(wave212): harden offline shell and isolated quality checks\n\n* fix(wave212): satisfy inventory skip ownership contract\n\n* fix(wave212): add Go fuzz shutdown headroom\n\n* fix(test): stabilize schedule E2E fixture across dates\n\n* fix(ci): unblock isolated quality and Go mutation checks\n\n* fix(ci): complete mutmut sandbox document contract\n\n* fix(ci): include SPIRE manifests in mutation sandbox\n\n* fix(ci): align mutation execution with verified budget\n\n* fix(ci): avoid SQLite contention in mutation shards\n\n* fix(ci): rebalance mutation statistics shards\n\n* fix(quality): close mutation and gateway verification gaps\n\n* fix(quality): close mutation survivor and timeout\n\n* fix(quality): assert outbox marker cleanup flags\n\n* fix(ci): retry transient OSV audit outages\n\n* fix(quality): close remaining mutation gaps\n\n* fix(ci): retry transient Helm dependency outages\n\n* fix(quality): assert feature and storage defaults\n\n* fix(quality): close exact mutation survivors\n\n* fix(quality): assert outbox shutdown cleanup\n\n* fix(quality): front-load mutation boundary contracts\n\n* fix(quality): cover naive dead-letter cleanup timestamps\n\n* fix(quality): cover nats reconnect policy\n\n* fix(quality): assert exact retention validation error\n\n* fix(quality): cover database and outbox contracts\n\n* fix(quality): close exact mutation survivors\n\n* fix(quality): close retry, DLQ and surrogate mutation gaps\n\n* fix(docker): reconcile compose env and retry dependency fetches\n\n* fix(quality): cover owned-session retention forwarding\n\n* fix(quality): close exact mutation survivors\n\n* fix(quality): remove equivalent Rust cast mutant\n\n* fix(quality): cover gateway revocation listener branches\n\n* fix(quality): make revocation timer test race-safe\n\n* fix(quality): close remaining mutation survivors\n\n* fix(quality): cover final mutation survivors\n\n* fix(quality): remove equivalent webpush timestamp mutant\n\n* fix(quality): remove unreachable retry assertion mutant\n\n* fix(quality): close image utility mutation survivors\n\n* fix(quality): type image resampling fallback explicitly\n\n* fix(quality): cover exact Pillow resampling lookup\n\n* fix(quality): isolate SPIFFE temp leak assertion\n\n* fix(quality): cover notification cleanup UTC default\n\n* fix(quality): enforce UTC cutoff normalization\n\n* fix(quality): bound uuid allocator mutation runtime\n\n* fix(quality): close remaining exact mutation gaps\n\n* fix(quality): remove equivalent notification result cast\n\n* fix(quality): isolate mutation-sensitive reconstruction paths\n\n* fix(quality): assert naive cleanup clocks use UTC\n\n* fix(quality): avoid surrogate allocator mutation timeout\n\n* fix(quality): close retry and cleanup mutation survivors\n\n* fix(quality): parallelize isolated Go mutation checks\n\n* fix(quality): satisfy shellcheck cleanup trap\n\n* fix(quality): kill UUID conversion mutant\n\n* fix(quality): close offline and mutation gaps\n\n* fix(quality): widen mutmut watchdog reserve\n\n* fix(quality): keep PWA precache within browser budgets\n\n* fix(quality): stabilize mutation watchdog and secret baseline\n\n* fix(quality): synchronize secrets baseline line numbers\n\n* fix(quality): refresh build and localization references\n\n* fix(quality): harden diagnostic build and mutation gates\n\n* fix(quality): align CI workflow checks and secret baseline\n\n* fix(quality): refresh deployment secret baseline\n\n* fix(quality): close aggregate coverage gaps\n\n* fix(quality): align mutation timeout envelope\n\n* fix(quality): correct mutation deadline diagnostic\n\n* fix(quality): disable unstable frontend AST remapping\n\n* fix(quality): close coverage and mutation regressions\n\n* fix(quality): remove synthetic frontend coverage callback\n\n* fix(docs): align ADR references with current implementation\n\n* fix(quality): cover late websocket timeout branch\n\n* fix(quality): cover fog particle recycle branch\n\n* fix(quality): clear news like celebration timer\n\n* fix(quality): cover repeated news celebration\n\n* fix(quality): stabilize SSR auth coverage mapping\n\n* fix(quality): close mutation and browser gates\n\n* fix(quality): align cache integration invalidation\n\n* fix(quality): isolate native schedule tests from mutmut\n\n* fix(quality): close gateway coverage gap\n\n* fix(quality): kill schedule conflict survivors\n\n* fix(quality): shard schemathesis and close mutation gaps\n\n* fix(quality): apply schemathesis filters before fixture resolution\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-25T00:51:11+03:00",
          "tree_id": "854a7bdf3be0cd0dc16dc7b1fa20c155aa7c0b88",
          "url": "https://github.com/egorribun/university_ecosystem/commit/18d4265d2452513e4e3177747f163282a2b5c85d"
        },
        "date": 1787613858908,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5999,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6990,
            "range": "± 56",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10115,
            "range": "± 135",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10805,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 98408,
            "range": "± 584",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5396,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6384,
            "range": "± 54",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9115,
            "range": "± 70",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9448,
            "range": "± 135",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 92010,
            "range": "± 3729",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5268,
            "range": "± 46",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6238,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8820,
            "range": "± 37",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9300,
            "range": "± 84",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 89975,
            "range": "± 1718",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bfe06224c06acf441952513fc5f98471e4315919",
          "message": "build(deps): Bump github.com/stretchr/testify (#1251)\n\nBumps the go-ws-hub group in /services/ws-hub with 1 update: [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/stretchr/testify` from 1.12.0 to 1.12.1\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.12.0...v1.12.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-25T00:57:16+03:00",
          "tree_id": "9508721ac18bdff1a3d94bd12af7d3d968a8788a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/bfe06224c06acf441952513fc5f98471e4315919"
        },
        "date": 1787615381325,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 4814,
            "range": "± 99",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 5493,
            "range": "± 72",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 7730,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 8278,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 73686,
            "range": "± 391",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 4665,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 5893,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 7352,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 7560,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 69445,
            "range": "± 1028",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 4205,
            "range": "± 87",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 5301,
            "range": "± 214",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 6672,
            "range": "± 205",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 6993,
            "range": "± 43",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 67522,
            "range": "± 2550",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d8fe19f41c69a9dbaf57921884204b1b0133afa3",
          "message": "build(deps): Bump the go-file-processor group (#1252)\n\nBumps the go-file-processor group in /services/file-processor with 2 updates: [github.com/minio/minio-go/v7](https://github.com/minio/minio-go) and [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/minio/minio-go/v7` from 7.2.1 to 7.3.0\n- [Release notes](https://github.com/minio/minio-go/releases)\n- [Commits](https://github.com/minio/minio-go/compare/v7.2.1...v7.3.0)\n\nUpdates `github.com/stretchr/testify` from 1.12.0 to 1.12.1\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.12.0...v1.12.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/minio/minio-go/v7\n  dependency-version: 7.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-25T00:57:48+03:00",
          "tree_id": "bac37fca2efdc33c84e1dbd37047f9dbf09ed6f9",
          "url": "https://github.com/egorribun/university_ecosystem/commit/d8fe19f41c69a9dbaf57921884204b1b0133afa3"
        },
        "date": 1787615388648,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6199,
            "range": "± 12",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7194,
            "range": "± 27",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10119,
            "range": "± 124",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10806,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95685,
            "range": "± 242",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5597,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6483,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9059,
            "range": "± 159",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9424,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 87661,
            "range": "± 523",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5398,
            "range": "± 8",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6388,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8861,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9309,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86087,
            "range": "± 336",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5eba3aff70220f27fd82a7d5b736cee2dc97cfad",
          "message": "build(deps): Bump github.com/stretchr/testify (#1253)\n\nBumps the go-gateway group in /services/gateway with 1 update: [github.com/stretchr/testify](https://github.com/stretchr/testify).\n\n\nUpdates `github.com/stretchr/testify` from 1.12.0 to 1.12.1\n- [Release notes](https://github.com/stretchr/testify/releases)\n- [Commits](https://github.com/stretchr/testify/compare/v1.12.0...v1.12.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/stretchr/testify\n  dependency-version: 1.12.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-25T00:58:56+03:00",
          "tree_id": "7d2068a24ee67bb647451276935b105abbd5ae44",
          "url": "https://github.com/egorribun/university_ecosystem/commit/5eba3aff70220f27fd82a7d5b736cee2dc97cfad"
        },
        "date": 1787615586969,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5945,
            "range": "± 54",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6932,
            "range": "± 170",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9961,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10794,
            "range": "± 61",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 97457,
            "range": "± 260",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5606,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6537,
            "range": "± 60",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9217,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9505,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 92262,
            "range": "± 8149",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5238,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6152,
            "range": "± 49",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8607,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9111,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90061,
            "range": "± 770",
            "unit": "ns/iter"
          }
        ]
      }
    ],
    "Rust Native Optimizer Regression Gate": [
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817311996,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 10203,
            "range": "± 289",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 28533,
            "range": "± 640",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 47517,
            "range": "± 1379",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 257463,
            "range": "± 7021",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191545222,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 10711,
            "range": "± 585",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 18552,
            "range": "± 676",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 30807,
            "range": "± 909",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 260262,
            "range": "± 8911",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191600606,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13302,
            "range": "± 337",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22665,
            "range": "± 1083",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39566,
            "range": "± 3707",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 341535,
            "range": "± 10437",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f237c814f173127f3da824054e54268c0b13916c",
          "message": "build(deps): Bump github.com/prometheus/client_golang from 1.24.0 to 1.24.1 in /services/ws-hub in the go-ws-hub group\n\nBumps the go-ws-hub group in /services/ws-hub with 1 update: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:41:59+05:00",
          "tree_id": "79e11a838dd1d04b22410bddc066c133f55b7ee1",
          "url": "https://github.com/egorribun/university_ecosystem/commit/f237c814f173127f3da824054e54268c0b13916c"
        },
        "date": 1785861990405,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13543,
            "range": "± 298",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22750,
            "range": "± 2395",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39183,
            "range": "± 1194",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 339244,
            "range": "± 8332",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9ec989da7f5d0df782b673fb2d50d68768437f45",
          "message": "build(deps): Update fastapi requirement from <0.141,>=0.135.3 to >=0.135.3,<0.142 in the pip-dependencies group\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi) to permit the latest version.\n\nUpdates `fastapi` to 0.141.1\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.141.1)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.141.1\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:42:47+05:00",
          "tree_id": "7ec6b02cd9bfa17c94c0e69c3cedacb3f6fa15db",
          "url": "https://github.com/egorribun/university_ecosystem/commit/9ec989da7f5d0df782b673fb2d50d68768437f45"
        },
        "date": 1785862077308,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13593,
            "range": "± 945",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22649,
            "range": "± 478",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 40298,
            "range": "± 2204",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 344970,
            "range": "± 9628",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c2d8ff6bf96176839f211ad558dfca6d90176f0d",
          "message": "ci(deps): Bump the github-actions group with 5 updates\n\nBumps the github-actions group with 5 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.5.1` | `4.6.0` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.0` | `4.2.1` |\n\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/init` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/analyze` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `docker/login-action` from 4.5.1 to 4.6.0\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/abd2ef45e78c5afb21d64d4ca52ee8550d9572c7...dbcb813823bdd20940b903addbd779551569679f)\n\nUpdates `actions/attest` from 4.2.0 to 4.2.1\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6...508db95dd578ae2727ebd6217d5ba78e4fbda05d)\n\n---\nupdated-dependencies:\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.6.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:43:42+05:00",
          "tree_id": "d4b018610642655bc581ca575c9905429435dd0f",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c2d8ff6bf96176839f211ad558dfca6d90176f0d"
        },
        "date": 1785862648329,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13438,
            "range": "± 564",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22791,
            "range": "± 2884",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39701,
            "range": "± 1301",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 341797,
            "range": "± 9477",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "31483859811bd2cffb4671782d4d8dfeb3e9e376",
          "message": "build(deps): Bump the go-gateway group across 1 directory with 2 updates\n\nBumps the go-gateway group with 2 updates in the /services/gateway directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:44:45+05:00",
          "tree_id": "7184b30dc72715dc394cc5ddb078f2fb3fa4742d",
          "url": "https://github.com/egorribun/university_ecosystem/commit/31483859811bd2cffb4671782d4d8dfeb3e9e376"
        },
        "date": 1785863089006,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13876,
            "range": "± 471",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 24321,
            "range": "± 1187",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 40663,
            "range": "± 1567",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 342813,
            "range": "± 15908",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "913c0db5636d6c86e28b1fc517288e551d5277ea",
          "message": "build(deps): Bump the go-file-processor group across 1 directory with 4 updates\n\nBumps the go-file-processor group with 4 updates in the /services/file-processor directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang), [go.temporal.io/api](https://github.com/temporalio/api-go), [go.temporal.io/sdk](https://github.com/temporalio/sdk-go) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `go.temporal.io/api` from 1.63.3 to 1.63.4\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.3...v1.63.4)\n\nUpdates `go.temporal.io/sdk` from 1.46.0 to 1.47.0\n- [Release notes](https://github.com/temporalio/sdk-go/releases)\n- [Changelog](https://github.com/temporalio/sdk-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/temporalio/sdk-go/compare/v1.46.0...v1.47.0)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/sdk\n  dependency-version: 1.47.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:02+05:00",
          "tree_id": "21adb758ca2821b4dc7f83d18e95b38375e28557",
          "url": "https://github.com/egorribun/university_ecosystem/commit/913c0db5636d6c86e28b1fc517288e551d5277ea"
        },
        "date": 1785863222176,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13484,
            "range": "± 685",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22602,
            "range": "± 1113",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 38995,
            "range": "± 1727",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 338849,
            "range": "± 9007",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4d8fcde61831ab6443e1f8dbfa86e644e3c28809",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [msgpack](https://github.com/msgpack/msgpack-python) and [pip](https://github.com/pypa/pip).\n\n\nUpdates `msgpack` from 1.1.2 to 1.2.1\n- [Release notes](https://github.com/msgpack/msgpack-python/releases)\n- [Changelog](https://github.com/msgpack/msgpack-python/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/msgpack/msgpack-python/compare/v1.1.2...v1.2.1)\n\nUpdates `pip` from 26.1 to 26.1.2\n- [Changelog](https://github.com/pypa/pip/blob/main/NEWS.rst)\n- [Commits](https://github.com/pypa/pip/compare/26.1...26.1.2)\n\n---\nupdated-dependencies:\n- dependency-name: msgpack\n  dependency-version: 1.2.1\n  dependency-type: indirect\n  dependency-group: uv\n- dependency-name: pip\n  dependency-version: 26.1.2\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:28+05:00",
          "tree_id": "d8c3204dc26f383bcbfda522958a3b9258229d5e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/4d8fcde61831ab6443e1f8dbfa86e644e3c28809"
        },
        "date": 1785863462831,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13430,
            "range": "± 438",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22837,
            "range": "± 1346",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39823,
            "range": "± 2066",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 346984,
            "range": "± 10057",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "dd9c6405161d8ec6c5bc34bd617712f667abe2d5",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [pyasn1](https://github.com/pyasn1/pyasn1) and [aiohttp](https://github.com/aio-libs/aiohttp).\n\n\nUpdates `pyasn1` from 0.6.3 to 0.6.4\n- [Release notes](https://github.com/pyasn1/pyasn1/releases)\n- [Changelog](https://github.com/pyasn1/pyasn1/blob/main/CHANGES.rst)\n- [Commits](https://github.com/pyasn1/pyasn1/compare/v0.6.3...v0.6.4)\n\nUpdates `aiohttp` from 3.14.1 to 3.14.3\n- [Changelog](https://github.com/aio-libs/aiohttp/blob/master/CHANGES.rst)\n- [Commits](https://github.com/aio-libs/aiohttp/compare/v3.14.1...v3.14.3)\n\n---\nupdated-dependencies:\n- dependency-name: pyasn1\n  dependency-version: 0.6.4\n  dependency-type: direct:production\n  dependency-group: uv\n- dependency-name: aiohttp\n  dependency-version: 3.14.3\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-05T00:36:25+05:00",
          "tree_id": "4af11d38f9b1dc1eacfe0e5b24369e5b9f8c65b7",
          "url": "https://github.com/egorribun/university_ecosystem/commit/dd9c6405161d8ec6c5bc34bd617712f667abe2d5"
        },
        "date": 1785872270941,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13452,
            "range": "± 663",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22687,
            "range": "± 714",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39568,
            "range": "± 4399",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 339755,
            "range": "± 6213",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "59a94734bf71377c8f83f1b486ae1f44d7a97070",
          "message": "ci(deps): Bump the npm_and_yarn group across 2 directories with 13 updates (#1226)\n\nBumps the npm_and_yarn group with 4 updates in the / directory: [undici](https://github.com/nodejs/undici), [handlebars](https://github.com/handlebars-lang/handlebars.js), [lodash](https://github.com/lodash/lodash) and [minimatch](https://github.com/isaacs/minimatch).\nBumps the npm_and_yarn group with 7 updates in the /frontend directory:\n\n| Package | From | To |\n| --- | --- | --- |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `5.0.7` | `5.0.9` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `2.1.2` | `2.1.4` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `1.1.16` | `1.1.18` |\n| [ip-address](https://github.com/beaugunderson/ip-address) | `10.2.0` | `10.4.0` |\n| [@vitest/browser](https://github.com/vitest-dev/vitest/tree/HEAD/packages/browser) | `3.2.6` | `4.1.10` |\n| [postcss](https://github.com/postcss/postcss) | `8.5.16` | `8.5.25` |\n| [sharp](https://github.com/lovell/sharp) | `0.34.5` | `0.35.0` |\n| [dompurify](https://github.com/cure53/DOMPurify) | `3.4.11` | `3.4.13` |\n| [fast-uri](https://github.com/fastify/fast-uri) | `3.1.2` | `3.1.5` |\n\n\n\nUpdates `undici` from 6.23.0 to 6.28.0\n- [Release notes](https://github.com/nodejs/undici/releases)\n- [Commits](https://github.com/nodejs/undici/compare/v6.23.0...v6.28.0)\n\nUpdates `handlebars` from 4.7.8 to 4.7.9\n- [Release notes](https://github.com/handlebars-lang/handlebars.js/releases)\n- [Changelog](https://github.com/handlebars-lang/handlebars.js/blob/v4.7.9/release-notes.md)\n- [Commits](https://github.com/handlebars-lang/handlebars.js/compare/v4.7.8...v4.7.9)\n\nUpdates `lodash` from 4.17.23 to 4.18.1\n- [Release notes](https://github.com/lodash/lodash/releases)\n- [Commits](https://github.com/lodash/lodash/compare/4.17.23...4.18.1)\n\nUpdates `minimatch` from 10.2.2 to 10.2.5\n- [Changelog](https://github.com/isaacs/minimatch/blob/main/changelog.md)\n- [Commits](https://github.com/isaacs/minimatch/compare/v10.2.2...v10.2.5)\n\nUpdates `sigstore` from 4.1.0 to 4.1.1\n- [Release notes](https://github.com/sigstore/sigstore-js/releases)\n- [Commits](https://github.com/sigstore/sigstore-js/compare/sigstore@4.1.0...sigstore@4.1.1)\n\nUpdates `tar` from 7.5.9 to 7.5.19\n- [Release notes](https://github.com/isaacs/node-tar/releases)\n- [Changelog](https://github.com/isaacs/node-tar/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/isaacs/node-tar/compare/v7.5.9...v7.5.19)\n\nUpdates `brace-expansion` from 5.0.7 to 5.0.9\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 2.1.2 to 2.1.4\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 1.1.16 to 1.1.18\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `ip-address` from 10.2.0 to 10.4.0\n- [Release notes](https://github.com/beaugunderson/ip-address/releases)\n- [Commits](https://github.com/beaugunderson/ip-address/compare/v10.2.0...v10.4.0)\n\nUpdates `@vitest/browser` from 3.2.6 to 4.1.10\n- [Release notes](https://github.com/vitest-dev/vitest/releases)\n- [Changelog](https://github.com/vitest-dev/vitest/blob/main/docs/releases.md)\n- [Commits](https://github.com/vitest-dev/vitest/commits/v4.1.10/packages/browser)\n\nUpdates `postcss` from 8.5.16 to 8.5.25\n- [Release notes](https://github.com/postcss/postcss/releases)\n- [Changelog](https://github.com/postcss/postcss/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/postcss/postcss/compare/8.5.16...8.5.25)\n\nUpdates `sharp` from 0.34.5 to 0.35.0\n- [Release notes](https://github.com/lovell/sharp/releases)\n- [Commits](https://github.com/lovell/sharp/compare/v0.34.5...v0.35.0)\n\nUpdates `dompurify` from 3.4.11 to 3.4.13\n- [Release notes](https://github.com/cure53/DOMPurify/releases)\n- [Commits](https://github.com/cure53/DOMPurify/compare/3.4.11...3.4.13)\n\nUpdates `fast-uri` from 3.1.2 to 3.1.5\n- [Release notes](https://github.com/fastify/fast-uri/releases)\n- [Commits](https://github.com/fastify/fast-uri/compare/v3.1.2...v3.1.5)\n\n---\nupdated-dependencies:\n- dependency-name: undici\n  dependency-version: 6.28.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: handlebars\n  dependency-version: 4.7.9\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: lodash\n  dependency-version: 4.18.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: minimatch\n  dependency-version: 10.2.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: sigstore\n  dependency-version: 4.1.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: tar\n  dependency-version: 7.5.19\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 5.0.9\n  dependency-type: direct:production\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 2.1.4\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 1.1.18\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: ip-address\n  dependency-version: 10.4.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: \"@vitest/browser\"\n  dependency-version: 4.1.10\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: postcss\n  dependency-version: 8.5.25\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: sharp\n  dependency-version: 0.35.0\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: dompurify\n  dependency-version: 3.4.13\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: fast-uri\n  dependency-version: 3.1.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T23:16:53+03:00",
          "tree_id": "358d295e79f3adb3f6a4dbcc1688157540dcc98a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/59a94734bf71377c8f83f1b486ae1f44d7a97070"
        },
        "date": 1785874695984,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 11131,
            "range": "± 445",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 31300,
            "range": "± 733",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 54181,
            "range": "± 1102",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 303425,
            "range": "± 8731",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "496ed7f2c5c0fd33da738b4687b4c31281f14d7e",
          "message": "fix(ci): restore checks after draft pull requests become ready (#1227)\n\n* feat(wave212): remove obsolete handoff prompt\n\n* fix(ci): trigger checks when draft PR becomes ready\n\n* test(quality): cover gateway TLS certificate failure paths\n\n* fix(ci): keep required OpenAPI check live on every PR\n\n* fix(ci): run frontend mutation gate during manual recovery\n\n* test(gateway): satisfy Go lint and nil analysis\n\n* fix(ci): add manual recovery triggers for Go analysis\n\n* fix(ci): make gosec test directive effective\n\n* fix(ci): use canonical lighthouse assertions\n\n* fix(ci): eliminate ws-hub shutdown race\n\n* fix(ci): handle ws-hub socket cleanup error\n\n* fix(ci): reduce ws-hub server complexity\n\n* fix(ci): align lighthouse gates with canonical config\n\n* fix(ci): isolate backend integration test scope\n\n* fix(ci): start minio for chaos services\n\n* fix(quality): consume frontend statement coverage\n\n* fix(ci): close PR check and coverage gaps\n\n* fix(ci): close analyzer findings\n\n* fix(ci): drain file processor servers before return\n\n* fix(ci): close coverage gate deficits\n\n* fix(ci): make PR quality gate reproducible\n\n* fix(ci): prevent security scan alert drift\n\n* fix(ci): retry testcontainer image pulls\n\n* fix(ci): stabilize browser e2e execution\n\n* fix(ci): close mutation and tier0 coverage gaps\n\n* fix(ci): unblock code scanning ruleset\n\n* fix(ci): preserve scoped trivy suppressions\n\n* fix(ci): filter suppressed checkov alerts\n\n* fix(ci): write filtered checkov sarif separately\n\n* fix(ci): use one trivy ignore format\n\n* fix(ci): make Semgrep SARIF analysis reliable\n\n* fix(ci): make Semgrep pull requests diff-aware\n\n* fix(ci): close Semgrep findings in integration gate\n\n* fix(ci): make gateway race performance gate stable\n\n* fix(ci): remove golangci schema network dependency\n\n* fix(ci): avoid redundant Lighthouse dependency bootstrap\n\n* fix(ci): close session crypto coverage branch\n\n* fix(ci): include workflow contract inputs in mutmut sandbox\n\n* fix(test): bound Miri sanitizer payload\n\n* fix(test): reduce Miri sanitizer fixture\n\n* fix(test): invalidate cached JWT keys on rotation\n\n* fix(test): isolate notification metrics state\n\n* chore: update codebase test coverage reports and configuration files\n\n* fix(ci): balance incremental mutmut shards\n\n* fix(test): clean up SPIFFE stress test lint\n\n* fix(test): isolate ChatWindow render suites\n\n* fix(frontend): guard profile sync auto-fetch reruns\n\n* fix(test): isolate profile coverage suites\n\n* fix(test): isolate component coverage suites\n\n* fix(test): isolate event hero coverage suites\n\n* fix(test): isolate schedule and event file suites\n\n* chore(test): checkpoint current branch changes\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-08T21:40:49+03:00",
          "tree_id": "26101b1ba5348abe8e9c0a22c539a733d8f96e1b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/496ed7f2c5c0fd33da738b4687b4c31281f14d7e"
        },
        "date": 1786214795987,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 679,
            "range": "± 7",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22838,
            "range": "± 4298",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 35952,
            "range": "± 1595",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 236883,
            "range": "± 6601",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada",
          "message": "ci(deps): Bump the github-actions group with 9 updates (#1230)\n\nBumps the github-actions group with 9 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [dtolnay/rust-toolchain](https://github.com/dtolnay/rust-toolchain) | `2c7215f132e9ebf062739d9130488b56d53c060c` | `6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.3114.0` | `12.3115.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `24.1.0` | `24.2.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.1` | `4.2.2` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.1` | `0.6.2` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/v7...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `dtolnay/rust-toolchain` from 2c7215f132e9ebf062739d9130488b56d53c060c to 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n- [Release notes](https://github.com/dtolnay/rust-toolchain/releases)\n- [Commits](https://github.com/dtolnay/rust-toolchain/compare/2c7215f132e9ebf062739d9130488b56d53c060c...6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772)\n\nUpdates `bridgecrewio/checkov-action` from 12.3114.0 to 12.3115.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/7b972723c44fb3d256283fac96fae5d7c1894bb7...9b70310bcd306d11740313070b940167d6b23085)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 24.1.0 to 24.2.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/6bf21b07787794f89a243495939cd651942aeabe...21c1be1b93ad9ed58fa840aacc3f279cde2a72ff)\n\nUpdates `github/codeql-action/init` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `github/codeql-action/analyze` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `actions/attest` from 4.2.1 to 4.2.2\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/508db95dd578ae2727ebd6217d5ba78e4fbda05d...1e69f48acb82d1966a394da916b4c1698aa569d6)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.1 to 0.6.2\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6fc4b006235f201fdab3722e17240ab420d580e5...3dc1ecc9bcb9e94e9b2c709687979e1298497054)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3115.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-10T12:31:09+03:00",
          "tree_id": "943e83367d58b7cd70d48bf646ef00f5ad5c36ce",
          "url": "https://github.com/egorribun/university_ecosystem/commit/8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada"
        },
        "date": 1786354350120,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 615,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 21316,
            "range": "± 1494",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 34537,
            "range": "± 761",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 238155,
            "range": "± 7057",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "83beb35c866c4baa10b60e2ef95c663568a3c58e",
          "message": "build(deps): Bump the go-file-processor group (#1233)\n\nBumps the go-file-processor group in /services/file-processor with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/minio](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.temporal.io/api](https://github.com/temporalio/api-go) | `1.63.4` | `1.63.5` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/minio` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.temporal.io/api` from 1.63.4 to 1.63.5\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.4...v1.63.5)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/minio\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.5\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-11T14:12:40+03:00",
          "tree_id": "d51f68500e421c60f18e4437922edb661971e41a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/83beb35c866c4baa10b60e2ef95c663568a3c58e"
        },
        "date": 1786446939563,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 635,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 21343,
            "range": "± 1364",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 34641,
            "range": "± 994",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 233116,
            "range": "± 6016",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2f04616dfc39026d11be988ae05d33eb9403f1c5",
          "message": "build(deps): Bump the go-ws-hub group (#1231)\n\nBumps the go-ws-hub group in /services/ws-hub with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.60.0` | `0.61.0` |\n| [github.com/quic-go/webtransport-go](https://github.com/quic-go/webtransport-go) | `0.11.1` | `0.12.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `github.com/quic-go/quic-go` from 0.60.0 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.60.0...v0.61.0)\n\nUpdates `github.com/quic-go/webtransport-go` from 0.11.1 to 0.12.0\n- [Release notes](https://github.com/quic-go/webtransport-go/releases)\n- [Commits](https://github.com/quic-go/webtransport-go/compare/v0.11.1...v0.12.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/webtransport-go\n  dependency-version: 0.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:07+03:00",
          "tree_id": "af20c3ca22f350fb2734115e77c0541b42988af5",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2f04616dfc39026d11be988ae05d33eb9403f1c5"
        },
        "date": 1786447223885,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 511,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 21769,
            "range": "± 1384",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 35563,
            "range": "± 3435",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 139560,
            "range": "± 2762",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "10c0ecff521b04524da5d7dd48aa9a93e8611647",
          "message": "build(deps): Bump the go-gateway group (#1232)\n\nBumps the go-gateway group in /services/gateway with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.59.1` | `0.61.0` |\n| [github.com/redis/go-redis/extra/redisprometheus/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n\n\nUpdates `github.com/quic-go/quic-go` from 0.59.1 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.59.1...v0.61.0)\n\nUpdates `github.com/redis/go-redis/extra/redisprometheus/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/extra/redisprometheus/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:36+03:00",
          "tree_id": "ca611e2a36d4ebc8176e6d30b8dc969e933c1748",
          "url": "https://github.com/egorribun/university_ecosystem/commit/10c0ecff521b04524da5d7dd48aa9a93e8611647"
        },
        "date": 1786447503112,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 496,
            "range": "± 1",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 17469,
            "range": "± 1136",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 27888,
            "range": "± 1734",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 182169,
            "range": "± 6622",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667",
          "message": "feat(quality): bootstrap trusted performance assets (#1234)\n\nasset bootstrap / no safe preexisting required context; base is missing base-trusted performance tooling; retaining path filter avoids widening legacy writable PR workflow.\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-11T20:19:16+03:00",
          "tree_id": "e6ce87a619a6dd553eef22861034220a6828012c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667"
        },
        "date": 1786468890456,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 644,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 26834,
            "range": "± 911",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 43154,
            "range": "± 1264",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 173999,
            "range": "± 10157",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "751414ffb59ac2f2de723c1074fa88f1331cfce9",
          "message": "fix(quality): permit rust benchmark workspace root (#1237)\n\n* fix(quality): permit rust benchmark workspace root\n\n* fix(quality): prefetch Go modules without workspace writes\n\n* fix(quality): disable Go workspace mutation in captures\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T00:58:14+05:00",
          "tree_id": "ac8481a0731fa299f91978f543c32455c51d042e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/751414ffb59ac2f2de723c1074fa88f1331cfce9"
        },
        "date": 1786478393722,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 612,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 21382,
            "range": "± 488",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 34728,
            "range": "± 1572",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 239613,
            "range": "± 9585",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1155f5f007a498aa3ffa10194b50cd403661aede",
          "message": "fix(ci): harden SQLMap OpenAPI scan (#1235)\n\n* fix(ci): harden SQLMap OpenAPI scan\n\n* fix(ci): bound SQLMap OpenAPI smoke scan\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T01:57:05+05:00",
          "tree_id": "c793336565247ba5b4d55a2ab9549d910c419079",
          "url": "https://github.com/egorribun/university_ecosystem/commit/1155f5f007a498aa3ffa10194b50cd403661aede"
        },
        "date": 1786482578183,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 628,
            "range": "± 5",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 21614,
            "range": "± 873",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 34731,
            "range": "± 3945",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 234059,
            "range": "± 6029",
            "unit": "ns/iter"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "96689a7514e55bbfda63504c83b484eed5e03fbd",
          "message": "fix(quality): keep isolated benchmark caches mounted (#1238)\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-12T02:46:21+05:00",
          "tree_id": "ed5af247033d8021b235e4c06769fe99d297a19d",
          "url": "https://github.com/egorribun/university_ecosystem/commit/96689a7514e55bbfda63504c83b484eed5e03fbd"
        },
        "date": 1786484859874,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 630,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 21408,
            "range": "± 636",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 34287,
            "range": "± 2370",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 238162,
            "range": "± 10442",
            "unit": "ns/iter"
          }
        ]
      }
    ],
    "WS-Hub Regression Gate": [
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817387510,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 596.8,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 596.8,
            "unit": "ns/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 599.4,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 599.4,
            "unit": "ns/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 604,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 604,
            "unit": "ns/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 598.4,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 598.4,
            "unit": "ns/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 593.7,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 593.7,
            "unit": "ns/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1545,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1545,
            "unit": "ns/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1558,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1558,
            "unit": "ns/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1542,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1542,
            "unit": "ns/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1547,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1547,
            "unit": "ns/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1537,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1537,
            "unit": "ns/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.82,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.82,
            "unit": "ns/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.86,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.86,
            "unit": "ns/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.79,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.79,
            "unit": "ns/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.78,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.78,
            "unit": "ns/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.99,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.99,
            "unit": "ns/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 793.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 793.9,
            "unit": "ns/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 796,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 796,
            "unit": "ns/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 782.1,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 782.1,
            "unit": "ns/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 782.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 782.9,
            "unit": "ns/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 778.5,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 778.5,
            "unit": "ns/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 90.42,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 90.42,
            "unit": "ns/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 90.89,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 90.89,
            "unit": "ns/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 91.17,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 91.17,
            "unit": "ns/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 93.89,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 93.89,
            "unit": "ns/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 92.58,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 92.58,
            "unit": "ns/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1424,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1424,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1393,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1393,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1421,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1421,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1418,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1418,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1428,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1428,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 53.12,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 53.12,
            "unit": "ns/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 48.64,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 48.64,
            "unit": "ns/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 47.34,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 47.34,
            "unit": "ns/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 46.98,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 46.98,
            "unit": "ns/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 48.35,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 48.35,
            "unit": "ns/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1995,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1995,
            "unit": "ns/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1600,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1600,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1654,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1654,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1632,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1632,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1757,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1757,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 64.79,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.79,
            "unit": "ns/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 65.27,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 65.27,
            "unit": "ns/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 63.89,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 63.89,
            "unit": "ns/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 64.32,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.32,
            "unit": "ns/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 64.12,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.12,
            "unit": "ns/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 693.3,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 693.3,
            "unit": "ns/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 695.4,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 695.4,
            "unit": "ns/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 704.7,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 704.7,
            "unit": "ns/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 704.9,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 704.9,
            "unit": "ns/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 711.1,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 711.1,
            "unit": "ns/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 13021,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 13021,
            "unit": "ns/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12995,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12995,
            "unit": "ns/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12764,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12764,
            "unit": "ns/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12903,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12903,
            "unit": "ns/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12964,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "92793 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12964,
            "unit": "ns/op",
            "extra": "92793 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "92793 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "92793 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191681114,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 496.5,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 496.5,
            "unit": "ns/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 499.3,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 499.3,
            "unit": "ns/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 496.8,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 496.8,
            "unit": "ns/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 499.4,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 499.4,
            "unit": "ns/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 501.2,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 501.2,
            "unit": "ns/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1412,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1412,
            "unit": "ns/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1337,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1337,
            "unit": "ns/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1347,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1347,
            "unit": "ns/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1338,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1338,
            "unit": "ns/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1353,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1353,
            "unit": "ns/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.75,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.75,
            "unit": "ns/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.93,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.93,
            "unit": "ns/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.91,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.91,
            "unit": "ns/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 19.03,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 19.03,
            "unit": "ns/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.98,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.98,
            "unit": "ns/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 694,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 694,
            "unit": "ns/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 693.7,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 693.7,
            "unit": "ns/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 687.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 687.9,
            "unit": "ns/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 692.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 692.9,
            "unit": "ns/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 682.2,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 682.2,
            "unit": "ns/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 83.06,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 83.06,
            "unit": "ns/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 81.99,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 81.99,
            "unit": "ns/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 82.42,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 82.42,
            "unit": "ns/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 82.18,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 82.18,
            "unit": "ns/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 80.87,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 80.87,
            "unit": "ns/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1256,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1256,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1262,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1262,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1262,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1262,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1295,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1295,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1292,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1292,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 68.97,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 68.97,
            "unit": "ns/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 66.83,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 66.83,
            "unit": "ns/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 66.88,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 66.88,
            "unit": "ns/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 67.87,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 67.87,
            "unit": "ns/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 66.91,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 66.91,
            "unit": "ns/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 2284,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 2284,
            "unit": "ns/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1898,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1898,
            "unit": "ns/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1855,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1855,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1836,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1836,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1833,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1833,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 83.4,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 83.4,
            "unit": "ns/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 81.42,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 81.42,
            "unit": "ns/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 82.04,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 82.04,
            "unit": "ns/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 83.94,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 83.94,
            "unit": "ns/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 82.12,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 82.12,
            "unit": "ns/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 632.7,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 632.7,
            "unit": "ns/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 632.5,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 632.5,
            "unit": "ns/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 633.6,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 633.6,
            "unit": "ns/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 648,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 648,
            "unit": "ns/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 639.8,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 639.8,
            "unit": "ns/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11612,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11612,
            "unit": "ns/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11758,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11758,
            "unit": "ns/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11572,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11572,
            "unit": "ns/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11480,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11480,
            "unit": "ns/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11943,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "107949 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11943,
            "unit": "ns/op",
            "extra": "107949 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "107949 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "107949 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191850305,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 589.9,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 589.9,
            "unit": "ns/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 589,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 589,
            "unit": "ns/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 590.1,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 590.1,
            "unit": "ns/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 591.8,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 591.8,
            "unit": "ns/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 594.6,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 594.6,
            "unit": "ns/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1530,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1530,
            "unit": "ns/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1525,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1525,
            "unit": "ns/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1524,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1524,
            "unit": "ns/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1509,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1509,
            "unit": "ns/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1528,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1528,
            "unit": "ns/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.41,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.41,
            "unit": "ns/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.73,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.73,
            "unit": "ns/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.66,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.66,
            "unit": "ns/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.78,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.78,
            "unit": "ns/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.84,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.84,
            "unit": "ns/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 775.6,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 775.6,
            "unit": "ns/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 732.5,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 732.5,
            "unit": "ns/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 753.1,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 753.1,
            "unit": "ns/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 751.3,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 751.3,
            "unit": "ns/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 762.5,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 762.5,
            "unit": "ns/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 89.12,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 89.12,
            "unit": "ns/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 86.28,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 86.28,
            "unit": "ns/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 86.63,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 86.63,
            "unit": "ns/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 86.25,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 86.25,
            "unit": "ns/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 87.42,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 87.42,
            "unit": "ns/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1365,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1365,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1303,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1303,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1402,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1402,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1403,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1403,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1383,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1383,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 49.56,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 49.56,
            "unit": "ns/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 46.8,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 46.8,
            "unit": "ns/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 47.73,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 47.73,
            "unit": "ns/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 48.27,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 48.27,
            "unit": "ns/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 46.98,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 46.98,
            "unit": "ns/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1815,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1815,
            "unit": "ns/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1553,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1553,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1572,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1572,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1570,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1570,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1596,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1596,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 63.55,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 63.55,
            "unit": "ns/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 67.13,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 67.13,
            "unit": "ns/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 64.01,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.01,
            "unit": "ns/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 63.62,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 63.62,
            "unit": "ns/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 72.46,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 72.46,
            "unit": "ns/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 691.7,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 691.7,
            "unit": "ns/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 696,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 696,
            "unit": "ns/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 695.2,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 695.2,
            "unit": "ns/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 694.4,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 694.4,
            "unit": "ns/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 693.9,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 693.9,
            "unit": "ns/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12992,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12992,
            "unit": "ns/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12921,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12921,
            "unit": "ns/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12838,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12838,
            "unit": "ns/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12907,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12907,
            "unit": "ns/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12983,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "93988 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12983,
            "unit": "ns/op",
            "extra": "93988 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93988 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93988 times\n4 procs"
          }
        ]
      }
    ]
  }
}