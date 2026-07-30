package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/cespare/xxhash/v2"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ---------------------------------------------------------
// 1. Hash Ring Deterministic Routing Tests
// ---------------------------------------------------------

func TestNodeStateString_CoversAllStates(t *testing.T) {
	tests := []struct {
		name  string
		state NodeState
		want  string
	}{
		{name: "healthy", state: StateHealthy, want: "HEALTHY"},
		{name: "degraded", state: StateDegraded, want: "DEGRADED"},
		{name: "failed", state: StateFailed, want: "FAILED"},
		{name: "unknown", state: NodeState(99), want: "UNKNOWN"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.want, tt.state.String())
		})
	}
}

func TestNodeHealthTracker_Defaults(t *testing.T) {
	tracker := NewNodeHealthTracker(0, 0, "pgvector_backup")

	assert.Equal(t, StateHealthy, tracker.GetState())
	tracker.RecordError()
	tracker.RecordError()
	assert.Equal(t, StateDegraded, tracker.GetState())
	assert.False(t, tracker.ShouldFallback())

	tracker.RecordError()
	assert.Equal(t, StateFailed, tracker.GetState())
	assert.True(t, tracker.ShouldFallback())
}

func TestHashRingAndVectorRouter_DefaultsAndRemoval(t *testing.T) {
	ring := NewHashRing(0)
	ring.AddNode("node-default")
	ring.AddNode("node-default")
	node, err := ring.GetNode("tenant-default")
	require.NoError(t, err)
	assert.Equal(t, "node-default", node)
	assert.Equal(t, []string{"node-default"}, ring.GetNodes())

	router := NewVectorRouter(0, "")
	router.AddNode("node-remove")
	router.AddNode("node-remove")
	tracker, err := router.GetTracker("node-remove")
	require.NoError(t, err)
	assert.Equal(t, StateHealthy, tracker.GetState())

	router.RemoveNode("node-remove")
	_, err = router.GetTracker("node-remove")
	assert.ErrorIs(t, err, ErrNodeNotFound)
	assert.NotPanics(t, func() { router.RemoveNode("missing-node") })
}

func TestHashRing_AddNodeHandlesVirtualNodeHashCollision(t *testing.T) {
	ring := NewHashRing(1)
	collisionHash := xxhash.Sum64String("node-collision#vnode0")
	ring.ring = append(ring.ring, collisionHash)
	ring.vnodeToNode[collisionHash] = "existing-node"

	ring.AddNode("node-collision")

	assert.Len(t, ring.ring, 2)
	assert.Contains(t, ring.vnodeToNode, collisionHash+1)
	assert.Equal(t, "node-collision", ring.vnodeToNode[collisionHash+1])
}

func TestHashRing_DeterministicRouting(t *testing.T) {
	ring := NewHashRing(128)
	ring.AddNode("node1")
	ring.AddNode("node2")
	ring.AddNode("node3")

	tenantID := "tenant-alpha-12345"

	// Repeated lookups must yield identical node assignment
	firstNode, err := ring.GetNode(tenantID)
	require.NoError(t, err)
	assert.NotEmpty(t, firstNode)

	for i := 0; i < 100; i++ {
		node, err := ring.GetNode(tenantID)
		require.NoError(t, err)
		assert.Equal(t, firstNode, node, "Hash ring lookup must be deterministic")
	}
}

func TestHashRing_VirtualNodeDistribution(t *testing.T) {
	ring := NewHashRing(128)
	nodes := []string{"node-a", "node-b", "node-c"}
	for _, n := range nodes {
		ring.AddNode(n)
	}

	counts := make(map[string]int)
	numKeys := 10000

	for i := 0; i < numKeys; i++ {
		key := fmt.Sprintf("tenant-%d", i)
		node, err := ring.GetNode(key)
		require.NoError(t, err)
		counts[node]++
	}

	// With 128 vnodes each node should get roughly ~33% (+/- 10%) of the total keys
	expectedPerNode := float64(numKeys) / float64(len(nodes))
	for _, n := range nodes {
		count := counts[n]
		diff := float64(count) - expectedPerNode
		if diff < 0 {
			diff = -diff
		}
		percentageDiff := (diff / expectedPerNode) * 100
		assert.Less(t, percentageDiff, 20.0, "Node %s distribution variance should be <20%%", n)
	}
}

