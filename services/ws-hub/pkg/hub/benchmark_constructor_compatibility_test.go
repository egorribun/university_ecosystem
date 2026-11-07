package hub

import (
	"errors"
	"io"
	"log/slog"
	"testing"

	"github.com/stretchr/testify/require"
)

// Compile and execute the same constructor expression as the immutable
// benchmark overlay, without changing the trusted benchmark source.
func TestTrackTestHubAcceptsConstructorPair(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	h := trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, nil, nil))
	t.Cleanup(func() {
		h.Stop()
		testHubs.Delete(h)
	})
	require.NotNil(t, h)
	_, tracked := testHubs.Load(h)
	require.True(t, tracked)
}

func TestTrackTestHubRetainsSingleResultCompatibility(t *testing.T) {
	h := &Hub{}
	t.Cleanup(func() { testHubs.Delete(h) })
	require.Same(t, h, trackTestHub(h))
	_, tracked := testHubs.Load(h)
	require.True(t, tracked)
}

func TestTrackTestHubRejectsConstructorFailureBeforeTracking(t *testing.T) {
	h := &Hub{}
	failure := errors.New("constructor failed")
	t.Cleanup(func() { testHubs.Delete(h) })
	require.PanicsWithValue(t, failure, func() {
		trackTestHub(h, failure)
	})
	_, tracked := testHubs.Load(h)
	require.False(t, tracked)
}

func TestTrackTestHubRejectsNilHub(t *testing.T) {
	require.PanicsWithValue(t, "nil ws-hub test fixture", func() {
		trackTestHub(nil, nil)
	})
}

func TestTrackTestHubRejectsMultipleConstructorErrors(t *testing.T) {
	h := &Hub{}
	t.Cleanup(func() { testHubs.Delete(h) })
	require.PanicsWithValue(t, "multiple ws-hub fixture constructor results", func() {
		trackTestHub(h, nil, nil)
	})
	_, tracked := testHubs.Load(h)
	require.False(t, tracked)
}
