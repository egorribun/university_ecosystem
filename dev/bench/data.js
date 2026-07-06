window.BENCHMARK_DATA = {
  "lastUpdate": 1783301874764,
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
      }
    ]
  }
}