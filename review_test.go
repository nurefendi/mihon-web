package main

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

// The resolver and transport are local fixtures: no public DNS or engine access.
func TestExplicitTrustedRepositoryStillRequiresPublicInitialURL(t *testing.T) {
	validConfigEnvironment(t)
	t.Setenv("TRUSTED_REPOSITORY_URLS", "https://repo.example/Index.json,https://127.0.0.1/index.json")
	cfg, err := loadConfig()
	if err != nil {
		t.Fatal(err)
	}
	a, _ := testApp(t)
	a.cfg.TrustedRepositoryURLs = cfg.TrustedRepositoryURLs
	c, csrf := login(t, a)
	socket, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer socket.Close()
	var dnsCalls atomic.Int32
	go func() {
		buf := make([]byte, 4096)
		for {
			n, peer, err := socket.ReadFrom(buf)
			if err != nil {
				return
			}
			if n < 17 {
				continue
			}
			end := 12
			for end < n && buf[end] != 0 {
				end += int(buf[end]) + 1
			}
			end += 5
			if end > n {
				continue
			}
			dnsCalls.Add(1)
			response := append([]byte(nil), buf[:end]...)
			response[2], response[3] = 0x81, 0x80
			for i := 6; i < 12; i++ {
				response[i] = 0
			}
			if binary.BigEndian.Uint16(buf[end-4:end-2]) == 1 {
				response[7] = 1
				response = append(response, 0xc0, 0x0c, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4, 8, 8, 8, 8)
			}
			_, _ = socket.WriteTo(response, peer)
		}
	}()
	old := net.DefaultResolver
	net.DefaultResolver = &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "udp", socket.LocalAddr().String())
	}}
	defer func() { net.DefaultResolver = old }()
	calls := 0
	a.transport = roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		var payload struct {
			Variables map[string]string `json:"variables"`
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || payload.Variables["indexUrl"] != "https://repo.example/Index.json" {
			t.Errorf("payload %+v: %v", payload, err)
		}
		return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(`{"data":{}}`))}, nil
	})
	w := request(a, "POST", "/api/bridge", `{"operation":"addRepository","variables":{"indexUrl":"https://repo.example/Index.json"}}`, c, "", csrf)
	if w.Code != 200 || calls != 1 || dnsCalls.Load() == 0 {
		t.Fatalf("trusted add: %d %s calls=%d DNS=%d", w.Code, w.Body.String(), calls, dnsCalls.Load())
	}
	for _, raw := range []string{"https://repo.example/index.json", "https://127.0.0.1/index.json"} {
		body, _ := json.Marshal(map[string]any{"operation": "addRepository", "variables": map[string]string{"indexUrl": raw}})
		w = request(a, "POST", "/api/bridge", string(body), c, "", csrf)
		expected := 403
		if strings.Contains(raw, "127.0.0.1") {
			expected = 400
		}
		if w.Code != expected || calls != 1 {
			t.Fatalf("invalid add: %s status=%d calls=%d", raw, w.Code, calls)
		}
	}
}

type gatedOversizedBody struct {
	entered   chan struct{}
	release   chan struct{}
	remaining int
	once      sync.Once
}

func (b *gatedOversizedBody) Read(p []byte) (int, error) {
	b.once.Do(func() { close(b.entered); <-b.release })
	if b.remaining == 0 {
		return 0, io.EOF
	}
	n := len(p)
	if n > b.remaining {
		n = b.remaining
	}
	clear(p[:n])
	b.remaining -= n
	return n, nil
}
func (*gatedOversizedBody) Close() error { return nil }

type observedBody struct{ reads atomic.Int32 }

func (b *observedBody) Read([]byte) (int, error) {
	b.reads.Add(1)
	return 0, fmt.Errorf("must not read")
}
func (*observedBody) Close() error { return nil }