func TestHashRing_NodeAdditionAndRemoval(t *testing.T) {
	ring := NewHashRing(128)
	ring.AddNode("node1")
	ring.AddNode("node2")

	numKeys := 1000
	initialMappings := make(map[string]string)
	for i := 0; i < numKeys; i++ {
		key := fmt.Sprintf("key-%d", i)
		node, err := ring.GetNode(key)
		require.NoError(t, err)
		initialMappings[key] = node
	}

	// Add node3: minimal remapping property check
	ring.AddNode("node3")
	remappedCount := 0
	for key, oldNode := range initialMappings {
		newNode, err := ring.GetNode(key)
		require.NoError(t, err)
		if newNode != oldNode {
			remappedCount++
			assert.Equal(t, "node3", newNode, "Keys should only be remapped to the newly added node")
		}
	}

	// Expect approx 1/3 of keys to be remapped
	expectedRemapped := float64(numKeys) / 3.0
	assert.InDelta(t, expectedRemapped, float64(remappedCount), float64(numKeys)*0.15)

	// Remove node3: keys should return to node1 or node2
	ring.RemoveNode("node3")
	for key, oldNode := range initialMappings {
		newNode, err := ring.GetNode(key)
		require.NoError(t, err)
		assert.Equal(t, oldNode, newNode, "Removed node keys should revert to initial mapping")
	}
}

func TestHashRing_EmptyRing(t *testing.T) {
	ring := NewHashRing(128)
	_, err := ring.GetNode("tenant-foo")
	assert.ErrorIs(t, err, ErrEmptyRing)
}

func TestHashRing_SingleNodeCluster(t *testing.T) {
	ring := NewHashRing(128)
	ring.AddNode("solo-node")

	for i := 0; i < 50; i++ {
		key := fmt.Sprintf("tenant-%d", i)
		node, err := ring.GetNode(key)
		require.NoError(t, err)
		assert.Equal(t, "solo-node", node)
	}
}

// ---------------------------------------------------------
// 2. Scatter-Gather Min-Heap Merging Tests
// ---------------------------------------------------------

func TestScatterGatherMerger_TopKSelectionAndOrdering(t *testing.T) {
	shard1 := []QueryResult{
		{VectorID: "v1", Score: 0.95},
		{VectorID: "v2", Score: 0.80},
		{VectorID: "v3", Score: 0.60},
	}
	shard2 := []QueryResult{
		{VectorID: "v4", Score: 0.99},
		{VectorID: "v5", Score: 0.88},
		{VectorID: "v6", Score: 0.70},
	}
	shard3 := []QueryResult{
		{VectorID: "v7", Score: 0.91},
		{VectorID: "v8", Score: 0.85},
		{VectorID: "v9", Score: 0.40},
	}

	merged := ScatterGatherMerger([][]QueryResult{shard1, shard2, shard3}, 5)

	require.Len(t, merged, 5)
	// Must be sorted in descending order of score
	assert.Equal(t, "v4", merged[0].VectorID)
	assert.Equal(t, float32(0.99), merged[0].Score)

	assert.Equal(t, "v1", merged[1].VectorID)
	assert.Equal(t, float32(0.95), merged[1].Score)

	assert.Equal(t, "v7", merged[2].VectorID)
	assert.Equal(t, float32(0.91), merged[2].Score)

	assert.Equal(t, "v5", merged[3].VectorID)
	assert.Equal(t, float32(0.88), merged[3].Score)

	assert.Equal(t, "v8", merged[4].VectorID)
	assert.Equal(t, float32(0.85), merged[4].Score)
}

