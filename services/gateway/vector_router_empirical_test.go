package gateway

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"sort"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ============================================================================
// EMPIRICAL VERIFICATION SUITE: GO GATEWAY VECTOR ROUTER & SCATTER-GATHER
// ============================================================================

// ----------------------------------------------------------------------------
// 1. Consistent Hashing Distribution & VNode Empirical Stress Tests
// ----------------------------------------------------------------------------

func TestEmpirical_HashRing_DistributionAcrossClusterSizes(t *testing.T) {
	clusterSizes := []int{3, 5, 8, 12}
	numKeys := 100000

	for _, size := range clusterSizes {
		t.Run(fmt.Sprintf("ClusterSize_%d_Nodes", size), func(t *testing.T) {
			ring := NewHashRing(128)
			nodes := make([]string, size)
			for i := 0; i < size; i++ {
				nodes[i] = fmt.Sprintf("qdrant-node-%d", i+1)
				ring.AddNode(nodes[i])
			}

			counts := make(map[string]int)
			for k := 0; k < numKeys; k++ {
				key := fmt.Sprintf("tenant-uuid-%08d-%d", k, k*31)
				node, err := ring.GetNode(key)
				require.NoError(t, err)
				counts[node]++
			}

			expected := float64(numKeys) / float64(size)
			t.Logf("Cluster size %d: Expected per node = %.0f", size, expected)

			var totalDev float64
			minKeys := numKeys
			maxKeys := 0

			for _, n := range nodes {
				cnt := counts[n]
				if cnt < minKeys {
					minKeys = cnt
				}
				if cnt > maxKeys {
					maxKeys = cnt
				}
				dev := math.Abs(float64(cnt)-expected) / expected * 100
				totalDev += dev
				t.Logf(" Node %s: %d keys (%.2f%% deviation)", n, cnt, dev)
			}

			avgDev := totalDev / float64(size)
			t.Logf(" Average deviation: %.2f%%, Max/Min ratio: %.2f", avgDev, float64(maxKeys)/float64(minKeys))

			// 128 vnodes guarantees standard deviation < 15% across nodes
			assert.Less(t, avgDev, 15.0, "Average key distribution variance should be <15%%")
			assert.Less(t, float64(maxKeys)/float64(minKeys), 1.5, "Max/Min node load ratio should be <1.5")
		})
	}
}

func TestEmpirical_HashRing_MinimalKeyRemapping(t *testing.T) {
	ring := NewHashRing(128)
	initialNodes := []string{"node-1", "node-2", "node-3", "node-4"}
	for _, n := range initialNodes {
		ring.AddNode(n)
	}

	numKeys := 20000
	initialMap := make(map[string]string, numKeys)
	for i := 0; i < numKeys; i++ {
		key := fmt.Sprintf("tenant-%d", i)
		n, err := ring.GetNode(key)
		require.NoError(t, err)
		initialMap[key] = n
	}

	// Add 5th node: expected remapped fraction is 1/5 = 20%
	ring.AddNode("node-5")
	remappedToNew := 0
	remappedToOther := 0

	for key, oldNode := range initialMap {
		newNode, err := ring.GetNode(key)
		require.NoError(t, err)
		if newNode != oldNode {
			if newNode == "node-5" {
				remappedToNew++
			} else {
				remappedToOther++
			}
		}
	}

	remappedPct := float64(remappedToNew) / float64(numKeys) * 100
	t.Logf("Remapped keys to node-5: %d (%.2f%%)", remappedToNew, remappedPct)

	// Minimal remapping property: NO keys should be remapped to existing nodes (node1-node4)
	assert.Equal(t, 0, remappedToOther, "Keys must only remap to the newly added node")
	// 20% +/- 5% range check for 5th node addition
	assert.InDelta(t, 20.0, remappedPct, 5.0, "Remapped fraction should be close to 1/N (20%%)")
}

