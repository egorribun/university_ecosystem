package gateway

import (
	"container/heap"
	"context"
	"errors"
	"fmt"
	"net/http"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/cespare/xxhash/v2"
	"github.com/gin-gonic/gin"
	"golang.org/x/sync/errgroup"
)

// Common errors.
var (
	ErrEmptyRing     = errors.New("hash ring is empty")
	ErrNodeNotFound  = errors.New("node not found in ring")
	ErrInvalidParams = errors.New("invalid parameters for vector query")
)

// QueryResult represents a single vector search match.
type QueryResult struct {
	VectorID string                 `json:"vector_id"`
	TenantID string                 `json:"tenant_id"`
	Score    float32                `json:"score"`
	Payload  map[string]interface{} `json:"payload"`
}

// VectorSearchRequest represents the incoming HTTP/gRPC vector search payload.
type VectorSearchRequest struct {
	TenantID       string    `json:"tenant_id"`
	CourseID       string    `json:"course_id"`
	Vector         []float32 `json:"vector"`
	TopK           int       `json:"top_k"`
	ScoreThreshold float32   `json:"score_threshold"`
	MultiShard     bool      `json:"multi_shard"`
}

// VectorSearchResponse represents the outbound vector search HTTP response.
type VectorSearchResponse struct {
	TargetNode string        `json:"target_node"`
	IsFallback bool          `json:"is_fallback"`
	Results    []QueryResult `json:"results"`
	Count      int           `json:"count"`
	LatencyMs  int64         `json:"latency_ms"`
}

// VectorQueryExecutor is a function type for querying a vector node.
type VectorQueryExecutor func(ctx context.Context, targetNode string) ([]QueryResult, error)

// NodeState indicates the health status of a vector shard node.
type NodeState int32

const (
	// StateHealthy indicates the node is operating normally.
	StateHealthy NodeState = iota
	// StateDegraded indicates the node is experiencing elevated latency.
	StateDegraded
	// StateFailed indicates the node has exceeded the error threshold.
	StateFailed
)

func (s NodeState) String() string {
	switch s {
	case StateHealthy:
		return "HEALTHY"
	case StateDegraded:
		return "DEGRADED"
	case StateFailed:
		return "FAILED"
	default:
		return "UNKNOWN"
	}
}

// HashRing implements virtual node consistent hashing using xxhash.
type HashRing struct {
	mu          sync.RWMutex
	vnodes      int
	ring        []uint64
	vnodeToNode map[uint64]string
	nodes       map[string]bool
}

// NewHashRing constructs a HashRing with specified vnodes per physical node.
func NewHashRing(vnodes int) *HashRing {
	if vnodes <= 0 {
		vnodes = 128
	}
	return &HashRing{
		vnodes:      vnodes,
		ring:        make([]uint64, 0),
		vnodeToNode: make(map[uint64]string),
		nodes:       make(map[string]bool),
	}
}

// AddNode adds a physical node to the ring with virtual nodes.
func (h *HashRing) AddNode(node string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if h.nodes[node] {
		return
	}

	h.nodes[node] = true
	for v := 0; v < h.vnodes; v++ {
		vnodeKey := fmt.Sprintf("%s#vnode%d", node, v)
		hash := xxhash.Sum64String(vnodeKey)
		for {
			if _, exists := h.vnodeToNode[hash]; !exists {
				break
			}
			hash++
		}
		h.ring = append(h.ring, hash)
		h.vnodeToNode[hash] = node
	}

	sort.Slice(h.ring, func(i, j int) bool {
		return h.ring[i] < h.ring[j]
	})
}

// RemoveNode removes a physical node and its virtual nodes from the ring.
func (h *HashRing) RemoveNode(node string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if !h.nodes[node] {
		return
	}

	delete(h.nodes, node)
	newRing := make([]uint64, 0, len(h.ring)-(h.vnodes))

	for _, hash := range h.ring {
		if mappedNode, exists := h.vnodeToNode[hash]; exists && mappedNode == node {
			delete(h.vnodeToNode, hash)
		} else {
			newRing = append(newRing, hash)
		}
	}

	h.ring = newRing
}

// GetNode returns the physical node mapped to key/tenant_id via consistent hashing.
func (h *HashRing) GetNode(key string) (string, error) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	if len(h.ring) == 0 {
		return "", ErrEmptyRing
	}

	hash := xxhash.Sum64String(key)
	idx := sort.Search(len(h.ring), func(i int) bool {
		return h.ring[i] >= hash
	})

	if idx == len(h.ring) {
		idx = 0
	}

	return h.vnodeToNode[h.ring[idx]], nil
}