func TestScatterGatherMerger_EdgeCases(t *testing.T) {
	t.Run("Zero topK", func(t *testing.T) {
		shard := []QueryResult{{VectorID: "v1", Score: 0.9}}
		merged := ScatterGatherMerger([][]QueryResult{shard}, 0)
		assert.Empty(t, merged)
	})

	t.Run("Empty shards", func(t *testing.T) {
		merged := ScatterGatherMerger([][]QueryResult{{}, {}}, 5)
		assert.Empty(t, merged)
	})

	t.Run("Duplicate scores", func(t *testing.T) {
		shard1 := []QueryResult{{VectorID: "v1", Score: 0.85}}
		shard2 := []QueryResult{{VectorID: "v2", Score: 0.85}}
		merged := ScatterGatherMerger([][]QueryResult{shard1, shard2}, 2)
		require.Len(t, merged, 2)
		assert.Equal(t, float32(0.85), merged[0].Score)
		assert.Equal(t, float32(0.85), merged[1].Score)
	})

	t.Run("TopK larger than total results", func(t *testing.T) {
		shard := []QueryResult{{VectorID: "v1", Score: 0.9}, {VectorID: "v2", Score: 0.8}}
		merged := ScatterGatherMerger([][]QueryResult{shard}, 10)
		require.Len(t, merged, 2)
		assert.Equal(t, "v1", merged[0].VectorID)
		assert.Equal(t, "v2", merged[1].VectorID)
	})
}

func TestVectorRouter_ScatterGatherQueryParallelExecution(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	nodes := []string{"qdrant-1", "qdrant-2", "qdrant-3"}
	for _, n := range nodes {
		router.AddNode(n)
	}

	queryFunc := func(ctx context.Context, node string) ([]QueryResult, error) {
		// Simulate network latency
		time.Sleep(10 * time.Millisecond)
		return []QueryResult{
			{VectorID: fmt.Sprintf("vec-%s", node), Score: rand.Float32()}, // #nosec G404
		}, nil
	}

	ctx := context.Background()
	start := time.Now()
	results, err := router.ScatterGatherQuery(ctx, nodes, 3, queryFunc)
	elapsed := time.Since(start)

	require.NoError(t, err)
	require.Len(t, results, 3)

	// Since queries run in parallel, total duration should be close to 10ms (much less than 3 * 10ms = 30ms)
	assert.Less(t, elapsed, 25*time.Millisecond, "Scatter-gather queries must execute concurrently")

	emptyResults, err := router.ScatterGatherQuery(context.Background(), nil, 3, queryFunc)
	require.NoError(t, err)
	assert.Empty(t, emptyResults)

	zeroResults, err := router.ScatterGatherQuery(context.Background(), nodes, 0, queryFunc)
	require.NoError(t, err)
	assert.Empty(t, zeroResults)
}

// ---------------------------------------------------------
// 3. Failover State Machine Tests
// ---------------------------------------------------------

func TestNodeHealthTracker_StateTransitions(t *testing.T) {
	tracker := NewNodeHealthTracker(3, 50*time.Millisecond, "pgvector_backup")

	// Initial state is HEALTHY
	assert.Equal(t, StateHealthy, tracker.GetState())
	assert.False(t, tracker.ShouldFallback())

	// Latency spike triggers DEGRADED state
	tracker.RecordSuccess(60 * time.Millisecond)
	assert.Equal(t, StateDegraded, tracker.GetState())
	assert.True(t, tracker.ShouldFallback(), "Degraded node should trigger fallback")

	// Fast latency restores to HEALTHY
	tracker.RecordSuccess(20 * time.Millisecond)
	assert.Equal(t, StateHealthy, tracker.GetState())
	assert.False(t, tracker.ShouldFallback())

	// Errors accumulation trigger FAILED state
	tracker.RecordError()
	assert.Equal(t, StateDegraded, tracker.GetState())
	tracker.RecordError()
	assert.Equal(t, StateDegraded, tracker.GetState())
	tracker.RecordError() // 3rd consecutive error >= threshold
	assert.Equal(t, StateFailed, tracker.GetState())
	assert.True(t, tracker.ShouldFallback())

	// Success resets errors and state back to HEALTHY
	tracker.RecordSuccess(15 * time.Millisecond)
	assert.Equal(t, StateHealthy, tracker.GetState())
	assert.False(t, tracker.ShouldFallback())
}

