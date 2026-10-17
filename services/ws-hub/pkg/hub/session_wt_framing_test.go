package hub

import (
	"bytes"
	"errors"
	"io"
	"strings"
	"testing"
	"testing/iotest"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
)

type framingTestStream struct {
	reader io.Reader
	writer io.Writer
}

func (s *framingTestStream) Read(p []byte) (int, error)  { return s.reader.Read(p) }
func (s *framingTestStream) Write(p []byte) (int, error) { return s.writer.Write(p) }
func (s *framingTestStream) Close() error {
	if closer, ok := s.reader.(io.Closer); ok {
		return closer.Close()
	}
	return nil
}
func (s *framingTestStream) SetReadDeadline(time.Time) error  { return nil }
func (s *framingTestStream) SetWriteDeadline(time.Time) error { return nil }

func TestWebTransportSessionReadsWholeJSONObjectsAcrossStreamChunks(t *testing.T) {
	messages := []string{
		`{"type":"join","room_id":"one"}`,
		`{"type":"leave","payload":{"text":"} { \\\"","list":[{"x":"{"}]}}`,
		`{"type":"join","room_id":"three"}`,
	}
	for _, chunking := range []string{"coalesced", "one byte", "half reads"} {
		t.Run(chunking, func(t *testing.T) {
			var reader io.Reader = strings.NewReader(" \n\t" + messages[0] + messages[1] + "\r\n" + messages[2])
			switch chunking {
			case "one byte":
				reader = iotest.OneByteReader(reader)
			case "half reads":
				reader = iotest.HalfReader(reader)
			}
			session := &WebTransportSession{stream: &framingTestStream{reader: reader}, readLimit: 128}
			for _, message := range messages {
				kind, data, err := session.ReadMessage()
				require.NoError(t, err)
				require.Equal(t, websocket.TextMessage, kind)
				require.Equal(t, message, string(data))
			}
			_, _, err := session.ReadMessage()
			require.ErrorIs(t, err, io.EOF)
		})
	}
}

func TestWebTransportSessionRejectsMalformedTruncatedAndOversizedObjects(t *testing.T) {
	for _, test := range []struct {
		name  string
		input string
		limit int64
	}{
		{name: "array", input: `[]`, limit: 64},
		{name: "scalar", input: `null`, limit: 64},
		{name: "non json", input: `hello`, limit: 64},
		{name: "malformed object", input: `{invalid}`, limit: 64},
		{name: "mismatched nesting", input: `{"x":[}}`, limit: 64},
		{name: "truncated object", input: `{"type":"join"`, limit: 64},
		{name: "oversized object", input: `{"type":"join"}`, limit: 14},
		{name: "unbounded whitespace", input: strings.Repeat(" ", 65), limit: 64},
		{name: "negative limit", input: `{}`, limit: -1},
		{name: "zero limit", input: `{}`, limit: 0},
	} {
		t.Run(test.name, func(t *testing.T) {
			session := &WebTransportSession{stream: &framingTestStream{reader: strings.NewReader(test.input)}, readLimit: test.limit}
			_, data, err := session.ReadMessage()
			require.Error(t, err)
			require.Empty(t, data, "partial or invalid objects must never reach the message consumer")
		})
	}
}

func TestWebTransportSessionAcceptsObjectAtReadLimit(t *testing.T) {
	input := `{"type":"join"}`
	session := &WebTransportSession{stream: &framingTestStream{reader: strings.NewReader(input)}, readLimit: int64(len(input))}
	_, data, err := session.ReadMessage()
	require.NoError(t, err)
	require.Equal(t, input, string(data))
}

func TestWebTransportSessionCloseInterruptsPartialObjectRead(t *testing.T) {
	reader, writer := io.Pipe()
	t.Cleanup(func() { _ = writer.Close() })
	session := &WebTransportSession{stream: &framingTestStream{reader: reader}, readLimit: 64}
	done := make(chan error, 1)
	go func() {
		_, _, err := session.ReadMessage()
		done <- err
	}()
	_, err := writer.Write([]byte(`{"type":`))
	require.NoError(t, err)
	require.NoError(t, session.Close())
	select {
	case err := <-done:
		require.Error(t, err)
	case <-time.After(time.Second):
		t.Fatal("Close did not interrupt a partial JSON-object read")
	}
}

type shortFramingWriter struct {
	bytes.Buffer
	noProgress bool
}

func (w *shortFramingWriter) Write(data []byte) (int, error) {
	if w.noProgress {
		return 0, nil
	}
	return w.Buffer.Write(data[:min(2, len(data))])
}

func TestWebTransportSessionPreservesOutboundBytesAcrossShortWrites(t *testing.T) {
	writer := &shortFramingWriter{}
	session := &WebTransportSession{stream: &framingTestStream{writer: writer}}
	messages := []string{`{"type":"joined"}`, `{"type":"left"}`}
	for _, message := range messages {
		require.NoError(t, session.WriteMessage(websocket.TextMessage, []byte(message)))
	}
	require.Equal(t, strings.Join(messages, ""), writer.String(), "outbound JSON retains its existing bytes with no new prefix or delimiter")
}

func TestWebTransportSessionRejectsWriteWithoutProgress(t *testing.T) {
	session := &WebTransportSession{stream: &framingTestStream{writer: &shortFramingWriter{noProgress: true}}}
	require.ErrorIs(t, session.WriteMessage(websocket.TextMessage, []byte(`{}`)), io.ErrShortWrite)
}

func TestWebTransportSessionPreservesReadErrors(t *testing.T) {
	want := errors.New("read canceled")
	session := &WebTransportSession{stream: &framingTestStream{reader: iotest.ErrReader(want)}, readLimit: 64}
	_, _, err := session.ReadMessage()
	require.ErrorIs(t, err, want)
}
