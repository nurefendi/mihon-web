package main

import (
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestProxyRejectsOversizedUploadBeforeForwarding(t *testing.T) {
	calls := 0
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++; w.WriteHeader(204) }))
	defer up.Close()
	a, _ := testApp(t)
	a.cfg.Engine = up.URL
	c, csrf := login(t, a)
	for _, chunked := range []bool{false, true} {
		r := httptest.NewRequest("POST", "/api/v1/backup/import", strings.NewReader(strings.Repeat("x", (32<<20)+1)))
		if chunked {
			r.ContentLength = -1
			r.TransferEncoding = []string{"chunked"}
		}
		r.AddCookie(c)
		r.Header.Set("X-CSRF-Token", csrf)
		w := httptest.NewRecorder()
		a.ServeHTTP(w, r)
		if w.Code != 413 {
			t.Fatal("oversize", chunked, w.Code)
		}
	}
	if calls != 0 {
		t.Fatal("partial oversize forwarded")
	}
}
func TestProxyVerifiesTLS(t *testing.T) {
	up := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	up.Config.ErrorLog = log.New(io.Discard, "", 0)
	up.StartTLS()
	defer up.Close()
	a, _ := testApp(t)
	a.cfg.Engine = up.URL
	c, _ := login(t, a)
	w := request(a, "GET", "/api/v1/source/list", "", c, "", "")
	if w.Code != 502 {
		t.Fatalf("untrusted TLS accepted %d", w.Code)
	}
}
func TestRateLimiterBounded(t *testing.T) {
	a, _ := testApp(t)
	for i := 0; i < 4096; i++ {
		if !a.allowLogin("peer-" + strings.Repeat("x", i/100) + string(rune(i+1000))) {
			t.Fatal("early limiter capacity")
		}
	}
	if a.allowLogin("another-peer") || len(a.attempts) != 4096 {
		t.Fatal("unbounded attempts map")
	}
}
func TestProxyRefusesEngineRedirects(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Location", "http://engine:4567/private")
		w.WriteHeader(302)
	}))
	defer up.Close()
	a, _ := testApp(t)
	a.cfg.Engine = up.URL
	c, _ := login(t, a)
	w := request(a, "GET", "/api/v1/source/list", "", c, "", "")
	if w.Code != 502 || w.Header().Get("Location") != "" {
		t.Fatalf("private redirect leaked %d %v", w.Code, w.Header())
	}
}