func TestNodeHealthTracker_SubThresholdErrorsNoFailover(t *testing.T) {
	tracker := NewNodeHealthTracker(3, 50*time.Millisecond, "pgvector_backup")

	// 1 error when errorThreshold is 3
	tracker.RecordError()

	// State is Degraded because of error, but 1 < 3 errors MUST NOT trigger failover
	assert.Equal(t, StateDegraded, tracker.GetState())
	assert.False(t, tracker.ShouldFallback(), "1 error (threshold 3) must NOT trigger failover")

	// 2nd error (2 < 3)
	tracker.RecordError()
	assert.Equal(t, StateDegraded, tracker.GetState())
	assert.False(t, tracker.ShouldFallback(), "2 errors (threshold 3) must NOT trigger failover")

	// 3rd error (3 >= 3) triggers StateFailed and failover
	tracker.RecordError()
	assert.Equal(t, StateFailed, tracker.GetState())
	assert.True(t, tracker.ShouldFallback(), "3 errors (threshold 3) MUST trigger failover")
}

func TestVectorRouter_Route_FailoverRerouting(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("node1")

	// Healthy route
	target, isFallback, err := router.Route("tenant-100")
	require.NoError(t, err)
	assert.Equal(t, "node1", target)
	assert.False(t, isFallback)

	// Inject errors into node1 health tracker
	tracker, err := router.GetTracker("node1")
	require.NoError(t, err)

	tracker.RecordError()
	tracker.RecordError()
	tracker.RecordError() // Triggers StateFailed

	// Routing should now reroute to pgvector backup with sub-100ms switch SLA
	start := time.Now()
	targetFallback, isFallback, err := router.Route("tenant-100")
	switchDuration := time.Since(start)

	require.NoError(t, err)
	assert.Equal(t, "pgvector_backup", targetFallback)
	assert.True(t, isFallback)
	assert.Less(t, switchDuration, 10*time.Millisecond, "Failover switch SLA must be <100ms")
}

func TestVectorRouter_Route_MissingTenantID(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("node1")

	// Empty tenant ID must fallback to pgvector backup safely
	target, isFallback, err := router.Route("")
	require.NoError(t, err)
	assert.Equal(t, "pgvector_backup", target)
	assert.True(t, isFallback)
}

func TestVectorRouter_RouteWithKey_CourseID(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("node1")

	// Test routing using tenantID
	targetTenant, isFallback, err := router.RouteWithKey("tenant-42", "")
	require.NoError(t, err)
	assert.Equal(t, "node1", targetTenant)
	assert.False(t, isFallback)

	// Test routing using courseID when tenantID is empty
	targetCourse, isFallback, err := router.RouteWithKey("", "course-cs101")
	require.NoError(t, err)
	assert.Equal(t, "node1", targetCourse)
	assert.False(t, isFallback)

	// Both empty should trigger fallback
	targetFallback, isFallback, err := router.RouteWithKey("", "")
	require.NoError(t, err)
	assert.Equal(t, "pgvector_backup", targetFallback)
	assert.True(t, isFallback)

	noNodes := NewVectorRouter(128, "pgvector_backup")
	targetEmpty, isFallback, err := noNodes.Route("tenant-without-nodes")
	require.NoError(t, err)
	assert.Equal(t, "pgvector_backup", targetEmpty)
	assert.True(t, isFallback)

	delete(router.trackers, "node1")
	targetMissingTracker, isFallback, err := router.Route("tenant-42")
	require.NoError(t, err)
	assert.Equal(t, "pgvector_backup", targetMissingTracker)
	assert.True(t, isFallback)
}