// GetNodes returns all physical nodes in the ring.
func (h *HashRing) GetNodes() []string {
	h.mu.RLock()
	defer h.mu.RUnlock()

	nodes := make([]string, 0, len(h.nodes))
	for n := range h.nodes {
		nodes = append(nodes, n)
	}
	sort.Strings(nodes)
	return nodes
}

// ResultMinHeap implements container/heap.Interface for bounded top-K min-heap.
type ResultMinHeap []QueryResult

func (h ResultMinHeap) Len() int { return len(h) }
func (h ResultMinHeap) Less(i, j int) bool {
	if h[i].Score == h[j].Score {
		return h[i].VectorID > h[j].VectorID
	}
	return h[i].Score < h[j].Score
}
func (h ResultMinHeap) Swap(i, j int) { h[i], h[j] = h[j], h[i] }

// Push appends an item to the ResultMinHeap for heap.Interface.
func (h *ResultMinHeap) Push(x interface{}) {
	*h = append(*h, x.(QueryResult))
}

// Pop removes and returns the min item from the ResultMinHeap for heap.Interface.
func (h *ResultMinHeap) Pop() interface{} {
	old := *h
	n := len(old)
	item := old[n-1]
	*h = old[0 : n-1]
	return item
}

// ScatterGatherMerger merges multi-shard results into a bounded top-K slice ordered by score descending.
func ScatterGatherMerger(shardResults [][]QueryResult, topK int) []QueryResult {
	if topK <= 0 {
		return []QueryResult{}
	}

	h := &ResultMinHeap{}
	heap.Init(h)

	for _, results := range shardResults {
		for _, res := range results {
			if h.Len() < topK {
				heap.Push(h, res)
			} else if res.Score > (*h)[0].Score || (res.Score == (*h)[0].Score && res.VectorID < (*h)[0].VectorID) {
				heap.Pop(h)
				heap.Push(h, res)
			}
		}
	}

	merged := make([]QueryResult, h.Len())
	for i := len(merged) - 1; i >= 0; i-- {
		merged[i] = heap.Pop(h).(QueryResult)
	}

	sort.Slice(merged, func(i, j int) bool {
		if merged[i].Score == merged[j].Score {
			return merged[i].VectorID < merged[j].VectorID
		}
		return merged[i].Score > merged[j].Score
	})

	return merged
}

// NodeHealthTracker monitors single node error rates & response latency.
type NodeHealthTracker struct {
	mu                sync.RWMutex
	state             NodeState
	consecutiveErrors int32
	errorThreshold    int32
	latencySLA        time.Duration
	lastLatency       time.Duration
	fallbackTarget    string
	totalRequests     int64
	totalFailovers    int64
}

// NewNodeHealthTracker constructs a health tracker.
func NewNodeHealthTracker(errorThreshold int32, latencySLA time.Duration, fallbackTarget string) *NodeHealthTracker {
	if errorThreshold <= 0 {
		errorThreshold = 3
	}
	if latencySLA <= 0 {
		latencySLA = 50 * time.Millisecond
	}
	return &NodeHealthTracker{
		state:          StateHealthy,
		errorThreshold: errorThreshold,
		latencySLA:     latencySLA,
		fallbackTarget: fallbackTarget,
	}
}

// GetState returns the current NodeState of the tracked node.
func (t *NodeHealthTracker) GetState() NodeState {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return t.state
}

// RecordSuccess records a successful query invocation and updates node state based on latency SLA.
func (t *NodeHealthTracker) RecordSuccess(latency time.Duration) {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.totalRequests++
	t.lastLatency = latency
	atomic.StoreInt32(&t.consecutiveErrors, 0)

	if latency > t.latencySLA {
		if t.state != StateFailed {
			t.state = StateDegraded
		}
	} else {
		t.state = StateHealthy
	}
}

// RecordError records a query failure and transitions state to degraded or failed.
func (t *NodeHealthTracker) RecordError() {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.totalRequests++
	errs := atomic.AddInt32(&t.consecutiveErrors, 1)

	if errs >= t.errorThreshold {
		if t.state != StateFailed {
			t.state = StateFailed
			t.totalFailovers++
		}
	} else {
		t.state = StateDegraded
	}
}

// ShouldFallback returns true if the node is failed or exceeding SLA boundaries.
func (t *NodeHealthTracker) ShouldFallback() bool {
	t.mu.RLock()
	defer t.mu.RUnlock()

	if t.state == StateFailed || atomic.LoadInt32(&t.consecutiveErrors) >= t.errorThreshold {
		return true
	}
	if t.lastLatency > t.latencySLA {
		return true
	}
	return false
}