func TestEmpirical_HashRing_LookupThroughputBenchmark(t *testing.T) {
	ring := NewHashRing(128)
	for i := 0; i < 16; i++ {
		ring.AddNode(fmt.Sprintf("node-%d", i))
	}

	numOps := 500000
	start := time.Now()

	var wg sync.WaitGroup
	workers := 8
	opsPerWorker := numOps / workers

	keys := make([]string, 1000)
	for i := 0; i < 1000; i++ {
		keys[i] = fmt.Sprintf("tenant-key-%d", i)
	}

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			for i := 0; i < opsPerWorker; i++ {
				key := keys[(workerID*opsPerWorker+i)%1000]
				_, err := ring.GetNode(key)
				if err != nil {
					t.Errorf("unexpected error: %v", err)
				}
			}
		}(w)
	}

	wg.Wait()
	elapsed := time.Since(start)
	opsPerSec := float64(numOps) / elapsed.Seconds()
	t.Logf("HashRing lookup throughput: %.0f ops/sec (total %v for %d lookups)", opsPerSec, elapsed, numOps)

	assert.Greater(t, opsPerSec, 250000.0, "HashRing lookup performance must exceed 250k ops/sec")
}

// ----------------------------------------------------------------------------
// 2. Failover SLA Switch & Health Tracker Empirical Stress Tests
// ----------------------------------------------------------------------------

func TestEmpirical_FailoverSLA_NodeFailureSwitchLatency(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("qdrant-primary-1")

	// Primary node fails immediately
	failingExecutor := func(ctx context.Context, target string) ([]QueryResult, error) {
		if target == "qdrant-primary-1" {
			return nil, fmt.Errorf("connection refused: qdrant node down")
		}
		if target == "pgvector_backup" {
			return []QueryResult{
				{VectorID: "pg-res-1", Score: 0.94, TenantID: "t-1"},
			}, nil
		}
		return nil, fmt.Errorf("unknown target: %s", target)
	}

	ctx := context.Background()

	// Measure switch latency over 100 consecutive failure calls
	var totalSwitchDuration time.Duration
	iterations := 50

	for i := 0; i < iterations; i++ {
		start := time.Now()
		res, target, isFallback, err := router.ExecuteVectorQuery(ctx, "t-1", "", failingExecutor)
		duration := time.Since(start)
		totalSwitchDuration += duration

		require.NoError(t, err)
		assert.True(t, isFallback)
		assert.Equal(t, "pgvector_backup", target)
		require.Len(t, res, 1)
		assert.Less(t, duration, 100*time.Millisecond, "Individual failover switch SLA must be <100ms")
	}

	avgSwitchLatency := totalSwitchDuration / time.Duration(iterations)
	t.Logf("Average failover switch latency under node failure: %v", avgSwitchLatency)
	assert.Less(t, avgSwitchLatency, 20*time.Millisecond, "Average failover switch latency should be <20ms")
}

func TestEmpirical_FailoverSLA_LatencySpikeSwitch(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("qdrant-primary-slow")

	// Primary node takes 70ms (> 50ms SLA)
	slowExecutor := func(ctx context.Context, target string) ([]QueryResult, error) {
		if target == "qdrant-primary-slow" {
			select {
			case <-time.After(70 * time.Millisecond):
				return []QueryResult{{VectorID: "slow-1", Score: 0.5}}, nil
			case <-ctx.Done():
				return nil, ctx.Err()
			}
		}
		if target == "pgvector_backup" {
			return []QueryResult{
				{VectorID: "pg-fast-1", Score: 0.91},
			}, nil
		}
		return nil, fmt.Errorf("unknown target")
	}

	ctx := context.Background()
	start := time.Now()
	res, target, isFallback, err := router.ExecuteVectorQuery(ctx, "tenant-slow", "", slowExecutor)
	switchDuration := time.Since(start)

	require.NoError(t, err)
	assert.True(t, isFallback, "Latency spike >50ms must trigger fallback")
	assert.Equal(t, "pgvector_backup", target)
	require.Len(t, res, 1)
	assert.Equal(t, "pg-fast-1", res[0].VectorID)

	t.Logf("Latency spike switch total duration: %v (Context timeout 50ms + pgvector execution)", switchDuration)
	assert.Less(t, switchDuration, 100*time.Millisecond, "Latency spike SLA switch must complete within <100ms")
}