func TestVectorRouter_ExecuteVectorQuery_TimeoutAndFailover(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("qdrant-primary")

	// Mock executor that fails or times out on primary node, but succeeds on pgvector_backup
	executor := func(ctx context.Context, targetNode string) ([]QueryResult, error) {
		if targetNode == "qdrant-primary" {
			// Simulate unresponsive node / SLA timeout (>50ms context limit)
			time.Sleep(70 * time.Millisecond)
			return nil, fmt.Errorf("connection timeout")
		}
		if targetNode == "pgvector_backup" {
			return []QueryResult{
				{VectorID: "fallback-vec-1", Score: 0.92, TenantID: "tenant-99"},
			}, nil
		}
		return nil, fmt.Errorf("unknown node: %s", targetNode)
	}

	ctx := context.Background()
	start := time.Now()
	results, target, isFallback, err := router.ExecuteVectorQuery(ctx, "tenant-99", "", executor)
	elapsed := time.Since(start)

	require.NoError(t, err)
	assert.True(t, isFallback)
	assert.Equal(t, "pgvector_backup", target)
	require.Len(t, results, 1)
	assert.Equal(t, "fallback-vec-1", results[0].VectorID)
	// Failover switch SLA total switch latency test
	assert.Less(t, elapsed, 100*time.Millisecond, "Seamless failover switch must take <100ms total")

	_, target, isFallback, err = router.ExecuteVectorQuery(
		context.Background(),
		"",
		"",
		func(context.Context, string) ([]QueryResult, error) {
			return nil, fmt.Errorf("fallback unavailable")
		},
	)
	assert.True(t, isFallback)
	assert.Equal(t, "pgvector_backup", target)
	assert.EqualError(t, err, "fallback unavailable")
}

// ---------------------------------------------------------
// 4. HTTP & gRPC Integration Handlers Tests
// ---------------------------------------------------------

func TestVectorSearchHandler_HTTPIntegration(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("node-1")
	router.AddNode("node-2")

	executor := func(ctx context.Context, target string) ([]QueryResult, error) {
		return []QueryResult{
			{VectorID: "v-101", Score: 0.95, TenantID: "tenant-abc"},
			{VectorID: "v-102", Score: 0.65, TenantID: "tenant-abc"},
		}, nil
	}

	handler := VectorSearchHandler(router, executor)

	t.Run("Single Tenant Vector Search", func(t *testing.T) {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		body := bytes.NewBufferString(`{"tenant_id": "tenant-abc", "top_k": 5}`)
		c.Request = httptest.NewRequest("POST", "/v1/vector/search", body)
		c.Request.Header.Set("Content-Type", "application/json")

		handler(c)

		assert.Equal(t, http.StatusOK, w.Code)
		var resp VectorSearchResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "node-1", resp.TargetNode)
		assert.False(t, resp.IsFallback)
		assert.Len(t, resp.Results, 2)
	})

	t.Run("Score Threshold Filtering", func(t *testing.T) {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		body := bytes.NewBufferString(`{"tenant_id": "tenant-abc", "score_threshold": 0.80}`)
		c.Request = httptest.NewRequest("POST", "/v1/vector/search", body)
		c.Request.Header.Set("Content-Type", "application/json")

		handler(c)

		assert.Equal(t, http.StatusOK, w.Code)
		var resp VectorSearchResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Len(t, resp.Results, 1)
		assert.Equal(t, "v-101", resp.Results[0].VectorID)
	})

	t.Run("Multi-Shard Scatter Gather", func(t *testing.T) {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		body := bytes.NewBufferString(`{"multi_shard": true, "top_k": 3}`)
		c.Request = httptest.NewRequest("POST", "/v1/vector/search", body)
		c.Request.Header.Set("Content-Type", "application/json")

		handler(c)

		assert.Equal(t, http.StatusOK, w.Code)
		var resp VectorSearchResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "scatter_gather_all", resp.TargetNode)
		assert.NotEmpty(t, resp.Results)
	})

	t.Run("Invalid JSON returns bad request", func(t *testing.T) {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		c.Request = httptest.NewRequest("POST", "/v1/vector/search", bytes.NewBufferString("{"))
		c.Request.Header.Set("Content-Type", "application/json")

		handler(c)

		assert.Equal(t, http.StatusBadRequest, w.Code)
		assert.Contains(t, w.Body.String(), ErrInvalidParams.Error())
	})

	t.Run("Executor error returns internal server error", func(t *testing.T) {
		failingHandler := VectorSearchHandler(router, func(context.Context, string) ([]QueryResult, error) {
			return nil, fmt.Errorf("vector backend unavailable")
		})
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		c.Request = httptest.NewRequest(
			"POST",
			"/v1/vector/search",
			bytes.NewBufferString(`{"tenant_id":"tenant-abc"}`),
		)
		c.Request.Header.Set("Content-Type", "application/json")

		failingHandler(c)

		assert.Equal(t, http.StatusInternalServerError, w.Code)
		assert.Contains(t, w.Body.String(), "vector backend unavailable")
	})
}