// VectorRouter manages hash ring, node health state, and scatter-gather operations.
type VectorRouter struct {
	mu             sync.RWMutex
	ring           *HashRing
	trackers       map[string]*NodeHealthTracker
	pgvectorBackup string
	errorThreshold int32
	latencySLA     time.Duration
}

// NewVectorRouter creates a VectorRouter instance.
func NewVectorRouter(vnodes int, pgvectorBackup string) *VectorRouter {
	if pgvectorBackup == "" {
		pgvectorBackup = "pgvector_backup"
	}
	return &VectorRouter{
		ring:           NewHashRing(vnodes),
		trackers:       make(map[string]*NodeHealthTracker),
		pgvectorBackup: pgvectorBackup,
		errorThreshold: 3,
		latencySLA:     50 * time.Millisecond,
	}
}

// AddNode adds a shard node to router.
func (vr *VectorRouter) AddNode(node string) {
	vr.mu.Lock()
	defer vr.mu.Unlock()

	vr.ring.AddNode(node)
	if _, exists := vr.trackers[node]; !exists {
		vr.trackers[node] = NewNodeHealthTracker(vr.errorThreshold, vr.latencySLA, vr.pgvectorBackup)
	}
}

// RemoveNode removes node from router.
func (vr *VectorRouter) RemoveNode(node string) {
	vr.mu.Lock()
	defer vr.mu.Unlock()

	vr.ring.RemoveNode(node)
	delete(vr.trackers, node)
}

// GetTracker returns health tracker for node.
func (vr *VectorRouter) GetTracker(node string) (*NodeHealthTracker, error) {
	vr.mu.RLock()
	defer vr.mu.RUnlock()

	tracker, exists := vr.trackers[node]
	if !exists {
		return nil, ErrNodeNotFound
	}
	return tracker, nil
}

// Route resolves tenantID to node and determines if pgvector fallback is required.
func (vr *VectorRouter) Route(tenantID string) (targetNode string, isFallback bool) {
	if tenantID == "" {
		return vr.pgvectorBackup, true
	}

	primaryNode, err := vr.ring.GetNode(tenantID)
	if err != nil {
		return vr.pgvectorBackup, true
	}

	tracker, err := vr.GetTracker(primaryNode)
	if err != nil || tracker.ShouldFallback() {
		return vr.pgvectorBackup, true
	}

	return primaryNode, false
}

// RouteWithKey resolves either tenantID or courseID partition key to node.
func (vr *VectorRouter) RouteWithKey(tenantID, courseID string) (targetNode string, isFallback bool) {
	partitionKey := tenantID
	if partitionKey == "" {
		partitionKey = courseID
	}
	return vr.Route(partitionKey)
}

// ExecuteVectorQuery routes the request and executes it with context SLA (50ms limit), seamlessly falling back to pgvector on failure.
func (vr *VectorRouter) ExecuteVectorQuery(
	ctx context.Context,
	tenantID string,
	courseID string,
	queryFunc VectorQueryExecutor,
) (results []QueryResult, targetNode string, isFallback bool, err error) {
	targetNode, isFallback = vr.RouteWithKey(tenantID, courseID)

	// 50ms context SLA limit per target node call
	queryCtx, cancel := context.WithTimeout(ctx, vr.latencySLA)
	defer cancel()

	start := time.Now()
	res, queryErr := queryFunc(queryCtx, targetNode)
	elapsed := time.Since(start)

	if !isFallback && targetNode != vr.pgvectorBackup {
		tracker, trackerErr := vr.GetTracker(targetNode)
		if queryErr != nil || errors.Is(queryCtx.Err(), context.DeadlineExceeded) {
			if trackerErr == nil {
				tracker.RecordError()
			}
			// Trigger seamless failover switch to pgvector fallback
			fallbackCtx, fallbackCancel := context.WithTimeout(ctx, 100*time.Millisecond)
			defer fallbackCancel()

			fallbackRes, fallbackErr := queryFunc(fallbackCtx, vr.pgvectorBackup)
			if fallbackErr == nil {
				return fallbackRes, vr.pgvectorBackup, true, nil
			}
			return nil, vr.pgvectorBackup, true, fmt.Errorf("primary query failed: %w; fallback query failed: %w", queryErr, fallbackErr)
		}

		if trackerErr == nil {
			tracker.RecordSuccess(elapsed)
		}
	}

	if queryErr != nil {
		return nil, targetNode, isFallback, queryErr
	}

	return res, targetNode, isFallback, nil
}

