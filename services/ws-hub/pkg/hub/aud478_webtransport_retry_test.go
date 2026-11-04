package hub

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/http3"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/require"
)

type aud478RecordedWebTransportClose struct {
	fakeWebTransportSession
	code   webtransport.SessionErrorCode
	reason string
	calls  int
}

func (s *aud478RecordedWebTransportClose) CloseWithError(code webtransport.SessionErrorCode, reason string) error {
	s.code = code
	s.reason = reason
	s.calls++
	return s.closeErr
}

func TestAUD478WebTransportTemporaryAdmissionUsesRetryableSessionClose(t *testing.T) {
	h := setupTestHub()
	h.authCacheTracked.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return false }
	t.Cleanup(h.Stop)
	transport := &aud478RecordedWebTransportClose{}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client := &Client{
		ID:     "aud478-webtransport",
		UserID: rdUser,
		Hub:    h,
		Conn:   &WebTransportSession{sess: transport},
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		ctx:    ctx,
		cancel: cancel,
	}

	client.handleJoin(ctx, Message{Type: "join", Room: rdRoom})
	require.Equal(t, webtransport.SessionErrorCode(websocket.CloseTryAgainLater), transport.code)
	require.Equal(t, "room admission temporarily unavailable", transport.reason)
	require.Equal(t, 1, transport.calls, "the subsequent cleanup close must not erase the retry code")
	require.False(t, client.isInRoom(rdRoom))
	require.ErrorIs(t, ctx.Err(), context.Canceled)
}

func TestAUD478WebTransportOtherCloseCodesRemainNormal(t *testing.T) {
	cases := []struct {
		name    string
		payload []byte
	}{
		{name: "empty payload"},
		{name: "short payload", payload: []byte{1}},
		{name: "normal close", payload: websocket.FormatCloseMessage(websocket.CloseNormalClosure, "done")},
		{name: "policy close", payload: websocket.FormatCloseMessage(websocket.ClosePolicyViolation, "denied")},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			transport := &aud478RecordedWebTransportClose{}
			session := &WebTransportSession{sess: transport}
			require.NoError(t, session.WriteMessage(websocket.CloseMessage, tc.payload))
			require.NoError(t, session.Close())
			require.Equal(t, webtransport.SessionErrorCode(0), transport.code)
			require.Equal(t, "normal closure", transport.reason)
			require.Equal(t, 1, transport.calls)
		})
	}
}

func TestAUD478WebTransportRetryCloseReportsTransportErrors(t *testing.T) {
	sessionErr := errors.New("session close failed")
	streamErr := errors.New("stream close failed")
	for _, tc := range []struct {
		name       string
		sessionErr error
		want       error
	}{
		{name: "stream error", want: streamErr},
		{name: "session error takes precedence", sessionErr: sessionErr, want: sessionErr},
	} {
		t.Run(tc.name, func(t *testing.T) {
			transport := &aud478RecordedWebTransportClose{}
			transport.closeErr = tc.sessionErr
			session := &WebTransportSession{sess: transport, stream: &fakeWebTransportStream{closeErr: streamErr}}
			err := session.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseTryAgainLater, "retry"))
			require.ErrorIs(t, err, tc.want)
			require.Equal(t, webtransport.SessionErrorCode(websocket.CloseTryAgainLater), transport.code)
		})
	}
}

func TestAUD478WebTransportPeerReceivesRetryableClose(t *testing.T) {
	certificateServer := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	certificate := certificateServer.TLS.Certificates[0]
	roots := x509.NewCertPool()
	roots.AddCert(certificateServer.Certificate())
	certificateServer.Close()

	packet, err := net.ListenPacket("udp4", "127.0.0.1:0")
	require.NoError(t, err)
	h3 := &http3.Server{TLSConfig: &tls.Config{
		MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{certificate}, NextProtos: []string{http3.NextProtoH3},
	}}
	server := &webtransport.Server{H3: h3}
	webtransport.ConfigureHTTP3Server(h3)
	accepted := make(chan *webtransport.Session, 1)
	upgradeErr := make(chan error, 1)
	h3.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		session, upgradeError := server.Upgrade(w, r)
		if upgradeError != nil {
			upgradeErr <- upgradeError
			return
		}
		accepted <- session
		<-session.Context().Done()
	})
	serveDone := make(chan error, 1)
	go func() { serveDone <- server.Serve(packet) }()
	t.Cleanup(func() {
		require.NoError(t, server.Close())
		<-serveDone
		_ = packet.Close()
	})
	transport := &webtransport.Transport{
		TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS13, RootCAs: roots},
		QUICConfig: &quic.Config{
			EnableDatagrams:                  true,
			EnableStreamResetPartialDelivery: true,
		},
	}
	t.Cleanup(func() { require.NoError(t, transport.Close()) })
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	response, peer, err := transport.Dial(ctx, "https://"+packet.LocalAddr().String()+"/webtransport", nil)
	if response != nil && response.Body != nil {
		defer response.Body.Close()
	}
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, response.StatusCode)
	var serverSession *webtransport.Session
	select {
	case serverSession = <-accepted:
	case upgradeError := <-upgradeErr:
		t.Fatal(upgradeError)
	case <-ctx.Done():
		t.Fatal("WebTransport server did not accept the session")
	}

	h := setupTestHub()
	var logs bytes.Buffer
	h.Logger = slog.New(slog.NewTextHandler(&logs, nil))
	h.authCacheTracked.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return false }
	t.Cleanup(h.Stop)
	clientCtx, cancelClient := context.WithCancel(context.Background())
	client := &Client{
		ID: "aud478-quic-peer", UserID: rdUser, SessionJTI: validSessionJTI,
		SessionExpiresAt: time.Now().Add(time.Hour), Hub: h,
		Conn: NewWebTransportSession(serverSession), Rooms: make(map[string]bool), Send: make(chan []byte, 1),
		ctx: clientCtx, cancel: cancelClient,
	}
	h.handleRegister(context.Background(), client)
	readDone := make(chan struct{})
	go func() {
		defer close(readDone)
		client.ReadPump(clientCtx)
	}()
	t.Cleanup(func() {
		cancelClient()
		select {
		case <-readDone:
		case <-time.After(3 * time.Second):
			t.Error("WebTransport reader did not stop")
		}
		h.handleUnregister(context.Background(), client)
	})
	stream, err := peer.OpenStreamSync(ctx)
	require.NoError(t, err)
	_, err = stream.Write([]byte(`{"type":"join","room":"` + rdRoom + `"}`))
	require.NoError(t, err)
	_, err = peer.AcceptStream(ctx)
	var sessionErr *webtransport.SessionError
	require.ErrorAs(t, err, &sessionErr)
	require.True(t, sessionErr.Remote)
	require.Equal(t, webtransport.SessionErrorCode(websocket.CloseTryAgainLater), sessionErr.ErrorCode)
	require.Equal(t, "room admission temporarily unavailable", sessionErr.Message)
	select {
	case <-readDone:
	case <-time.After(3 * time.Second):
		t.Fatal("WebTransport reader did not finish after the close")
	}
	require.NotContains(t, logs.String(), "Failed to write close control frame")
}