func TestProxyAllowsOnlyOneBufferedUpload(t *testing.T) {
	a, _ := testApp(t)
	c, csrf := login(t, a)
	var upstream atomic.Int32
	a.transport = roundTripFunc(func(*http.Request) (*http.Response, error) {
		upstream.Add(1)
		return &http.Response{StatusCode: 204, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(""))}, nil
	})
	serve := func(body io.ReadCloser) int {
		r := httptest.NewRequest("POST", "/api/v1/backup/import", nil)
		r.Body = body
		r.ContentLength = -1
		r.AddCookie(c)
		r.Header.Set("X-CSRF-Token", csrf)
		w := httptest.NewRecorder()
		a.ServeHTTP(w, r)
		return w.Code
	}
	body := &gatedOversizedBody{entered: make(chan struct{}), release: make(chan struct{}), remaining: (32 << 20) + 1}
	done := make(chan int, 1)
	go func() { done <- serve(body) }()
	released := false
	defer func() {
		if !released {
			close(body.release)
		}
	}()
	select {
	case <-body.entered:
	case <-time.After(5 * time.Second):
		t.Fatal("first upload never started")
	}
	var wg sync.WaitGroup
	rejectedBody := &observedBody{}
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if status := serve(rejectedBody); status != 503 && status != 429 {
				t.Errorf("concurrent upload: %d", status)
			}
		}()
	}
	wg.Wait()
	if reads := rejectedBody.reads.Load(); reads != 0 {
		t.Errorf("consumed %d competing bodies", reads)
	}
	close(body.release)
	released = true
	select {
	case status := <-done:
		if status != 413 {
			t.Errorf("oversized upload: %d", status)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("first upload did not finish")
	}
	if upstream.Load() != 0 {
		t.Fatalf("oversized/concurrent body forwarded: %d", upstream.Load())
	}
	if status := serve(io.NopCloser(strings.NewReader("small"))); status != 204 {
		t.Fatalf("slot not released: %d", status)
	}
}

func TestLoginClientHeaderFailsClosed(t *testing.T) {
	for _, tc := range []struct {
		name, remote string
		trusted      bool
		headers      []string
	}{
		{"untrusted peer spoof", "198.51.100.20:1000", true, []string{"198.51.100.1"}},
		{"no trusted proxies", "172.18.0.5:1000", false, []string{"198.51.100.1"}},
		{"missing", "172.18.0.5:1000", true, nil},
		{"not IP", "172.18.0.5:1000", true, []string{"client.example"}},
		{"comma list", "172.18.0.5:1000", true, []string{"198.51.100.1, 198.51.100.2"}},
		{"two header values", "172.18.0.5:1000", true, []string{"198.51.100.1", "198.51.100.2"}},
		{"IP with port", "172.18.0.5:1000", true, []string{"198.51.100.1:80"}},
		{"whitespace", "172.18.0.5:1000", true, []string{" 198.51.100.1 "}},
		{"bracketed IPv6", "172.18.0.5:1000", true, []string{"[2001:db8::1]"}},
		{"IPv6 zone", "172.18.0.5:1000", true, []string{"fe80::1%eth0"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			a, _ := testApp(t)
			if tc.trusted {
				_, network, _ := net.ParseCIDR("172.18.0.5/32")
				a.cfg.TrustedProxyCIDRs = []*net.IPNet{network}
			}
			for i := 0; i < 10; i++ {
				if !a.allowLogin(tc.remote) {
					t.Fatal("initial limit")
				}
			}
			if status := loginAttempt(a, tc.remote, tc.headers); status != 429 {
				t.Fatalf("header bypassed peer limit: %d", status)
			}
		})
	}
}

func TestTrustedIPv6ClientCanonicalization(t *testing.T) {
	a, _ := testApp(t)
	_, network, _ := net.ParseCIDR("::1/128")
	a.cfg.TrustedProxyCIDRs = []*net.IPNet{network}
	for i := 0; i < 10; i++ {
		if status := loginAttempt(a, "[::1]:1000", []string{"2001:db8::1"}); status != 401 {
			t.Fatalf("attempt %d: %d", i, status)
		}
	}
	if status := loginAttempt(a, "[::1]:2000", []string{"2001:0db8:0:0:0:0:0:1"}); status != 429 {
		t.Fatalf("IPv6 spelling bypass: %d", status)
	}
	if status := loginAttempt(a, "[::1]:2000", []string{"2001:db8::2"}); status != 401 {
		t.Fatalf("IPv6 B blocked: %d", status)
	}
}