// ScatterGatherQuery executes parallel search queries across nodes using errgroup and merges top-K results.
func (vr *VectorRouter) ScatterGatherQuery(
	ctx context.Context,
	nodes []string,
	topK int,
	queryFunc VectorQueryExecutor,
) ([]QueryResult, error) {
	if topK <= 0 || len(nodes) == 0 {
		return []QueryResult{}, nil
	}

	g, gctx := errgroup.WithContext(ctx)
	resultsChan := make(chan []QueryResult, len(nodes))

	for _, node := range nodes {
		n := node
		g.Go(func() error {
			// Apply 50ms context SLA limit
			nodeCtx, cancel := context.WithTimeout(gctx, vr.latencySLA)
			defer cancel()

			start := time.Now()
			res, err := queryFunc(nodeCtx, n)
			elapsed := time.Since(start)

			tracker, trackerErr := vr.GetTracker(n)
			if err != nil || errors.Is(nodeCtx.Err(), context.DeadlineExceeded) {
				if trackerErr == nil {
					tracker.RecordError()
				}
				// On single node error in scatter-gather, return empty results for that shard or record error
				resultsChan <- []QueryResult{}
				return nil
			}

			if trackerErr == nil {
				tracker.RecordSuccess(elapsed)
			}
			resultsChan <- res
			return nil
		})
	}

	_ = g.Wait() //nolint:errcheck
	close(resultsChan)

	var allResults [][]QueryResult
	for res := range resultsChan {
		allResults = append(allResults, res)
	}

	return ScatterGatherMerger(allResults, topK), nil
}

// VectorSearchHandler returns a Gin HandlerFunc for processing HTTP vector search requests.
func VectorSearchHandler(router *VectorRouter, executor VectorQueryExecutor) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req VectorSearchRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": ErrInvalidParams.Error()})
			return
		}

		if req.TopK <= 0 {
			req.TopK = 10
		}

		start := time.Now()
		var results []QueryResult
		var targetNode string
		var isFallback bool
		var err error

		if req.MultiShard {
			nodes := router.ring.GetNodes()
			results, err = router.ScatterGatherQuery(c.Request.Context(), nodes, req.TopK, executor)
			targetNode = "scatter_gather_all"
			isFallback = false
		} else {
			results, targetNode, isFallback, err = router.ExecuteVectorQuery(
				c.Request.Context(),
				req.TenantID,
				req.CourseID,
				executor,
			)
		}

		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		// Filter by score threshold if specified
		if req.ScoreThreshold > 0 {
			filtered := make([]QueryResult, 0, len(results))
			for _, r := range results {
				if r.Score >= req.ScoreThreshold {
					filtered = append(filtered, r)
				}
			}
			results = filtered
		}

		c.JSON(http.StatusOK, VectorSearchResponse{
			TargetNode: targetNode,
			IsFallback: isFallback,
			Results:    results,
			Count:      len(results),
			LatencyMs:  time.Since(start).Milliseconds(),
		})
	}
}

// VectorSearchGRPCHandler handles gRPC vector search request logic.
func VectorSearchGRPCHandler(
	ctx context.Context,
	router *VectorRouter,
	req *VectorSearchRequest,
	executor VectorQueryExecutor,
) (*VectorSearchResponse, error) {
	if req == nil {
		return nil, ErrInvalidParams
	}

	topK := req.TopK
	if topK <= 0 {
		topK = 10
	}

	start := time.Now()
	var results []QueryResult
	var targetNode string
	var isFallback bool
	var err error

	if req.MultiShard {
		nodes := router.ring.GetNodes()
		results, err = router.ScatterGatherQuery(ctx, nodes, topK, executor)
		targetNode = "scatter_gather_all"
	} else {
		results, targetNode, isFallback, err = router.ExecuteVectorQuery(
			ctx,
			req.TenantID,
			req.CourseID,
			executor,
		)
	}

	if err != nil {
		return nil, err
	}

	if req.ScoreThreshold > 0 {
		filtered := make([]QueryResult, 0, len(results))
		for _, r := range results {
			if r.Score >= req.ScoreThreshold {
				filtered = append(filtered, r)
			}
		}
		results = filtered
	}

	return &VectorSearchResponse{
		TargetNode: targetNode,
		IsFallback: isFallback,
		Results:    results,
		Count:      len(results),
		LatencyMs:  time.Since(start).Milliseconds(),
	}, nil
}