func TestVectorSearchGRPCHandler(t *testing.T) {
	router := NewVectorRouter(128, "pgvector_backup")
	router.AddNode("node-alpha")

	executor := func(ctx context.Context, target string) ([]QueryResult, error) {
		return []QueryResult{
			{VectorID: "grpc-v1", Score: 0.88},
		}, nil
	}

	req := &VectorSearchRequest{
		TenantID: "tenant-grpc",
		TopK:     5,
	}

	resp, err := VectorSearchGRPCHandler(context.Background(), router, req, executor)
	require.NoError(t, err)
	assert.Equal(t, "node-alpha", resp.TargetNode)
	assert.False(t, resp.IsFallback)
	require.Len(t, resp.Results, 1)
	assert.Equal(t, "grpc-v1", resp.Results[0].VectorID)

	t.Run("nil request is rejected", func(t *testing.T) {
		resp, err := VectorSearchGRPCHandler(context.Background(), router, nil, executor)
		assert.Nil(t, resp)
		assert.ErrorIs(t, err, ErrInvalidParams)
	})

	t.Run("executor errors are returned", func(t *testing.T) {
		resp, err := VectorSearchGRPCHandler(
			context.Background(),
			router,
			&VectorSearchRequest{TenantID: "tenant-grpc"},
			func(context.Context, string) ([]QueryResult, error) {
				return nil, fmt.Errorf("query failed")
			},
		)
		assert.Nil(t, resp)
		assert.ErrorContains(t, err, "primary query failed: query failed")
		assert.ErrorContains(t, err, "fallback query failed: query failed")
	})

	t.Run("defaults topK and applies score threshold", func(t *testing.T) {
		resp, err := VectorSearchGRPCHandler(
			context.Background(),
			router,
			&VectorSearchRequest{TenantID: "tenant-grpc", ScoreThreshold: 0.9},
			func(context.Context, string) ([]QueryResult, error) {
				return []QueryResult{
					{VectorID: "above", Score: 0.95},
					{VectorID: "below", Score: 0.5},
				}, nil
			},
		)
		require.NoError(t, err)
		require.NotNil(t, resp)
		assert.Equal(t, 1, resp.Count)
		assert.Equal(t, "above", resp.Results[0].VectorID)
	})

	t.Run("multi-shard requests use scatter-gather", func(t *testing.T) {
		multiRouter := NewVectorRouter(128, "pgvector_backup")
		multiRouter.AddNode("node-alpha")
		multiRouter.AddNode("node-beta")
		resp, err := VectorSearchGRPCHandler(
			context.Background(),
			multiRouter,
			&VectorSearchRequest{MultiShard: true, TopK: 1},
			func(_ context.Context, target string) ([]QueryResult, error) {
				return []QueryResult{{VectorID: target, Score: 0.9}}, nil
			},
		)
		require.NoError(t, err)
		require.NotNil(t, resp)
		assert.Equal(t, "scatter_gather_all", resp.TargetNode)
		assert.Len(t, resp.Results, 1)
	})
}