func TestTrustedProxySeparatesLoginClients(t *testing.T) {
	validConfigEnvironment(t)
	t.Setenv("TRUSTED_PROXY_CIDRS", "172.18.0.5/32, ::1/128")
	cfg, err := loadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if len(cfg.TrustedProxyCIDRs) != 2 {
		t.Fatalf("parsed CIDRs: %v", cfg.TrustedProxyCIDRs)
	}
	a, _ := testApp(t)
	a.cfg.TrustedProxyCIDRs = cfg.TrustedProxyCIDRs
	for i := 0; i < 10; i++ {
		if status := loginAttempt(a, "172.18.0.5:1000", []string{"198.51.100.1"}); status != 401 {
			t.Fatalf("A attempt %d: %d", i, status)
		}
	}
	if status := loginAttempt(a, "172.18.0.5:2000", []string{"198.51.100.1"}); status != 429 {
		t.Fatalf("A not limited: %d", status)
	}
	if status := loginAttempt(a, "172.18.0.5:2000", []string{"198.51.100.2"}); status != 401 {
		t.Fatalf("A blocked B behind proxy: %d", status)
	}
}

func loginAttempt(a *App, remote string, clientHeaders []string) int {
	r := httptest.NewRequest("POST", "/login", strings.NewReader("username=unknown&password=wrong"))
	r.RemoteAddr = remote
	r.Header.Set("Origin", a.cfg.Origin)
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("X-Forwarded-For", "203.0.113.8")
	r.Header.Set("X-Real-IP", "203.0.113.9")
	for _, v := range clientHeaders {
		r.Header.Add("X-Mihon-Client-IP", v)
	}
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	return w.Code
}

func TestRepositoryRemovalDoesNotResolve(t *testing.T) {
	a, _ := testApp(t)
	c, csrf := login(t, a)
	old := net.DefaultResolver
	dnsCalls, calls := 0, 0
	net.DefaultResolver = &net.Resolver{PreferGo: true, Dial: func(context.Context, string, string) (net.Conn, error) { dnsCalls++; return nil, fmt.Errorf("offline") }}
	defer func() { net.DefaultResolver = old }()
	a.transport = roundTripFunc(func(*http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"data":{}}`)), Header: make(http.Header)}, nil
	})
	for _, raw := range []string{"https://offline.example/index.json", "https://127.0.0.1/index.json", "https://localhost:8443/index.json"} {
		body, _ := json.Marshal(map[string]any{"operation": "removeRepository", "variables": map[string]string{"indexUrl": raw}})
		w := request(a, "POST", "/api/bridge", string(body), c, "", csrf)
		if w.Code != 200 {
			t.Errorf("remove %s: %d %s", raw, w.Code, w.Body.String())
		}
	}
	for _, raw := range []string{"http://localhost/index.json", "https:///index.json", "https://u:p@localhost/index.json", "https://localhost/" + strings.Repeat("x", 2048), "https://localhost/index.json#fragment", "https://localhost/index.json?query"} {
		body, _ := json.Marshal(map[string]any{"operation": "removeRepository", "variables": map[string]string{"indexUrl": raw}})
		if w := request(a, "POST", "/api/bridge", string(body), c, "", csrf); w.Code != 400 {
			t.Errorf("invalid remove %q: %d", raw, w.Code)
		}
	}
	if dnsCalls != 0 || calls != 3 {
		t.Fatalf("DNS=%d engine=%d", dnsCalls, calls)
	}
}

func TestRepositoryAddFailsClosedBeforeDNSOrEngine(t *testing.T) {
	a, _ := testApp(t)
	c, csrf := login(t, a)
	old := net.DefaultResolver
	dnsCalls, engineCalls := 0, 0
	net.DefaultResolver = &net.Resolver{PreferGo: true, Dial: func(context.Context, string, string) (net.Conn, error) {
		dnsCalls++
		return nil, fmt.Errorf("DNS forbidden")
	}}
	defer func() { net.DefaultResolver = old }()
	a.transport = roundTripFunc(func(*http.Request) (*http.Response, error) { engineCalls++; return nil, fmt.Errorf("engine forbidden") })
	for _, raw := range []string{"https://repo.example/index.json", "https://127.0.0.1/index.json", "http://github.com/index.json", "https://user:pass@github.com/index.json"} {
		body, _ := json.Marshal(map[string]any{"operation": "addRepository", "variables": map[string]string{"indexUrl": raw}})
		w := request(a, "POST", "/api/bridge", string(body), c, "", csrf)
		if w.Code != 403 || !strings.Contains(w.Body.String(), "URL repositori belum diizinkan di server (TRUSTED_REPOSITORY_URLS).") || dnsCalls != 0 || engineCalls != 0 {
			t.Fatalf("status=%d body=%s DNS=%d engine=%d", w.Code, w.Body.String(), dnsCalls, engineCalls)
		}
	}
}