func TestEmpirical_Failover_ConcurrentFlappingStress(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("qdrant-flapping")

	var primaryQueryCount int64
	var fallbackQueryCount int64
	var totalErrors int64

	// Flapping node mock executor
	executor := func(ctx context.Context, target string) ([]QueryResult, error) {
		if target == "qdrant-flapping" {
			atomic.AddInt64(&primaryQueryCount, 1)
			if rand.Float32() < 0.4 { //nolint:gosec // G404: 40% error rate for test simulation
				return nil, fmt.Errorf("transient i/o error")
			}
			return []QueryResult{{VectorID: "qdrant-vec", Score: 0.88}}, nil
		}
		atomic.AddInt64(&fallbackQueryCount, 1)
		return []QueryResult{{VectorID: "pgvector-vec", Score: 0.85}}, nil
	}

	var wg sync.WaitGroup
	workers := 20
	requestsPerWorker := 100

	ctx := context.Background()
	start := time.Now()

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for r := 0; r < requestsPerWorker; r++ {
				_, _, _, err := router.ExecuteVectorQuery(ctx, "tenant-concurrent", "", executor)
				if err != nil {
					atomic.AddInt64(&totalErrors, 1)
				}
			}
		}()
	}

	wg.Wait()
	elapsed := time.Since(start)

	t.Logf("Concurrent Flapping Stress Results (%v): Primary calls=%d, Fallback calls=%d, Errors=%d",
		elapsed, primaryQueryCount, fallbackQueryCount, totalErrors)

	assert.Equal(t, int64(0), totalErrors, "Zero errors expected due to seamless pgvector failover")
	assert.Greater(t, fallbackQueryCount, int64(0), "Fallback queries should be executed when node degrades")
}

// ----------------------------------------------------------------------------
// 3. Scatter-Gather Bounded Min-Heap & Ranking Empirical Tests
// ----------------------------------------------------------------------------

func TestEmpirical_ScatterGather_LargeScaleMergingCorrectness(t *testing.T) {
	numShards := 50
	itemsPerShard := 1000
	topK := 25

	shardResults := make([][]QueryResult, numShards)
	allItems := make([]QueryResult, 0, numShards*itemsPerShard)

	for s := 0; s < numShards; s++ {
		shardResults[s] = make([]QueryResult, itemsPerShard)
		for i := 0; i < itemsPerShard; i++ {
			score := rand.Float32() // #nosec G404
			res := QueryResult{
				VectorID: fmt.Sprintf("s%d-v%d", s, i),
				TenantID: fmt.Sprintf("tenant-%d", s),
				Score:    score,
			}
			shardResults[s][i] = res
			allItems = append(allItems, res)
		}
	}

	// Calculate ground truth global top-K by sorting all items
	sort.Slice(allItems, func(i, j int) bool {
		return allItems[i].Score > allItems[j].Score
	})
	groundTruthTopK := allItems[:topK]

	// Execute ScatterGatherMerger
	start := time.Now()
	mergedResults := ScatterGatherMerger(shardResults, topK)
	elapsed := time.Since(start)

	t.Logf("ScatterGatherMerger merged 50,000 items across 50 shards in %v", elapsed)

	require.Len(t, mergedResults, topK)

	// Verify exact match with ground truth scores and order
	for i := 0; i < topK; i++ {
		assert.Equal(t, groundTruthTopK[i].Score, mergedResults[i].Score,
			"Item at rank %d score mismatch: expected %f, got %f", i, groundTruthTopK[i].Score, mergedResults[i].Score)
		assert.Equal(t, groundTruthTopK[i].VectorID, mergedResults[i].VectorID,
			"Item at rank %d vectorID mismatch", i)
	}

	// Verify strict descending ordering
	for i := 0; i < len(mergedResults)-1; i++ {
		assert.GreaterOrEqual(t, mergedResults[i].Score, mergedResults[i+1].Score,
			"Merged results must be sorted in descending order of score")
	}

	assert.Less(t, elapsed, 50*time.Millisecond, "ScatterGatherMerger execution should be <50ms for 50k items")
}

