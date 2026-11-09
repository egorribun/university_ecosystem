package hub

import (
	"testing"
	"time"

	lru "github.com/hashicorp/golang-lru/v2"
)

func TestAuthLRUConstructorBehavior(t *testing.T) {
	for _, size := range []int{-1, 0} {
		got, err := newAuthLRUFunc(size)
		want, wantErr := lru.New[string, cacheEntry](size)
		if err == nil || wantErr == nil || err.Error() != wantErr.Error() || (got == nil) != (want == nil) {
			t.Fatalf("size %d: got (%v, %v), want same nil status and error as (%v, %v)", size, got == nil, err, want == nil, wantErr)
		}
	}
	cache, err := newAuthLRUFunc(1)
	if err != nil || cache == nil {
		t.Fatalf("size 1: cache=%v err=%v", cache, err)
	}
	first := cacheEntry{allowed: true, expiresAt: time.Unix(5, 0), generation: 42}
	second := cacheEntry{allowed: false, expiresAt: time.Unix(7, 0), generation: 99}
	if cache.Add("first", first) || !cache.Add("second", second) {
		t.Fatal("capacity one did not evict exactly the oldest entry")
	}
	if _, ok := cache.Get("first"); ok {
		t.Fatal("evicted authorization entry remained")
	}
	if got, ok := cache.Get("second"); !ok || got != second {
		t.Fatalf("authorization value = (%v, %v), want (%v, true)", got, ok, second)
	}
}

func TestDedupLRUConstructorBehavior(t *testing.T) {
	for _, size := range []int{-1, 0} {
		got, err := newDedupLRUFunc(size)
		want, wantErr := lru.New[string, time.Time](size)
		if err == nil || wantErr == nil || err.Error() != wantErr.Error() || (got == nil) != (want == nil) {
			t.Fatalf("size %d: got (%v, %v), want same nil status and error as (%v, %v)", size, got == nil, err, want == nil, wantErr)
		}
	}
	cache, err := newDedupLRUFunc(1)
	if err != nil || cache == nil {
		t.Fatalf("size 1: cache=%v err=%v", cache, err)
	}
	first, second := time.Unix(5, 0), time.Unix(7, 0)
	if cache.Add("first", first) || !cache.Add("second", second) {
		t.Fatal("capacity one did not evict exactly the oldest entry")
	}
	if _, ok := cache.Get("first"); ok {
		t.Fatal("evicted dedup entry remained")
	}
	if got, ok := cache.Get("second"); !ok || got != second {
		t.Fatalf("dedup value = (%v, %v), want (%v, true)", got, ok, second)
	}
}