func TestEmpirical_ScatterGather_NegativeCosineSimilarityScores(t *testing.T) {
	shard1 := []QueryResult{
		{VectorID: "neg-1", Score: -0.10},
		{VectorID: "neg-2", Score: -0.50},
		{VectorID: "neg-3", Score: -0.85},
	}
	shard2 := []QueryResult{
		{VectorID: "pos-1", Score: 0.40},
		{VectorID: "neg-4", Score: -0.05},
		{VectorID: "neg-5", Score: -0.99},
	}

	merged := ScatterGatherMerger([][]QueryResult{shard1, shard2}, 4)
	require.Len(t, merged, 4)

	// Expected rank: pos-1 (0.40), neg-4 (-0.05), neg-1 (-0.10), neg-2 (-0.50)
	assert.Equal(t, "pos-1", merged[0].VectorID)
	assert.Equal(t, float32(0.40), merged[0].Score)

	assert.Equal(t, "neg-4", merged[1].VectorID)
	assert.Equal(t, float32(-0.05), merged[1].Score)

	assert.Equal(t, "neg-1", merged[2].VectorID)
	assert.Equal(t, float32(-0.10), merged[2].Score)

	assert.Equal(t, "neg-2", merged[3].VectorID)
	assert.Equal(t, float32(-0.50), merged[3].Score)
}

func TestEmpirical_ScatterGatherQuery_ParallelPerformance(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	numNodes := 16
	nodes := make([]string, numNodes)
	for i := 0; i < numNodes; i++ {
		nodes[i] = fmt.Sprintf("qdrant-shard-%d", i)
		router.AddNode(nodes[i])
	}

	simulatedLatency := 20 * time.Millisecond

	queryFunc := func(ctx context.Context, target string) ([]QueryResult, error) {
		select {
		case <-time.After(simulatedLatency):
			return []QueryResult{
				{VectorID: fmt.Sprintf("vec-%s", target), Score: rand.Float32()}, // #nosec G404
			}, nil
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}

	ctx := context.Background()
	start := time.Now()
	results, err := router.ScatterGatherQuery(ctx, nodes, 10, queryFunc)
	elapsed := time.Since(start)

	require.NoError(t, err)
	assert.NotEmpty(t, results)

	t.Logf("ScatterGatherQuery across %d nodes with %v latency completed in %v", numNodes, simulatedLatency, elapsed)
	// Parallel execution should complete in ~1x latency, not 16x latency (320ms)
	assert.Less(t, elapsed, 40*time.Millisecond, "ScatterGatherQuery must execute across nodes in parallel")
}

func TestEmpirical_ScatterGatherQuery_PartialShardFailureResilience(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	nodes := []string{"healthy-1", "failing-1", "healthy-2"}
	for _, n := range nodes {
		router.AddNode(n)
	}

	queryFunc := func(ctx context.Context, target string) ([]QueryResult, error) {
		if target == "failing-1" {
			return nil, fmt.Errorf("shard unreachable")
		}
		return []QueryResult{
			{VectorID: fmt.Sprintf("res-%s", target), Score: 0.90},
		}, nil
	}

	results, err := router.ScatterGatherQuery(context.Background(), nodes, 5, queryFunc)
	require.NoError(t, err)
	require.Len(t, results, 2, "Partial shard failure should return results from remaining healthy shards")

	// Tracker for failing-1 should record failure
	tracker, err := router.GetTracker("failing-1")
	require.NoError(t, err)
	assert.Equal(t, StateDegraded, tracker.GetState())
}
